import httpx

from tracing import trace


@trace("http_request")
async def http_request(args: dict) -> dict:
    url = args["url"]
    method = args.get("method", "GET").upper()
    headers = args.get("headers", {})
    body = args.get("body")
    timeout = args.get("timeout", 30)

    async with httpx.AsyncClient(timeout=timeout) as client:
        if isinstance(body, dict):
            resp = await client.request(method, url, headers=headers, json=body)
        elif isinstance(body, str):
            resp = await client.request(method, url, headers=headers, content=body)
        else:
            resp = await client.request(method, url, headers=headers)

    return {
        "status_code": resp.status_code,
        "body": resp.text[:8192],
        "headers": dict(resp.headers),
        "ok": resp.is_success,
    }


SCHEMA = {
    "description": "Make an HTTP request to any URL.",
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The URL to call"},
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
        "headers": {"type": "object", "description": "Request headers"},
        "body": {"description": "Request body (object for JSON, string for raw)"},
        "timeout": {"type": "integer", "default": 30},
    },
    "required": ["url"],
}
