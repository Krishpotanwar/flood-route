"""Shared fixtures for FastAPI tests."""

from __future__ import annotations

import json
import socket
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from floodroute.api.deps import get_db
from floodroute.api.main import create_app

PRIMARY_TOKEN = "test-only-primary-operator-token-1234567890"
SECONDARY_TOKEN = "test-only-secondary-operator-token-1234567890"


@pytest.fixture(autouse=True)
def operator_registry(monkeypatch):
    monkeypatch.setenv(
        "FLOODROUTE_OPERATOR_TOKENS",
        json.dumps(
            {
                "op-primary": PRIMARY_TOKEN,
                "op-secondary": SECONDARY_TOKEN,
            }
        ),
    )
    # All outbound HTTP in these tests is mocked. Keep DNS deterministic too.
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, port, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", port))
        ],
    )


@pytest.fixture
def client(app_db) -> Generator[TestClient, None, None]:
    """TestClient wired to the migrated throwaway database acting as floodroute_app."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    with TestClient(
        app,
        headers={
            "Authorization": f"Bearer {PRIMARY_TOKEN}",
            "X-FloodRoute-Co-Signature": SECONDARY_TOKEN,
        },
    ) as c:
        yield c


@pytest.fixture
def anonymous_client(app_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    with TestClient(app) as c:
        yield c
