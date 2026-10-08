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

### Checkpoint 19: Advanced Model Calibration & Multi-Horizon Backtest Evaluation Engine
- **Status**: Completed
- **Actions & Findings**:
  - **TRD 15 Model Calibration & Statistical Decomposition (`apps/api/floodroute/score/backtest.py`)**:
    - Implemented Area Under the ROC Curve (`compute_roc_auc`) via trapezoidal integration over sorted discrimination thresholds, validating model ranking performance against ground-truth flood observations.
    - Implemented Brier Score Decomposition (`decompose_brier_score`) based on Murphy (1973), separating total quadratic error into Reliability (calibration error: differences between forecast probabilities and observed relative frequencies), Resolution (ability to discriminate event from non-event instances), and Uncertainty (inherent climatological base-rate variance).
    - Added Reliability Diagram Generator (`compute_reliability_diagram`) producing binned probability intervals (0.0 to 1.0) with sample counts, mean predicted probability, and empirical event frequencies for visualization.
    - Added Threshold Optimization Sweep (`compute_threshold_sweep`) evaluating cutoffs from 0.05 to 0.80, computing full contingency metrics (Hits, Misses, False Alarms, Correct Negatives, POD, FAR, CSI / Threat Score, Accuracy, and F1-score) to find the optimal decision boundary maximizing Critical Success Index.
    - Implemented Multi-Horizon Matrix Audit (`run_full_calibration_audit`) running a comprehensive 4x4 evaluation across all 4 vehicle classes (two_wheeler, car, ambulance, heavy) and all 4 forecast horizons (0m, 30m, 60m, 120m) against verified historical flood events.
  - **CLI Instrumentation (`apps/api/floodroute/score/__main__.py`)**:
    - Added `--seed-benchmark` CLI flag to populate historical ground-truth waterlogging records from Bengaluru municipal flood benchmarks.
    - Added `--audit-matrix` CLI option running the complete 16-cell calibration audit across all vehicle profiles and forecast horizons.
  - **Verification & Testing**:
    - Added 4 new calibration test cases to `apps/api/tests/score/test_score_backtest.py` (`test_compute_roc_auc`, `test_decompose_brier_score_and_diagram`, `test_compute_threshold_sweep`, and `test_db_backtest_calibration_and_audit`).
    - Total API test suite expanded to 644 passing tests (100% pass rate in 38.5s).
    - 0 ruff lint errors across all Python code.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 20: Enterprise Fleet Webhooks, Route Material-Change Watch & OASIS CAP 1.2 Emergency Feed
- **Status**: Completed
- **Actions & Findings**:
  - **Database Migration (`0005_webhooks_and_watch.sql`)**:
    - Created `webhook_subscription` table supporting multi-tenant event notifications with HMAC secrets and URL validation.
    - Created `webhook_delivery` table tracking delivery attempts, HTTP status codes, latencies, payloads, and error logs.
    - Created `route_watch` table storing route decisions, monitored segments, baseline states, notification channels (FCM, WhatsApp, SMS, webhook), and alert counts.
  - **OASIS CAP 1.2 XML Feed (`GET /v1/feed/cap.xml`)**:
    - Implemented standard Common Alerting Protocol v1.2 XML generator compliant with OASIS standard (`urn:oasis:names:tc:emergency:cap:1.2`), matching SACHET (NDMA) and SDMA feed specifications.
    - Emits structured `<alert>` documents with `<info>` blocks containing event codes (`SAME / FLW`), urgency, severity (`Extreme` for impassable, `Severe` for risky), certainty (`Observed`), and localized descriptions.
    - Represents road segment geometries using CAP `<circle>` elements centered on segment midpoints with 150m impact radius, alongside road class and depth parameters.
  - **Enterprise Webhook Subsystem (`apps/api/floodroute/webhook/`)**:
    - Implemented HMAC-SHA256 cryptographic signing in `signing.py`, emitting `X-FloodRoute-Signature-256`, `X-FloodRoute-Event-Id`, and `X-FloodRoute-Timestamp` headers.
    - Built asynchronous event dispatcher in `dispatcher.py` persisting execution audit records to `webhook_delivery`.
    - Created API endpoints in `apps/api/floodroute/api/routes/webhooks.py` (`POST /v1/webhooks`, `GET /v1/webhooks`, `DELETE /v1/webhooks/{id}`, `POST /v1/webhooks/{id}/test`, and `GET /v1/webhooks/{id}/deliveries`).
  - **Route Material-Change Watch Engine (`apps/api/floodroute/route/watch.py`)**:
    - Built route watch subscription manager linking planned routes (`POST /v1/routes/{id}/watch`, `GET /v1/routes/{id}/watch`, `DELETE /v1/routes/{id}/watch`).
    - Implemented pure material change detection logic: triggers when a segment on a watched route becomes Impassable or when its risk band elevates.
    - Enforced strict alert fatigue controls: rate-limited to a maximum of 3 notifications per user/route per hour.
  - **Background Worker Loop Integration (`apps/api/floodroute/worker.py`)**:
    - Wired route watch evaluations and `segment.state_changed` webhook broadcasts directly into the 5-minute scoring loop.
    - Added automatic deactivation of expired watches to the daily retention prune cycle.
  - **Verification & Testing**:
    - Added 10 comprehensive tests across `test_api_feed.py`, `test_api_webhooks.py`, `test_route_watch.py`, and `test_api_watch.py`.
    - Total API test suite expanded to 654 passing tests (100% pass rate in 39.7s).
    - 0 ruff lint errors across all Python code.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 21: Citizen WhatsApp Bot & DLT-Compliant Multilingual SMS Alert Engine
