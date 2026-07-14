from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APITestCase
from rest_framework import status
import json

from core.models import (
    Organization, Role, KnowledgeBase, Document, Chunk, 
    Conversation, Message, CacheEntry, TokenUsage
)
from core.services.cache_service import CacheService
from core.services.routing_engine import RoutingEngine
from core.services.rag_service import RAGService
from core.services.document_processing import DocumentProcessor

User = get_user_model()

class CoreModelsTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Chetopia Org", plan_tier="enterprise")
        self.role = Role.objects.create(name="analyst", permissions={"read": True})
        self.user = User.objects.create_user(
            username="cheto_user",
            email="cheto@example.com",
            password="testpassword",
            org=self.org,
            role=self.role
        )

    def test_organization_creation(self):
        self.assertEqual(self.org.name, "Chetopia Org")
        self.assertEqual(self.org.plan_tier, "enterprise")

    def test_user_associations(self):
        self.assertEqual(self.user.org, self.org)
        self.assertEqual(self.user.role, self.role)


class RAGAndIngestionTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(
            username="user_rag", password="pwd", org=self.org
        )
        self.kb = KnowledgeBase.objects.create(
            org=self.org, owner=self.user, name="Main KB", status="active"
        )
        self.doc = Document.objects.create(
            kb=self.kb, uploaded_by=self.user, source_type="file",
            original_filename="sample.txt", storage_url="sample.txt",
            status="completed"
        )
        # Create a sample chunk with text and embedding
        self.chunk = Chunk.objects.create(
            document=self.doc,
            chunk_text="Chetopia AI is an enterprise knowledge management system.",
            chunk_index=0,
            token_count=10,
            embedding=[0.0] * 1536
        )

    def test_semantic_chunking(self):
        text = "This is sentence one. This is sentence two. This is sentence three."
        chunks = DocumentProcessor._semantic_chunking(text, max_chunk_size=50)
        self.assertTrue(len(chunks) > 0)

    def test_hybrid_retrieval(self):
        # Verify query embedding retrieval works on SQLite (uses python similarity fallback)
        results = RAGService.retrieve_context(self.kb.id, "Chetopia AI", top_k=2)
        self.assertEqual(len(results), 1)
        self.assertIn("Chetopia AI is an enterprise knowledge", results[0]["text"])


class RoutingAndCacheTestCase(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Cache Org")
        self.user = User.objects.create_user(username="cache_user", password="pwd", org=self.org)
        self.kb = KnowledgeBase.objects.create(org=self.org, owner=self.user, name="Cache KB")
        self.conv = Conversation.objects.create(kb=self.kb, user=self.user, title="Session")

    def test_semantic_cache(self):
        query = "What is Chetopia AI?"
        response = "Chetopia AI is an intelligent knowledge platform."
        
        # Test Cache Set
        CacheService.set_semantic_cache(query, response, expire_days=1)
        
        # Test Cache Get
        cached = CacheService.get_semantic_cache(query)
        self.assertEqual(cached, response)

        # Test semantic similarity query (slightly different text)
        cached_sim = CacheService.get_semantic_cache("Explain what Chetopia AI is?")
        self.assertEqual(cached_sim, response)


class APITests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="API Org")
        self.role = Role.objects.create(name="admin")
        self.user = User.objects.create_user(
            username="api_user", password="securepassword", org=self.org, role=self.role
        )
        self.kb = KnowledgeBase.objects.create(org=self.org, owner=self.user, name="API KB")
        self.conv = Conversation.objects.create(kb=self.kb, user=self.user, title="API Chat")

    def test_login_and_jwt(self):
        # 1. Login
        response = self.client.post('/api/v1/auth/login', {
            "username": "api_user",
            "password": "securepassword"
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        
        token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 2. Get Knowledge Bases
        kb_response = self.client.get('/api/v1/knowledge-bases/')
        self.assertEqual(kb_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(kb_response.data), 1)
        self.assertEqual(kb_response.data[0]["name"], "API KB")

        # 3. Submit a query to conversation messages
        msg_response = self.client.post(f'/api/v1/conversations/{self.conv.id}/messages', {
            "content": "Tell me a general joke",
            "provider": "openai",
            "model_name": "gpt-4o",
            "stream": False
        })
        self.assertEqual(msg_response.status_code, status.HTTP_201_CREATED)
        self.assertIn("content", msg_response.data)
        self.assertEqual(msg_response.data["route"], "llm_native")

