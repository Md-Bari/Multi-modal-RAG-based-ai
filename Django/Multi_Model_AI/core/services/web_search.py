import os
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WebSearchService:
    @staticmethod
    def search_duckduckgo(query: str, max_results: int = 3) -> list:
        """Search DuckDuckGo for results."""
        results = []
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", "")
                    })
        except ImportError:
            logger.warning("duckduckgo_search not installed")
            return WebSearchService._mock_search(query)
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {str(e)}")
        return results

    @staticmethod
    def _mock_search(query: str) -> list:
        """Fallback mock search."""
        return [{
            "title": f"Web search results for: {query}",
            "url": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
            "snippet": f"Search results for '{query}'. No live search available."
        }]

    @staticmethod
    def scrape_url(url: str) -> str:
        """Scrape a URL and extract clean text content."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            # Try crawl4ai first
            try:
                from crawl4ai import WebCrawler
                crawler = WebCrawler()
                result = crawler.crawl(url)
                if result and result.markdown:
                    return result.markdown[:8000]
            except ImportError:
                pass

            # Fallback to requests + BeautifulSoup
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    tag.decompose()
                text = soup.get_text(separator="\n")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                return "\n".join(lines[:200])
        except Exception as e:
            logger.error(f"Scraping {url} failed: {str(e)}")
        return ""

    @staticmethod
    def search_wikipedia(query: str) -> str:
        """Search Wikipedia for a topic."""
        try:
            import wikipediaapi
            user_agent = "ChetopiaAI/1.0"
            api = wikipediaapi.Wikipedia(user_agent, "en")
            page = api.page(query)
            if page.exists():
                return page.summary[:4000]
        except ImportError:
            logger.warning("wikipedia-api not installed")
        except Exception as e:
            logger.error(f"Wikipedia search failed: {str(e)}")

        # Fallback to REST API
        try:
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": 1
            }
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                pages = data.get("query", {}).get("search", [])
                if pages:
                    title = pages[0]["title"]
                    extract_resp = requests.get(
                        "https://en.wikipedia.org/w/api.php",
                        params={
                            "action": "query",
                            "prop": "extracts",
                            "exintro": True,
                            "explaintext": True,
                            "titles": title,
                            "format": "json"
                        },
                        timeout=10
                    )
                    if extract_resp.status_code == 200:
                        pages_data = extract_resp.json().get("query", {}).get("pages", {})
                        for p in pages_data.values():
                            return p.get("extract", "")[:4000]
        except Exception as e:
            logger.error(f"Wikipedia REST API failed: {str(e)}")
        return ""

    @staticmethod
    def search_web(query: str) -> list:
        """Multi-engine web search: DuckDuckGo + Wikipedia. Returns list of dicts with title, url, text."""
        results = []

        # DuckDuckGo
        ddg_results = WebSearchService.search_duckduckgo(query)
        for r in ddg_results[:2]:
            scraped = WebSearchService.scrape_url(r["url"])
            results.append({
                "title": r["title"],
                "url": r["url"],
                "text": scraped or r["snippet"],
                "source": "web"
            })

        # Wikipedia
        wiki_text = WebSearchService.search_wikipedia(query)
        if wiki_text:
            results.append({
                "title": f"Wikipedia: {query}",
                "url": f"https://en.wikipedia.org/wiki/{query.replace(' ', '_')}",
                "text": wiki_text,
                "source": "wikipedia"
            })

        return results
