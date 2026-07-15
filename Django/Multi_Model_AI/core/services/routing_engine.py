import logging
from typing import Dict, Any, List, Optional
from core.models import KnowledgeBase, User, Conversation, Message, Document
from core.services.cache_service import CacheService
from core.services.rag_service import RAGService
from core.services.llm_service import LLMService
from core.services.document_processing import DocumentProcessor
from core.services.web_search import WebSearchService
from core.services.vision_service import VisionService

logger = logging.getLogger(__name__)

class RoutingEngine:
    @staticmethod
    def route_and_generate(
        user: User,
        kb_id: int,
        conversation_id: int,
        query: str,
        provider: Optional[str] = None,
        model_name: Optional[str] = None,
        stream: bool = False,
        images: Optional[List[bytes]] = None
    ) -> Dict[str, Any]:
        """
        Main orchestration entrypoint for user queries.
        Implements 6-step routing flow:
        1. Semantic cache check
        2. KB retrieval (RAG)
        3. LLM native knowledge
        4. Live web search fallback (DuckDuckGo + crawl4ai + Wikipedia)
        5. Generate response with context
        6. Optionally save web content to KB
        """
        # Step 1: Semantic Response Cache check
        cached_response = CacheService.get_semantic_cache(query)
        if cached_response:
            return {
                "content": cached_response,
                "route": "cache_hit",
                "citations": []
            }

        # Fetch conversation history (last 6 messages)
        history = list(
            Message.objects.filter(conversation_id=conversation_id)
            .order_by('created_at')[:6]
        )
        history_formatted = [{"role": msg.role, "content": msg.content} for msg in history]

        # Handle images: caption them and prepend as context
        image_context = ""
        if images:
            for img_bytes in images:
                caption = VisionService.caption_image(img_bytes)
                image_context += f"\n[User uploaded image]:\n{caption}\n"
            if image_context:
                query = f"{image_context}\nUser query: {query}"

        similarity_threshold = RAGService.get_similarity_threshold()
        top_k = RAGService.get_top_k()

        # Step 2: KB search & Confidence Evaluation
        context_chunks = RAGService.retrieve_context(kb_id, query, top_k=top_k)
        has_confidence = len(context_chunks) > 0 and any(
            c["score"] >= similarity_threshold for c in context_chunks
        )

        if has_confidence:
            logger.info("Routing query to: Grounded RAG (KB)")
            messages = RAGService.construct_rag_prompt(query, context_chunks, history_formatted)
            response_content = LLMService.generate_response(provider, model_name, messages, stream=stream)

            if stream:
                return {
                    "content": response_content,
                    "route": "rag_kb",
                    "citations": [c["filename"] for c in context_chunks]
                }

            RAGService.record_usage(
                user, Conversation.objects.get(id=conversation_id),
                model_name or LLMService.get_llm_model(),
                str(messages), response_content
            )
            CacheService.set_semantic_cache(query, response_content)
            return {
                "content": response_content,
                "route": "rag_kb",
                "citations": list(set(c["filename"] for c in context_chunks))
            }

        # Step 3: Native Knowledge Check
        check_prompt = [
            {"role": "system", "content": (
                "You are a routing classification system. Respond with exactly 'YES' if the "
                "user's question is general knowledge that does not require private documents "
                "or real-time web information. Respond with 'NO' otherwise."
            )},
            {"role": "user", "content": f"Question: {query}"}
        ]
        try:
            decision = LLMService.generate_response(provider, model_name, check_prompt).strip().upper()
        except Exception:
            decision = "NO"

        if "YES" in decision:
            logger.info("Routing query to: LLM Native Knowledge")
            messages = [
                {"role": "system", "content": "You are Chetopia AI. Answer using your native knowledge."}
            ] + history_formatted + [{"role": "user", "content": query}]

            response_content = LLMService.generate_response(provider, model_name, messages, stream=stream)
            if stream:
                return {"content": response_content, "route": "llm_native", "citations": []}

            RAGService.record_usage(
                user, Conversation.objects.get(id=conversation_id),
                model_name or LLMService.get_llm_model(),
                str(messages), response_content
            )
            CacheService.set_semantic_cache(query, response_content)
            return {"content": response_content, "route": "llm_native", "citations": []}

        # Step 4 & 5: Live Web Fallback
        logger.info("Routing query to: Live Web Fallback")
        web_results = WebSearchService.search_web(query)

        web_text = ""
        scraped_urls = []
        for r in web_results:
            web_text += f"\n--- Source: {r['title']} ({r['url']}) ---\n{r['text']}\n"
            scraped_urls.append(r['url'])

        if not web_text:
            web_text = f"[Web search returned no results for '{query}']"
            scraped_urls = [f"https://duckduckgo.com/?q={query.replace(' ', '+')}"]

        web_chunks = DocumentProcessor._semantic_chunking(web_text, max_chunk_size=800)
        temp_context = []
        for chunk in web_chunks[:5]:
            temp_context.append({
                "filename": scraped_urls[0] if scraped_urls else "Live Web Search",
                "document_id": 0,
                "text": chunk,
                "score": 0.9
            })

        messages = RAGService.construct_rag_prompt(query, temp_context, history_formatted)
        response_content = LLMService.generate_response(provider, model_name, messages, stream=stream)

        if stream:
            return {
                "content": response_content,
                "route": "web_fallback",
                "citations": scraped_urls,
                "can_save_to_kb": True,
                "web_content": web_text,
                "scraped_url": scraped_urls[0] if scraped_urls else None
            }

        RAGService.record_usage(
            user, Conversation.objects.get(id=conversation_id),
            model_name or LLMService.get_llm_model(),
            str(messages), response_content
        )
        CacheService.set_semantic_cache(query, response_content)

        return {
            "content": response_content,
            "route": "web_fallback",
            "citations": scraped_urls,
            "can_save_to_kb": True,
            "web_content": web_text,
            "scraped_url": scraped_urls[0] if scraped_urls else None
        }
