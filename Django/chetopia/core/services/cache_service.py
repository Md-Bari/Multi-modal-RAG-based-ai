import logging
import numpy as np
from django.utils import timezone
from datetime import timedelta
from django.core.cache import cache
from core.models import CacheEntry
from core.services.rag_service import RAGService
import json

logger = logging.getLogger(__name__)

class CacheService:
    @staticmethod
    def get_semantic_cache(query: str, threshold: float = 0.95) -> str:
        """
        Check CacheEntry for semantically similar queries.
        Returns the cached response if similarity is above threshold, otherwise None.
        """
        try:
            # 1. Try memory cache first for exact matches
            try:
                exact_match_key = f"exact_cache:{query.strip().lower()}"
                exact_val = cache.get(exact_match_key)
                if exact_val:
                    logger.info("Exact cache hit!")
                    return exact_val
            except Exception as cache_err:
                logger.warning(f"Exact Redis cache lookup failed (Redis may be offline): {str(cache_err)}")

            # 2. Semantic lookup
            query_embedding = RAGService.get_query_embedding(query)
            query_vec = np.array(query_embedding)
            query_norm = np.linalg.norm(query_vec)
            if query_norm == 0:
                query_norm = 1e-9

            # Fetch active cache entries
            now = timezone.now()
            entries = CacheEntry.objects.filter(cache_type="semantic", expires_at__gt=now)

            best_match = None
            best_sim = 0.0

            for entry in entries:
                try:
                    # The cache key stores the embedding as a JSON list of floats
                    cache_key_data = json.loads(entry.cache_key)
                    cached_emb = cache_key_data.get("embedding")
                    if not cached_emb:
                        continue

                    cached_vec = np.array(cached_emb)
                    cached_norm = np.linalg.norm(cached_vec)
                    if cached_norm == 0:
                        cached_norm = 1e-9

                    sim = np.dot(query_vec, cached_vec) / (query_norm * cached_norm)
                    if sim > best_sim:
                        best_sim = sim
                        best_match = entry
                except Exception as e:
                    logger.error(f"Error parsing cache key for entry {entry.id}: {str(e)}")

            if best_match and best_sim >= threshold:
                logger.info(f"Semantic cache hit! Similarity: {best_sim:.4f}")
                best_match.hit_count += 1
                best_match.save()
                return best_match.cache_value

        except Exception as e:
            logger.error(f"Failed semantic cache lookup: {str(e)}")

        return None

    @staticmethod
    def set_semantic_cache(query: str, response: str, expire_days: int = 7) -> None:
        """
        Save the query, response, and its embedding into the semantic cache.
        """
        try:
            # 1. Save exact match to Redis cache
            try:
                exact_match_key = f"exact_cache:{query.strip().lower()}"
                cache.set(exact_match_key, response, timeout=60 * 60 * 24 * expire_days)
            except Exception as cache_err:
                logger.warning(f"Failed to write exact cache to Redis: {str(cache_err)}")

            # 2. Save semantic cache to DB CacheEntry
            query_embedding = RAGService.get_query_embedding(query)
            
            cache_key_data = {
                "query": query,
                "embedding": query_embedding
            }

            expires_at = timezone.now() + timedelta(days=expire_days)

            CacheEntry.objects.create(
                cache_type="semantic",
                cache_key=json.dumps(cache_key_data),
                cache_value=response,
                expires_at=expires_at
            )
            logger.info("Semantic cache successfully saved to database.")
        except Exception as e:
            logger.error(f"Failed to write to semantic cache: {str(e)}")
