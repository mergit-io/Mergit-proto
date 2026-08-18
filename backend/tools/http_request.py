"""Fetch a URL on the open internet — and only the open internet.

This tool is on both the `researcher` and the `integrator`, and the researcher reads
attacker-authored text: a GitHub issue body is untrusted input that the model will happily
act on. The original accepted any URL, any method and an arbitrary header dict, and
returned every response header. That is three primitives in one:

  * **SSRF.** `http://169.254.169.254/…` is the cloud metadata endpoint; `http://127.0.0.1:8000/api/config/keys`
    is Mergit's own unauthenticated key store. Both were reachable from a sentence in an
    issue body.
  * **Exfiltration.** An arbitrary `headers` dict lets the model put anything it has been
    told into a request to a host of the attacker's choosing.
  * **Credential capture.** Returning `dict(resp.headers)` hands `Set-Cookie` and any
    `Authorization` echo straight back into model context.

The fixes, in order of how much they matter:

1. **Resolve the hostname and reject private space** — checking the *name* is worthless,
   since `evil.com` can simply have an A record of `127.0.0.1`. Every address the name
   resolves to must be public, not merely the first: a name with one public and one
   private record would otherwise be a coin flip that the attacker gets to call.

   Residual risk, stated rather than hidden: this is check-then-connect, so a DNS
   rebinding attack can still win the race between our lookup and httpx's. Closing that
   needs the connection pinned to the vetted IP, which for HTTPS means overriding SNI and
   certificate verification hostname — real complexity for a narrow attack. The honest
   mitigation is that the truly dangerous targets (cloud metadata, Mergit's own port) are
   reached by *address*, and those are refused outright.
2. **HTTPS only, no redirects.** A permitted https:// URL that 302s to
   `http://169.254.169.254/` would otherwise walk straight through the check.
3. **No caller-supplied headers.** Removed from the schema entirely. An agent that needs
   to authenticate somewhere should be given a first-class tool with a real credential
   from the broker, not the ability to hand-roll a bearer header.
4. **Response headers are filtered to a safe allowlist**, so nothing sensitive is returned.
"""
import ipaddress
import socket

import httpx

#: Everything a caller may learn about the response. Enough to act on (content type,
#: rate limits, redirect target) without returning Set-Cookie or an Authorization echo.
_SAFE_RESPONSE_HEADERS = (
    "content-type", "content-length", "date", "server", "location",
    "retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
)

_MAX_BODY = 8192


def _vet_host(host: str) -> tuple[str | None, str | None]:
    """Resolve `host` and return (ip, error). The IP is the one we will connect to.

    Every address the name resolves to must be public: a name with both a public and a
    private A record would otherwise be a coin flip, and the attacker picks the coin.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return None, f"could not resolve host {host!r}: {e}"
    if not infos:
        return None, f"could not resolve host {host!r}"

    chosen = None
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return None, f"unparseable address for {host!r}"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            # Named explicitly, because "request blocked" with no reason sends the agent
            # into a retry loop against a target it will never be allowed to reach.
            return None, (
                f"refusing to call {host!r}: it resolves to {addr}, which is a private, "
                "loopback or link-local address. Only public internet hosts are allowed."
            )
        if chosen is None:
            chosen = addr
    return chosen, None


async def http_request(args: dict) -> dict:
    url = args["url"]
    method = args.get("method", "GET").upper()
    body = args.get("body")
    timeout = min(int(args.get("timeout", 30) or 30), 60)

    try:
        parsed = httpx.URL(url)
    except Exception as e:
        return {"ok": False, "error": f"invalid URL: {e}"}

    if parsed.scheme != "https":
        return {"ok": False, "error": (
            f"refusing to call {parsed.scheme!r}:// — only https:// is allowed. "
            "Plain HTTP is how internal metadata and localhost services get reached."
        )}
    if not parsed.host:
        return {"ok": False, "error": "URL has no host"}

    _ip, err = _vet_host(parsed.host)
    if err:
        return {"ok": False, "error": err}

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            # A redirect is a fresh URL that never passed the checks above — following one
            # would let a permitted https:// host bounce us to http://169.254.169.254/.
            # The Location header is returned instead, so a caller that legitimately needs
            # to follow it can re-issue the call and get it re-checked.
            follow_redirects=False,
            headers={"User-Agent": "Mergit/0.1 (+https://github.com/mergit-io)"},
        ) as client:
            if isinstance(body, dict):
                resp = await client.request(method, url, json=body)
            elif isinstance(body, str):
                resp = await client.request(method, url, content=body)
            else:
                resp = await client.request(method, url)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "status_code": resp.status_code,
        "body": resp.text[:_MAX_BODY],
        "headers": {k: v for k, v in resp.headers.items()
                    if k.lower() in _SAFE_RESPONSE_HEADERS},
        "ok": resp.is_success,
    }


SCHEMA = {
    "description": (
        "Make an HTTPS request to a public internet URL and return the status and body. "
        "Only https:// is supported; private, loopback and link-local addresses are refused; "
        "redirects are not followed. Custom request headers are not available — if a call "
        "needs authentication, it needs a dedicated tool, not this one."
    ),
    "type": "object",
    "properties": {
        "url": {"type": "string", "description": "The https:// URL to call"},
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"], "default": "GET"},
        # `headers` is deliberately absent. See the module docstring.
        "body": {"description": "Request body (object for JSON, string for raw)"},
        "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds (max 60)"},
    },
    "required": ["url"],
}
