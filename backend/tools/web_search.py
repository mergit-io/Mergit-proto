from config import settings
from tracing import trace


@trace("web_search")
async def web_search(args: dict) -> dict:
    from tavily import TavilyClient
    client = TavilyClient(api_key=settings.tavily_api_key)
    query = args["query"]
    max_results = args.get("max_results", 5)
    mode = args.get("mode", "search")

    if mode == "qna":
        answer = client.qna_search(query)
        return {"answer": answer, "results": []}

    response = client.search(query, max_results=max_results)
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", ""), "score": r.get("score", 0)}
        for r in response.get("results", [])
    ]
    return {"results": results}


SCHEMA = {
    "description": "Search the web for information on a topic.",
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "The search query"},
        "max_results": {"type": "integer", "default": 5, "description": "Number of results to return"},
        "mode": {"type": "string", "enum": ["search", "qna"], "default": "search", "description": "search returns result list; qna returns a direct answer"},
    },
    "required": ["query"],
}
