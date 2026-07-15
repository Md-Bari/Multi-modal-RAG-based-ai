import logging
import numpy as np
import requests
import json
from django.db import connection
from django.conf import settings
from core.models import Chunk, Document, Conversation, Message, TokenUsage
from core.services.llm_service import LLMService
import os

logger = logging.getLogger(__name__)

# Try importing pgvector CosineDistance
try:
    from pgvector.django import CosineDistance
    pgvector_available = True
except ImportError:
    CosineDistance = None
    pgvector_available = False

EMBED_DIM = 768

class RAGService:
    @staticmethod
    def get_embedding_dim() -> int:
        return EMBED_DIM

    @staticmethod
    def get_similarity_threshold() -> float:
        return float(os.environ.get("SIMILARITY_THRESHOLD", "0.45"))

    @staticmethod
    def get_top_k() -> int:
        return int(os.environ.get("TOP_K", "5"))

    @staticmethod
    def get_query_embedding(query: str) -> list:
        """
        Generate embedding for user query using Ollama's nomic-embed-text.
        """
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        model = LLMService.get_embedding_model()
        url = f"{base_url}/api/embed"
        try:
            response = requests.post(url, json={"model": model, "input": query}, timeout=30)
            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if embeddings:
                    return embeddings[0]
        except Exception as e:
            logger.error(f"Ollama embedding failed: {str(e)}")
        
        # Fallback dummy vector
        vector = [0.0] * EMBED_DIM
        vector[0] = 1.0
        return vector

    @staticmethod
    def retrieve_context(kb_id: int, query: str, top_k: int = 5) -> list:
        """
        Retrieve chunks using hybrid search (semantic + keyword) and cross-encoder reranking.
        """
        query_embedding = RAGService.get_query_embedding(query)
        
        # Get all completed documents for the KB
        docs = Document.objects.filter(kb_id=kb_id, status='completed')
        chunks_qs = Chunk.objects.filter(document__in=docs)
        
        if not chunks_qs.exists():
            return []

        candidates = []
        
        # 1. Semantic Search
        db_engine = settings.DATABASES['default']['ENGINE']
        is_postgres = 'postgresql' in db_engine

        if is_postgres and pgvector_available and CosineDistance is not None:
            try:
                # pgvector DB query
                semantic_results = chunks_qs.annotate(
                    distance=CosineDistance('embedding', query_embedding)
                ).order_by('distance')[:top_k * 3]
                
                for chunk in semantic_results:
                    candidates.append({
                        "id": chunk.id,
                        "document_id": chunk.document.id,
                        "filename": chunk.document.original_filename,
                        "text": chunk.chunk_text,
                        "score": 1.0 - getattr(chunk, 'distance', 0.5)
                    })
            except Exception as e:
                logger.error(f"PostgreSQL pgvector similarity query failed: {str(e)}. Falling back to Python similarity.")
                candidates = RAGService._python_similarity(chunks_qs, query_embedding, top_k * 3)
        else:
            # SQLite / Local Python fallback
            candidates = RAGService._python_similarity(chunks_qs, query_embedding, top_k * 3)

        # 2. Keyword Search Integration (Hybrid)
        # Find exact keyword matches and boost them
        keywords = [word.lower() for word in query.split() if len(word) > 3]
        for term in keywords:
            kw_matches = chunks_qs.filter(chunk_text__icontains=term)[:top_k]
            for chunk in kw_matches:
                # Check if already in candidates
                existing = next((c for c in candidates if c["id"] == chunk.id), None)
                if existing:
                    existing["score"] += 0.2  # Boost factor
                else:
                    candidates.append({
                        "id": chunk.id,
                        "document_id": chunk.document.id,
                        "filename": chunk.document.original_filename,
                        "text": chunk.chunk_text,
                        "score": 0.5
                    })

        # Remove duplicates
        unique_candidates = []
        seen_ids = set()
        for c in candidates:
            if c["id"] not in seen_ids:
                unique_candidates.append(c)
                seen_ids.add(c["id"])

        # 3. Cross-Encoder Reranking (Simulated here)
        # Rerank candidates based on keyword density/overlap and semantic score
        reranked = RAGService._rerank_chunks(unique_candidates, query)
        
        return reranked[:top_k]

    @staticmethod
    def _python_similarity(chunks_qs, query_embedding, limit: int) -> list:
        results = []
        query_vec = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vec)
        
        if query_norm == 0:
            query_norm = 1e-9

        # Since this is a fallback for testing, we load metadata
        for chunk in chunks_qs:
            emb = chunk.embedding
            if not emb:
                continue
            
            # embedding is saved as list in SQLite custom field
            emb_vec = np.array(emb)
            emb_norm = np.linalg.norm(emb_vec)
            
            if emb_norm == 0:
                emb_norm = 1e-9
                
            sim = np.dot(query_vec, emb_vec) / (query_norm * emb_norm)
            
            results.append({
                "id": chunk.id,
                "document_id": chunk.document.id,
                "filename": chunk.document.original_filename,
                "text": chunk.chunk_text,
                "score": float(sim)
            })

        # Sort by similarity descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    @staticmethod
    def _rerank_chunks(candidates: list, query: str) -> list:
        """
        Simulate a Cross-Encoder Reranking.
        Combines vector cosine similarity with token overlap metrics.
        """
        query_words = set(query.lower().split())
        
        for c in candidates:
            chunk_words = set(c["text"].lower().split())
            overlap = len(query_words.intersection(chunk_words))
            
            # Formula: semantic score + overlap boost
            overlap_ratio = overlap / max(len(query_words), 1)
            c["score"] = c["score"] * 0.7 + overlap_ratio * 0.3
            
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    @staticmethod
    def construct_rag_prompt(query: str, context_chunks: list, conversation_history: list) -> list:
        """
        Construct system instructions and format the prompt.
        """
        system_content = (
            "You are Chetopia AI, a premium enterprise-grade Knowledge Management assistant.\n"
            "Answer the query truthfully using the provided Context. Always ground your answers "
            "in the context and cite your sources in the format [Source: Filename] or [Doc ID].\n"
            "If the context does not contain the answer, say that you cannot find it in the "
            "internal knowledge base.\n\n"
            "--- Context ---\n"
        )
        
        for idx, chunk in enumerate(context_chunks):
            system_content += f"\n[Document: {chunk['filename']} (ID: {chunk['document_id']})]\n{chunk['text']}\n"
            
        system_content += "\n--- End Context ---"

        messages = [{"role": "system", "content": system_content}]
        
        # Add conversation history
        for msg in conversation_history[-5:]:  # Last 5 turns
            messages.append({"role": msg["role"], "content": msg["content"]})
            
        # Add current user query
        messages.append({"role": "user", "content": query})
        
        return messages

    @staticmethod
    def record_usage(user, conversation, model_name: str, input_text: str, output_text: str) -> None:
        """
        Calculate token count, cost, and save usage metrics.
        """
        input_tokens = len(input_text.split()) * 1.3  # Rough token multiplier
        output_tokens = len(output_text.split()) * 1.3
        
        # Mock cost calculation
        cost_per_million_input = 2.50  # USD
        cost_per_million_output = 10.00
        cost = ((input_tokens * cost_per_million_input) + (output_tokens * cost_per_million_output)) / 1000000.0

        TokenUsage.objects.create(
            user=user,
            conversation=conversation,
            model_name=model_name,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cost=cost
        )
