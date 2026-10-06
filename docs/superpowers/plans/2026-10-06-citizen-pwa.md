# Citizen PWA Implementation Plan

Plan for completing the Citizen PWA mobile interface, pointer gesture bottom sheet, API integration, bundle build, and FastAPI static mounting.

## Context and Global Constraints
- Strict safety invariant: never use or render the word "safe" in any user-facing text, badges, or API responses (use "Clear", "Watch", "Risky", "Impassable").
- Zero em-dashes in any user-facing strings, code, or documentation (use hyphens, colons, or parentheses).
- Single-hand ergonomics: primary touch targets >= 48px height, bottom sheet accessible with one thumb.
- Privacy compliance (DPDP Act 2023): photo evidence uploaded via `/v1/reports/photo` must have EXIF stripped before persistence.
- Design tokens: import `@floodroute/ui/tokens.css` and use CSS custom properties (`--fr-canvas`, `--fr-surface`, `--fr-accent`, `--fr-radius-control`, `--fr-radius-sheet`, etc.).
- 100% test pass rate across `apps/api/tests/` and 0 ruff lint errors.

## Task 1: Create BottomSheet Gesture Component
Create `apps/citizen/src/components/BottomSheet.tsx` implementing a draggable bottom sheet with touch and pointer gestures.
Requirements:
- Three snap heights:
  - Collapsed: 96px (`6rem`)
  - Half: 50% dynamic viewport height (`50dvh`)
  - Expanded: 90% dynamic viewport height (`90dvh`)
- Pointer event handlers: `onPointerDown`, `onPointerMove`, `onPointerUp`, `onPointerCancel` with pointer capture on the drag handle.
- Velocity and distance threshold detection for snap point snapping.
- Smooth CSS transition when snapping (`cubic-bezier(0.16, 1, 0.3, 1)`).
- Handle bar indicator at the top for visual affordance.
- ARIA accessibility attributes: `role="dialog"`, `aria-label="Route details and actions"`.
- Clean TypeScript types for props (`initialSnap`, `children`, `title`, `headerExtra`).

## Task 2: Create App.tsx and main.tsx Assembly
Create `apps/citizen/src/App.tsx` and `apps/citizen/src/main.tsx` assembling the full Citizen PWA.
Requirements:
- In `main.tsx`:
  - Import `@floodroute/ui/tokens.css` and `./styles/app.css`.
  - Render `<App />` inside `#root`.
- In `App.tsx`:
  - Manage state: `theme` ("light" | "dark" | "sunlight" | "hc"), `lang` (Language), `vclass` (VehicleClass), `activeRoute` (PlannedRoute | null), `rerouteData` (RerouteResponse | null), `isSimulating` (boolean), `reportModalOpen` (boolean), `isOnline` (boolean).
  - Sync `theme` to `document.documentElement.setAttribute("data-theme", theme)`.
  - Poll `GET /v1/health` periodically or on mount to update `isOnline`.
  - Wire `Header` with theme selector, language selector, and report button.
  - Wire `RouteForm` submitting to `POST /v1/route` with origin, destination, and vehicle class.
  - Wire `RouteCard` displaying the current plan with worst-state chip, ETA, and reasons.
  - Wire `LiveSimulator` with step tick submitting to `POST /v1/route/reroute`.
  - Wire `ReportModal` submitting photo evidence to `POST /v1/reports/photo` and report to `POST /v1/reports`.
  - Render inside bottom sheet and main viewport layout.

## Task 3: Build and Verify Citizen PWA Production Bundle
Build and verify the citizen web application using pnpm and Vite.
Requirements:
- Ensure all TypeScript types are fully satisfied.
- Run `npx pnpm --filter @floodroute/citizen build`.
- Confirm `apps/citizen/dist` contains `index.html`, compiled `.js`, `.css`, and asset bundles.
- Check bundle size and ensure no build warnings or broken asset references.

## Task 4: Mount Citizen PWA in FastAPI API
Mount the citizen web application in the FastAPI backend so it is accessible over HTTP.
Requirements:
- In `apps/api/floodroute/api/main.py`:
  - Mount `/app` (and static assets) pointing to `apps/citizen/dist` when directory exists.
  - Add fallback route or static files handler so index.html is served cleanly.
  - Preserve existing `/static` console and API routes (`/v1/*`).
- Add tests in `apps/api/tests/api/test_api_citizen.py` verifying:
  - `GET /app` or `GET /app/` returns 200 OK with HTML content.
  - Citizen HTML contains FloodRoute title and script tags.

## Task 5: End-to-End Test Suite and Checkpoint 16 Documentation
Run full verification suite and update documentation.
Requirements:
- Run full pytest test suite across `apps/api/tests` (ensuring 100% pass rate).
- Run `ruff check floodroute tests` ensuring 0 lint errors.
- Run token verification `npx pnpm --filter @floodroute/ui check`.
- Record Checkpoint 16 in `PROGRESS_CHECKPOINTS.md` documenting:
  - Citizen PWA architecture, components, and BottomSheet gestures.
  - Token-based theming and multi-language support.
  - Live API integration with `/v1/route`, `/v1/route/reroute`, `/v1/reports/photo`, `/v1/reports`.
  - Build pipeline and FastAPI `/app` mount.
