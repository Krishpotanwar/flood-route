# Backend runbook

Last verified: **8 October 2026**. The current source builds a complete Docker API image and runs against an isolated PostGIS database with ten migrations and a self-hosted Bengaluru Valhalla graph. Local endpoint and source-ingestion checks are recorded below. Public hosting, current rain observations, calibration, and field validation remain separate requirements. The frontend can be deployed independently.

The local stack is FastAPI, PostGIS, a scoring/snapshot worker, and an optional Valhalla road router. The API image builds the citizen frontend from source and serves it at `/app/`. Raw OSM files and routing tiles stay outside Git.

## Docker setup

Run from the repository root with Docker Desktop or a Docker engine running. The current API requires explicit WhatsApp secrets at startup, including when the webhook is unused. Generate local values; use credentials from Meta only when connecting an actual webhook. Never put real secrets in a `VITE_` variable.

```sh
export WHATSAPP_VERIFY_TOKEN="$(openssl rand -hex 32)"
export WHATSAPP_APP_SECRET="$(openssl rand -hex 32)"
export FLOODROUTE_OPERATOR_TOKENS="$(python3 -c 'import json,secrets; print(json.dumps({"operator-one": secrets.token_hex(32), "operator-two": secrets.token_hex(32)}))')"
export FLOODROUTE_CONTACT=https://github.com/Krishpotanwar/flood-route
docker compose config --quiet
docker compose build api
docker compose up -d api
# Load the checked-in OSM-derived Bengaluru inventory, not synthetic hotspot roads.
docker compose run --rm api sh -c 'python -m floodroute.inventory.seed --db-url "$DATABASE_URL" --city bengaluru'
```

