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

### Checkpoint 11: Backtesting Harness & Model Calibration Evaluation
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/score/backtest.py`:
    - Contingency table calculation: Probability of Detection (POD / Hit Rate), False Alarm Ratio (FAR), Critical Success Index (CSI / Threat Score), and overall accuracy. Guarded against division by zero.
    - Probabilistic calibration metrics: Brier score ($\frac{1}{N}\sum (p_i - o_i)^2$) and Mean Absolute Error (MAE) for inundation depth.
    - Ground-truth evaluation against `observed_event` table (PRD FR-R9, TRD 15).
    - Breakdowns by forecast horizon (0, 30, 60, 120 min), vehicle class, label tier (`high`, `medium`, `low`), and source kind (`traffic_police`, `control_room`, `news`, `crowd`, `sensor`).
    - Seeded benchmark historical flood events from documented Bengaluru storms (September 2022 and May 2025 across Bellandur ORR, Silk Board, Windsor Manor, K.R. Circle, Domlur).
  - Integrated `backtest` subcommand into `python -m floodroute.score backtest`.
  - Added 6 thorough tests in `apps/api/tests/score/test_score_backtest.py`.
  - Reached 618 passing tests (100% pass rate in 33s) with 0 ruff lint errors.

### Checkpoint 12: Control Room Situation Board Console & Static Asset Serving
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/api/static/console.html` and static asset serving:
    - Operator Situation Board: live top strip with real-time health pings, database connectivity, and data staleness indicators.
    - Interactive controls: vehicle class selector (`car`, `two_wheeler`, `ambulance`, `heavy`), forecast horizon scrubber (Now, +30m, +60m, +120m), and theme selector (`light`, `dark`, `hc`, `sunlight`).
    - Key metrics dashboard: Monitored segments count, active road closures, risky segments count, and citizen reports counter.
    - Incident list: sorted priority queue of monitored road segments with risk chips, probability of unusability, and depth estimates.
    - Interactive Leaflet / OpenStreetMap map: live rendering of Bengaluru road corridors and real-time GeoJSON closure feeds from `/v1/feed/closures.geojson`.
    - Operator closure modal: human road closure override with mandatory two-operator verification calling `POST /v1/overrides`.
    - Citizen flood report modal: simulation tool submitting crowd waterlogging observations directly to `POST /v1/reports`.
    - Strict compliance with `DESIGN.md` tokens, zero em-dashes in UI copy, and safety invariant (never uses "safe" label).
  - Mounted `/static` directory in `main.py` and routed `GET /` and `GET /console` to serve the interactive Console.
  - Added unit test in `apps/api/tests/api/test_api_console.py`.
  - Reached 619 passing tests (100% pass rate in 33.8s) with 0 ruff lint errors.

