# FloodRoute hackathon handoff

Last verified: **8 October 2026**. The HHGoa submission deadline, portal, and required assets still need to be supplied by the project owner.

Track completed work and verification in [Progress checkpoints](../PROGRESS_CHECKPOINTS.md). The frontend source passes TypeScript, 18 Node tests, and the production build. The [backend runbook](BACKEND_RUNBOOK.md) documents the verified Docker API, ten migrations, self-hosted Bengaluru router, and source-data limits. The latest complete backend run passed 879 tests with one expected opt-in graph skip; 71 focused tests passed after the final client cleanup, and Ruff passed. Current [desktop](../output/frontend-preview/2026-10-06-dots/desktop.png), [mobile](../output/frontend-preview/2026-10-06-dots/mobile.png), and [black theme](../output/frontend-preview/2026-10-06-dots/black-planner.png) captures show the dotted background and labelled hero route illustration.

## Run the frontend

Use Node.js 24 and the repository's pinned pnpm 10.28.0. Run these commands from the repository root:

```sh
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @floodroute/citizen dev --host 0.0.0.0
```

Open `http://localhost:5173`. With no API origin configured, the frontend starts in **Demo** mode: routes, conditions, navigation events, and reports are local presentation examples. Use the **Live data** control or open `http://localhost:5173/?live=1` to request real API responses through the development proxy. A failed live route request shows an error instead of an invented route.

The frontend now includes a whole-page dot background that reacts subtly to a pointer, stays static for touch and reduced motion, and stops animating when idle. The hero route is a labelled SVG illustration; it is separate from the road route returned by the API.

The Vite development and preview proxies expect the local API at `http://127.0.0.1:8080`. Complete the environment/database setup in the [backend runbook](BACKEND_RUNBOOK.md) first. The verified Docker API also serves the built citizen app at `http://127.0.0.1:8080/app/?live=1`.

To use a different API port in Vite:

```sh
FLOODROUTE_DEV_API_URL=http://127.0.0.1:8000 corepack pnpm --filter @floodroute/citizen dev
```

The API needs Python dependencies, configured PostGIS, migrations, road inventory, source observations, and a routing service. Starting the server alone does not provide live flood guidance. The Compose defaults use loopback API port `8080` and isolated database port `54330`, leaving the existing test database on `54329`. Required startup secrets, inventory seeding, the worker, and optional self-hosted routing are described in the runbook.

## Check and build

```sh
corepack pnpm --filter @floodroute/ui check
corepack pnpm --filter @floodroute/citizen check
corepack pnpm --filter @floodroute/citizen preview --host 0.0.0.0
```

`check` runs TypeScript, the existing Node tests, and Vite's production build. Open `http://localhost:4173` for the production preview, or append `--port 5174` to use `http://localhost:5174`. Preview uses the same `FLOODROUTE_DEV_API_URL` override as development. The deployable static files are in `apps/citizen/dist`; Vite preview is for local verification. The frontend GitHub Actions workflow runs the same checks with a frozen lockfile and uploads `floodroute-frontend` as a build artifact.

## Static hosting and API configuration

