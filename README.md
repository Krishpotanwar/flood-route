# FloodRoute

Flood-aware route planning for Indian cities. A responsive hackathon prototype with a monochrome frontend, vehicle selection, road conditions, community reports, and a controlled rerouting demonstration.

The presentation demo runs without an API. Its white and black frontend includes a subtle pointer-responsive dot background and a labelled hero route illustration. Dots stay static on touch devices and with reduced motion, and the animation stops when idle. [Progress checkpoints](PROGRESS_CHECKPOINTS.md) record completed work and verification.

![FloodRoute desktop preview](output/frontend-preview/2026-10-06-dots/desktop.png)

Actual browser capture with the dotted background and route illustration. Displayed conditions are labelled demo data.

## Run the demo

Use Node.js 24 and the pinned pnpm 10.28.0:

```sh
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @floodroute/citizen dev
```

Open `http://localhost:5173`. Demo mode works without a backend. Select a city and vehicle, plan a journey, and preview rising water, a detour, and a road closure. The supported city presets are Bengaluru, Mumbai, and Gurugram. White and black themes work on desktop and mobile.

Demo routes, travel times, and conditions are illustrative. Real observations and routing require a configured API and data sources. Simulation events and demo reports remain explicitly labelled.

## Build and check

```sh
corepack pnpm --filter @floodroute/ui check
corepack pnpm --filter @floodroute/citizen check
corepack pnpm --filter @floodroute/citizen preview
```

The current frontend check passed TypeScript, 18 Node tests, and the production build. Preview opens on `http://localhost:4173`; add `--port 5174` to use that port instead. Publish `apps/citizen/dist` on a static host; the default presentation demo requires no API configuration. Generated bundles are built locally and in CI, rather than committed.

## Deploy the frontend on Vercel

Import this repository with **Root Directory `.`** and **Node.js `24.x`**. Add the environment variable `ENABLE_EXPERIMENTAL_COREPACK=1`; Vercel uses it to honor the pinned pnpm version. Install, build, and output settings are provided by [vercel.json](vercel.json). See [Vercel's Corepack guidance](https://vercel.com/docs/builds/configure-a-build#corepack).

The frontend starts in Demo mode without an API environment variable. A separate live API can be connected later with `VITE_API_BASE_URL`; Vercel's static frontend deployment does not start the Python backend.

## Connect the backend

The verification below describes the current local working tree, including pending API safety/governance changes and migrations. Those API changes are separate from this frontend push; the local runtime evidence is not a claim that the backend has been deployed.

Follow the [backend runbook](docs/BACKEND_RUNBOOK.md) for API dependencies, PostGIS setup, migrations, routing configuration, and container commands. The current source API serves the built app at `http://127.0.0.1:8080/app/?live=1`. In Vite, select **Live data** or open `http://localhost:5173/?live=1`. Both development and preview servers proxy `/v1` to `http://127.0.0.1:8080`; override the local API target when needed:

```sh
FLOODROUTE_DEV_API_URL=http://127.0.0.1:8000 corepack pnpm --filter @floodroute/citizen dev
```

`FLOODROUTE_DEV_API_URL` configures the local Vite servers. For a deployed frontend on a separate origin, set `VITE_API_BASE_URL` **before building** and configure API CORS; the local proxy is not part of the static bundle.

The current source backend was verified against isolated PostGIS on port `54330`, with eight migrations and 5,383 Bengaluru road segments loaded. The app, health, and snapshot endpoints returned HTTP 200. An initial public-landmark route through the external Valhalla demo returned 203 road-shape vertices; its flood state was `unknown` with zero assessed segments. The worker then persisted 86,128 risk rows, all `unknown`. The connected frontend displayed the real road geometry and counted only known road statuses. Snapshots remained empty and stale because current observations were missing.

The fresh API image build is blocked by PyPI connectivity, and the self-hosted Valhalla image pull failed before graph construction. The source API works locally; a fresh container deployment and self-hosted routing remain unverified. The runbook includes the native-source fallback and full verification evidence.

Live routing needs a configured routing service and road coverage. API availability alone does not establish fresh flood observations. Failed live requests show errors rather than demo routes; navigation previews remain explicitly simulated.

For the API integration:

```sh
cd apps/api
FLOODROUTE_REQUIRE_DB=1 .venv/bin/pytest -q
.venv/bin/ruff check floodroute tests
```

The API suite needs PostGIS at `DATABASE_URL_ADMIN` (default `postgresql://postgres@127.0.0.1:54329/postgres`). Requiring the database makes an unavailable test database fail instead of skipping integration checks. Build the frontend first for the `/app/` serving tests. The API and frontend CI workflows perform that build from source.

## Submission material

- [Hackathon runbook, deployment configuration, and judge walkthrough](docs/HACKATHON.md)
- [Backend setup and known limitations](docs/BACKEND_RUNBOOK.md)
- [Work progress and verified checkpoints](PROGRESS_CHECKPOINTS.md)
- Current browser screenshots: [desktop](output/frontend-preview/2026-10-06-dots/desktop.png), [mobile](output/frontend-preview/2026-10-06-dots/mobile.png), [planned route](output/frontend-preview/2026-10-06-dots/route.png), and [black theme](output/frontend-preview/2026-10-06-dots/black-planner.png)
- [Connected road route with unknown flood status](output/frontend-preview/2026-10-06-dots/live-route.png) and [browser verification record](output/frontend-preview/2026-10-06-dots/verification.md)
- [Original visual references and generation prompts](output/design-samples/2026-10-06-white-minimal/prompts.md)
- [Product and engineering documentation](docs/README.md)

Frontend: React, TypeScript, Vite, and MapLibre. Backend: FastAPI and PostGIS, with routing integration and scoring modules. Live route coverage, Valhalla setup, source access, and field calibration remain tracked in the [G0 evidence pack](docs/G0-evidence.md).
