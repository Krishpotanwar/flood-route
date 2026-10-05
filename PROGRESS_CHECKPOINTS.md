# FloodRoute Local Work Progress & Checkpoints Log

This document tracks local execution, verification, fixes, and ongoing progress after inheriting the unreviewed agent snapshot from `claude/floodroute-project-plan-g5cntf` (commit `c5e9750`).

---

## Session Initialization & Context

- **Source Git Remote**: `https://github.com/Krishpotanwar/flood-route`
- **Branch**: `claude/floodroute-project-plan-g5cntf` (mirrored to local branch `main` as well)
- **Local Workspace**: `/Users/krish/Desktop/study/project/flood-route`
- **Starting Commit**: `c5e9750` ("wip: final snapshot of agent work, agents stopped mid-run")
- **Initial State**:
  - Routing module (`680059b`) was previously reviewed and tested (163 tests passing).
  - Unreviewed snapshots:
    - Database layer (`apps/api/floodroute/db/`, migrations 0001-0003)
    - Ingestion layer (`apps/api/floodroute/ingest/`, SACHET CAP 1.2, MET Norway)
    - Scoring engine (`apps/api/floodroute/score/`, evidence, config, state, replay)
    - Hotspot inventory (`apps/api/floodroute/inventory/`, OSM extract, geocoding)
    - UI tokens (`packages/ui/`)
    - Outreach docs (`docs/outreach/`)
    - Valhalla spike (`tools/spikes/s1_valhalla/`)

---

## Checkpoint Log

### Checkpoint 1: Repository & Environment Setup
- **Status**: Completed
- **Actions**:
  - Cloned mirror of `https://github.com/Krishpotanwar/flood-route` into local workspace before remote repository deletion.
  - Initialized full git working tree at `/Users/krish/Desktop/study/project/flood-route` on branch `claude/floodroute-project-plan-g5cntf` and created matching `main` branch.
  - Created Python virtual environment at `apps/api/.venv` using Python 3.12.
  - Installed project in editable mode with development dependencies (`fastapi`, `uvicorn`, `psycopg[binary]`, `httpx`, `pytest`, `ruff`).

### Checkpoint 2: Syntax & Lint Cleanliness
- **Status**: Completed
- **Issues Discovered**:
  - `apps/api/floodroute/ingest/sachet.py`: Line 1 had six double-quotes (`""""""`) instead of triple-quotes (`"""`), prematurely closing the docstring and causing Python 3.12 syntax errors on the date `2026-10-05` (leading zero parsed as octal integer literal).
  - `apps/api/tests/score/score_helpers.py`, `test_score_config.py`, `test_score_evidence.py`, `test_score_model.py`, `test_score_state.py`: Unsorted imports, `zip()` instead of `itertools.pairwise()`, unused unpack `r1`.
- **Fixes Applied**:
  - Corrected docstring in `sachet.py`.
  - Ran `ruff check --fix` and addressed all remaining lint issues.
  - `ruff check floodroute tests` now passes with 0 errors.
### Checkpoint 3: PostGIS Database & Test Suite Verification
- **Status**: Completed
- **Actions**:
  - Started PostgreSQL 16 + PostGIS 3.4 in Docker container `floodroute-test-pg` on port 54329.
  - Installed `osmium` into virtualenv to satisfy OSM extractor tests.
  - Ran full test suite across DB migrations, roles, schema, spatial tables, and unit tests.
  - **Result**: All 589 test cases passed (100% pass rate).
  - Applied migrations `0001_init.sql`, `0002_roles_and_audit.sql`, and `0003_observed_event.sql` to persistent database `floodroute`.

### Checkpoint 4: Legal & Licensing Audit (ODbL & MET Norway)
- **Status**: Completed
- **Actions & Findings**:
  - **ODbL 1.0 Attribution**: Added `data/inventory/NOTICE.md` giving explicit OpenStreetMap contributor credit and documenting the collective database boundary architecture (storing proprietary risk scores in distinct tables from OSM geometries).
  - **MET Norway API Licensing**: Subagent research confirmed `api.met.no` is licensed under CC BY 4.0 and NLOD 2.0, explicitly allowing commercial use with credit ("Data from MET Norway"). Documented operational rules (max 20 req/s, <=4 decimal places, User-Agent with contact info).
  - Updated `docs/outreach/data-terms-tracker.md` with full MET Norway terms.

### Checkpoint 5: Valhalla Spike S1 Evaluation & Routing Fix
- **Status**: Completed
- **Evaluation & Decision**: **GO on Valhalla for Phase 0 / R1**.
  - 100% success rate on dynamic closures and vehicle class isolation across 3 instances with ~478 MB PSS shared memory.
  - Sub-10ms in-place publication for 1,000 edges.
  - Identified critical bug in `apps/api/floodroute/route/valhalla.py`: `request_body` omitted `date_time`, causing Valhalla 3.9.0 to ignore live overlays/closures.
  - Fixed `valhalla.py` to pass `date_time` (either ISO timestamp or `type: 0` for current). All 163 route tests re-verified.

