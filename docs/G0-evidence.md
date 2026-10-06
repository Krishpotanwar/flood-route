# G0 Evidence Pack

Date: 2026-10-06. Source of every figure: a command run against the dev DB
(Docker container `floodroute-test-pg`, host port 54329, database `floodroute`,
trust auth). Commands and outputs are quoted verbatim. Nothing here is invented.
Stale or weak results are reported as they are.

Config in effect for all runs below: model `v0.0.1`, config hash
`ebb6ad79e7665448`, horizons `(0, 30, 60, 120)` minutes, 4 supported vehicle
classes of 7 configured (`two_wheeler`, `car`, `ambulance`, `heavy`; the scoring
engine also emits `pedestrian`, `auto_rickshaw`, `suv` rows in memory but the DB
bridge persists only the supported 4).

## 1. Priors check (Chennai)

Requirement: verify `segment_static` priors exist for the 1550 Chennai segments
before any shadow run. Result: present, no invention needed.

Command:

```
.venv/bin/python -c "
import psycopg
url='postgresql://postgres@127.0.0.1:54329/floodroute'
with psycopg.connect(url) as c:
    with c.cursor() as cur:
        cur.execute('select city_id, count(*) from segment group by city_id order by city_id')
        print('segments by city:', cur.fetchall())
        cur.execute('select city_id, count(*) from segment_static ss join segment s using (segment_id) group by city_id order by city_id')
        print('priors by city:', cur.fetchall())
        ..."
```

Output:

```
segments by city: [(1, 5383), (2, 1550)]
priors by city: [(1, 5383), (2, 1550)]
chennai segments: (1550,)
chennai priors: (1550,)
chennai risk rows: (0,)
bengaluru risk rows: (86128,)
observed_event: (12,)
official_alert: (10,)
rain_fcst: (63,)
shadow_run: (3,)
history rows: (258384,)
audit rows: (86145,)
```

Follow-up detail (same session):

```
assessed by city: [(1, True, 5383), (2, True, 1550)]
chennai null base_logit: (0,)
chennai structures: [('low_bridge', 675), ('dip', 316), ('underpass', 249), ('culvert', 241), ('none', 69)]
```

Reading: all 1550 Chennai segments are assessed and carry priors. Zero Chennai
risk rows existed before this task. The shadow run below used the existing
Checkpoint 10 path with no code change.

## 2. Chennai shadow scoring run

Pre-run totals:

```
PRE segment_risk total: (86128,)
PRE history total: (258384,)
PRE audit total: (86145,)
PRE max run_id: (4,)
chennai zones: (1,)
bengaluru zones: (1,)
```

Run command (existing entry point `execute_score_run` in
`floodroute/score/db.py`, scores all assessed segments in both cities):

```
.venv/bin/python -c "
import psycopg
from floodroute.score.db import execute_score_run
url='postgresql://postgres@127.0.0.1:54329/floodroute'
with psycopg.connect(url, autocommit=True) as conn:
    run_id, result = execute_score_run(conn, notes='Task 3 G0 closeout: Chennai shadow scoring run (all assessed segments, both cities)')
    print('run_id:', run_id)
    print('result rows:', len(result.rows))
    print('result changes:', len(result.changes))
"
```

Output:

```
run_id: 5
result rows: 194124
result changes: 108012
```

Reading: 194124 = 6933 assessed segments x 7 configured classes x 4 horizons
(in-memory rows; only supported-class rows are persisted, see below).

Post-run verification:

```
POST segment_risk total: (110928,)
risk rows by city: [(1, 86128), (2, 24800)]
history rows run_id=5: (110928,)
history total: (369312,)
audit total: (110961,)
audit rows this run window: (24816,)
shadow_run 5: (5, datetime.datetime(2026, 10, 6, 10, 23, 12, 815562, tzinfo=...), 'v0.0.1', 'ebb6ad79e7665448', 'Task 3 G0 closeout: Chennai shadow scoring run (all assessed segments, both cities)')
chennai state distribution: [('unknown', 24800)]
chennai by vclass: [('ambulance', 6200), ('car', 6200), ('heavy', 6200), ('two_wheeler', 6200)]
chennai by horizon: [(0, 6200), (30, 6200), (60, 6200), (120, 6200)]
```

Reading:

