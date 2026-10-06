# Cursor session log

Handoff log for work after Antigravity. Update this file at the start and end of each Cursor slice. Do not treat `PROGRESS_CHECKPOINTS.md` as the Cursor log; that file stays the Antigravity checkpoint mill.

**Claude-mem:** observer allowance exhausted since 2026-09-17 (`Provider reported the inference allowance exhausted`). This session is not remembered. Do not restart the worker.

**Ponytail:** ultra. No new product surface unless it is on the Phase 0 critical path.

---

## 2026-10-06 resume

### Where Antigravity stopped

- Branch: `claude/floodroute-project-plan-g5cntf`
- Last commit: `c6c6875` kill switch / advisory freeze (Checkpoint 26)
- Tests claimed: 694 pytest, 0 ruff
- Uncommitted leftovers:
  - `PROGRESS_CHECKPOINTS.md`: Checkpoint 26 notes (code already committed)
  - `apps/api/Dockerfile`: started, not wired. Broken COPY (`floodroute/` plus `apps/api/floodroute/` from the same context). No compose. No CI. Entrypoint is a no-op `sh -c` wrapping a uvicorn CMD that does not select worker mode despite comments.
- Calendar: Phase 0 week 1 (`docs/PLAN.md`). Engineering already jumped to an R1-shaped stack (PWA, WhatsApp, webhooks, Mumbai/Gurugram, Prometheus). Partnerships, counsel, IMD, DLT, interviews are human-only and still undone.

### Gaps that still matter

| Need | Status |
|---|---|
| SACHET + MET Norway ingest, Valhalla S1, Bengaluru inventory, v0 score, API, console, PWA | Built |
| Docker image that actually builds and runs API + worker | Leftover, broken |
| CI (pytest + ruff, PostGIS) | Missing. Tests mention `FLOODROUTE_REQUIRE_DB=1` |
| Local PostGIS | `infra/dev/pg.sh` (port 54329) already exists |
| Chennai hotspot seed for NE monsoon shadow / G0 | Registry entry exists (`city_id=2`, bbox `80.05,12.85,80.35,13.25`) with `hotspot_count=0` and no CSV |
| GCC 859 full list | Not in repo. Do not invent 859 points |

### Decision this session

User: pick a path. Cursor default: run two exclusive agents, keep this log.

1. **Harden** (infra only): fix Dockerfile, add compose, add GitHub Actions.
2. **Next Phase 0 task:** Chennai chronic hotspot seed (~20 rows, same pattern as Mumbai/Gurugram), provenance via `hotspots.validate`, wire `CITY_REGISTRY.hotspot_count`.

No git commits unless the user asks.

### Path ownership (do not collide)

| Owner | Writes |
|---|---|
| Harden agent | `apps/api/Dockerfile`, `apps/api/.dockerignore`, `docker-compose.yml`, `.github/workflows/` |
| Chennai agent | `data/hotspots/chennai_seed.csv`, `data/hotspots/chennai.csv`, `apps/api/floodroute/inventory/multicity.py` (count/metadata only), `apps/api/tests/inventory/test_inventory_multicity.py`, `apps/api/tests/api/test_api_cities.py` |
| Main session | `cursor.md`, later `PROGRESS_CHECKPOINTS.md` if a checkpoint is recorded |

### Status

- [x] Context restored
- [x] `cursor.md` created
- [x] Harden agent `a9223508-10c0-4b1c-95a3-4e328b40e9b7`
- [x] Chennai agent `ee50a715-774d-4ced-8a2f-6b776c87e4a7`
- [x] Integrate, one pytest + ruff check, update this log

### Opencode closeout (2026-10-06, SDD plan `docs/superpowers/plans/chennai-harden-closeout.md`)

Both paths closed via subagent-driven-development, each with task review and a
final whole-branch review. Log: `opencode.md`. Workspace:
`.superpowers/sdd/chennai-harden-closeout/`.

- Harden: verified + minimal fix (Docker `WORKDIR /app/apps/api` so
  `score/config.py parents[4]` resolves; read-only compose mount for
  `data/config/scoring.v0.json` on api and worker). `docker compose config`
  and `docker build` exit 0; in-container `load_config()` OK.
- Chennai: 20 verified rows shipped (`data/hotspots/chennai_seed.csv`,
  `data/hotspots/chennai.csv`), registry `hotspot_count` 0 to 20, mirrored
  tests. Reviewer spot-fetched 3/20 source URLs, all corroborate.
- Fresh evidence: 36 passed (multicity + cities + score config), ruff clean.
- Final verdict: Ready to merge. No commits made (rule carries over).