### Checkpoint 13: Photo Evidence Sanitization Pipeline & DPDP Act 2023 Compliance
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/api/photo.py`:
    - Privacy-safe photo processing satisfying DPDP Act 2023 (Section 8, FR-M4).
    - EXIF metadata stripping: completely purges GPS coordinates, camera/device serial numbers, timestamps, and orientation tags.
    - Resolution normalization: downsizes oversized images to max 1600px dimension preserving aspect ratio.
    - Pure RGB re-encoding: discards color profile and auxiliary channels, re-encoding clean JPEG with quality 85.
    - Content-addressed reference: deterministic SHA-256 digest reference `ph_<hash>.jpg` (24 hex characters).
    - Hard limit enforcement: 5 MB file size limit and format allowlist (`JPEG`, `PNG`, `WEBP`, `MPO`).
  - Added photo upload and retrieval endpoints to `apps/api/floodroute/api/routes/reports.py`:
    - `POST /v1/reports/photo`: accepts raw image stream, strips EXIF, stores sanitized file, returns `photo_ref`, dimension, and size.
    - `GET /v1/reports/photo/{photo_ref}`: serves sanitized JPEG with security headers (`Cache-Control: public, max-age=86400, immutable`, `X-Content-Type-Options: nosniff`), and strict path traversal protection.
  - Linked photo evidence with crowd flood reports via optional `photo_ref` in `ReportCreate` and `evidence.uri`.
  - Added Pillow dependency in `apps/api/pyproject.toml` and updated `.gitignore` for photo caches.
  - Added 4 comprehensive tests in `apps/api/tests/api/test_api_photo.py`.
  - Reached 623 passing tests (100% pass rate in 36.8s) with 0 ruff lint errors.

### Checkpoint 14: Live Navigation Rerouting Endpoint & Pure Trip State Decisioning
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `POST /v1/route/reroute` endpoint in `apps/api/floodroute/api/routes/route.py` exposing `floodroute.route.reroute.decide` for mobile clients and navigation apps (TRD 7.4, FR-RT5 to FR-RT7).
  - Defined request and response Pydantic models in `apps/api/floodroute/route/models.py`:
    - `RerouteRequest`: current vehicle position, destination, remaining route edges with geometry and turn-off availability, vehicle class, profile, and client trip state memory.
    - `TripStatePayload`: persistent memory between position ticks containing `last_suggestion_at`, `baseline_band`, and `closed_at` timestamps for recently closed road segments.
    - `RerouteResponse`: decision action (`keep`, `suggest`, `hold`), reason strings localized via `explain.say`, machine-readable code, warning flag, current route risk state, and complete `RouteOut` suggested detour.
  - Extended `Plan` dataclass in `apps/api/floodroute/route/validate.py` with `accepted: Assessment | None` preserving backward compatibility while providing direct access to the validated candidate assessment.
  - Enforced key safety invariants:
    - Never uses "safe" label in any client responses or explanations.
    - Preserves commit zone hold (`hold`, `commit_zone`) when water is within 300m and no junction permits turning off.
    - Enforces 2.5 min dwell time (`dwell`) between reroute suggestions while continuing to warn of flooding ahead.
    - Rejects candidate routes entering segments closed within the last 15 minutes (`recently_closed`).
  - Added 7 comprehensive tests in `apps/api/tests/api/test_api_reroute.py`.
  - Reached 630 passing tests (100% pass rate in 37.8s) with 0 ruff lint errors.

### Checkpoint 15: Scheduled Background Worker Loop & Data Retention Engine
- **Status**: Completed
- **Actions & Findings**:
  - Implemented `apps/api/floodroute/worker.py` orchestrating continuous background execution (TRD sections 3, 5, 13, 19):
    - Multi-cadence scheduler tracking timestamps across independent tasks:
      - SACHET alert feed ingestion (every 5 min)
      - MET Norway weather forecast ingestion (hourly)
      - Shadow scoring cycle evaluation (every 5 min)
      - Data retention cleanup (daily)
    - `prune_retention`: executes age-based deletes on `route_decision` table (> 365 days retention per TRD 13), purges expired sensor/crowd evidence past TTL from `evidence` table (FR-M3), and cleans resolved/rejected crowd reports (> 90 days DPDP compliance).
    - Graceful process termination with signal handlers for SIGINT and SIGTERM.
    - CLI entrypoint: `python -m floodroute.worker [--once] [--db-url ...]` for both container daemons and cron/Kubernetes jobs.
  - Refined Valhalla route requests in `apps/api/floodroute/route/valhalla.py`: converted departure timestamps to UTC before serializing `date_time`, fixing silent overlay drops detected during Spike S1.
  - Added 4 comprehensive tests in `apps/api/tests/test_worker.py`.
  - Reached 634 passing tests (100% pass rate in 35.9s) with 0 ruff lint errors.

### Checkpoint 16: Citizen React PWA, Gesture BottomSheet & FastAPI Mounting
- **Status**: Completed
- **Actions & Findings**:
  - Implemented mobile-first Citizen React PWA in `apps/citizen/`:
    - `BottomSheet.tsx`: pointer-event gesture interaction with velocity detection (|v| >= 0.3 px/ms), distance thresholds, and 3 snap heights:
      - Collapsed: 96px (`6rem`)
      - Half: 50% dynamic viewport height (`50dvh`)
      - Expanded: 90% dynamic viewport height (`90dvh`)
      - Fluid spring transition curve `cubic-bezier(0.16, 1, 0.3, 1)` and ARIA accessibility.
    - `Header.tsx`: live health indicator dot, report modal launcher, language switcher (en, hi, kn, ta, te), and theme selector.
    - `RouteForm.tsx`: vehicle class selector (two-wheeler, car) with preset Bengaluru origin and destination coordinates.
    - `RouteCard.tsx`: plain-language reasoning, ETA, monitored segment count, and worst state chip badge ("Clear", "Watch", "Risky", "Impassable").
    - `LiveSimulator.tsx`: simulated turn-by-turn navigation ticks interacting with live reroute engine (`POST /v1/route/reroute`), displaying detour suggestions and commit-zone holds.
    - `ReportModal.tsx`: crowd waterlogging reporting with camera photo capture and EXIF metadata sanitization via `POST /v1/reports/photo`.
    - `App.tsx` and `main.tsx`: complete state coordination, theme synchronization via `<html data-theme="...">`, offline fallback routing, and report queueing.
  - Package build:
    - Added `"exports": { "./tokens.css": "./tokens.css" }` to `packages/ui/package.json`.
    - Configured relative base (`base: "./"`) in `apps/citizen/vite.config.ts`.
    - Production bundle compiled with Vite in ~650ms to `apps/citizen/dist`.
  - Backend integration:
    - Mounted `/app` static files in `apps/api/floodroute/api/main.py` serving the citizen SPA with HTML fallback.
    - Added 3 unit tests in `apps/api/tests/api/test_api_citizen.py`.
  - Verification:
    - 637 passing tests across `apps/api/tests/` (100% pass rate in 36.3s).
    - 0 ruff lint errors across all Python code.
    - All WCAG 2.x contrast and color-vision token checks pass (`pnpm --filter @floodroute/ui check`).
    - Zero em-dashes and strict safety invariant maintained.

### Checkpoint 17: Performance Benchmark Suite, Connection Pooling & Vehicle Stalling Calibration
- **Status**: Completed
- **Actions & Findings**:
  - **Performance Benchmark Harness (`tools/benchmark.py`)**:
    - Created asynchronous multi-scenario load testing suite with statistical percentiles (p50, p90, p95, p99, RPS).
    - Benchmarked against TRD target SLOs: `/v1/health` (<50ms), `/v1/risk` (<100ms), `/v1/route` (<500ms car, <300ms ambulance), `/v1/route/reroute` (<200ms), `/v1/feed/closures.geojson` (<150ms).
  - **Database Connection Pooling (`apps/api/floodroute/api/deps.py`)**:
    - Replaced per-request connection creation with `psycopg_pool.ConnectionPool(min_size=10, max_size=50, open=True)`.
    - Eliminated cold TCP/SSL setup latency under concurrency; dropped endpoint p50 latencies from 35ms+ down to 10-18ms.
  - **Spatial Risk Indexing (`0004_perf_indexes.sql`)**:
    - Added composite index `idx_segment_risk_query` on `segment_risk (vclass, horizon_min, segment_id)`.
    - Eliminated sequential scans across 86k+ partition rows during bbox spatial joins, reducing `/v1/risk` query duration by over 50%.
  - **Benchmark Validation Results (10 concurrent clients, 50 requests/scenario)**:
    - `GET /v1/health`: 661.7 RPS, p50 = 12.82ms, p95 = 21.40ms (SLO: <50ms) -> PASS
    - `GET /v1/risk (Central BBox)`: 254.6 RPS, p50 = 24.77ms, p95 = 91.02ms (SLO: <100ms) -> PASS
    - `GET /v1/risk (Silk Board Corridor)`: 742.2 RPS, p50 = 11.75ms, p95 = 18.89ms (SLO: <100ms) -> PASS
    - `POST /v1/route (Standard Car)`: 398.4 RPS, p50 = 18.45ms, p95 = 51.45ms (SLO: <500ms) -> PASS
    - `POST /v1/route (Ambulance Profile)`: 519.1 RPS, p50 = 16.65ms, p95 = 26.68ms (SLO: <300ms) -> PASS
    - `POST /v1/route/reroute (Tick)`: 562.5 RPS, p50 = 17.05ms, p95 = 19.11ms (SLO: <200ms) -> PASS
    - `GET /v1/feed/closures.geojson`: 1036.8 RPS, p50 = 7.45ms, p95 = 15.45ms (SLO: <150ms) -> PASS
  - **Vehicle Depth Stalling Research Catalog (`docs/research/07-vehicle-depth-stalling-thresholds.md`)**:
    - Completed exhaustive engineering study on vehicle ground clearances, air intakes, exhaust heights, hydrostatic locking, and hydrodynamic drag instability ($D \cdot V$).
    - Adapted Pregnolato speed-reduction curves for Indian heterogeneous traffic conditions.
    - Compiled empirical flood observations from Bengaluru (2022/2025), Chennai (2015/2023), and Mumbai municipal subway closure protocols.
  - **Ambulance Profile Threshold Calibration**:
    - Calibrated `ambulance` vehicle profile in `data/config/scoring.v0.json` from `caution_cm: 15.0, unusable_cm: 20.0` to `caution_cm: 20.0, unusable_cm: 35.0` based on Indian 108 emergency fleet specifications (Force Traveller ladder-frame GC 210mm, air intake >680mm; Tata Winger GC 180mm).
    - Resolved the inversion defect where small hatchbacks (30cm unusable) were routed through water that blocked emergency ambulances (20cm).
    - Updated `apps/api/tests/score/test_score_config.py` and dynamic migration ordering in `apps/api/tests/db/test_db_roles.py`.
  - **Verification**:
    - 640 passing tests across `apps/api/tests/` (100% pass rate in 37.1s).
    - 0 ruff lint errors across all Python code.
    - Vite production bundle compiled in 654ms with 0 TypeScript errors.
    - Zero em-dashes and strict safety invariant maintained.

### Checkpoint 18: MapLibre Interactive Map View, Polyline Engine & Real-Time Closures Feed
- **Status**: Completed
- **Actions & Findings**:
  - **Valhalla Polyline Engine & Interpolation (`apps/citizen/src/utils/polyline.ts`)**:
    - Implemented high-precision (factor 1e6) polyline encoder and decoder mapping Valhalla geometry strings directly to GeoJSON `[lon, lat]` coordinates.
    - Added bounding box calculator (`calculateBounds`) for automatic viewport framing with bottom-sheet-aware padding.
    - Implemented linear distance path interpolator (`sampleCoordinateAlongLine`) mapping fractional navigation progress (0.0 to 1.0) to smooth vehicle coordinates.
    - Created unit test suite in `apps/citizen/src/utils/polyline.test.ts` with 5 passing tests under Node 22 native runner.
  - **MapLibre Interactive Map Component (`apps/citizen/src/components/MapView.tsx`)**:
    - Integrated MapLibre GL JS with theme-reactive base styles (Carto Dark for dark and high-contrast modes; OpenStreetMap / Carto Voyager for light modes).
    - Added multi-layer GeoJSON route visualization with contrast dark casing and foreground line colored by risk band (clear: emerald, watch: amber, risky: orange, impassable: crimson).
    - Rendered dashed polyline overlay for suggested detour alternatives (`rerouteData.suggested_route`).
    - Added custom HTML pin markers for Origin (A, emerald) and Destination (B, blue).
    - Added pulsing vehicle location marker (`📍`) that animates smoothly along the route during live trip simulation.
    - Integrated live road closures overlay querying `GET /v1/feed/closures.geojson?vclass=car`, rendering active impassable road closures directly on the map canvas.
    - Added floating touch action controls: Recenter (targeting route bounds), Hotspots / Closures toggle, and Zoom (+ / -).
    - Built comprehensive SVG vector fallback that renders road grid, route polyline, origin/dest pins, and vehicle marker if WebGL context is unavailable.
  - **Layout & BottomSheet Integration (`apps/citizen/src/App.tsx` & `apps/citizen/vite.config.ts`)**:
    - Placed `MapView` as the primary hero canvas behind the gesture-driven `BottomSheet`.
    - Maintained 3 ergonomic snap points (collapsed 96px, half 50dvh, expanded 90dvh).
    - Configured manual vendor chunking for `maplibre-gl` in Vite build (`maplibre-vendor.js`), keeping core application bundle compact (245 KB minified, 76 KB gzipped).
  - **Verification**:
    - All 5 TypeScript polyline tests pass (`npm test` in `apps/citizen`).
    - Production bundle compiled with Vite in 1.78s with 0 errors.
    - All 640 API tests pass (`uv run pytest` in `apps/api`, 100% pass rate).
    - 0 ruff lint errors across all Python modules.
    - All WCAG 2.x contrast and color-vision token checks pass (`pnpm --filter @floodroute/ui check`).
    - Zero em-dashes and strict safety invariant maintained.

---



