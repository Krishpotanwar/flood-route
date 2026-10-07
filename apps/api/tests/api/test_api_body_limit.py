"""Limits apply to streamed bodies before any handler can buffer the request."""

import pytest
from fastapi.testclient import TestClient

from floodroute.api.body_limit import JSON_BODY_BYTES, RequestBodyLimit
from floodroute.api.main import create_app
from floodroute.api.photo import MAX_PHOTO_BYTES


@pytest.mark.parametrize("root_path", ["", "/api"])
def test_chunked_photo_and_unsigned_bot_are_rejected_before_processing(root_path):
    with TestClient(create_app(), root_path=root_path) as client:
        photo = client.post(root_path + "/v1/reports/photo", content=iter([b"x" * (MAX_PHOTO_BYTES + 1)]))
        assert photo.status_code == 413
        bot = client.post(root_path + "/v1/whatsapp/webhook", content=iter([b"x" * (JSON_BODY_BYTES + 1)]))
        assert bot.status_code == 413


@pytest.mark.anyio
async def test_body_limit_stops_consuming_stream_and_does_not_call_handler():
    received = 0
    responses = []

    async def receive():
        nonlocal received
        received += 1
        return {"type": "http.request", "body": b"x" * JSON_BODY_BYTES, "more_body": True}

    async def handler(*_):
        pytest.fail("Oversized request reached the handler")

    async def send(message):
        responses.append(message)

    await RequestBodyLimit(handler)({"type": "http", "path": "/v1/route"}, receive, send)
    assert received == 2
    assert responses[0]["status"] == 413