* Expected multiple holds exactly: 1550 x 4 classes x 4 horizons = 24800
  Chennai rows. Bengaluru rows were upserted in place (86128 before and after).
* History: 110928 rows tagged run_id 5 (one per persisted risk row).
* Audit: 86145 to 110961 = 24816 new rows in the run window, split by city as
  `[(1, 16), (2, 24800)]`. The 24800 Chennai rows are first-time states; the 16
  Bengaluru rows are state transitions on existing segments.
* All 24800 Chennai rows carry state `unknown`. Cause, verified by query: the
  `rain_obs` table is empty (0 rows) and Chennai zone 2 has no forecast rows at
  all (`rain_fcst by zone` shows only zone 1 entries; `rain_obs by zone` is
  empty). With no rain signal in the lookup window the scorer records unknown
  rather than asserting a clear state. This is reported as observed behavior,
  not tuned.

## 3. Backtest

### 3a. Seed state check (no seeding performed)

`--seed-benchmark` was NOT passed: the 6 benchmark events are already present in
`observed_event`, each exactly twice (12 rows total), so seeding again would
have inserted a third copy. State check command and output:

```
select note, count(*) from observed_event group by note having count(*) > 1
duplicate notes (seed-benchmark state check):
 count=2 note=Water accumulation 15cm on 100 Feet Road Indiranagar near Domlur
 count=2 note=K.R. Circle underpass inundated, cars stranded
 count=2 note=Windsor Manor underpass water pumped out, road reopened for traffic
 count=2 note=Severe flooding on Outer Ring Road near Bellandur EcoSpace; traffic di
 count=2 note=Windsor Manor railway underpass closed due to 70cm water accumulation
 count=2 note=Silk Board junction underpass waterlogged, 35cm standing water
events without segment: (0,)
```

All 12 events resolve to segments and sit in city 1 (Bengaluru). No Chennai
events exist yet. The duplicate seeding is a data hygiene issue for a later
cleanup task; figures below use the 12 rows as found.

### 3b. Backtest, Bengaluru, car, horizon 0

Command:

```
.venv/bin/python -m floodroute.score backtest --city-id 1 --db-url 'postgresql://postgres@127.0.0.1:54329/floodroute'
```

Output:

```
Backtest results:
{'samples': 12, 'hits': 0, 'misses': 10, 'false_alarms': 0, 'correct_negatives': 2, 'pod': 0.0, 'far': None, 'csi': 0.0, 'accuracy': 0.1667, 'brier_score': 0.7972, 'mae_depth_cm': 30.0, 'roc_auc': 0.2, 'brier_decomp': {'brier_score': 0.7972, 'reliability': 0.6563, 'resolution': 0.0, 'uncertainty': 0.1389, 'base_rate': 0.8333}, 'optimal_threshold_csi': 0.05}
```

Reading: POD 0.0 and FAR None (no alerts raised at threshold 0.30) are reported
as required. The scores are weak because current predicted probabilities sit at
prior levels (0.01 to 0.03, see per-event table) with no live rain signal behind
them. This measures the DB state as found, not model quality under storm input.

### 3c. Full calibration audit matrix, Bengaluru

Command:

```
.venv/bin/python -m floodroute.score backtest --city-id 1 --audit-matrix --db-url 'postgresql://postgres@127.0.0.1:54329/floodroute'
```

Output:

```
=== FloodRoute Full Calibration Matrix (TRD 15) ===

Vehicle Class: two_wheeler
  0m   : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7381
  30m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7381
  60m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7381
  120m : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7381

Vehicle Class: car
  0m   : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7972
  30m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7972
  60m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7972
  120m : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.7972

Vehicle Class: ambulance
  0m   : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8044
  30m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8044
  60m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8044
  120m : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8044

Vehicle Class: heavy
  0m   : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8162
  30m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8162
  60m  : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8162
  120m : samples=12 | CSI=0.0 | POD=0.0 | FAR=None | ROC-AUC=0.2 | Brier=0.8162
```

Reading: values are identical across horizons because the current inputs carry
no time-varying rain signal (empty `rain_obs`, aged `rain_fcst`), so horizon
adds no information in this run. Brier differs slightly by class (prior offsets).

### 3d. Backtest, Chennai

Command:

```
.venv/bin/python -m floodroute.score backtest --city-id 2 --db-url 'postgresql://postgres@127.0.0.1:54329/floodroute'
```

Output:

