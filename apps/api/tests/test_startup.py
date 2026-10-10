"""Tests for automated startup orchestration:
migrations, inventory seeding, snapshot priming.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from floodroute.startup import main, run_startup


def test_startup_orchestration_full_flow(monkeypatch):
    """Test full startup orchestration runs migrations, seeds, primes snapshots."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("FLOODROUTE_OPERATOR_TOKENS", json.dumps({"op-alpha": "secret-key-12345"}))

    mock_conn = MagicMock()
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn

    with (
        patch("floodroute.startup.migrate") as mock_migrate,
        patch("floodroute.startup.psycopg.connect", mock_connect),
        patch("floodroute.startup.seed_inventory") as mock_seed,
        patch("floodroute.startup.generate_city_closure_snapshot") as mock_snapshot,
    ):
        mock_migrate.return_value = ["0001_init.sql", "0002_roles_and_audit.sql"]
        mock_seed.return_value = MagicMock(
            city="bengaluru",
            city_id=1,
            total_candidates=5383,
            inserted_segments=0,
            inserted_static=0,
            matched_hotspots=0,
            by_structure={},
        )
        mock_snapshot.return_value = {"type": "FeatureCollection", "features": []}

        summary = run_startup()

        # Migrations called
        mock_migrate.assert_called_once_with("postgresql://test:test@localhost:5432/test")
        assert summary["migrations_applied"] == ["0001_init.sql", "0002_roles_and_audit.sql"]

        # Inventory seeding called with if_empty=True for Bengaluru
        mock_seed.assert_called_once_with(mock_conn, city="bengaluru", if_empty=True)

        # Snapshot priming called for cities / vclasses
        assert mock_snapshot.call_count >= 1

        # Operator tokens diagnosed as active
        assert summary["operator_tokens_configured"] is True
        assert summary["operator_token_count"] == 1


def test_startup_orchestration_missing_operator_tokens(monkeypatch):
    """Test that missing operator tokens are noted but do not halt startup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.delenv("FLOODROUTE_OPERATOR_TOKENS", raising=False)

    mock_conn = MagicMock()
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn

    with (
        patch("floodroute.startup.migrate") as mock_migrate,
        patch("floodroute.startup.psycopg.connect", mock_connect),
        patch("floodroute.startup.seed_inventory") as mock_seed,
        patch("floodroute.startup.generate_city_closure_snapshot"),
    ):
        mock_migrate.return_value = []
        mock_seed.return_value = MagicMock(
            city="bengaluru",
            city_id=1,
            total_candidates=5383,
            inserted_segments=5383,
            inserted_static=5383,
            matched_hotspots=233,
            by_structure={"underpass": 100},
        )

        summary = run_startup()
        assert summary["operator_tokens_configured"] is False
        assert summary["operator_token_count"] == 0
        assert summary["migrations_applied"] == []


def test_startup_orchestration_invalid_operator_tokens(monkeypatch):
    """Test that malformed operator tokens JSON logs warning and reports unconfigured."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("FLOODROUTE_OPERATOR_TOKENS", "invalid-json-string")

    mock_conn = MagicMock()
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn

    with (
        patch("floodroute.startup.migrate") as mock_migrate,
        patch("floodroute.startup.psycopg.connect", mock_connect),
        patch("floodroute.startup.seed_inventory") as mock_seed,
        patch("floodroute.startup.generate_city_closure_snapshot"),
    ):
        mock_migrate.return_value = []
        mock_seed.return_value = MagicMock(
            city="bengaluru",
            city_id=1,
            total_candidates=5383,
            inserted_segments=0,
            inserted_static=0,
            matched_hotspots=0,
            by_structure={},
        )

        summary = run_startup()
        assert summary["operator_tokens_configured"] is False


def test_startup_snapshot_failure_is_non_fatal(monkeypatch):
    """Snapshot generation failures should be logged and not prevent API startup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.delenv("FLOODROUTE_OPERATOR_TOKENS", raising=False)

    mock_conn = MagicMock()
    mock_connect = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn

    with (
        patch("floodroute.startup.migrate"),
        patch("floodroute.startup.psycopg.connect", mock_connect),
        patch("floodroute.startup.seed_inventory"),
        patch(
            "floodroute.startup.generate_city_closure_snapshot",
            side_effect=RuntimeError("Snapshot error"),
        ),
    ):
        summary = run_startup()
        assert summary["snapshot_errors"] >= 1


def test_startup_main_cli(monkeypatch):
    """Test CLI entrypoint main() runs and exits cleanly."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

    with patch("floodroute.startup.run_startup") as mock_run:
        mock_run.return_value = {
            "migrations_applied": [],
            "operator_tokens_configured": False,
            "operator_token_count": 0,
            "snapshot_errors": 0,
        }
        main()
        mock_run.assert_called_once()
