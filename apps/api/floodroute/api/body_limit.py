"""Bound API request bodies before JSON parsing, signatures, or photo processing."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from floodroute.api.photo import MAX_PHOTO_BYTES

JSON_BODY_BYTES = 1024 * 1024


class RequestBodyLimit:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        root = scope.get("root_path", "").rstrip("/")
        if root and (path == root or path.startswith(root + "/")):
            path = path[len(root):]
        if not path.startswith("/v1/"):
            return await self.app(scope, receive, send)
        limit = MAX_PHOTO_BYTES if path.rstrip("/") == "/v1/reports/photo" else JSON_BODY_BYTES
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                response = JSONResponse({"detail": "Request body exceeds limit"}, status_code=413)
                return await response(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay() -> dict:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
