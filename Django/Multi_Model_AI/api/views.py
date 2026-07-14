import os
import logging
from django.conf import settings
from django.http import StreamingHttpResponse
from django.db.models import Sum
from django.utils import timezone
from rest_framework import status, viewsets, mixins
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from core.models import (
    KnowledgeBase, Document, Conversation, Message, TokenUsage, KBAccess
)
from api.serializers import (
    KnowledgeBaseSerializer, DocumentSerializer, 
    ConversationSerializer, MessageSerializer, TokenUsageSerializer
)
from core.services.routing_engine import RoutingEngine
from core.tasks import process_document_task

logger = logging.getLogger(__name__)

class LoginView(TokenObtainPairView):
    """
    POST /api/v1/auth/login
    Issue access/refresh JWT tokens.
    """
    permission_classes = [AllowAny]


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    """
    GET / POST /api/v1/knowledge-bases
    Manage Knowledge Bases.
    Scoped by User's Organization.
    """
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Enforce multi-tenancy scoping by user organization
        user = self.request.user
        if not user.org:
            return KnowledgeBase.objects.none()
        return KnowledgeBase.objects.filter(org=user.org)

    def perform_create(self, serializer):
        serializer.save(
            org=self.request.user.org,
            owner=self.request.user
        )


class DocumentViewSet(viewsets.GenericViewSet, 
                      mixins.CreateModelMixin, 
                      mixins.RetrieveModelMixin, 
                      mixins.ListModelMixin):
    """
    POST /api/v1/documents - Ingest doc
    GET /api/v1/documents/{id} - Get doc processing status
    """
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        if not user.org:
            return Document.objects.none()
        return Document.objects.filter(kb__org=user.org)

    def create(self, request, *args, **kwargs):
        # We can receive either a file upload or a URL.
        kb_id = request.data.get('kb')
        source_type = request.data.get('source_type', 'file')
        
        # Verify access to KnowledgeBase
        try:
            kb = KnowledgeBase.objects.get(id=kb_id, org=request.user.org)
        except KnowledgeBase.DoesNotExist:
            return Response({"error": "Knowledge Base not found or access denied."}, status=status.HTTP_404_NOT_FOUND)

        if source_type == 'url':
            url = request.data.get('url')
            if not url:
                return Response({"error": "url is required when source_type is 'url'"}, status=status.HTTP_400_BAD_REQUEST)
                
            doc = Document.objects.create(
                kb=kb,
                uploaded_by=request.user,
                source_type='url',
                original_filename=f"url_{url.split('/')[-1] or 'link'}.txt",
                storage_url=url,
                status='pending'
            )
        else:
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return Response({"error": "file is required for 'file' ingestion"}, status=status.HTTP_400_BAD_REQUEST)
            
            # Ensure upload folder exists
            upload_dir = os.path.join(settings.BASE_DIR, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            
            storage_path = os.path.join(upload_dir, f"{timezone.now().timestamp()}_{uploaded_file.name}")
            with open(storage_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            doc = Document.objects.create(
                kb=kb,
                uploaded_by=request.user,
                source_type='file',
                original_filename=uploaded_file.name,
                storage_url=storage_path,
                status='pending'
            )

        # Dispatch async Celery task to process the document
        process_document_task.delay(doc.id)

        serializer = self.get_serializer(doc)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationViewSet(viewsets.ModelViewSet):
    """
    GET / POST /api/v1/conversations
    Manage conversations (chat history).
    """
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.org:
            return Conversation.objects.none()
        return Conversation.objects.filter(kb__org=user.org, user=user)

    def perform_create(self, serializer):
        kb_id = self.request.data.get('kb')
        # Validate that the user belongs to the KB's organization
        try:
            kb = KnowledgeBase.objects.get(id=kb_id, org=self.request.user.org)
        except KnowledgeBase.DoesNotExist:
            raise serializers.ValidationError("Invalid Knowledge Base or unauthorized access.")
            
        serializer.save(
            user=self.request.user,
            kb=kb
        )


class MessageView(APIView):
    """
    POST /api/v1/conversations/{id}/messages
    Submit a prompt to trigger the Intelligent Routing Engine & RAG.
    Supports streaming answers.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            conversation = Conversation.objects.get(id=pk, kb__org=request.user.org, user=request.user)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        query = request.data.get('content')
        if not query:
            return Response({"error": "content is required."}, status=status.HTTP_400_BAD_REQUEST)

        provider = request.data.get('provider', 'openai')
        model_name = request.data.get('model_name', 'gpt-4o')
        stream_raw = request.data.get('stream', False)
        stream = stream_raw in [True, 'true', 'True', 1, '1', 'true', 'True']

        # Save user query to DB first
        user_msg = Message.objects.create(
            conversation=conversation,
            role='user',
            content=query,
            token_count=len(query.split())
        )

        # Triggers Knowledge Routing Engine
        result = RoutingEngine.route_and_generate(
            user=request.user,
            kb_id=conversation.kb.id,
            conversation_id=conversation.id,
            query=query,
            provider=provider,
            model_name=model_name,
            stream=stream
        )

        if stream:
            # Return Streaming HTTP Response
            generator = result["content"]
            
            def stream_response():
                full_reply = ""
                # Yield JSON chunks compatible with EventStream
                for chunk in generator:
                    full_reply += chunk
                    yield f"data: {chunk}\n\n"
                
                # After stream finishes, record message and usage
                assistant_msg = Message.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=full_reply,
                    citations={"sources": result["citations"]},
                    token_count=len(full_reply.split())
                )
                
                # Dynamic RAG analytics
                from core.services.rag_service import RAGService
                from core.services.cache_service import CacheService
                RAGService.record_usage(request.user, conversation, model_name, query, full_reply)
                CacheService.set_semantic_cache(query, full_reply)
                
                yield f"event: done\ndata: [Done]\n\n"

            return StreamingHttpResponse(stream_response(), content_type='text/event-stream')
        
        else:
            # Return standard JSON response
            assistant_msg = Message.objects.create(
                conversation=conversation,
                role='assistant',
                content=result["content"],
                citations=result["citations"],
                token_count=len(result["content"].split())
            )
            
            return Response({
                "role": "assistant",
                "content": result["content"],
                "citations": result["citations"],
                "route": result["route"]
            }, status=status.HTTP_201_CREATED)


class AnalyticsView(APIView):
    """
    GET /api/v1/analytics/usage
    Returns statistics of tokens and total estimated cost.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        usage_qs = TokenUsage.objects.filter(user=user)
        
        # Aggregations
        totals = usage_qs.aggregate(
            total_input=Sum('input_tokens'),
            total_output=Sum('output_tokens'),
            total_cost=Sum('cost')
        )
        
        # Scoped breakdown
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