Open [the citizen app](http://127.0.0.1:8080/app/?live=1), [API documentation](http://127.0.0.1:8080/docs), or [health](http://127.0.0.1:8080/v1/health). The `live=1` flag selects the API instead of the explicitly labelled presentation demo. The separate Vite server proxies `/v1` to port `8080`; set `FLOODROUTE_DEV_API_URL` when the local API uses another port. Add `?live=1` or select Live in that frontend too.

The defaults bind only loopback: API `8080`, PostGIS `54330`, optional Valhalla `8002`. The existing test database can keep port `54329`. Set `FLOODROUTE_API_PORT`, `FLOODROUTE_DB_PORT`, or `FLOODROUTE_ROUTING_PORT` to avoid conflicts. Named volumes persist database rows, snapshots, and photos. `docker compose down` preserves them. Change the local database password with `FLOODROUTE_DB_PASSWORD` before its first initialization; this value must be URL-safe because it appears in the local connection URL.

The migration service applies forward-only migrations before API/worker startup. A migration failure prevents those services from starting. After pulling code with new migrations, rebuild and run `docker compose up -d api worker` again.

## Operator controls and request limits

`FLOODROUTE_OPERATOR_TOKENS` is a JSON object mapping operator names to unique secrets. Each secret must contain 32–512 ASCII characters with no whitespace; the registry accepts at most 100 operators. Keep it in the backend environment or a private environment file. An absent or invalid registry disables operator administration with HTTP 503; public citizen endpoints remain available.

Send `Authorization: Bearer <operator-secret>` for override, safety, webhook-administration, and city-seeding controls, and for the privileged `ambulance` route/reroute profile. A supplied `operator_id` must match the authenticated registry name. Arterial reopening or cancellation and kill-switch release require a distinct registered second operator: provide that operator's name as `second_operator_id` and their secret in `X-FloodRoute-Co-Signature`. The API reference documents whether the name belongs in a JSON body or query parameter.

The [operator console](http://127.0.0.1:8080/console) keeps entered keys in memory for the open page; reloading clears them. The citizen frontend does not acquire these credentials automatically. Never put operator or WhatsApp secrets into `VITE_` variables or the frontend's Vercel environment. For a separate frontend origin, configure `FLOODROUTE_CORS_ORIGINS` on the API; allowing CORS does not supply authorization headers.

API request bodies are bounded before parsing or photo processing: 1 MiB for `/v1/*` JSON/webhook requests and 5 MiB for `/v1/reports/photo`. Oversized bodies return HTTP 413, including chunked requests.

## Self-hosted road routing

The optional routing profile uses the official multiarchitecture `valhalla-scripted` image pinned by digest. Its local input directory defaults to `$HOME/.cache/floodroute-routing/bengaluru`. Set `FLOODROUTE_ROUTING_DIR` to another absolute cache directory when needed. The official [Valhalla Docker documentation](https://github.com/valhalla/valhalla/blob/master/docker/README.md) describes graph generation from a local PBF and the environment settings used here.

Provide a genuine Bengaluru OSM PBF in that directory before starting the profile. An empty directory provides no routing coverage. The following commands reproduce the existing city clip; they download a regional source once, then reuse the existing clip tool. The clipping step requires pyosmium, which is already installed in the current developer environment; a fresh environment can install the optional extraction tool with `uv pip install --python apps/api/.venv/bin/python osmium`.

```sh
mkdir -p "$HOME/.cache/floodroute-routing/raw" "$HOME/.cache/floodroute-routing/bengaluru"
curl -fL --retry 2 -o "$HOME/.cache/floodroute-routing/raw/southern-zone.osm.pbf.part" \
  https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf
mv "$HOME/.cache/floodroute-routing/raw/southern-zone.osm.pbf.part" \
  "$HOME/.cache/floodroute-routing/raw/southern-zone.osm.pbf"
apps/api/.venv/bin/python tools/spikes/s1_valhalla/clip_bbox.py \
  "$HOME/.cache/floodroute-routing/raw/southern-zone.osm.pbf" \
  "$HOME/.cache/floodroute-routing/bengaluru/bengaluru.osm.pbf" 77.40,12.80,77.85,13.20
docker compose --profile routing up -d valhalla
docker compose --profile routing logs -f valhalla
```

Initial graph construction takes time. Check [routing status](http://127.0.0.1:8002/status), then run the route-required smoke check below. Changing the host routing port does not change the internal API URL, which remains `http://valhalla:8002`. For another trusted Valhalla instance, set `VALHALLA_URL` before creating the API container. This graph supplies road geometry and baseline travel estimates, not live traffic or flood observations. OpenStreetMap data must retain [its attribution and licence](../data/inventory/NOTICE.md).

The API follows each Valhalla route with a strict `edge_walk` trace and checks each graph edge against an assessed inventory row on the same OSM way within 50 m. Missing matches remain unassessed; ambiguous same-way matches stop the route instead of silently choosing one. The route and trace must agree on geometry and travel time. This is a conservative local mapping, not nationwide inventory coverage or field calibration. To exercise a real graph with synthetic risk confined to a disposable test database:

```sh
cd apps/api
FLOODROUTE_REQUIRE_DB=1 FLOODROUTE_LIVE_ROUTER_URL=http://127.0.0.1:8002 \
  .venv/bin/pytest -q tests/route/test_route_live.py
```

## Observations and the worker

Set `FLOODROUTE_CONTACT` to an actual contact email or project URL before using MET Norway. The API source adapters fetch SACHET alerts and MET Norway rainfall forecasts; source access can fail independently of API/database health. Missing rainfall/observations, unreviewed inventory matches, and uncalibrated risk coefficients limit flood guidance even when roads can be routed.

```sh
# Supply an actual contact value in your shell first.
docker compose up -d worker
docker compose logs --tail 60 worker
docker compose run --rm api python -m floodroute.ingest metno --once
docker compose run --rm api python -m floodroute.ingest sachet --once
```

Check `/v1/health` source timestamps and errors plus `/v1/feed/snapshot/closures?city=bengaluru&vclass=car`. Empty closure geometry is not proof that roads are clear. Missing required feed provenance yields `stale: true`; route output without current road assessments remains `unknown`. Never label seeded inventory, illustrative frontend scenarios, or an external demo router as live flood data.

A full inventory pass currently takes several minutes because the scorer writes risk, history, and audit rows individually. The database supports the four frontend vehicle classes. The scoring configuration also includes `auto_rickshaw`, `pedestrian`, and `suv`; their research rows are explicitly omitted from persistence rather than remapped to another vehicle class.

Worker statistics report watch `alerts_generated`: these are computed alert objects, not messages delivered to subscribers. Actual SMS, WhatsApp, or push delivery needs a configured provider integration and its delivery handling. The inbound WhatsApp webhook and outbound event-webhook mechanism do not establish subscriber-message delivery.

## Smoke check

The script uses only Python's standard library. The default tolerates an unavailable router only if the API returns its documented `502` error. `--require-route` demands real route geometry from a configured router. `--report` writes one explicitly synthetic pending report outside the seeded inventory; it must remain unmatched and therefore adds no road evidence.

```sh
python3 tools/dev-backend.py
python3 tools/dev-backend.py --require-route --report
# For a changed API host port:
python3 tools/dev-backend.py --url http://127.0.0.1:8090 --require-route
```

## Native development fallback

For source-level development, the existing local Python environment can run against the same isolated Compose database. The complete Docker image is now verified; this fallback remains useful for editing without rebuilding it.

```sh
# On a fresh machine, create the environment first when PyPI is reachable.
uv venv apps/api/.venv --python 3.12
uv pip install --python apps/api/.venv/bin/python -e 'apps/api[dev]'
corepack pnpm --filter @floodroute/citizen build
export DATABASE_URL=postgresql://postgres:floodroute-local@127.0.0.1:54330/floodroute
export PYTHONPATH=apps/api
export FLOODROUTE_SNAPSHOT_DIR="$HOME/.cache/floodroute-routing/snapshots"
export WHATSAPP_VERIFY_TOKEN="$(openssl rand -hex 32)"
export WHATSAPP_APP_SECRET="$(openssl rand -hex 32)"
export FLOODROUTE_OPERATOR_TOKENS="$(python3 -c 'import json,secrets; print(json.dumps({"operator-one": secrets.token_hex(32), "operator-two": secrets.token_hex(32)}))')"
export FLOODROUTE_CONTACT=https://github.com/Krishpotanwar/flood-route
docker compose up -d db
apps/api/.venv/bin/python -m floodroute.db.migrate
apps/api/.venv/bin/python -m floodroute.inventory.seed --db-url "$DATABASE_URL" --city bengaluru
# Use your local Valhalla graph once it is built:
export VALHALLA_URL=http://127.0.0.1:8002
apps/api/.venv/bin/python -m uvicorn floodroute.api.main:app --host 127.0.0.1 --port 8080
```

For a small integration probe using only public landmark presets, the official [Valhalla public demo documentation](https://valhalla.github.io/valhalla/valhalla-intro/) lists `https://valhalla1.openstreetmap.de`. Its fair-use limits apply. It is an external demo service; use self-hosted routing for deployment. Publishing an app that uses it also requires following its operator's identification/contact guidance.

## Verification checkpoint — 8 October 2026

- The refreshed API image built and served the route-required smoke check on `8080`; the isolated database applied migration 0010 and has the assessed OSM-way lookup index. A recorded Bengaluru route has 102 graph edges. The opt-in test against the actual local graph passed a synthetic interior closure detour and an origin-closure `no_safe_route` check, using only a disposable database.
- Departure time is sent in the origin's local IST clock to Valhalla. The graph trace uses that same time and the same costing as the route. Unknown, ambiguous, or inconsistent edge mappings fail closed.
- The previous full API run passed 879 tests with one expected external-graph skip. After the final HTTP-client lifecycle fix, 71 focused route/API tests and the opt-in live test passed, and Ruff passed. A subsequent full rerun stopped when Docker Desktop shut down; it is not counted as a pass. The rebuilt image includes the lifecycle fix.
- A bounded SACHET catch-up on 7 October stored 100 alerts; 80 had no polygon because SACHET's polygon endpoint returned HTTP 403. The 8 October worker step succeeded and stored ten new feed items, with 89 more flagged for later runs. MET Norway returned 62 forecast rows. The worker reported 64,596 score changes, zero watch alerts, and four empty city snapshots. There were no active route watches or webhook subscriptions. These counts do not imply current rainfall observations or verified road states.
- The 8 October connected-browser recapture could not complete after Docker Desktop was quit externally. The genuine earlier browser screenshot remains labelled with its 7 October date. See [the graph-edge verification record](../output/backend-verification/2026-10-08-graph-edges/verification.md).

## Historical verification checkpoint — 7 October 2026

- A fresh complete API image built successfully. Its Compose API served `/app/`, health, closure snapshots, and the route/report smoke checks on loopback port `8080`.
- The isolated PostGIS database on `54330` is healthy with all nine migrations applied, 5,383 genuine OSM-derived Bengaluru road segments, and 233 hotspot matches.
- The pinned official Valhalla image built the local Bengaluru graph and is healthy on `8002`. The route-required smoke check returned real road geometry from this self-hosted router. It did not substitute a frontend illustration or an external demo route.
- MET Norway ingestion stored 62 forecast rows for the database's one configured Bengaluru zone. Source-issued lag was 9,977 seconds at ingestion and 10,041 seconds during the worker run. Forecasts are not rain observations.
- SACHET fetched 99 feed items and stored 10 CAP alerts in its first bounded pass. It reported a catch-up warning with 89 items pending. A second pass brought the stored total to 20 alerts; these bounded passes do not establish a fully current alert feed.
- The subsequent `worker --once` cycle completed both source adapters with status 0, reported 64,596 score changes and zero generated watch alerts, and built four city snapshots with zero features. Retention removed zero rows.
- The database then contained 86,128 `segment_risk` rows, all `unknown`, and zero `rain_obs` observations. The Bengaluru closure snapshot remained stale. Empty closure geometry does not show that roads are clear.
- The final backend suite passed **843 tests**, and Ruff passed. The only reported warning was the existing Starlette TestClient/httpx deprecation warning.

These checks establish local service integration, including a browser route request to the Docker API with no response interception ([captured route](../output/backend-verification/2026-10-07/self-hosted-route.png)). They do not verify public deployment, production source coverage, calibrated flood accuracy, or subscriber-message delivery. Release status is maintained in [Progress checkpoints](../PROGRESS_CHECKPOINTS.md); the [G0 evidence pack](G0-evidence.md) tracks observation, terms, calibration, and field-validation gates.

## Historical verification — 6 October 2026

Verified with the current local source, not a newly built API image:

- Both Compose configurations validate; the isolated PostGIS database is healthy on `54330`.
- All eight migrations applied. The real checked-in Bengaluru candidate inventory loaded 5,383 road segments and 233 hotspot matches.
- The API served `/app/?live=1`, health, and closure snapshots with HTTP 200. Initial health had no source observations; the empty snapshot was correctly marked stale.
- One Bengaluru public-landmark route through the external FOSSGIS Valhalla demo returned HTTP 200: one route, 25-minute estimate, 203 decoded road-shape vertices. Its flood state was `unknown` with zero assessed segments, reflecting absent current source observations.
- One synthetic unmatched report returned HTTP 201 and produced no segment evidence.
- A local-only worker pass completed scoring, retention, and snapshots for all four cities. It persisted 86,128 risk rows, all `unknown`; unsupported research classes were omitted. Source ingestion was deliberately skipped because no contact value was configured. The post-run snapshot remained empty and stale, with no source observations.
- A separate check against an unavailable localhost router returned HTTP 502 with `routing temporarily unavailable`; no substitute geometry was fabricated.
- Source Docker build completed its frontend stage, but Python installation failed on an unreachable PyPI endpoint. A second logged attempt was stopped after another network stall; no new API image is verified. The official Valhalla image manifest resolved, but its registry blob transfers failed with EOF on bounded attempts. Local routing graph construction is therefore **not verified**.
- The 532 MB regional source and 11 MB city clip are cached outside the repository. The city clip contains 234,787 highway ways and 879,946 referenced nodes, retaining 416 turn restrictions.

The 6 October local API logs and smoke evidence are in `/tmp/floodroute-backend-check/`, including `api.log`, `smoke.log`, `worker-local.log`, `unavailable-route.log`, `docker-build.log`, and the captured audited `bengaluru-route.json`; these are temporary runtime evidence, not committed deployment artifacts. The PyPI/image-pull and graph-construction blockers in this historical check were resolved in the 7 October verification above. Public hosting, rain-observation access, calibration, terms review, and field validation remain open.
