# FloodRoute hackathon handoff

Frontend preparation: 6 October 2026. The HHGoa submission deadline, portal, and required assets still need to be supplied by the project owner.

## Run the frontend

Use Node.js 24 and the repository's pinned pnpm 10.28.0. Run these commands from the repository root:

```sh
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @floodroute/citizen dev --host 0.0.0.0
```

Open `http://localhost:5173`. With no API origin configured, the frontend starts in **Demo** mode: routes, conditions, navigation events, and reports are local presentation examples. Use the **Live data** control or open `http://localhost:5173/?live=1` to request real API responses through the development proxy. A failed live route request shows an error instead of an invented route.

For a live local API, the Vite development proxy expects `http://127.0.0.1:8000`:

```sh
cd apps/api
python -m uvicorn floodroute.api.main:app --host 127.0.0.1 --port 8000
```

The API needs its Python dependencies, configured PostGIS database, migrations, road inventory, scored segments, and routing service. Starting the server alone does not provide live flood routing. The existing Docker Compose API instead exposes port `8080`; see the separate-origin configuration below when using it directly.

## Check and build

```sh
corepack pnpm --filter @floodroute/ui check
corepack pnpm --filter @floodroute/citizen check
corepack pnpm --filter @floodroute/citizen preview --host 0.0.0.0
```

`check` runs TypeScript, the existing Node tests, and Vite's production build. Open `http://localhost:4173` for the production preview. The deployable static files are in `apps/citizen/dist`; Vite preview is for local verification. The frontend GitHub Actions workflow runs the same checks with a frozen lockfile and uploads `floodroute-frontend` as a build artifact.

## Static hosting and API configuration

Configure a static host with repository root as the working directory, Node.js 24, pnpm 10.28.0, build command `pnpm install --frozen-lockfile && pnpm --filter @floodroute/citizen build`, and publish directory `apps/citizen/dist`.

Serve the frontend over HTTPS at the domain root or a directory such as `/app/` or `/flood-route/`. The manifest, app icon, service worker, and offline shell use relative, directory-scoped URLs. Use a trailing slash on directory URLs and configure the host to redirect `/app` to `/app/`, for example; relative Vite assets resolve against that directory. The API's existing `/app/` static mount can serve the locally built frontend when `apps/citizen/dist` is present, but the current API Docker image does not include that sibling directory.

Choose one API setup:

| Setup | Configuration |
| --- | --- |
| Presentation demo | No API configuration required. **Demo** is selected by default; no real report is posted. Label sample conditions, illustrative routes, and simulated navigation honestly. |
| API on the same origin | Leave `VITE_API_BASE_URL` empty and choose **Live data** or open `?live=1`. Configure the host's `/v1/*` reverse proxy to the API. Vite's development proxy is not included in the production build. |
| API on a separate origin | Set `VITE_API_BASE_URL` to the API origin **before building**, without a `/v1` suffix. Live mode is the default for a configured API origin. The API must permit the frontend origin with `FLOODROUTE_CORS_ORIGINS`; use HTTPS for both public origins. |

For example, to build against a local Docker API on port 8080:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8080 corepack pnpm --filter @floodroute/citizen build
```

For a public deployment, replace that value with the public API's HTTPS origin. `VITE_` values are bundled into browser JavaScript and must contain no secrets. `apps/citizen/.env.example` documents the same setting; copy it to `.env` in that directory if a local file is preferred. Rebuild after changing the API origin.

Verify the hosted app directory, `manifest.webmanifest`, `icons/floodroute.svg`, and `sw.js` return their expected files within that directory. Then test route planning, report submission, theme switching, and a narrow mobile viewport using the hosted build. Confirm that API requests reach the intended origin.

## Three-minute judge demo

1. Open the default Bengaluru view in **Demo** mode. Explain that FloodRoute plans around road conditions for the selected vehicle class.
2. Select a start and destination from the available presets; compare the car and two-wheeler controls. Plan a route and point out its ETA, risk state, and sample-data label. Explicitly identify the path as an illustrative demo.
3. Start the navigation simulation. Advance the position ticks to show the caution, detour suggestion, and hold states. Accept the proposed detour when it appears; explain that these are controlled demonstration events.
4. Open the flood-report form, choose a water-depth category, and submit a sample report. In Demo mode this is only a local demonstration; it is not uploaded or queued for later delivery. If demonstrating a connected live API separately, explain whether that report was sent or queued for retry.
5. Switch city and theme, then show the mobile layout. Close by distinguishing the frontend demonstration from the live data and routing work below.

## Demo and live limits

- Preset locations and corridor examples demonstrate the flow; they are not current field observations or a full address search.
- A generated demo path is illustrative. It is not a calculated road-network route and must not be used for travel guidance.
- The simulation advances through demonstration scenarios rather than tracking a real vehicle or receiving live navigation telemetry. It remains labelled as a demo even when live data is selected.
- Previously fetched snapshots and visited assets can be cached. Offline map coverage is not guaranteed, and first-load offline operation is unavailable. Service worker registration is skipped on localhost.
- Street tiles come from OpenStreetMap and use browser HTTP caching, following the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/). The schematic view remains available if tiles cannot load.
- In Live mode, queued reports remain in browser storage and retry when the app regains API access. Background Sync asks an open app client to flush; it does not independently upload reports after the app is closed. Evidence photos are excluded from the service worker's public cache.
- Live risk states and timestamps depend on the API and upstream data; an available health endpoint alone does not establish fresh, complete road coverage.

## Remaining work before a live pilot

1. Validate the API, PostGIS migrations, road-to-segment matching, and scored coverage end to end for each submitted city. Confirm no-route responses and unavailable services remain clear in the frontend.
2. Bring up Valhalla and verify route geometry, vehicle overlays, and detour behavior against the real road graph. Docker Compose currently defines database, API, and worker services, but no Valhalla service.
3. Confirm feed access, data terms, freshness, coverage, and calibration. The existing [G0 evidence pack](G0-evidence.md) tracks incomplete routing and human-dependent data/validation work.
4. Complete production handling for report photos, privacy, retention, moderation, and delivery retries. The hackathon frontend is an advisory demonstration, not an operational public warning system.

## Push preparation

- Run the token and frontend checks above, and verify the production build in a browser. Keep the existing API CI passing for backend changes.
- Review `git diff` and stage only intended source, metadata, CI, documentation, and sample artifacts. This checkout already contains backend work; preserve it and review its push scope separately.
- Check the target remote and branch before committing or pushing. Do not include `.env`, credentials, or local dependency directories.
- Prepare the hosted demo URL, repository URL, a short recorded walkthrough, and sample screenshots once the owner supplies the actual HHGoa submission requirements. These are preparation suggestions, not verified event requirements.

The source checkout excludes generated `apps/citizen/dist`. Both CI workflows build it; the API workflow builds before its frontend-serving tests. Run the frontend build locally before testing the API's `/app/` integration.
