"""Basic browser security headers for every API response.

The API only returns JSON and PDFs, never pages, so the policy can be as tight as it gets.
"""

from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    # Browsers ignore HSTS on plain http, so it is safe to send everywhere. Render only
    # serves the API over https.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Resource-Policy": "cross-origin",
}


class SecurityHeadersMiddleware:
    """Adds the headers above. A header a route already set is left alone.

    `docs_paths` (only when the API docs are turned on) skip the CSP, because the Swagger page
    needs scripts and styles from a CDN.
    """

    def __init__(self, app: ASGIApp, *, docs_paths: Iterable[str] = ()) -> None:
        self.app = app
        self.docs_paths = tuple(docs_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"] in self.docs_paths

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    if name not in headers:
                        headers[name] = value
                if not is_docs and "Content-Security-Policy" not in headers:
                    headers["Content-Security-Policy"] = API_CSP
            await send(message)

        await self.app(scope, receive, send_with_headers)
