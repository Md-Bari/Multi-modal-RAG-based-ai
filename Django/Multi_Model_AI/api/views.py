import os
import io
import logging
from django.conf import settings
from django.http import StreamingHttpResponse
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets, mixins, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django.contrib.auth import get_user_model
User = get_user_model()

from core.models import (
    KnowledgeBase, Document, Conversation, Message, TokenUsage
)
from api.serializers import (
    KnowledgeBaseSerializer, DocumentSerializer, 
    ConversationSerializer, MessageSerializer, TokenUsageSerializer
)
from core.services.routing_engine import RoutingEngine
from core.services.llm_service import LLMService
from core.tasks import process_document_task

logger = logging.getLogger(__name__)

DEV_USERNAME = "devuser"


def _get_dev_user():
    """Get or create a default dev user for unauthenticated mode."""
    user, _ = User.objects.get_or_create(
        username=DEV_USERNAME,
        defaults={
            "email": "dev@chetopia.local",
            "is_active": True,
        }
    )
    # Ensure an org exists
    if not user.org:
        from core.models import Organization
        org, _ = Organization.objects.get_or_create(name="Default Org")
        user.org = org
        user.save()
    return user


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/v1/knowledge-bases
    Manage Knowledge Bases. Dev mode: no auth required.
    """
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [AllowAny]

    def _get_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return _get_dev_user()

    def get_queryset(self):
        user = self._get_user()
        if not user.org:
            return KnowledgeBase.objects.none()
        return KnowledgeBase.objects.filter(org=user.org)

    def perform_create(self, serializer):
        user = self._get_user()
        serializer.save(org=user.org, owner=user)


class DocumentViewSet(viewsets.GenericViewSet,
                      mixins.CreateModelMixin,
                      mixins.RetrieveModelMixin,
                      mixins.ListModelMixin):
    """
    POST /api/v1/documents - Ingest doc
    GET /api/v1/documents/{id} - Get doc processing status
    """
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return _get_dev_user()

    def get_queryset(self):
        user = self._get_user()
        if not user.org:
            return Document.objects.none()
        return Document.objects.filter(kb__org=user.org)

    def create(self, request, *args, **kwargs):
        user = self._get_user()
        kb_id = request.data.get('kb')
        source_type = request.data.get('source_type', 'file')

        try:
            kb = KnowledgeBase.objects.get(id=kb_id, org=user.org)
        except KnowledgeBase.DoesNotExist:
            return Response({"error": "Knowledge Base not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        if source_type == 'url':
            url = request.data.get('url')
            if not url:
                return Response({"error": "url is required when source_type is 'url'"}, status=status.HTTP_400_BAD_REQUEST)
            doc = Document.objects.create(
                kb=kb, uploaded_by=user, source_type='url',
                original_filename=f"url_{url.split('/')[-1] or 'link'}.txt",
                storage_url=url, status='pending'
            )
        else:
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return Response({"error": "file is required for 'file' ingestion"}, status=status.HTTP_400_BAD_REQUEST)

            upload_dir = os.path.join(settings.BASE_DIR, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            storage_path = os.path.join(upload_dir, f"{timezone.now().timestamp()}_{uploaded_file.name}")
            with open(storage_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            doc = Document.objects.create(
                kb=kb, uploaded_by=user, source_type='file',
                original_filename=uploaded_file.name,
                storage_url=storage_path, status='pending'
            )

        process_document_task.delay(doc.id)
        serializer = self.get_serializer(doc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationViewSet(viewsets.ModelViewSet):
    """
    GET/POST /api/v1/conversations
    Manage conversations (chat history). Dev mode: no auth.
    """
    serializer_class = ConversationSerializer
    permission_classes = [AllowAny]

    def _get_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return _get_dev_user()

    def get_queryset(self):
        user = self._get_user()
        if not user.org:
            return Conversation.objects.none()
        return Conversation.objects.filter(kb__org=user.org, user=user)

    def perform_create(self, serializer):
        user = self._get_user()
        kb_id = self.request.data.get('kb')
        try:
            kb = KnowledgeBase.objects.get(id=kb_id, org=user.org)
        except KnowledgeBase.DoesNotExist:
            raise serializers.ValidationError("Invalid Knowledge Base or unauthorized access.")
        serializer.save(user=user, kb=kb)


class MessageView(APIView):
    """
    POST /api/v1/conversations/{id}/messages
    Submit a prompt to trigger the Intelligent Routing Engine & RAG.
    Supports streaming answers and optional image uploads.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _get_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return _get_dev_user()

    def post(self, request, pk):
        user = self._get_user()
        try:
            conversation = Conversation.objects.get(id=pk, kb__org=user.org, user=user)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        query = request.data.get('content', '')
        stream_raw = request.data.get('stream', False)
        stream = stream_raw in [True, 'true', 'True', 1, '1']

        # Handle optional image uploads
        images = []
        uploaded_files = request.FILES.getlist('images')
        for f in uploaded_files:
            images.append(f.read())

        if not query and not images:
            return Response({"error": "content or images is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Save user query
        user_msg = Message.objects.create(
            conversation=conversation, role='user',
            content=query or "[Image uploaded]",
            token_count=len(query.split()) if query else 0
        )

        result = RoutingEngine.route_and_generate(
            user=user,
            kb_id=conversation.kb.id,
            conversation_id=conversation.id,
            query=query or "Describe the uploaded image.",
            stream=stream,
            images=images if images else None
        )

        if stream:
            generator = result["content"]
            citations = result.get("citations", [])

            def stream_response():
                full_reply = ""
                for chunk in generator:
                    full_reply += chunk
                    yield f"data: {chunk}\n\n"

                Message.objects.create(
                    conversation=conversation, role='assistant',
                    content=full_reply,
                    citations={"sources": citations},
                    token_count=len(full_reply.split())
                )
                from core.services.rag_service import RAGService
                from core.services.cache_service import CacheService
                RAGService.record_usage(user, conversation, LLMService.get_llm_model(), query or "", full_reply)
                CacheService.set_semantic_cache(query or "", full_reply)
                yield f"event: done\ndata: [Done]\n\n"

            return StreamingHttpResponse(stream_response(), content_type='text/event-stream')

        # Non-streaming response
        Message.objects.create(
            conversation=conversation, role='assistant',
            content=result["content"],
            citations=result.get("citations", []),
            token_count=len(result["content"].split())
        )
        return Response({
            "role": "assistant",
            "content": result["content"],
            "citations": result.get("citations", []),
            "route": result.get("route", "unknown")
        }, status=status.HTTP_201_CREATED)


class TranscribeView(APIView):
    """
    POST /api/v1/transcribe
    Transcribe audio file (WebM/WAV) to text using faster-whisper.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({"error": "audio file is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            audio_bytes = audio_file.read()
            text = self._transcribe(audio_bytes)
            return Response({"text": text})
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _transcribe(self, audio_bytes: bytes) -> str:
        try:
            from faster_whisper import WhisperModel
            import tempfile

            model_size = os.environ.get("WHISPER_MODEL", "base")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                segments, _ = model.transcribe(tmp_path)
                text = " ".join(seg.text for seg in segments)
                return text.strip() or "[Transcription returned no text]"
            finally:
                os.unlink(tmp_path)
        except ImportError:
            logger.warning("faster-whisper not installed, using mock transcription")
            return "[Mock transcription: faster-whisper not available]"


class AnalyticsView(APIView):
    """
    GET /api/v1/analytics/usage
    Returns token usage statistics.
    """
    permission_classes = [AllowAny]

    def _get_user(self):
        if self.request.user.is_authenticated:
            return self.request.user
        return _get_dev_user()

    def get(self, request):
        user = self._get_user()
        usage_qs = TokenUsage.objects.filter(user=user)
        totals = usage_qs.aggregate(
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            total_cost=Sum('cost')
        )
        breakdown = []
        models_list = usage_qs.values('model_name').annotate(
            input_sum=Sum('input_tokens'),
            output_sum=Sum('output_tokens'),
            cost_sum=Sum('cost')
        )
        for m in models_list:
            breakdown.append({
                "model_name": m["model_name"],
                "input_tokens": m["input_sum"] or 0,
                "output_tokens": m["output_sum"] or 0,
                "cost": float(m["cost_sum"] or 0.0)
            })
        return Response({
            "total_input_tokens": totals["total_input"] or 0,
            "total_output_tokens": totals["total_output"] or 0,
            "total_estimated_cost": float(totals["total_cost"] or 0.0),
            "breakdown_by_model": breakdown
        })