### Checkpoint 6: Live Ingestion Adapter Testing
- **Status**: Completed
- **Actions & Findings**:
  - Executed `floodroute.ingest sachet --once` against live NDMA/C-DOT CAP RSS feeds. Successfully ingested live alerts from Andhra Pradesh SDMA, Karnataka SNDMC, and IMD Chennai into `official_alert` with `source_health` tracking.
  - Seeded sample Bengaluru zone and executed `floodroute.ingest metno --once`. Successfully ingested 63 hourly rainfall forecast rows from MET Norway into `rain_fcst`.

### Checkpoint 7: Scoring DB Bridge & Integration Tests
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/score/db.py` providing `load_run_input`, `persist_run_result`, and `execute_score_run`.
  - Enforced `SUPPORTED_VCLASSES = ('two_wheeler', 'car', 'ambulance', 'heavy')` matching database check constraints (`0001_init.sql`).
  - Implemented JSONB serialization for audit log state change tracking (`before`/`after` payloads).
  - Verified two-lock security architecture on `audit_log`: permission denial under `floodroute_app` role and trigger refusal under table owner.
  - Implemented 6 thorough integration tests in `apps/api/tests/score/test_score_db.py`.

### Checkpoint 8: FastAPI v1 Application & Test Suite
- **Status**: Completed
- **Actions & Findings**:
  - Implemented complete v1 HTTP API (`apps/api/floodroute/api/`):
    - `deps.py`: Database pool dependency (`set role floodroute_app`), configs, and segment/risk lookups.
    - `routes/health.py`: `GET /v1/health` with live DB ping, source health lags, and model version.
    - `routes/risk.py`: `GET /v1/risk` with bbox spatial query (`ST_Intersects` on `ST_MakeEnvelope`), horizon, and vehicle class filtering. Enforces safety invariant (never returns "safe").
    - `routes/route.py`: `POST /v1/route` wired to `floodroute.route.validate.plan` with arrival-time validation loop and `route_decision` audit logging.
    - `routes/reports.py`: `POST /v1/reports` for citizen reports with spatial map-matching within 100m to candidate segments.
    - `routes/overrides.py`: `POST /v1/overrides` for human operator road closures/reopens with two-operator verification and audit logging.
    - `routes/feed.py`: `GET /v1/feed/closures.geojson` returning standard GeoJSON FeatureCollection of impassable/risky segments.
    - `main.py`: `create_app()` factory with CORS middleware.
  - Added 12 comprehensive integration tests in `apps/api/tests/api/test_api_*.py`.
  - Reached 607 passing tests (100% pass rate in 32s) with 0 ruff lint errors.

### Checkpoint 9: Inventory Seeding Pipeline & Test Suite
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/inventory/seed.py`:
    - `candidate_id_to_segment_id`: Deterministic mapping from OSM candidate IDs (including sub-features like `8680571-x1`) to positive 63-bit integers (`bigint`), zero collisions across full municipal extracts.
    - `load_hotspot_counts`: Maps BBMP and traffic police hotspot matches from matched CSV files to candidates.
    - `ensure_city_zone`: Creates base multi-polygon bounding zone for municipal areas.
    - `seed_inventory`: High-throughput batched upsert pipeline loading candidate GeoJSON and snapped hotspots into `segment` and `segment_static`.
  - Added 5 integration/unit tests in `apps/api/tests/inventory/test_inventory_seed.py`.
  - Full test suite passed (612 tests passing, 0 ruff lint errors).

### Checkpoint 10: End-to-End Bengaluru Shadow Scoring & Live Verification
- **Status**: Completed
- **Actions & Findings**:
  - Seeded complete Bengaluru candidate inventory:
    - 5,383 road segments (`assessed = true`).
    - 5,383 static risk priors (1,801 dips, 1,558 low bridges, 1,232 culverts, 609 underpasses, 183 unmapped).
    - 233 historical hotspot matches (134 unique segments with up to 6 historical flood events).
  - Config adjustment: added `"metno"` to `source_priority` in `data/config/scoring.v0.json` for live NWP forecast matching.
  - Executed baseline shadow scoring run (`execute_score_run`):
    - Evaluated and generated 86,128 segment risk records (5,383 segments x 4 classes x 4 horizons).
    - Archived 86,128 partition rows in `segment_risk_history` and logged state transitions in `audit_log`.
  - Verified live FastAPI endpoints against real Bengaluru database:
    - `GET /v1/health`: 200 OK with live DB ping, model version `v0.0.1`, active `sachet` and `metno` source health lags.
    - `GET /v1/risk`: 200 OK returning 361 assessed flood-vulnerable segments in central Bengaluru bounding box within milliseconds; strict safety invariant observed (no "safe" label).
    - `POST /v1/reports`: 201 Created with citizen knee-deep flood report dynamically snapped within 100m to 80 Feet Road culvert (segment `2201617750100158755`), automatically generating `report` and `evidence` entries. Re-scoring verified two-wheeler unusable probability immediately escalated.
    - `POST /v1/overrides`: 201 Created with two-operator closure override, verified across audit log and immediate transition to `impassable` across all vehicle classes and horizons.
    - `GET /v1/feed/closures.geojson`: 200 OK delivering RFC 7946 GeoJSON FeatureCollection with live segment geometry and impassability properties.

---
