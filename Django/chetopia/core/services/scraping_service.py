import requests
from bs4 import BeautifulSoup
import hashlib
import logging

logger = logging.getLogger(__name__)

class ScrapingService:
    @staticmethod
    def scrape_url(url: str) -> dict:
        """
        Scrape a URL, extract clean text content, and return clean text, titles, and hash of the text.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                logger.error(f"Failed to scrape {url}, status code: {response.status_code}")
                return {
                    "text": "",
                    "title": "",
                    "change_hash": "",
                    "error": f"HTTP {response.status_code}"
                }
            
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Remove scripts, styles, navs, footers, etc.
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
                
            title = soup.title.string.strip() if soup.title else url
            text = soup.get_text(separator="\n")
            
            # Clean up whitespace
            lines = [line.strip() for line in text.splitlines()]
            clean_text = "\n".join([line for line in lines if line])
            
            # Calculate content hash
            change_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()
            
            return {
                "text": clean_text,
                "title": title,
                "change_hash": change_hash,
                "error": None
            }
        except Exception as e:
            logger.error(f"Exception scraping {url}: {str(e)}")
            return {
                "text": "",
                "title": "",
                "change_hash": "",
                "error": str(e)
            }
