# G0 closeout plan (autonomous engineering remainder)

Finish every automatable Phase 0 engineering item. Human-only items
(partnerships, counsel, IMD/DLT/WhatsApp onboarding, interviews, field survey,
VAPT, insurance) are out of scope and will be listed as blocked, not built.

## Context and Global Constraints
- Ponytail ultra: shortest diff, no new dependencies, no unverifiable code.
  Do NOT build an IMERG adapter (NASA Earthdata login is human-gated and live
  data cannot be verified from here); record it as blocked instead.
- Safety invariant: never emit the word "safe" in user-facing text or docs
  (use "Clear", "Watch", "Risky", "Impassable"). Zero em-dashes.
- Trust boundaries: `hotspots.validate` provenance rules; two-operator
  overrides; audit log append-only. Do not weaken any of them.
- Live dev DB: Docker container `floodroute-test-pg`, host port 54329,
  database `floodroute`. Known state: city 1 (Bengaluru) 5383 segments with
  86128 risk rows; city 2 (Chennai) 1550 segments with NO risk rows;
  `observed_event` 12 rows; `official_alert` 10; `rain_fcst` 63.
- Never invent numbers. Every figure in the evidence doc comes from a command
  you ran; quote commands and outputs.
- No git commits (main session commits). Scratch output stays out of the repo.

## Task 3: Chennai shadow scoring run plus G0 evidence pack
Owned writes: `apps/api/floodroute/score/` (only if a minimal city-scoping
change is required, prefer existing entry points), `docs/G0-evidence.md` (new),
plus read-only everything else. Small test additions allowed only if they cover
new code paths you added.
Requirements:
- Chennai shadow run: check `segment_static` priors exist for the 1550 Chennai
  segments. If priors are missing, do NOT invent them; report BLOCKED with the
  exact counts. If present, run the existing shadow scoring entry point
  (`execute_score_run` in `floodroute/score/db.py`, same path Checkpoint 10
  used) for Chennai and verify the expected risk-row multiple
  (segments x 4 vehicle classes x 4 horizons) landed in `segment_risk` and
  history/audit rows were written.
- G0 evidence pack `docs/G0-evidence.md`: run the existing backtest CLI
  (`python -m floodroute.score backtest`, including `--seed-benchmark` state
  check and `--audit-matrix` if it completes in reasonable time) and record the
  real POD, FAR, CSI/accuracy numbers per event/horizon, the shadow-run stats
  for both cities, and a gate checklist mapping each G0 criterion from
  `docs/PLAN.md` section 2 to status done / blocked-human with one line each.
  No invented figures; stale or failed runs are reported as such, not smoothed.
- Verification: relevant pytest subset for anything touched, `ruff check` on
  touched Python files, banned-token scan on the new doc. Report exact commands
  and outputs.

## Task 4: Chennai rain inputs, benchmark dedupe, evidence refresh
Follow-up to Task 3 findings (all-Chennai-unknown for lack of rain inputs;
`observed_event` double-seeded; backtest POD 0.0 on stale inputs).
Owned writes: `apps/api/floodroute/ingest/` (only if a minimal Chennai-zone
change is required, prefer existing `metno --once` entry point),
`apps/api/floodroute/score/backtest.py` (idempotent benchmark seeder only),
`apps/api/tests/score/test_score_backtest.py` (idempotency test only),
`docs/G0-evidence.md` (refresh numbers only). Read-only elsewhere.
Requirements:
- MET Norway ingest for Chennai: Checkpoint 6 ran `floodroute.ingest metno
  --once` for a seeded Bengaluru zone under CC BY 4.0 rules (User-Agent with
  contact, max 20 req/s, <=4 decimals; see `docs/outreach/data-terms-tracker.md`
  and `Checkpoint 4`). Do the same for a Chennai zone (city 2 center
  13.0827, 80.2707): seed the zone row if the existing seeder supports it,
  run the existing `--once` entry point, verify `rain_fcst` rows landed for
  the Chennai zone. No new adapter code unless the existing entry point cannot
  address a second zone, then smallest change possible.
- Benchmark dedupe: `observed_event` holds 6 events x 2 copies. Deduplicate to
  6 canonical rows (keep earliest row per event, delete exact-duplicate
  copies; verify counts before and after) and make `seed_benchmark_events`
  idempotent (re-running `--seed-benchmark` adds zero rows; prove by running it
  twice). Minimal diff: guard clause or ON CONFLICT style dedupe, whichever is
  smaller. Add one test asserting double-seed yields no new rows.
- Refresh: re-run the Chennai/Bengaluru shadow scoring entry point and the
  backtest car/0m numbers, then update ONLY the affected figures in
  `docs/G0-evidence.md` (shadow run id, state distribution, POD/FAR/CSI,
  Brier). If states are still unknown, report that honestly; do not tune
  thresholds to manufacture signal.
- Verification: pytest subset for touched areas, `ruff check` on touched files,
  banned-token scan on the doc. Report exact commands and outputs.
