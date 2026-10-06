# Frontend verification

Verified 6 October 2026 against the production Vite preview.

- TypeScript, 17 frontend tests, production build, and shared token checks pass.
- 18 browser checks pass at 1440px desktop and 390px/375px mobile.
- Real street-map captures confirm both endpoints fit, white/black themes preserve markers, and demo requests do not call the API. No page errors or unexpected console errors.
- API suite: 806 passed; API lint passes. Frontend-serving integration verifies the native `/app/` redirect preserves the live-mode query.
- Live service failures and stale snapshots were exercised with network mocks. Successful production live routing requires configured data sources and Valhalla.

Screenshots: [desktop](desktop.png), [mobile](mobile.png), [route](route.png), [black planner](black-planner.png).
