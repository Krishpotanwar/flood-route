# Graph-edge routing verification — 8 October 2026

The previous [connected browser screenshot](../2026-10-07/self-hosted-route.png) is a genuine 7 October capture of the earlier maneuver mapping. The 8 October browser recapture failed when Docker Desktop quit during the run, so this folder contains no new screenshot or API response presented as a successful capture.

## Source and database

- The rebuilt `floodroute-api:dev` image started on loopback port `8080`. Its migration service applied migration 0010; the isolated PostGIS database reported ten migrations and the `segment_assessed_osm_way_idx` index. The existing genuine Bengaluru inventory has 5,383 road segments.
- `python3 tools/dev-backend.py --require-route` passed against the Docker API and self-hosted Bengaluru Valhalla. Health and snapshot returned HTTP 200; the snapshot was stale with zero closure features; the route endpoint returned one real route and `no_safe_route: false`.
- The source fixture [`indiranagar_silk_board.json`](../../../apps/api/tests/route/fixtures/indiranagar_silk_board.json) records a genuine Valhalla 3.9.1 route and strict `edge_walk` trace for public Bengaluru landmarks. It has 102 graph edges. The map geometry is checked against the trace before any segment is assessed.
- The opt-in `test_route_live.py` passed against that local graph with synthetic risk only in a disposable `fr_test_*` database: a blocked interior graph edge produced a detour, while a blocked origin produced `no_safe_route`. This checks routing behavior, not the accuracy of flood observations.

## Tests and source freshness

- Published [API CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37809981322) passed **879 tests** with two expected skips: the opt-in live graph test and an optional `osmium` test. [Frontend CI](https://github.com/Krishpotanwar/flood-route/actions/runs/37809981418) passed on the same source commit. Locally, 71 focused route/API tests passed after the final HTTP-client lifecycle edit, and Ruff and `git diff --check` passed. A local full rerun was interrupted when Docker Desktop quit; its database connection errors are not counted as code failures or as a pass.
- The 7 October bounded SACHET catch-up stored 100 alerts. At inspection, 80 lacked area geometry: 72 polygon fetches were skipped after HTTP 403 and eight directly returned HTTP 403. Those rows keep their raw CAP and error provenance; no geometry was invented.
- On 8 October, a complete worker step stored ten newly published SACHET items and flagged 89 items pending; MET Norway returned 62 forecast rows. The worker reported 64,596 score changes, zero generated watch alerts, and four empty closure snapshots. The database had zero active route watches and zero webhook subscriptions before that step. `rain_obs` was empty at inspection, so route status is not evidence of current street-level flood safety.

## Remaining work

Public backend hosting and the Vercel frontend URL have not been supplied. Current rain observations, area recovery for SACHET's HTTP 403 responses, inventory coverage, calibrated road-risk accuracy, and subscriber delivery remain unverified. The graph-edge mapper fails closed when multiple assessed rows of the same OSM way fall within its 50 m proximity query; interval-level inventory splitting is the next upgrade if that ceiling affects a real route.
