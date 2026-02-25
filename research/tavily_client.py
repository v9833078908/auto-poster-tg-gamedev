"""Tavily search client wrapper for gamedev AI research."""
from typing import List, Dict, Any, Optional


from tavily import TavilyClient


# Gamedev-specific domains for better search results
GAMEDEV_DOMAINS = [
    "gamedeveloper.com",
    "unrealengine.com",
    "unity.com",
    "aiandgames.com",
    "80.lv",
    "gdcvault.com",
    "gamasutra.com",
    "blog.unity.com",
    "dev.epicgames.com",
]


class TavilySearchClient:
    """Wrapper for Tavily web search API."""

    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key=api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        topic: str = "general",
        time_range: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search web using Tavily.

        Args:
            query: Search query
            max_results: Maximum number of results (default: 5)
            search_depth: "basic" or "advanced" (default: advanced)
            topic: "general" or "news" (default: general)
            time_range: "day", "week", "month", "year" or None
            include_domains: List of domains to prioritize

        Returns:
            List of search results with url, title, content, score
        """
        try:
            query = query[:380]  # Tavily hard limit is 400 chars
            kwargs = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_answer": True,
                "include_raw_content": False,
                "topic": topic,
            }

            if time_range:
                kwargs["time_range"] = time_range

            if include_domains:
                kwargs["include_domains"] = include_domains

            response = self.client.search(**kwargs)

            results = []
            for result in response.get("results", []):
                results.append({
                    "url": result.get("url"),
                    "title": result.get("title"),
                    "content": result.get("content"),
                    "score": result.get("score", 0)
                })

            return results
        except Exception as e:
            raise RuntimeError(f"Tavily search failed: {e}") from e
