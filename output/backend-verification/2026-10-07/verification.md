# Backend verification · 7 October 2026

This is local runtime evidence from the reviewed source and newly built Docker image. It does not establish a public deployment or field accuracy. The browser used the real API directly; no route responses were intercepted or substituted.

## Verified stack

- Dedicated PostGIS on loopback `54330`, leaving the test database on `54329` untouched. Nine migrations applied, including forward-only governance and release fixes.
- 5,383 OSM-derived Bengaluru road segments and 233 hotspot matches. One configured Bengaluru forecast zone.
- Complete `floodroute-api:dev` image built from source, including the citizen frontend. API healthy on `8080`; `/app/?live=1`, health, and closure snapshots returned HTTP 200.
- Official digest-pinned Valhalla container healthy on `8002`, using the cached Bengaluru OSM clip and generated local road graph. Router version: `3.9.1-f28832966`.
- `tools/dev-backend.py --require-route --report` passed. Its explicitly synthetic report remained unmatched, so it created no road evidence.
- Operator-only webhook administration returned HTTP 401 anonymously and HTTP 200 with a configured operator credential. Credentials are excluded from these artifacts.

## Actual browser route

[Screenshot](self-hosted-route.png) · [API route response](road-route.json) · [Router status](router-status.json)

The public-landmark journey from Indiranagar to Silk Board returned HTTP 200, 203 decoded road vertices, and an 18-minute baseline estimate. Both matched segments were assessed as `unknown`; the frontend displayed **0 / 2 segments with known status**, an unassessed label, and the stale-data warning. The map rendered its route and both endpoint markers after loading. No browser exceptions occurred. The journey simulation remains a labelled demonstration.

## Sources and worker

[Health response](health.json) · [Closure snapshot](closure-snapshot.json)

- MET Norway requests succeeded and stored 62 rainfall forecast rows for the one configured zone. Forecast issue age was 10,041 seconds during the worker pass; successful HTTP access does not establish current flood observations.
- Two bounded SACHET passes stored 20 official alerts. The second pass flagged 79 pending items for later passes; the feed was still catching up.
- A complete worker `--once` cycle finished ingestion, scoring, retention, and four-city snapshots. The database then contained 86,128 road-risk rows, all `unknown`. Unsupported research vehicle classes were omitted from persistence without remapping.
- `rain_obs` remained empty. Source health was `degraded`; the Bengaluru snapshot contained zero closure features and remained `stale: true`. An empty snapshot is not evidence that roads are clear.
- The worker generated zero watch alert objects. No subscriptions or route watches were configured, and no subscriber message was sent. SMS/WhatsApp/push delivery still requires a provider integration.

## Reproduce

The final current-source backend suite passed **843 tests in 64.36 seconds**, with no skipped database checks. Ruff and diff checks passed. The existing Starlette TestClient/httpx deprecation warning was the only warning. Code, Python, database, and security reviews covered the release; the final security review reported no remaining critical/high findings in the audited changes.

Follow the [backend runbook](../../../docs/BACKEND_RUNBOOK.md) for secrets, inventory, graph preparation, and startup. Runtime build, test, smoke, ingest, worker, and browser logs are in `/tmp/floodroute-backend-release-*.log` on the checked machine; those logs are temporary and not deployment assets.

Public HTTPS hosting, rainfall observations, model calibration, field validation, city coverage, provider delivery, and the human gates in [G0 evidence](../../../docs/G0-evidence.md) remain outstanding.
