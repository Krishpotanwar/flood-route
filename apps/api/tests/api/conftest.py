"""Shared fixtures for FastAPI tests."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from floodroute.api.deps import get_db
from floodroute.api.main import create_app


@pytest.fixture
def client(app_db) -> Generator[TestClient, None, None]:
    """TestClient wired to the migrated throwaway database acting as floodroute_app."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: app_db
    with TestClient(app) as c:
        yield c