```
Backtest results:
{'samples': 0, 'hits': 0, 'misses': 0, 'false_alarms': 0, 'correct_negatives': 0, 'pod': None, 'far': None, 'csi': None, 'accuracy': None, 'brier_score': None, 'mae_depth_cm': None, 'roc_auc': None, 'brier_decomp': None, 'optimal_threshold_csi': None}
```

Reading: empty, as expected. Chennai has risk rows but zero labelled events, so
there is nothing to score against. Chennai label capture remains future work.

### 3e. Per-event detail (car, horizon 0)

Query: each `observed_event` joined to current `segment_risk` (`car`, 0 min).

```
(1, 2022-09-05 02:30+00, 'impassable', 'high', 0.0148, 'unknown')
(7, 2022-09-05 02:30+00, 'impassable', 'high', 0.0148, 'unknown')
(2, 2022-09-05 03:15+00, 'flooded', 'high', 0.0148, 'unknown')
(8, 2022-09-05 03:15+00, 'flooded', 'high', 0.0148, 'unknown')
(3, 2022-09-05 04:00+00, 'impassable', 'high', 0.0293, 'unknown')
(9, 2022-09-05 04:00+00, 'impassable', 'high', 0.0293, 'unknown')
(4, 2022-09-05 04:30+00, 'flooded', 'low', 0.0293, 'unknown')
(10, 2022-09-05 04:30+00, 'flooded', 'low', 0.0293, 'unknown')
(5, 2022-09-05 10:00+00, 'cleared', 'high', 0.0293, 'unknown')
(11, 2022-09-05 10:00+00, 'cleared', 'high', 0.0293, 'unknown')
(6, 2025-05-18 14:20+00, 'flooded', 'medium', 0.0219, 'unknown')
(12, 2025-05-18 14:20+00, 'flooded', 'medium', 0.0219, 'unknown')
```

Reading: 10 of 12 events are flood truth (misses at threshold 0.30), 2 are
`cleared` (correct negatives). All pairs are duplicated rows, matching the
double seeding in 3a. Event tiers: high 8, medium 2, low 2. Sources:
traffic_police 6, control_room 2, crowd 2, news 2.

## 4. Input provenance snapshot

```
fcst sources: [('metno', 63)]
alert senders: [('Andhra-Pradesh-SDMA', 4), ('IMD-Chennai', 1), ('Karnataka-SNDMC', 1), ('Uttarakhand-SDMA', 1), ('Uttar-Pradesh-SDMA', 3)]
event sources: [('control_room', 2), ('crowd', 2), ('news', 2), ('traffic_police', 6)]
rain_obs total: (0,)
fcst valid range: min 2026-10-05 21:00+00, max 2026-10-08 11:00+00 (issued 2026-10-05 19:00+00)
```

Reading: MET Norway forecast rows and SACHET-style official alerts are present
in the DB from earlier ingestion work; `rain_obs` currently holds no rows, which
explains the all-unknown states in run 5. No live public feed was read during
this task; all figures come from DB state.

## 5. Gate G0 checklist (PLAN.md section 2)

Each line maps one G0 criterion to done or blocked-human.

1. Shadow season produced a labelled event log: done (12 `observed_event` rows,
   6 unique benchmark events across tiers and sources, all Bengaluru; Chennai
   labels still at zero).
2. v0 backtest on at least 3 events with POD and FAR reported: done (12 samples;
   POD 0.0, FAR None at threshold 0.30; full 4x4 matrix in 3c).
3. Shadow scoring running on Chennai and Bengaluru hotspot sets: done (run_id 5;
   Bengaluru 86128 rows, Chennai 24800 rows, multiple verified).
4. Counsel view on advisory framing in hand: blocked-human (retaining counsel
   and getting the advisory wording view needs a human; not attempted here).
5. At least 6 interviews done plus ranked design-partner candidates: blocked-human
   (human outreach; no interview records exist in this engineering scope).
