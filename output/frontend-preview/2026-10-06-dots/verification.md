# Browser captures: 6 October 2026

Production preview: `http://127.0.0.1:5174/`, with current source API on port 8080.
Captured asset: `index-CMWuZY0L.js`.

- TypeScript, 18 Node tests, and production build passed.
- All 18 journey checks passed at desktop 1440px and mobile 390px/375px, including demo planning, scenarios, reports, navigation, stale observations, and live-request errors.
- Canvas checks passed for pointer repulsion, return to grid, stopped rendering when settled, static reduced-motion/touch behavior, and pixel density capped at 1.5. This was functional verification, not a frame-rate benchmark.
- Desktop/mobile captures used actual OpenStreetMap tiles; all observed tile responses were 200. No browser exceptions or unexpected console errors. Demo mode made no API requests.
- Connected preview health and snapshots returned 200 through the Vite proxy. A real route request returned 203 decoded road vertices and unknown flood status. After the worker, two segments had model rows, both unknown; neither counts as a known road status.
- The final known-status counter was checked by replaying that recorded API response, without another upstream routing request. `live-route.png` shows that response with real health/snapshot endpoints and the corrected counter.
- Frontend and infra reviews completed; the stale proxy comment and missing-status counter guard were corrected. Python smoke-script review reported no actionable issues.

`desktop.png`, `mobile.png`, `route.png`, and `black-planner.png` show explicitly labelled demo conditions. The hero strip is a route illustration, not a geographical route or flood observation. `live-route.png` shows actual road geometry but no known flood statuses.

`overview.png` is an additional actual 1440×1000 landing-page capture for the README gallery. It was captured from the production preview with service workers blocked and no browser exceptions; it does not add or change any route observations.

Fresh container installation and self-hosted Valhalla graph construction remain blocked by recorded network failures. Forecast ingestion still needs a real contact value; current observations and field calibration are unavailable. See the [backend runbook](../../../docs/BACKEND_RUNBOOK.md) and [checkpoints](../../../PROGRESS_CHECKPOINTS.md).
