# Opencode session log

Continuation of Cursor session (`cursor.md`) after Antigravity checkpoints 1-26
(`PROGRESS_CHECKPOINTS.md`, commit `c6c6875`, 694 tests claimed).

Skills in force (inherited from prior agents, reloaded via skill tool):
- `ponytail` at level `ultra` (per `CLAUDE.md`; governs all code choices)
- `subagent-driven-development` (execution: fresh implementer per task + task review + final review)
- `requesting-code-review` (review dispatch template)
- `verification-before-completion` (no completion claims without fresh command evidence)

## 2026-10-06 resume (opencode)

### Inherited state
- Branch: `claude/floodroute-project-plan-g5cntf` (HEAD `c6c6875` kill switch).
- Uncommitted Harden output (from Cursor Harden agent, not yet verified):
  - `apps/api/Dockerfile` (fixed COPY vs the broken version noted in `cursor.md`)
  - `apps/api/.dockerignore`
  - `docker-compose.yml` (db on 54329, api + worker services)
  - `.github/workflows/api.yml` (pytest + ruff on PostGIS service)
- Chennai work (Cursor Chennai agent `ee50a715`) has NO output in tree:
  - No `data/hotspots/chennai_seed.csv`, no `data/hotspots/chennai.csv`.
  - `CITY_REGISTRY["chennai"].hotspot_count` is still `0`.
  - `load_city_hotspots("chennai")` returns `[]` (no CSV on disk).
- `PROGRESS_CHECKPOINTS.md` has uncommitted Checkpoint 26 notes (code committed in `c6c6875`).

### Pre-flight verification (main session, before SDD)
- `apps/api/pyproject.toml`: `[project.optional-dependencies] dev` exists, so CI
  `pip install -e ".[dev]"` is valid.
- `floodroute/score/config.py:17` DEFAULT_PATH resolves to repo-root
  `data/config/scoring.v0.json` (parents[4]). Docker build context is `apps/api`,
  so the image has NO `data/` tree. Scoring in-container would fall back to
  baked defaults or fail if the file is required at runtime. Flagged as the one
  real Harden gap; fix must be minimal (mount or context change, not a rebuild).
- `docker-compose.yml` ports and healthcheck match `infra/dev/pg.sh` convention (54329).
- No em-dashes in this log. Safety invariant holds (never "safe").

### SDD plan
Plan file: `docs/superpowers/plans/chennai-harden-closeout.md`
Workspace: `.superpowers/sdd/chennai-harden-closeout/` (via `sdd-workspace` script)

| Task | Scope | Owner writes only |
|---|---|---|
| 1. Harden closeout verify+fix | `apps/api/Dockerfile`, `docker-compose.yml`, `.github/workflows/api.yml` (scoring config availability only; no rebuild) | implementer A |
| 2. Chennai chronic hotspot seed (~20 rows) | `data/hotspots/chennai_seed.csv`, `data/hotspots/chennai.csv`, `multicity.py` count only, `test_inventory_multicity.py`, `test_api_cities.py` | implementer B |

Path ownership enforced. No commits unless asked (Cursor rule carries over).
`PROGRESS_CHECKPOINTS.md` stays the Antigravity mill; `cursor.md` stays the
Cursor log; this file is the opencode log.

### Ledger
- [x] Context restored, skills reloaded (ponytail, sdd, requesting-code-review, verification-before-completion)
- [x] opencode.md created
- [x] SDD Task 1 dispatched, reviewed (Spec PASS, Quality Approved, no fix loop)
- [x] SDD Task 2 dispatched, reviewed (Spec PASS, Quality Approved, no fix loop)
- [x] Final whole-branch review dispatched (Ready to merge, 3 parked infos, no fix wave)
- [x] Fresh pytest + ruff evidence, logs updated

### SDD execution record (BASE `c6c6875`, sequential, no parallel implementers)

Task 1 Harden closeout (implementer A, Task 2 brief untouched until Task 1 done):
- Implementer found a deeper root cause than the pre-flight note: not just a
  missing data file, `config.py:17 parents[4]` raises `IndexError` at import time
  under old `WORKDIR /app` (only 4 parents). Fix: `WORKDIR /app/apps/api`
  (1 line + comment) plus read-only compose mount of
  `./data/config/scoring.v0.json` to `/app/data/config/scoring.v0.json` on api
  and worker. Evidence: `docker compose config` exit 0, `docker build` exit 0,
  in-container `load_config()` prints `model_version: v0.0.1, exists: True`,
  host `test_score_config.py` 27 passed, ruff clean.
- Reviewer independently reproduced the `IndexError` mechanics, confirmed CI
  install matches the `dev` extra, entrypoints resolve under new WORKDIR,
  banned-token scan clean. Spec PASS, Quality Approved.

Task 2 Chennai seed (implementer B, owned paths only):
- Shipped 20 verified rows with per-row consulted URLs (Michaung Dec 2023,
  Fengal Nov 2024, Oct 2024 NE onset). Dropped Maduravoyal (no
  flooding-specific source) and did not use the GCC 859 list (no citable copy).
  Extra verified points (Pallavaram, Thiruvottiyur, Tambaram, Villivakkam,
  Porur) cut to hold 20-parity and recorded as extension candidates.
- Registry one-liner (`hotspot_count` 0 to 20), mirrored tests, `validate` OK,
  subset 9 passed, ruff clean.
- Reviewer re-ran header/row/bbox/validate/keyword/parity checks, fetched 3/20
  URLs (all corroborate, including weakest-domain `tamilthoguppu.com`), confirmed
  one-line registry diff. Spec PASS, Quality Approved.

Final review: Ready to merge. Parked (all fail-closed, none fix-now): dev-grade
bind mount, lazy `parents[4]` sites, hotspot CSVs absent from image (in-container
hotspot loads return truthful empty). One new info: `/v1/cities/chennai` reports
registry `hotspot_count: 20` while `/hotspots` returns `total_hotspots: 0`
in-container; cosmetic, pre-existing pattern for all cities.

### Fresh verification (main session, this message)
- `cd apps/api && .venv/bin/pytest
  tests/inventory/test_inventory_multicity.py tests/api/test_api_cities.py
  tests/score/test_score_config.py -q` gives 36 passed in 1.92s.
- `.venv/bin/ruff check floodroute tests` gives All checks passed.
- Scope note: targeted subset only (touched surface). Full suite needs Postgres
  per `FLOODROUTE_REQUIRE_DB` and was not re-run; prior full-suite claim stands
  at Checkpoint 26 (694 passing).

### Rulings I made
- Harden fix shape (WORKDIR depth mirror + ro mount over build-context
  restructure): chose smallest change that un-breaks container import. Costs if
  wrong: prod-without-checkout still fails closed; bake-in needs context change.
- Chennai 20-row parity over larger verified set: keeps registry/tests/count in
  lockstep. Costs if wrong: extension later must bump all three together.
- No fix wave after final review (SDD rule: one wave max, residuals adjudicated):
  all residuals parked as fail-closed infos. Costs if wrong: first container run
  without compose mount errors instead of degrading silently (intended).

No commits made (rule carries over). Working tree holds the change set for review.
