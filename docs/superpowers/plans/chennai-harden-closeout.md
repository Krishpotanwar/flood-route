# Chennai + Harden closeout plan

Close out the two Cursor paths from `cursor.md` with minimal diffs.

## Context and Global Constraints
- Ponytail ultra: deletion before addition, stdlib first, fewest files, shortest
  working diff. One runnable check per non-trivial logic.
- Strict safety invariant: never use or render the word "safe" in any user-facing
  text, badges, or API responses (use "Clear", "Watch", "Risky", "Impassable").
- Zero em-dashes in any user-facing strings, code, or documentation.
- Trust boundary: `hotspots.validate` rules are load-bearing. Every seed row keeps
  provenance (`name`, `source_name`, `source_url` http(s), `source_date`
  YYYY-MM-DD, `list_kind`, `raw_text`). No invented URLs, numbers, or citations.
  Tag research claims verified (URL) or unverified. Do not invent the GCC 859 list.
- Chennai coordinates must fall inside `CITIES["chennai"]`
  (80.05, 12.85, 80.35, 13.25). `load_city_hotspots` structure inference keys on
  `raw_text` containing underpass/subway/rub, culvert/bridge, dip/low.
- 100% test pass rate across `apps/api/tests/` and 0 ruff lint errors.
- Each task owns its paths and writes only there. No git commits (main session commits).
- Scratch and large files go in the session scratchpad, never in the repo.

## Task 1: Harden closeout verify and minimal fix
Verify the uncommitted Harden output and apply the smallest fix for the one known
gap. Files owned: `apps/api/Dockerfile`, `apps/api/.dockerignore`,
`docker-compose.yml`, `.github/workflows/api.yml`. Read-only elsewhere.
Requirements:
- Confirm `docker compose config` parses (or report the exact error verbatim).
- Confirm `.github/workflows/api.yml` install step matches
  `apps/api/pyproject.toml` extras (it uses `pip install -e ".[dev]"`).
- Close the scoring-config gap: `floodroute/score/config.py` DEFAULT_PATH points
  at repo-root `data/config/scoring.v0.json`, but the Docker build context is
  `apps/api`, so the image carries no `data/` tree. Apply the minimal fix that
  keeps scoring working in-container (compose volume mount plus one-line doc
  comment, or equivalent smallest change). Do NOT restructure build contexts,
  add stages, or add dependencies.
- No new services, no healthcheck frameworks, no rebuild of what parses.

## Task 2: Chennai chronic hotspot seed (~20 rows)
Follow the exact Mumbai/Gurugram pattern. Files owned:
`data/hotspots/chennai_seed.csv`, `data/hotspots/chennai.csv`,
`apps/api/floodroute/inventory/multicity.py` (hotspot_count/metadata only),
`apps/api/tests/inventory/test_inventory_multicity.py`,
`apps/api/tests/api/test_api_cities.py`. Read-only elsewhere.
Requirements:
- `chennai_seed.csv` columns match `mumbai_seed.csv` header exactly:
  `name,ward_or_area,source_name,source_url,source_date,list_kind,raw_text,src_lat,src_lon,geocode_query,extent,note`.
  About 20 rows of real chronic Chennai waterlogging points (NE monsoon shadow /
  G0 set). Every row passes `hotspots.validate`: non-empty provenance, http(s)
  URL, YYYY-MM-DD date. Real source URLs only (Greater Chennai Corporation
  flood/stormwater pages, Chennai Traffic Police advisories, or equivalent civic
  pages the author actually consulted). If a URL was not consulted, do not list
  it; use fewer rows rather than invented provenance.
- `chennai.csv` columns match `mumbai.csv` header exactly:
  `name,ward_or_area,source_name,source_url,source_date,list_kind,raw_text,lat,lon,geocode_method,geocode_confidence,needs_review`.
  Coordinates inside the Chennai bbox. `geocode_method=source_latlon`,
  `geocode_confidence=high`, `needs_review=false` where source coordinates are
  used directly.
- `multicity.py`: set Chennai `hotspot_count` to the real row count. No other
  registry changes.
- Tests: extend `test_inventory_multicity.py` with a Chennai load test mirroring
  the Mumbai/Gurugram assertions (count, bbox, structure set); extend
  `test_api_cities.py` only if the endpoint behavior for Chennai needs coverage
  (list/detail already generic; keep the diff minimal).
- Run `ruff check` on touched Python files and the relevant pytest subset; report
  the exact command and output.