For Vercel repository import, keep **Root Directory `.`**, select **Node.js `24.x`**, and set `ENABLE_EXPERIMENTAL_COREPACK=1`. The root `vercel.json` supplies the install command, citizen build command, and output directory. Leave `VITE_API_BASE_URL` unset for the presentation demo. [Corepack setup](https://vercel.com/docs/builds/configure-a-build#corepack).

If using the Vercel CLI, upgrade the installed `50.37.3` before deploying (`62.7.0` is the current recommended version): `npm i -g vercel@latest` or `pnpm add -g vercel@latest`. Repository import through the dashboard does not require the local CLI.

Configure a static host with repository root as the working directory, Node.js 24, pnpm 10.28.0, build command `pnpm install --frozen-lockfile && pnpm --filter @floodroute/citizen build`, and publish directory `apps/citizen/dist`.

Serve the frontend over HTTPS at the domain root or a directory such as `/app/` or `/flood-route/`. The manifest, app icon, service worker, and offline shell use relative, directory-scoped URLs. Use a trailing slash on directory URLs and configure the host to redirect `/app` to `/app/`, for example; relative Vite assets resolve against that directory. The API's `/app/` static mount serves the locally built frontend when `apps/citizen/dist` is present. The Dockerfile builds this frontend from the repository root, and the fresh complete API image passed its local serving checks on 7 October.

Choose one API setup:

| Setup | Configuration |
| --- | --- |
| Presentation demo | No API configuration required. **Demo** is selected by default; no real report is posted. Label sample conditions, illustrative routes, and simulated navigation honestly. |
| API on the same origin | Leave `VITE_API_BASE_URL` empty and choose **Live data** or open `?live=1`. Use the API's `/app/` mount, or configure the host's `/v1/*` reverse proxy to the API. Vite's development/preview proxy is not included in the production build. |
| API on a separate origin | Set `VITE_API_BASE_URL` to the API origin **before building**, without a `/v1` suffix. Live mode is the default for a configured API origin. The API must permit the frontend origin with `FLOODROUTE_CORS_ORIGINS`; use HTTPS for both public origins. |

For example, to build against a local Docker API on port 8080:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8080 corepack pnpm --filter @floodroute/citizen build
```

For a public deployment, replace that value with the public API's HTTPS origin. `VITE_` values are bundled into browser JavaScript and must contain no secrets. `apps/citizen/.env.example` documents the same setting; copy it to `.env` in that directory if a local file is preferred. Rebuild after changing the API origin.

This repository's Vercel configuration deploys the citizen frontend. It does not start the Compose database, worker, or road router. Configure and verify the public API separately before claiming a connected deployment. Operator credentials belong only in the backend environment and the operator console's in-memory key field; Vercel frontend configuration does not automatically authenticate operator requests.

Verify the hosted app directory, `manifest.webmanifest`, `icons/floodroute.svg`, and `sw.js` return their expected files within that directory. Then test route planning, report submission, theme switching, and a narrow mobile viewport using the hosted build. Confirm that API requests reach the intended origin.

## Three-minute judge demo

1. Open the default Bengaluru view in **Demo** mode. Explain that FloodRoute plans around road conditions for the selected vehicle class.
2. Select a start and destination from the available presets; compare the car and two-wheeler controls. Plan a route and point out its ETA, risk state, and sample-data label. Explicitly identify the path as an illustrative demo.
3. Start the navigation simulation. Advance the position ticks to show the caution, detour suggestion, and hold states. Accept the proposed detour when it appears; explain that these are controlled demonstration events.
4. Open the flood-report form, choose a water-depth category, and submit a sample report. In Demo mode this is only a local demonstration; it is not uploaded or queued for later delivery. If demonstrating a connected live API separately, explain whether that report was sent or queued for retry.
5. Switch city and theme, then show the mobile layout. Close by distinguishing the frontend demonstration from the live data and routing work below.

For a connected-source demo, the verified Docker API on port `8080` serves real road geometry through its self-hosted Bengaluru Valhalla graph on `8002` ([7 October browser capture](../output/backend-verification/2026-10-07/self-hosted-route.png)). Its isolated database has 5,383 OSM-derived road segments and 233 hotspot matches. The 8 October image and migration 0010 were verified, and the route-required smoke check passed. A new opt-in integration test verified a detour around a synthetic blocked interior graph edge, plus `no_safe_route` when the origin was blocked; it never changed demo road states. MET Norway supplied 62 forecast rows for the one configured Bengaluru zone. The 7 October SACHET catch-up stored 100 alerts, but 80 lacked polygons; the 8 October worker stored ten new alerts and flagged 89 pending. Rain observations remain absent. Present this as API/road-routing integration with limited source ingestion, not verified live flood guidance. Use the [backend smoke check](BACKEND_RUNBOOK.md#smoke-check) to reproduce the endpoint checks.

## Demo and live limits

- Preset locations and corridor examples demonstrate the flow; they are not current field observations or a full address search.
- A generated demo path is illustrative. It is not a calculated road-network route and must not be used for travel guidance.
- The simulation advances through demonstration scenarios rather than tracking a real vehicle or receiving live navigation telemetry. It remains labelled as a demo even when live data is selected.
- Previously fetched snapshots and visited assets can be cached. Offline map coverage is not guaranteed, and first-load offline operation is unavailable. Service worker registration is skipped on localhost.
- Street tiles come from OpenStreetMap and use browser HTTP caching, following the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/). The schematic view remains available if tiles cannot load.
- In Live mode, queued reports remain in browser storage and retry when the app regains API access. Background Sync asks an open app client to flush; it does not independently upload reports after the app is closed. Evidence photos are excluded from the service worker's public cache.
- Live risk states and timestamps depend on the API and upstream data; an available health endpoint alone does not establish fresh, complete road coverage.

## Remaining work before a live pilot

1. Deploy the frontend and supply its hosted URL for browser verification. Provision the public API, PostGIS, worker, and routing services if the submission needs connected functionality; local health checks do not establish a hosted deployment.
2. Obtain current rain observations, finish alert-feed catch-up, and validate forecast freshness, scored coverage, and road-to-segment matching for every submitted city. Forecast rows and road geometry alone do not establish live flood assessments.
3. Confirm data terms, model calibration, and field accuracy. The [G0 evidence pack](G0-evidence.md) records the remaining human-dependent observation, terms, and validation gates. Verify vehicle overlays and detours against real conditions before a live pilot.
4. Connect and verify actual SMS, WhatsApp, or push delivery if subscriber alerts are required. Worker `alerts_generated` counts computed objects; provider delivery is still pending. Confirm production report moderation, photo storage/retention, privacy, and delivery retries. The hackathon frontend remains an advisory demonstration.

## Push preparation

- Run the token and frontend checks above, and verify the production build in a browser. Keep the existing API CI passing for backend changes.
- Review `git diff` and stage only intended source, metadata, CI, documentation, and sample artifacts. This checkout already contains backend work; preserve it and review its push scope separately.
- Check the target remote and branch before committing or pushing. Do not include `.env`, credentials, or local dependency directories.
- Prepare the hosted demo URL, repository URL, a short recorded walkthrough, and sample screenshots once the owner supplies the actual HHGoa submission requirements. These are preparation suggestions, not verified event requirements.

The source checkout excludes generated `apps/citizen/dist`. Both CI workflows build it; the API workflow builds before its frontend-serving tests. Run the frontend build locally before testing the API's `/app/` integration. Record the final verification and any unfinished deployment work in [Progress checkpoints](../PROGRESS_CHECKPOINTS.md).
