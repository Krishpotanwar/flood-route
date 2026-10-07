# Whole-project audit plan

Line-by-line audit of every source file, then fix batches for confirmed defects.

## Context and Global Constraints
- Ponytail ultra: fix root causes, minimal diffs, no new dependencies, no
  refactors beyond what a defect requires. Style nits are out (ruff owns style).
- Safety invariant: never emit the word "safe" in user-facing text. The audit
  must flag every trust-boundary, validation, and safety-logic weakening.
- Never simplify away validation at trust boundaries, security, accessibility,
  or explicitly requested behavior. Road-closure and routing logic is
  safety-critical.
- Severity bar: Critical (wrong routing/closure advice, data loss, auth bypass,
  crash on valid input), Important (silent wrong numbers, missing validation,
  contract mismatch with DB/tests, dead code paths that mislead), Minor (only if
  it risks becoming Important; otherwise note and skip).
- Verify against actual code, not assumptions. Quote file:line for everything.
- Auditors are read-only: no writes, no commits, no DB writes, no network
  calls beyond reading. Fix implementers come after triage.
- No git commits (main session commits).

## Audit areas (parallel, read-only)
1. `audit-db`: `apps/api/floodroute/db/` (migrator + 6 migrations), roles and
   audit triggers vs what `api/deps.py` and code assume (`floodroute_app` role,
   check constraints, RLS/tenant expectations).
2. `audit-ingest`: `ingest/` (sachet, metno, common, `__main__`), `worker.py`,
   `feed/snapshot.py`. Feed parsing edge cases, error handling, scheduling,
   atomic writes, staleness behavior.
3. `audit-score`: all of `score/` (12 files). Model math, config loader paths,
   state degrade logic, evidence TTL, replay determinism, backtest stats
   (division by zero, empty samples), idempotency, JSONB audit payloads.
4. `audit-inventory`: `inventory/` (7 files) plus `tools/` scripts and
   `tools/spikes/s1_valhalla/` scripts. Geocode confidence caps, bbox checks,
   id mapping collisions, seed pipeline batching, spike script rot.
5. `audit-route`: `route/` (8 files) plus `webhook/` (4 files). Valhalla
   request bodies, closure handling, commit-zone/dwell/recently-closed logic,
   watch rate limits, HMAC verification (constant-time compare, replay
   windows), dispatcher retries.
6. `audit-api`: `api/` (17 files), `bot/`, `safety/`, `metrics/`,
   `api/static/console.html`. Endpoint validation, auth/tenant scoping, audit
   logging completeness, photo pipeline limits, SMS budgets, WhatsApp flows,
   kill-switch enforcement paths, metric cardinality, console JS errors.
7. `audit-frontend`: `apps/citizen/src/` (all TS/TSX), `apps/citizen/public/sw.js`,
   `packages/ui/` (tokens + check script). Gesture math, offline queue,
   snapshot staleness, map fallback, a11y attributes, token contrast claims,
   service-worker cache versioning, bundle config.
