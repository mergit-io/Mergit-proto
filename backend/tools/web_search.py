import logging

from config import settings
from tracing import trace

logger = logging.getLogger(__name__)


async def _ddg_search(query: str, max_results: int) -> dict:
    """Free fallback using DuckDuckGo Instant Answer API (no key required)."""
    import httpx
    params = {"q": query, "format": "json", "no_redirect": "1", "no_html": "1"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.duckduckgo.com/", params=params)
            r.raise_for_status()
            data = r.json()

        results = []
        # Abstract (direct answer)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "content": data["AbstractText"],
                "score": 1.0,
            })
        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:80],
                    "url": topic.get("FirstURL", ""),
                    "content": topic.get("Text", ""),
                    "score": 0.8,
                })
            if len(results) >= max_results:
                break

        if results:
            logger.info("DuckDuckGo fallback returned %d results for: %s", len(results), query)
            return {"results": results, "_source": "duckduckgo"}
    except Exception as e:
        logger.warning("DuckDuckGo fallback failed: %s", e)

    # Final fallback: tell the model to use its knowledge
    return {
        "results": [],
        "_source": "none",
        "note": (
            f"Web search is currently unavailable. "
            f"Use your training knowledge to answer the question about: {query}"
        ),
    }


@trace("web_search")
async def web_search(args: dict) -> dict:
    query = args["query"]
    max_results = args.get("max_results", 5)
    mode = args.get("mode", "search")

    # Try Tavily first if key is configured and not a placeholder
    api_key = settings.tavily_api_key or ""
    if api_key and not api_key.startswith("tvly-...") and len(api_key) > 10:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            if mode == "qna":
                answer = client.qna_search(query)
                return {"answer": answer, "results": [], "_source": "tavily"}
            response = client.search(query, max_results=max_results)
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                }
                for r in response.get("results", [])
            ]
            return {"results": results, "_source": "tavily"}
        except Exception as e:
            logger.warning("Tavily failed (%s) — falling back to DuckDuckGo", e)

    return await _ddg_search(query, max_results)


SCHEMA = {
    "description": "Search the web for information. Returns results from multiple sources.",
    "type": "object",
    "properties": {
        "query":       {"type": "string", "description": "The search query"},
        "max_results": {"type": "integer", "default": 5, "description": "Max results to return"},
        "mode":        {"type": "string", "enum": ["search", "qna"], "default": "search",
                        "description": "search returns a result list; qna returns a direct answer"},
    },
    "required": ["query"],
}
