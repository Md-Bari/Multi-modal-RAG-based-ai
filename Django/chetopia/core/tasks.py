from celery import shared_task
from django.utils import timezone
from core.models import Document, WebScrapeSource, ScrapeJob
from core.services.document_processing import DocumentProcessor
from core.services.scraping_service import ScrapingService
import logging
import os

logger = logging.getLogger(__name__)

@shared_task(name="core.tasks.process_document_task")
def process_document_task(document_id: int) -> bool:
    """
    Celery task to run document ingestion asynchronously.
    """
    logger.info(f"Starting Celery document processing task for ID {document_id}")
    return DocumentProcessor.process_document(document_id)

@shared_task(name="core.tasks.crawl_web_source_task")
def crawl_web_source_task(source_id: int) -> bool:
    """
    Celery task to crawl a web scraping source.
    Check content hash to see if we need to re-index.
    """
    try:
        source = WebScrapeSource.objects.get(id=source_id)
    except WebScrapeSource.DoesNotExist:
        logger.error(f"WebScrapeSource {source_id} not found.")
        return False

    job = ScrapeJob.objects.create(
        source=source,
        status="running",
        started_at=timezone.now()
    )

    try:
        logger.info(f"Crawling web source: {source.url}")
        scrape_result = ScrapingService.scrape_url(source.url)
        
        if scrape_result["error"]:
            raise Exception(scrape_result["error"])

        new_hash = scrape_result["change_hash"]
        
        # Check if hash has changed
        if new_hash != source.change_hash:
            logger.info(f"Web content has changed for {source.url}. Re-indexing.")
            
            # Find or create the Document representing this URL in the KB
            doc, created = Document.objects.get_or_create(
                kb=source.kb,
                original_filename=f"web_scrape_{source.id}.txt",
                defaults={
                    "source_type": "url",
                    "storage_url": f"web_crawled_source_{source.id}.txt",
                    "status": "pending",
                    "metadata": {"url": source.url}
                }
            )
            
            # Save scraped content to storage URL
            with open(doc.storage_url, "w", encoding="utf-8") as f:
                f.write(scrape_result["text"])

            # Run document processor synchronously inside this task
            DocumentProcessor.process_document(doc.id)
            
            # Update source metadata
            source.change_hash = new_hash
            source.last_crawled_at = timezone.now()
            source.save()
            
        else:
            logger.info(f"Web content unchanged for {source.url}. Skipping re-indexing.")
            source.last_crawled_at = timezone.now()
            source.save()

        job.status = "completed"
        job.save()
        return True

    except Exception as e:
        logger.exception(f"Web crawl failed for source {source_id}")
        job.status = "failed"
        job.save()
        return False