- **Status**: Completed
- **Actions & Findings**:
  - **TRAI DLT SMS Template & Budget Engine (`apps/api/floodroute/bot/sms.py`)**:
    - Implemented strict single-segment SMS character budget enforcement: 70 characters for Indic Unicode scripts (Kannada, Hindi, Tamil, Telugu) and 160 characters for standard GSM-7 Latin.
    - Registered pre-approved DLT templates (`KN_ROAD_CLOSED`, `KN_WATERLOGGED_WARNING`, `KN_REROUTE_SUGGEST`, `HI_ROAD_CLOSED`, `HI_WATERLOGGED_WARNING`, `HI_REROUTE_SUGGEST`, `EN_ROAD_CLOSED`, `EN_WATERLOGGED_WARNING`, `EN_REROUTE_SUGGEST`) with associated Entity, Header, and Template IDs.
    - Built template rendering engine with variable slot interpolation (`{#var#}`) and automated length validation preventing accidental multi-segment billing or TRAI gateway rejection.
    - Built auto-truncation logic for long street and landmark names to preserve single-segment delivery.
  - **WhatsApp Business Cloud API Bot (`apps/api/floodroute/bot/whatsapp.py`)**:
    - Built Meta Cloud API webhook verification handshake responder (`GET /v1/whatsapp/webhook` with `hub.mode`, `hub.verify_token`, and `hub.challenge`).
    - Implemented conversational intent processor for incoming text messages, quick-reply interactive buttons, and geolocation payloads (`POST /v1/whatsapp/webhook`).
    - Built spatial location check using PostGIS (`ST_DWithin` 1500m) to inspect nearest underpasses and roads, returning localized waterlogging status with estimated depths and detour advice.
    - Added multilingual support with native Kannada (kn), Hindi (hi), and English (en) responses and persistent user session memory (`UserSession`).
    - Added vehicle clearance profile selection (`two_wheeler`, `car`, `ambulance`) tailoring passability advice to vehicle ground clearance.
    - Implemented city-wide flood summary queries (`status`, `rain`, `flood`).
  - **API Endpoints (`apps/api/floodroute/api/routes/bot.py`)**:
    - Created `GET /v1/whatsapp/webhook` and `POST /v1/whatsapp/webhook` mounted directly in the main FastAPI application.
    - Created `GET /v1/sms/templates` and `POST /v1/sms/render` for dispatchers and fleet integrations to validate outbound SMS text before sending.
  - **Verification & Testing**:
    - Added 15 comprehensive tests across `test_bot_sms.py`, `test_bot_whatsapp.py`, and `test_api_bot.py`.
    - Total API test suite expanded to 669 passing tests (100% pass rate in 40.5s).
    - 0 ruff lint errors across all Python code.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 22: Dispatcher Control Room Suite - Impact Preview, Audit Log Export & Emergency Unit Assignment
- **Status**: Completed
- **Actions & Findings**:
  - **Dispatcher Control Room API Subsystem (`apps/api/floodroute/api/routes/overrides.py`)**:
    - Implemented `POST /v1/overrides/preview`: pre-submission impact evaluation analyzing road hierarchy classification, enforcing two-person verification for arterial roadways (`motorway`, `trunk`, `primary`), counting affected active route watches, and assessing operational impact tier (`low`, `moderate`, `high`).
    - Implemented `GET /v1/overrides`: lists all currently active human overrides.
    - Implemented `DELETE /v1/overrides/{override_id}`: early manual cancellation of active closure overrides, expiring the record and logging an audit event (`override_reverted_{action}`).
    - Implemented `GET /v1/audit`: queries append-only compliance audit trail with filtering by actor and action patterns, supporting both JSON representation and streaming CSV export (`?format=csv`) for legal compliance and post-incident investigation.
  - **Control Room Console UI Enhancements (`apps/api/floodroute/api/static/console.html`)**:
    - Integrated keyboard navigation shortcuts (`J`/`K` to step through monitored incidents, `C` to open closure override modal on selected segment, `A` to open emergency unit assignment, `Esc` to dismiss all active modals).
    - Added closure impact preview card within the override modal, automatically querying `/v1/overrides/preview` on segment input changes and displaying arterial co-signature warnings and impacted subscriber watch counts.
    - Built emergency unit clearance and dispatch modal (`#emergency-modal`) supporting ambulance (Force Traveller) and heavy rescue (Fire Tender) profiles, preset hospital/station facilities, automated clearance corridor checks via `/v1/route`, and unit callsign dispatch confirmation.
    - Built compliance audit log viewer (`#audit-modal`) with live actor/action filtering and direct CSV export download (`/v1/audit?format=csv`).
    - Added forecast lead-time stepping buttons (`<` and `>`) navigating through horizons (0m, 30m, 60m, 120m).
  - **Verification & Testing**:
    - Added 4 new test cases to `apps/api/tests/api/test_api_overrides.py` (`test_override_arterial_requires_second_operator`, `test_list_and_revert_overrides`, `test_override_preview_impact`, `test_query_audit_log_json_and_csv`).
    - Updated `apps/api/tests/api/test_api_console.py` verifying serving of control room console components.
    - Total API test suite expanded to 673 passing tests (100% pass rate in 48.8s).
    - 0 ruff lint errors across all Python code.
    - Citizen frontend tests pass (5/5) and Vite bundle builds cleanly.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 23: Multi-City Onboarding Pipeline - Mumbai & Gurugram Expansion