6. S1 returned go or an agreed fallback: blocked-human (the Valhalla spike needs
   a live Bengaluru-graph benchmark; `tests/route/test_route_valhalla.py` states
   its sample is hand-written from the API reference and "Spike S1 must replace
   it with a real recording").
7. IMERG adapter live: blocked-human (NASA Earthdata login is human-gated; per
   plan no adapter was built here).

## 6. Verification

* No Python files were changed (existing entry points only), so no new code
  paths exist and no test additions were needed.
* Banned-token scan on this doc: `rg -n` with the prohibited-word pattern plus
  the em-dash character returns no matches.
* Relevant pytest subset and lint were run; exact commands and outputs are in
  the Task 3 report (`.superpowers/sdd/g0-closeout/task-3-report.md`).

## 7. Follow-ups for the main session

1. Deduplicate `observed_event` (each benchmark event exists twice; a third
   `--seed-benchmark` run would triple them; consider making the seeder
   idempotent).
2. Chennai has risk rows but zero labels; backtest for city 2 stays empty until
   label capture starts there.
3. `rain_obs` is empty and `rain_fcst` is aging; the next shadow run will keep
   reporting unknown unless ingestion refreshes these tables.
4. S1, counsel, and interviews remain human-gated G0 items (see checklist).

## 8. Task 4 refresh (2026-10-06): Chennai rain inputs, benchmark dedupe

Follow-up to the two Task 3 caveats (no Chennai rain inputs; double-seeded
benchmark). Figures below come from commands run this session against the same
dev DB. Earlier sections are left as the Task 3 record.

### 8a. MET Norway ingest for Chennai (no code change)

The Chennai zone row already existed (`zone_id 2`, city 2,
`POINT(80.2 13.05)`), and the existing `metno --once` entry point reads every
zone in the zone table, so no zone seeding and no adapter change were needed.
No Python files under `floodroute/ingest/` were modified.

Command:

```
DATABASE_URL='postgresql://postgres@127.0.0.1:54329/floodroute' .venv/bin/python -m floodroute.ingest metno --once
```

Output:

```
{"source": "metno", "ok": true, "lag_s": 3858, "warn": null, "zones": 2, "rows": 124}
exit: 0
```

Post-run verification:

```
POST rain_fcst: [('metno', 1, 125, ...), ('metno', 2, 62, ...)]
zone 2 issued: 2026-10-06 09:00+00, valid 2026-10-06 10:00+00 to 2026-10-08 23:00+00
chennai zone2 mm stats: [(2, 62, 0.018, 0.500)]
POST source_health metno: [('metno', 2026-10-06 10:28:38+00, None, 3858)]
```

Reading: Chennai zone 2 went from 0 to 62 forecast rows. The spell is nearly
dry (mean 0.018 mm/h, max 0.500 mm/h). Zone 1 refreshed in the same pass
(63 to 125 rows, latest issued 2026-10-06 09:00+00). Attribution and contact
rules from `docs/outreach/data-terms-tracker.md` still hold (CC BY 4.0 credit
"Data from MET Norway", descriptive User-Agent, 4-decimal coordinates).

### 8b. Benchmark dedupe and idempotent seeder

Pre-check: `BEFORE observed_event: (12,)` with exactly 6 distinct
business-key groups (city, time, segment, kind, depth, source, tier, url,
note), confirming the 12 rows were 6 events held twice.

Dedupe (one operation; keep the earliest row per group, delete
exact-duplicate copies):

```
deleted rows: 6
AFTER observed_event: (6,)
```

Remaining rows are event_ids 1 to 6 (the canonical first copies).

Seeder change (`floodroute/score/backtest.py`, `seed_benchmark_events` only):
the insert is now a `SELECT ... WHERE NOT EXISTS` on
(city_id, observed_at, note) and counts `cur.rowcount`, so a re-run inserts
zero rows and returns 0. No schema change was needed.

Double-seed proof on the dev DB (via the seeder the `--seed-benchmark` entry
point calls):

```
before first seed: (6,)
first seed inserted: 0
between seeds: (6,)
second seed inserted: 0
after second seed: (6,)
```

One new test only (`tests/score/test_score_backtest.py`,
`test_seed_benchmark_events_is_idempotent`): fresh seed returns 6, second seed
returns 0, table count stays 6.

### 8c. Shadow re-run (run 6)

Run command (same existing `execute_score_run` entry point as Task 3):

```
run_id: 6
result rows: 194124
result changes: 83196
```

Post-run verification:

```
segment_risk total: (110928,)
risk rows by city: [(1, 86128), (2, 24800)]
chennai state distribution: [('unknown', 24800)]
bengaluru state distribution: [('unknown', 86128)]
chennai by vclass: [('ambulance', 6200), ('car', 6200), ('heavy', 6200), ('two_wheeler', 6200)]
chennai by horizon: [(0, 6200), (30, 6200), (60, 6200), (120, 6200)]
history rows run_id=6: (110928,)
history total: (480240,)
audit total: (110961,)
shadow_run 6: (6, 2026-10-06 10:29:26+00, 'v0.0.1', 'ebb6ad79e7665448', 'Task 4 G0 closeout: shadow re-run after Chennai MET Norway ingest and benchmark dedupe')
```

Reading: states are still all unknown in both cities, reported honestly with
no threshold tuning. Verified cause: `rain_obs total: (0,)` still holds, so
each zone reports no observation (`has_obs` false, evidence age None) and
`state.degrade` maps clear states to unknown (`stale_data`). Fresh
`rain_fcst` rows alone cannot clear this; the scorer needs a rain observation
source inside the staleness window. Audit total is unchanged (110961) because
no state transitions occurred (unknown to unknown); history gained the
expected 110928 rows tagged run_id 6.

### 8d. Backtest on deduped events

Command:

```
.venv/bin/python -m floodroute.score backtest --city-id 1 --db-url 'postgresql://postgres@127.0.0.1:54329/floodroute'
```

Output:

```
Backtest results:
{'samples': 6, 'hits': 0, 'misses': 5, 'false_alarms': 0, 'correct_negatives': 1, 'pod': 0.0, 'far': None, 'csi': 0.0, 'accuracy': 0.1667, 'brier_score': 0.7972, 'mae_depth_cm': 30.0, 'roc_auc': 0.2, 'brier_decomp': {'brier_score': 0.7972, 'reliability': 0.6563, 'resolution': 0.0, 'uncertainty': 0.1389, 'base_rate': 0.8333}, 'optimal_threshold_csi': 0.05}
```

Audit matrix (`--audit-matrix`, city 1): samples 6 in every cell; POD 0.0,
FAR None, CSI 0.0, ROC-AUC 0.2 everywhere; Brier 0.7381 (two_wheeler), 0.7972
(car), 0.8044 (ambulance), 0.8162 (heavy); identical across horizons.

Chennai (`--city-id 2`): still empty (`samples 0`, all metrics None); zero
labelled events there.

Per-event detail (car, horizon 0), now 6 rows:

```
(1, 2022-09-05 02:30+00, 'impassable', 'high', 0.0148, 'unknown')
(2, 2022-09-05 03:15+00, 'flooded', 'high', 0.0148, 'unknown')
(3, 2022-09-05 04:00+00, 'impassable', 'high', 0.0293, 'unknown')
(4, 2022-09-05 04:30+00, 'flooded', 'low', 0.0293, 'unknown')
(5, 2022-09-05 10:00+00, 'cleared', 'high', 0.0293, 'unknown')
(6, 2025-05-18 14:20+00, 'flooded', 'medium', 0.0219, 'unknown')
```

Reading: 5 of 6 events are flood truth (misses at threshold 0.30), 1 is
`cleared` (correct negative). POD 0.0 and FAR None are reported as required.
Brier and ROC-AUC are unchanged from Task 3 because per-event predicted
probabilities are identical (risk rows carry the same p values); only the
sample counts halved with the duplicates gone. Tiers: high 4, medium 1,
low 1. Sources: traffic_police 3, control_room 1, news 1, crowd 1.

Provenance snapshot:

```
fcst sources: [('metno', 187)]
fcst by zone: [('metno', 1, 125), ('metno', 2, 62)]
rain_obs total: (0,)
fcst valid range: min 2026-10-05 21:00+00, max 2026-10-08 23:00+00 (issued up to 2026-10-06 09:00+00)
```

Note for section 5 line 1: the labelled event log is now 6 canonical
`observed_event` rows (was 12 with duplicates); Bengaluru/Chennai split is
unchanged (all Bengaluru, Chennai labels still zero).

### 8e. Task 4 verification

* `.venv/bin/pytest tests/score/test_score_backtest.py
  tests/score/test_score_db.py -q` produced `17 passed in 2.76s`.
* `.venv/bin/ruff check floodroute/score/backtest.py
  tests/score/test_score_backtest.py` produced `All checks passed!`.
* Banned-token scan on this doc (`rg -n` with the prohibited-word pattern
  plus the em-dash character) returns no matches.
