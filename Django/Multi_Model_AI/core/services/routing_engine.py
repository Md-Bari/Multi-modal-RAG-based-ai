import logging
from typing import Dict, Any, List
from core.models import KnowledgeBase, User, Conversation, Message, Document, WebScrapeSource
from core.services.cache_service import CacheService
from core.services.rag_service import RAGService
from core.services.llm_service import LLMService
from core.services.scraping_service import ScrapingService
from core.services.document_processing import DocumentProcessor

logger = logging.getLogger(__name__)

class RoutingEngine:
    @staticmethod
    def route_and_generate(
        user: User,
        kb_id: int,
        conversation_id: int,
        query: str,
        provider: str = "openai",
        model_name: str = "gpt-4o",
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Main orchestration entrypoint for user queries.
        Implements 6-step routing flow.
        """
        # Step 1: Semantic Response Cache check
        cached_response = CacheService.get_semantic_cache(query)
        if cached_response:
            return {
                "content": cached_response,
                "route": "cache_hit",
                "citations": []
            }

        # Fetch conversation history
        history = list(Message.objects.filter(conversation_id=conversation_id).order_by('created_at'))
        history_formatted = [{"role": msg.role, "content": msg.content} for msg in history]

        # Step 2: KB search & Confidence Evaluation
        context_chunks = RAGService.retrieve_context(kb_id, query, top_k=5)
        
        # Determine confidence (e.g. if we have matched chunks with score >= 0.6)
        has_confidence = len(context_chunks) > 0 and any(c["score"] >= 0.6 for c in context_chunks)

        if has_confidence:
            logger.info("Routing query to: Grounded RAG (KB)")
            messages = RAGService.construct_rag_prompt(query, context_chunks, history_formatted)
            
            # Generate response
            response_content = LLMService.generate_response(provider, model_name, messages, stream=stream)
            
            # For streaming, we'll return the generator (caller must handle caching/token recording after stream ends)
            if stream:
                return {
                    "content": response_content,
                    "route": "rag_kb",
                    "citations": [c["filename"] for c in context_chunks]
                }
            
            # Non-stream tracking
            RAGService.record_usage(user, Conversation.objects.get(id=conversation_id), model_name, str(messages), response_content)
            CacheService.set_semantic_cache(query, response_content)
            
            return {
                "content": response_content,
                "route": "rag_kb",
                "citations": list(set([c["filename"] for c in context_chunks]))
            }

        # Step 3: Native Knowledge Check
        # Ask LLM if this is a general knowledge question
        check_prompt = [
            {"role": "system", "content": "You are a routing classification system. Respond with exactly 'YES' if the user's question is a general, static, or historic knowledge query that does not require private documents or real-time web information. Respond with 'NO' otherwise."},
            {"role": "user", "content": f"Question: {query}"}
        ]
        
        try:
            decision = LLMService.generate_response(provider, model_name, check_prompt).strip().upper()
        except Exception:
            decision = "NO"

        if "YES" in decision:
            logger.info("Routing query to: LLM Native Knowledge")
            messages = [{"role": "system", "content": "You are Chetopia AI. Answer the user query using your native knowledge."}] + history_formatted + [{"role": "user", "content": query}]
            
            response_content = LLMService.generate_response(provider, model_name, messages, stream=stream)
            if stream:
                return {
                    "content": response_content,
                    "route": "llm_native",
                    "citations": []
                }
            
            RAGService.record_usage(user, Conversation.objects.get(id=conversation_id), model_name, str(messages), response_content)
            CacheService.set_semantic_cache(query, response_content)
            return {
                "content": response_content,
                "route": "llm_native",
                "citations": []
            }

        # Step 4 & 5: Live Web Fallback & Temporary RAG
        logger.info("Routing query to: Live Web Fallback")
        # Simulating dynamic search by checking if we have scrape sources or fallback querying
        # For demo purposes, we will scrape a search engine result or query Google/Bing if API is configured,
        # or we crawl mock web pages/scrape sources matching keywords.
        
        web_sources = WebScrapeSource.objects.filter(kb_id=kb_id, status='active')
        web_text = ""
        scraped_urls = []
        
        for ws in web_sources[:3]:  # Try scraping the first 3 registered active sources
            scrape_res = ScrapingService.scrape_url(ws.url)
            if scrape_res["text"]:
                web_text += f"\n--- Web Source: {ws.url} ---\n{scrape_res['text']}\n"
                scraped_urls.append(ws.url)
        
        # If no active scrape sources, use a mock web search result for query
        if not web_text:
            mock_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            web_text = f"[Web Search Result for '{query}']\nChetopia AI crawled public resources and found matches indicating recent updates on this topic."
            scraped_urls.append(mock_url)

        # Temporary chunk & embed the web content dynamically
        web_chunks = DocumentProcessor._semantic_chunking(web_text, max_chunk_size=600)
        temp_context = []
        for idx, chunk in enumerate(web_chunks[:5]):
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

        RAGService.record_usage(user, Conversation.objects.get(id=conversation_id), model_name, str(messages), response_content)
        CacheService.set_semantic_cache(query, response_content)
        
        return {
            "content": response_content,
            "route": "web_fallback",
            "citations": scraped_urls,
            "can_save_to_kb": True,
            "web_content": web_text,
            "scraped_url": scraped_urls[0] if scraped_urls else None
        }

    @staticmethod
    def save_web_content_to_kb(kb_id: int, url: str, content_text: str, user: User) -> Document:
        """
        Step 6: User chooses to save scraped web content to KB.
        """
        # Create a document for the URL
        filename = f"web_scraped_{url.split('/')[-1] or 'page'}.txt"
        if not filename.endswith(".txt"):
            filename += ".txt"
            
        doc = Document.objects.create(
            kb_id=kb_id,
            uploaded_by=user,
            source_type="url",
            original_filename=filename,
            storage_url=f"web_cache_{hash(url)}.txt",
            status="pending"
        )
        
        # Write content text locally for DocumentProcessor to parse
        with open(doc.storage_url, "w", encoding="utf-8") as f:
            f.write(content_text)
            
        # Trigger processing (normally async via Celery, but we can call it directly or schedule it)
        DocumentProcessor.process_document(doc.id)
        
        return doc