- **Status**: Completed
- **Actions & Findings**:
  - **Multi-City Inventory Registry (`apps/api/floodroute/inventory/multicity.py` & `__init__.py`)**:
    - Expanded `CITIES` spatial envelopes and `CITY_IDS` registry to include Mumbai (`city_id: 3`, bbox: `72.75, 18.88, 73.05, 19.30`) and Gurugram (`city_id: 4`, bbox: `76.85, 28.32, 77.15, 28.56`).
    - Added `CityMetadata` cataloging municipal operational parameters: state, display name, center coordinates, bounding box, hydrology classification (`tidal_coastal` for Mumbai with Mithi river / Arabian Sea backwater interaction; `arid_ridge_catchment` for Gurugram with Badshahpur drain / Aravalli ridge runoff), and rainfall trigger thresholds (`r_low`).
    - Implemented `load_city_hotspots` with automatic structure inference (`underpass`, `culvert`, `dip`, `low_bridge`) and coordinate bounds validation.
    - Implemented `seed_city_hotspots_into_db`: automated PostGIS seeding ensuring base `zone`, creating assessed `segment` records, and populating `segment_static` with correct base logits and drain distances.
  - **Municipal Hotspot Seed Catalogs**:
    - **Mumbai** (`data/hotspots/mumbai_seed.csv` and `mumbai.csv`): 20 verified chronic flood locations authenticated against BMC Disaster Management Cell monsoon hotspots and Mumbai Traffic Police advisories (Milan Subway, Andheri Subway, Khar Subway, Malad Subway, Dahisar Subway, King's Circle / Gandhi Market, Hindmata, Kurla West / Mithi River bridge, Chunabhatti EEH, BKC Mithi outfall, Chembur Postal Colony, Tilak Nagar, Parel TT, Vidyavihar, Mankhurd, Mahalaxmi Dhobi Ghat, Wadala Bridge, Kalina).
    - **Gurugram** (`data/hotspots/gurugram_seed.csv` and `gurugram.csv`): 20 verified chronic waterlogging locations authenticated against GMDA Flood Control Room and Gurugram Traffic Police monsoon advisories (Subhash Chowk, Rajiv Chowk underpass, Hero Honda Chowk underpass, IFFCO Chowk, Shankar Chowk, Genpact Chowk underpass, DLF Phase 1 underpass, Bristol Chowk, Signature Tower underpass, Medanta underpass, Narsinghpur express corridor, Khandsa / Badshahpur drain breach, Basai Road RUB, Sheetla Mata Road culvert, Old Delhi-Gurugram Road, Pataudi Road RUB, Rampura flyover underpass, Kherki Daula toll, Vatika Chowk SPR, Sector 29 underpass).
    - Both datasets strictly verified against `hotspots.validate` trust boundaries (source URL regex, source date format, non-empty provenance).
  - **Multi-City API Endpoints (`apps/api/floodroute/api/routes/cities.py`)**:
    - `GET /v1/cities`: catalog of all supported municipal regions with bounding boxes, hydrology classifications, and rainfall triggers.
    - `GET /v1/cities/{city}`: city-specific metadata and operational parameters.
    - `GET /v1/cities/{city}/hotspots`: paginated municipal hotspot inventory query (`limit`, `offset`).
    - `POST /v1/cities/{city}/seed`: triggers PostGIS infrastructure and segment seeding.
  - **Verification & Testing**:
    - Added 4 tests in `apps/api/tests/inventory/test_inventory_multicity.py`.
    - Added 4 tests in `apps/api/tests/api/test_api_cities.py`.
### Checkpoint 24: Production Observability, Prometheus Metrics Exporter & Offline CDN Snapshot Engine (TRD 11 & 13)
- **Status**: Completed
- **Actions & Findings**:
  - **Pure-Python Prometheus Metrics Collector (`apps/api/floodroute/metrics/collector.py`)**:
    - Thread-safe zero-dependency metrics collector implementing `Counter`, `Gauge`, and `Histogram` types.
    - Standard Prometheus text format exposition (`# HELP`, `# TYPE`, formatted labels, and bucket histograms).
    - Core operational metrics registered in `METRICS` singleton: `floodroute_api_requests_total`, `floodroute_api_request_duration_seconds`, `floodroute_score_runs_total`, `floodroute_score_duration_seconds`, `floodroute_active_overrides`, `floodroute_active_watches`, `floodroute_ingest_events_total`.
  - **Telemetry HTTP Middleware (`apps/api/floodroute/metrics/middleware.py`)**:
    - `PrometheusMetricsMiddleware` records request counts and execution durations per normalized endpoint pattern (normalizing numeric segment IDs and path slugs to prevent high-cardinality metric label explosions).
    - Tracks HTTP status code, method, and latency buckets.
  - **Prometheus Metrics Exposition Endpoint (`apps/api/floodroute/api/routes/metrics.py`)**:
    - `GET /metrics`: serves Prometheus text exposition for direct scraping by Prometheus, VictoriaMetrics, or monitoring agents.
  - **Offline CDN Snapshot Generator (`apps/api/floodroute/feed/snapshot.py`)**:
    - Implements TRD 11 edge CDN snapshot caching and network outage resilience.
    - Queries active human overrides and impassable segments per city and vehicle class.
    - Exports standard GeoJSON `FeatureCollection` with `conditions_as_of`, `feature_count`, and SHA-256 ETag.
    - Atomic write via temporary files (`.tmp.<timestamp>`) and rename to prevent partial reads by web servers.
    - Status introspection (`list_snapshot_status`) tracking file age, stale detection (>5 min), and byte size.
  - **Snapshot API Endpoints (`apps/api/floodroute/api/routes/snapshot.py`)**:
    - `GET /v1/feed/snapshot/closures`: returns pre-generated snapshot with HTTP caching headers (`Cache-Control: public, max-age=120, stale-while-revalidate=600`, `ETag`) and full HTTP 304 Not Modified conditional GET support (`If-None-Match`).
    - `POST /v1/feed/snapshot/generate`: on-demand snapshot generation trigger.
    - `GET /v1/feed/snapshot/status`: status monitor of all cached snapshots.
  - **Worker Integration (`apps/api/floodroute/worker.py`)**:
    - Added Task 5 running every 2 minutes (`snapshot_interval_s = 120.0`) to pre-generate CDN closure snapshots for Bengaluru, Mumbai, and Gurugram.
    - Telemetry hooks recording scoring run count and duration metrics.
  - **Verification & Testing**:
    - Added 3 unit tests in `apps/api/tests/test_metrics.py`.
    - Added 1 integration test in `apps/api/tests/api/test_api_metrics.py`.
    - Added 3 integration tests in `apps/api/tests/api/test_api_snapshot.py`.
    - Full test suite: 688 passing tests (100% pass rate in 44.8s).
    - 0 ruff lint errors across all Python code.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 25: PWA Service Worker Offline Resilience & Background Sync Engine (TRD 11, 12 & 16)
- **Status**: Completed
- **Actions & Findings**:
  - **Service Worker Enhancements (`apps/citizen/public/sw.js`)**:
    - Upgraded cache configuration to `floodroute-v2`.
    - Implemented stale-while-revalidate caching strategy for dynamic CDN closure snapshots (`/v1/feed/snapshot/closures`) and multi-city metadata (`/v1/cities`), ensuring map and closure layers load instantly even when offline or experiencing high network latency.
    - Preserved network-first caching with fallback for route planning, rerouting, and health endpoints.
    - Added Background Sync API event listener (`floodroute-sync-reports`) dispatching `FLUSH_OFFLINE_REPORTS` message to active browser client tabs when network connectivity is restored.
  - **Offline Resilience & Queue Utility (`apps/citizen/src/utils/offline.ts`)**:
    - `formatConditionsAsOf`: formats timestamps into standard TRD 11 banner format ("Conditions as of HH:MM").
    - `isSnapshotStale`: evaluates data staleness against the 5-minute threshold (300 seconds).
    - `getSnapshotAgeMinutes`: calculates non-negative elapsed minutes from conditions timestamp.
    - Offline crowd report queue manager: `queueOfflineReport`, `getQueuedOfflineReports`, `removeQueuedOfflineReport`, `clearQueuedOfflineReports`, and `flushOfflineReports`.
    - Local snapshot caching and fetching: `saveCachedSnapshot`, `getCachedSnapshot`, and `fetchClosureSnapshot` with HTTP 304 conditional GET handling (`If-None-Match`).
  - **Multi-City Support & Citizen UI Integration (`apps/citizen/src/App.tsx`, `Header.tsx`, `RouteForm.tsx`, `MapView.tsx`)**:
    - Added municipal city selector (`bengaluru`, `mumbai`, `gurugram`) to top navigation bar.
    - Updated `RouteForm` with localized landmarks and presets across Bengaluru (Indiranagar, MG Road, Silk Board, etc.), Mumbai (BKC, Dadar TT, Andheri Subway, Milan Subway, South Mumbai Fort), and Gurugram (Cyber City, IFFCO Chowk, Subhash Chowk, Hero Honda Chowk, Golf Course Rd).
    - Dynamic flood corridor risk monitoring list per selected city.
    - Map automatically re-centers and renders city-specific chronic hotspots.
    - MapView renders active closures directly from pre-generated CDN GeoJSON snapshots (`snapshot` prop and `/v1/feed/snapshot/closures`) as red dashed closure vectors.
    - TRD 11 offline resilience banner: displays "Offline Mode Active: Conditions as of HH:MM" with staleness caution advisory when data age exceeds 5 minutes.
    - Automatic background flush of queued citizen crowd reports upon reconnecting or receiving Service Worker sync events.
  - **Verification & Testing**:
    - Added 7 unit tests in `apps/citizen/src/utils/offline.test.ts` (12/12 passing tests across `apps/citizen`).
    - TypeScript compiler passed with 0 errors (`npx tsc --noEmit`).
    - Vite production build succeeded cleanly (`npm run build`).
    - Backend test suite verified: 688/688 passing tests in `apps/api`.
    - 0 ruff lint errors across all Python code.
    - Zero em-dashes and strict safety invariant maintained.

---

### Checkpoint 26: Safety Case Emergency Kill Switch and Advisory Freeze (TRD 16)
- **Status**: Completed
- **Commit**: `c6c6875`
- **Tests**: 694/694 passing (0 ruff errors)
- **Components Implemented**:
  - **DB Migration (`apps/api/floodroute/db/migrations/0006_safety_kill_switch.sql`)**:
    - `kill_switch` table with columns: `kill_switch_id`, `scope` (global/city/tenant), `tenant_id`, `city_id`, `reason`, `operator`, `engaged_at`, `disengaged_at`, `disengaged_by`.
    - Applied to the persistent `floodroute` dev DB via migrator.
  - **Kill Switch Service (`apps/api/floodroute/safety/kill_switch.py`)**:
    - `engage_kill_switch(...)`: validates reason (>=5 chars), inserts row, writes `kill_switch_engaged` audit log entry.
    - `disengage_kill_switch(...)`: enforces two-operator co-verification (`op1 != op2`, case-insensitive), writes `kill_switch_disengaged` audit log.
    - `get_active_kill_switch(conn, tenant_id, city_id)`: returns first active switch matching global > city > tenant priority.
    - `list_kill_switches(conn, ...)`: paginated history with optional `active_only` filter.
  - **Safety API Router (`apps/api/floodroute/api/routes/safety.py`)**:
    - `GET /v1/safety/kill-switch` - list active switches.
    - `POST /v1/safety/kill-switch` - engage a kill switch.
    - `POST /v1/safety/kill-switch/{id}/disengage` - disengage (POST alias for TestClient compatibility).
    - `DELETE /v1/safety/kill-switch/{id}` - disengage via DELETE (production use).
    - `GET /v1/safety/kill-switch/history` - paginated audit history.
  - **Route Integration (`apps/api/floodroute/api/routes/route.py`)**:
    - `compute_route`: After `plan()`, appends `[ADVISORY FREEZE: ...]` to every route's reasons if kill switch is active.
    - `compute_reroute`: Returns early `RerouteResponse(action="keep", code="advisory_off")` if kill switch is active.
  - **Tests**: 4 DB-level + 1 API lifecycle + 1 route freeze test added (all passing).
  - **Verification**: 694/694 tests passing, 0 ruff errors, zero em-dashes.

---

### Checkpoint 27: Harden Closeout, Dockerfile Import Fix and CI (opencode SDD Task 1)
- **Status**: Completed
- **Actions & Findings**:
  - Verified uncommitted Harden output (`apps/api/Dockerfile`, `apps/api/.dockerignore`, `docker-compose.yml`, `.github/workflows/api.yml`).
  - Root cause found deeper than the missing data file: `score/config.py parents[4]` raised `IndexError` at import time under old `WORKDIR /app`. Fix: `WORKDIR /app/apps/api` (1 line + comment) plus read-only compose mount of `data/config/scoring.v0.json` on api and worker.
  - CI `pip install -e ".[dev]"` confirmed against the `dev` extra in `pyproject.toml`.
  - Evidence: `docker compose config` exit 0, `docker build` exit 0, in-container `load_config()` returns v0.0.1.
  - SDD task review: Spec PASS, Quality Approved.

### Checkpoint 28: Chennai Chronic Hotspot Seed, 20 Verified Rows (opencode SDD Task 2)
- **Status**: Completed
- **Actions & Findings**:
  - Shipped `data/hotspots/chennai_seed.csv` and `data/hotspots/chennai.csv` (20 rows each, headers byte-identical to Mumbai pattern, all coordinates inside the Chennai bbox, structures 5 underpass / 4 culvert / 11 dip).
  - Every row carries consulted provenance (Michaung Dec 2023, Fengal Nov 2024, Oct 2024 NE onset). Maduravoyal dropped for lack of verification; GCC 859 list unused (no citable copy).
  - Registry `hotspot_count` 0 to 20 (one line); mirrored tests (`test_load_chennai_hotspots` plus Chennai assertions in `test_api_cities.py`).
  - Reviewer fetched 3/20 source URLs, all corroborate. SDD task review: Spec PASS, Quality Approved.

### Checkpoint 29: G0 Evidence Pack, Chennai Shadow Run and Benchmark Dedupe (opencode SDD Tasks 3-4)
- **Status**: Completed
- **Actions & Findings**:
  - Chennai shadow run (run 5, existing `execute_score_run` entry point): 24800 risk rows (1550 x 4 classes x 4 horizons), history and audit rows written. MET Norway ingest extended to Chennai zone 2 (62 fresh forecast rows, run 6 re-score).
  - New `docs/G0-evidence.md`: real backtest numbers (deduped 6 events, car/0m POD 0.0, FAR None, CSI 0.0, Brier 0.7972, ROC-AUC 0.2), both-city shadow stats, G0 gate checklist (done vs blocked-human: counsel, interviews/partners, S1 live benchmark, IMERG Earthdata login).
  - Honest limitation recorded: all rows score unknown because `rain_obs` is empty and `state.degrade` maps clear to unknown on missing observations; no threshold tuning applied.
  - Fixed double-seeded `observed_event` (12 to 6 canonical rows) and made `seed_benchmark_events` idempotent with a new test.
  - Verification: 696/696 tests passing (100% in 44.4s), 0 ruff errors, zero em-dashes. SDD task reviews: Spec PASS, Quality Approved. Final whole-branch review: Ready to merge.

---


### Checkpoint 30: Premium hackathon frontend baseline
- **Status**: Completed locally; not pushed or deployed.
- **Commit**: `450a732` on `codex/hhgoa-frontend`.
- **Verified at the end of the preceding work**: 17 frontend tests, 18 production-browser checks, 806 backend tests, TypeScript, Vite build, and Python lint passed.
- White/black themes, labelled demo route planning, controlled rerouting scenarios, road reports, responsive layouts, native `/app/` redirect, and source-built CI are implemented.
- Original generated concepts and actual desktop/mobile screenshots are under `output/`. These are design/demo artifacts, not live flood observations.
- Existing backend safety and governance changes remain in the working tree; they were preserved rather than included in the frontend-only commit.

### Checkpoint 31: Hover dots, hero route illustration, and backend delivery
- **Status**: Frontend and documentation complete locally. Current-source backend verified; fresh container deployment and self-hosted routing are blocked by network downloads. Updated 6 October 2026, 21:33 IST.
- **Requested scope**: Whole-page dotted hover background, missing wide hero route preview, backend end-to-end delivery, README refresh, and an evidence-based checkpoint.
- **Frontend**: Native viewport canvas with local dot repulsion, frame-rate-independent easing, pixel density capped at 1.5, no idle animation loop, static reduced-motion/touch behavior, hidden-tab suspension, and listener cleanup. A deterministic SVG route strip sits below the hero; it is explicitly an illustration and does not assert live road status. Vite development and preview now proxy `/v1` to local API port 8080, configurable with `FLOODROUTE_DEV_API_URL`.
- **Frontend verification**: TypeScript, 18 Node tests, and the production build passed. All 18 journey browser checks passed, including desktop/mobile layouts, forms, scenarios, stale snapshots, and honest API errors. Canvas browser checks confirmed pointer movement, return to grid, stopped idle rendering, reduced motion, touch behavior, and the pixel-density cap. Actual OSM tiles returned 200 without browser errors; current captures are in `output/frontend-preview/2026-10-06-dots/`. These checks do not claim a measured frame-rate benchmark.
- **Live integration**: The preview on 5174 connected through its proxy to the current source API on 8080. Health and snapshots returned 200; a real external-router journey returned 200 with 203 decoded road vertices and a 25-minute estimate. Its worst state remained `unknown`. The first pre-worker probe had zero scored segments. After the worker, two matched segments had scored rows, both with unknown state. The route counter now counts known statuses, excluding missing/null/unknown states, rather than presenting unknown model rows as known road conditions.
- **Documentation**: README and hackathon runbook now include current screenshots, reproducible run/check commands, Demo/Live distinctions, verified source-runtime behavior, and recorded blockers. `docs/BACKEND_RUNBOOK.md` and the stdlib `tools/dev-backend.py` cover startup and endpoint checks.
- **Backend packaging**: Root-context Docker build includes the frontend; Compose adds isolated persistent PostGIS on port 54330, migrations, API/worker, snapshots/photos volumes, and an optional pinned Valhalla service. Existing test PostGIS on 54329 is untouched. Compose configurations validate; frontend-stage image build succeeded. Code and Python reviewers found no remaining actionable infra issues.
- **Backend runtime verification**: Eight migrations applied to the isolated database; real Bengaluru candidate inventory loaded 5,383 road segments and 233 hotspot matches. Native current-source API served the built frontend, health, and snapshots. A synthetic unmatched report returned 201 without creating road evidence. A local worker pass persisted 86,128 risk rows, all unknown, and produced four-city snapshots. Snapshots remained empty/stale with no source observations. An unavailable router returned the expected 502 without fabricated geometry. Full inventory scoring takes several minutes; unsupported research vehicle classes are omitted rather than remapped.
- **Routing preparation and blockers**: A real regional OSM extract and Bengaluru clip are cached outside Git. The official external Valhalla demo supplied the verified road route under its documented fair-use conditions. Fresh Python image installation failed on PyPI connectivity; official routing-image blobs failed with EOF on bounded attempts. A fresh complete API image and a self-hosted Valhalla graph have not been verified. These external failures are recorded, with no background retry loop left running.
- **Final build and capture**: `index-CMWuZY0L.js` passed the final TypeScript/test/build check. Desktop, mobile, demo-route, and black-theme captures were refreshed. The recorded real API route was replayed after the counter correction to verify zero known statuses without another external router request. The capture record is `output/frontend-preview/2026-10-06-dots/verification.md`.
- **Review and repository state**: Frontend review corrections addressed the old proxy-port comment and missing-status counter guard. Existing API safety/governance edits, migrations, and inventory changes remain preserved in the working tree. They are distinct from this frontend/infra delivery and still need their own release checkpoint. Nothing has been pushed or deployed.
- **External live-pilot requirements remain**: Fresh flood observations, source access/terms, coverage calibration, field validation, and the actual hackathon submission/deployment requirements. No field evidence or production accuracy is being invented.

### Checkpoint 32: Direct frontend push and Vercel import preparation
- **Status**: Completed. User-authorized direct push verified on 6 October 2026, 23:21 IST, to the existing remote default branch, `claude/floodroute-project-plan-g5cntf`. Vercel deployment remains with the user.
- Remote default HEAD `c5e9750` is an ancestor of this checkout. The push can fast-forward existing history without force or a pull request.
- Root `vercel.json` builds only `@floodroute/citizen` and publishes `apps/citizen/dist`. Import instructions specify root `.`, Node 24.x, and `ENABLE_EXPERIMENTAL_COREPACK=1`; no API variable is needed for Demo mode.
- Vercel configuration review, token checks, TypeScript, all 18 frontend tests, and the production build passed before push.
- Push scope: reviewed frontend, screenshots, documentation, local backend packaging and smoke helper. Existing API safety/governance source edits, migrations, inventory changes, and their tests remain local and are excluded from this frontend release.
- Delivery commit `deebd0ee651604d696c82548d99871bfb8f61129` was pushed normally, with no force or pull request. GitHub's remote branch SHA matched the local commit exactly.
- The configured HTTPS credential failed, and the GitHub CLI token lacked workflow-publishing scope. Existing SSH authentication for `Krishpotanwar` completed the push; no new token, account permission, or SSH key was created.

### Checkpoint 33: README gallery and spoken-prompt attribution
- **Status**: Documentation update completed and reviewed on 6 October 2026 for publication to the same default branch.
- README now presents the white landing page and black route planner, with an expandable desktop/mobile gallery and a clearly labelled recorded live route.
- Added a genuine 1440×1000 browser overview capture, with no browser exceptions. Local image/link paths and gallery markup were checked; documentation review approved the change.
- The README states that project prompts were dictated with Wispr Flow instead of typed by hand, reflecting the user's attribution. A short description links Wispr's official site and documentation.
- Application source and pending backend changes are unchanged. This update consists only of README/checkpoint documentation and the overview image.

### Checkpoint 34: Backend release, security review, and self-hosted routing
- **Status**: Local backend integration verified and published on 7 October 2026 via the user-authorized direct push to `claude/floodroute-project-plan-g5cntf`. Source release commit: `fb6e4e7e21f79e37f1b41aa94ff673a8eabd96e4`. Remote SHA matched exactly; public hosting is still pending.
- **Release scope**: The preserved backend audit fixes are now reviewed together: authenticated operator controls and distinct co-signatures, public-HTTPS webhook targets with DNS/IP pinning, signed receipt freshness, bounded request bodies, atomic report/evidence and override/audit writes, conservative horizon/snapshot freshness, retired-row filtering, stable inventory identities, immutable history permissions, and forward-only migrations 0007–0009. Photo processing and inbound bot DB work run off the event loop; a process-local lock preserves serial session access. No new dependency was added.
- **CI correction**: The in-process benchmark uses its disposable migrated test database instead of a hardcoded development database. Functional tests check successful scenarios; the benchmark CLI retains measured latency criteria. Privileged ambulance benchmarks require an operator token.
- **Container and router**: The fresh API image builds successfully, including its citizen frontend. Dedicated PostGIS is healthy on `54330`, all nine migrations applied, and the existing 5,383 genuine OSM-derived Bengaluru segments/233 hotspot matches remain loaded. The official pinned Valhalla image built a local Bengaluru graph and is healthy on `8002`; the previous network/download blockers are resolved.
- **Real runtime evidence**: Docker API on `8080` served the app, health, and snapshots with HTTP 200. The route-required smoke check passed against self-hosted routing. One explicitly synthetic unmatched report returned HTTP 201 without creating road evidence. Anonymous operator administration returned 401; a configured credential returned 200.
- **Browser integration**: A direct request from the citizen frontend to the Docker API returned a real Indiranagar-to-Silk Board route: 203 decoded road vertices and an 18-minute baseline estimate. Both matched road segments remained unknown; the frontend displayed zero known statuses, an unassessed label, and stale-data warning. Route and endpoint markers rendered after map loading, with no browser exceptions. No route response was intercepted or fabricated. Captures and responses are in `output/backend-verification/2026-10-07/`.
- **Source and worker checks**: Actual MET Norway access supplied 62 forecast rows for one Bengaluru zone. Two bounded SACHET passes stored 20 alerts, with 79 feed items still pending. A complete worker cycle finished ingestion, scoring, retention, and four-city snapshots. All 86,128 persisted road-risk rows remain unknown because `rain_obs` is empty. Source health reported degraded freshness; the empty Bengaluru closure snapshot remained stale. Zero watch alert objects were generated; no subscriber message was sent.
- **Review and tests**: Code, Python, database, and security reviewers cross-checked the release. Final security review found no remaining critical/high findings in the audited changes. The final full backend run passed all 843 tests in 64.36 seconds, with no skipped database checks. Ruff and diff checks passed; the existing TestClient/httpx deprecation warning remains.
- **Published CI**: Both [API CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37570294868) and [frontend CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37570294901) passed for the published source commit. The prior API benchmark database failure is resolved. GitHub reported action-runtime deprecation annotations, with the actions running successfully on Node 24.
- **Documentation**: README preserves the Wispr Flow spoken-prompt attribution and white/black gallery, adds an actual self-hosted-route capture, and replaces obsolete container blockers with current evidence. Backend/hackathon runbooks document operator setup, request limits, truthful data states, and remaining delivery requirements.
- **Console follow-up**: The operator report selector now labels wet as approximately 2 cm and ankle as approximately 10 cm, matching the existing API depth mapping. All four option labels were checked against that mapping; code review approved the text correction. Submitted category values remain unchanged.
- **Remaining external work**: Verify the user's hosted frontend URL; configure public API/database/worker/router hosting; obtain current rainfall observations; finish data/terms review, calibration, city coverage and field validation; integrate real subscriber messaging when required. These are not represented as completed or as production accuracy.

### Checkpoint 35: Console padding-hook triage
- **Scope**: Review the unattributed console spacing finding without treating existing styling as a regression or redesigning the page.
- **Fix**: Health/risk badges, shortcut hint, toggle buttons, and audit-table cells now use the existing 8px spacing token. The same header-control strip wraps to accommodate those controls on mobile.
- **Verification**: Actual browser checks at 1440px and 390px confirmed computed 8px padding and no horizontal overflow. The mobile document width changed from 746px to 390px. Independent code review approved the diff. Operator audit access, memory-only credentials, reload locking, and depth labels also passed browser checks, with no browser exceptions.
- **Detector triage**: The remaining cramped-padding warning names the bordered audit-table scroll wrapper, while all 255 rendered header/data cells provide their own 8px inset. That wrapper is a confident false positive. Saved a shared, console-file-scoped `cramped-padding` value exception through `impeccable hooks ignore-value`, with the evidence recorded in `.impeccable/config.json`; other detector rules remain active.
- **Local preview**: Updated the running development container's static console from source. The Docker image itself has not been rebuilt for this CSS-only follow-up; the next source image build includes it.

### Checkpoint 36: Graph-edge route assessment and backend refresh
- **Status**: Source and local runtime verified on 8 October 2026. Release commit `ee965d8656e6446a86ddd27f04d481202e85aaf2` was directly pushed to the existing remote default branch; the remote SHA matched.
- **Routing root cause**: The former mapper checked two long Valhalla maneuvers on the reference journey, which could miss a flooded road between turns. The new strict `edge_walk` maps all 102 recorded graph edges to assessed inventory by positive OSM way ID and 50 m geometry proximity. Missing edges remain unassessed; ambiguous same-way matches and inconsistent trace geometry or elapsed time stop routing. The route and trace share local IST departure time, costing, and units. Request-scoped HTTP clients close after use.
- **Report and database**: New reports match assessed roads only, so retired inventory rows cannot capture evidence. Forward-only migration 0010 adds the partial assessed OSM-way index. The final Docker image built and the isolated database applied all ten migrations; the real 5,383-row Bengaluru inventory remained loaded.
- **Behavior checks**: The standard full backend suite passed 879 tests with one expected opt-in external-graph skip before the final HTTP-client cleanup. After that cleanup, 71 focused route/API tests passed. The opt-in integration test passed against the genuine local Bengaluru graph, with synthetic risk in a disposable database: an interior closure detoured and an origin closure returned `no_safe_route`. Ruff and diff checks passed. The rebuilt Docker API passed `tools/dev-backend.py --require-route` against self-hosted routing.
- **Data checks**: Eight bounded SACHET passes on 7 October stored 100 official alerts. Eighty had missing area geometry after polygon HTTP 403 responses; raw CAP and error provenance were retained. The 8 October worker stored ten new alerts and flagged 89 pending, ingested 62 MET Norway forecast rows, reported 64,596 score changes and zero watch alerts, and made four empty closure snapshots. `rain_obs` remained empty at inspection. No active watches or subscriptions existed, and no subscriber message was sent.
- **Runtime limit**: Docker Desktop quit during a later full-suite rerun and the attempted new browser capture. Those interrupted results are not counted as passing. The genuine 7 October screenshot remains labelled as historical; [8 October evidence](output/backend-verification/2026-10-08-graph-edges/verification.md) records the new source and live-graph checks without inventing a capture.
- **Published CI**: [API CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37809981322) passed the release commit with 879 tests, two expected skips (opt-in live graph and optional `osmium`), and Ruff. [Frontend CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37809981418) passed on the same commit.
- **Known ceiling and external work**: Same-way inventory overlaps within 50 m fail closed until intervals are split. Public API/database/worker/router hosting, current rain observations, source area recovery, calibration, provider messaging, and the user's Vercel URL remain outstanding. No live-road safety claim follows from these local checks.

### Checkpoint 37: Vercel frontend deployment
- **Status**: Frontend deployed on 8 October 2026 at [flood-route-rosy.vercel.app](https://flood-route-rosy.vercel.app/) from GitHub default-branch commit `c11f78db68af0b93438d0412d230e6d314334dc6`.
- **Verification**: Vercel reported deployment success. The public homepage, JavaScript/CSS bundles, manifest, service worker, and icon returned HTTP 200 over HTTPS. In a real browser, the page showed the route illustration, map, and planner with Demo selected and sample conditions explicitly labelled. This deployment has no `VITE_API_BASE_URL`. A public Python API, PostGIS database, worker, and Valhalla router are not yet connected.
- **Hosting assessment**: The existing Render account is available, but its Free web instance has 512 MB RAM, sleeps after 15 minutes idle, and has ephemeral storage; Free Render Postgres expires after 30 days. That does not host the complete API, worker, PostGIS, and self-hosted Bengaluru Valhalla stack as one durable deployment. Oracle Cloud's current Always Free Ampere allowance is a possible VM target if the owner has an account and capacity is available, but the current `postgis/postgis:16-3.4` image is amd64-only and would require an arm64-compatible replacement before deploying there. HTTPS and SSH access are also needed. No backend provider has been provisioned or verified in this checkpoint.
