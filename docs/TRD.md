# FloodRoute: Technical Requirements Document

Version 0.1 draft, 2026-10-05. Companion to [PRD.md](PRD.md). Evidence: [research 01 to 06](research/). Tags: **[V]** verified in a source, **[U]** unverified, **[EST]** estimate, **[SPIKE]** must be proven by a time-boxed experiment before we rely on it.

Ponytail `ultra` governs the technology choices here: delete before adding, stdlib and native first, no new dependency for what a few lines can do. Section 3 applies the ladder to every component and names the measured trigger that earns each upgrade. Safety logic, validation at trust boundaries, security and accessibility are never simplified away.

## 1. Goals and constraints

1. Score road segments for P(unusable) per vehicle class at 0, 30, 60 and 120 minutes, refreshed every 5 minutes.
2. Route with each edge checked at arrival time, with hysteresis, explanations and an honest "no safe route" answer.
3. Serve a dispatcher console, a fleet API, a WhatsApp bot and a light PWA from one state.
4. Degrade safely: stale means Unknown, outages fall back to a static snapshot and cached clients.
5. Keep every decision auditable for one year.
6. Stay inside Indian rules: DPDP, CERT-In, TRAI, geospatial guidelines, India residency.

Constraints that shape the design:
- No source observes street-level flooding. Road risk is built from rainfall, terrain and structure priors, hotspot history and our own evidence [V, report 01].
- Convective nowcast skill is low. One Indian study gives 0.15 at 2 hours [V snippet, unconfirmed paper], so uncertainty and evidence correction are core [report 04].
- Commercial map APIs cannot take custom flood risk. Google bars non-Google maps, caching and ML use. Ola bars ML and predictive analytics and ODbL mixing [V, report 02].
- Official feeds are fragile. CWC's flood-forecast site was down for over a week in June 2026 [V, report 01].
- Small team, about 9 months to a live pilot.

## 2. Architecture

```
 INGEST (cron adapters, one table each)        STATE (one Postgres + PostGIS)             SERVE
 SACHET CAP feeds ----------\                  +-----------------------------+
 IMD API / nowcast ---------\                  | segment, segment_static      |       api (FastAPI)
 GFS / ECMWF open, IMERG ----> adapters ---->  | zone, rain_obs, rain_fcst    | ----> /v1/risk /v1/route /v1/reports
 KSNDMC & city gauges ------/   (idempotent)   | evidence, report, override   |       /v1/overrides /v1/feed
 Fleet probes, reports ----/                   | segment_risk (+ _history)    |             |
 Hotspot lists, OSM ------/                    | audit_log, route_decision    |             +--> Citizen PWA (React, MapLibre)
                                               +--------------+--------------+             +--> Dispatcher console (React)
                                                              |                            +--> Fleet API clients, webhooks
        score job (every 5 min, Python + SQL) ----------------+                            +--> WhatsApp bot, SMS, push
        1 read rain + evidence  2 compute p per class/horizon  3 hysteresis  4 write changed segments only
                                                              |
        publish job -----------> traffic overlays per class -> Valhalla (3 containers, shared tiles)
                         \-----> risk snapshot (GeoJSON/PMTiles) -> S3 + CloudFront (static, survives backend loss)
 Offline: backtest, calibration, physics scenarios (HEC-RAS / RIM2D / CA design storms), training
```

One repository, one backend codebase (API plus CLI jobs), one Postgres, one routing engine, one CDN bucket.

## 3. Component decisions (ponytail ladder)

For each need: does it have to exist, is it already in the codebase, does the stdlib or Postgres do it, is it native, only then a dependency.

| Need | Chosen | Rungs skipped, and the trigger to revisit |
|---|---|---|
| Event stream | **Postgres tables plus a poll loop** | Kafka, Redpanda, NATS. Revisit when ingest inserts exceed what one Postgres handles at p95 under 60 s, or when more than 3 consumers need independent replay [report 04 suggested Redpanda; deferred under the ladder]. |
| Live segment state cache | **Postgres (`segment_risk`) with an in-process LRU for hot reads** | Redis. Revisit when read latency p95 on `/v1/risk` exceeds 100 ms under load test. |
| Time series | **Postgres partitioned by month** | TimescaleDB, ClickHouse. Revisit above about 500 M rows or when backtests take over an hour. |
| Spatial index | **PostGIS GiST on segment geometry, plus a precomputed `cell_id` column** | H3 library, DuckDB. Revisit when multi-city aggregation or offline analytics need it [report 02]. |
| Routing | **Valhalla, self-hosted, three instances** (section 7) | Custom time-dependent A*, GraphHopper, OSRM. Revisit if the validation loop in 7.3 fails the accuracy or latency test, or per-class overlays cannot refresh within 2 min [SPIKE S1]. |
| Scoring | **SQL plus Python rule layer (v0)** | ML models, ONNX serving, GPU. Revisit at v1 once spatial cross-validation on labelled events beats v0. |
| Tiles | **MapLibre, PMTiles on S3 behind CloudFront, Protomaps basemap, SoI boundary overlay** | Tile server (Martin, pg_tileserv), commercial tiles. Static files survive a backend outage [V Protomaps cost basis, report 02]. |
| API | **FastAPI, one process type, one container image** | Microservices, GraphQL, gRPC. |
| Jobs | **CLI commands run by cron (or a Kubernetes CronJob)** | Airflow, Celery, Flink. |
| Auth | **Hosted identity for console (OIDC), hashed API keys for fleets, anonymous device token for citizens** | Self-built identity. ADR-11. |
| Messaging | **WhatsApp Business Cloud API via one BSP, DLT-registered SMS gateway, FCM push** | Own SMS routes, cell broadcast (not allowed for private parties) [V, report 05]. |
| Geocoding | **Ola Maps free tier, with written clarification of its ML and predictive-analytics clause; fallback Photon on OSM** | Mappls, Google. See ADR-9. |
| Frontend | **React 19, Vite PWA, Tailwind v4, Radix primitives with own tokens, Motion, FormatJS, Phosphor sprite** [report 06 section F] | Next.js, shadcn defaults, Radix Themes. |
| Infra as code | **Terraform, Docker, one VM class for api and routing** | Kubernetes at MVP. Revisit past 10 cities. |
| Observability | **CloudWatch logs and metrics, one dashboard, one on-call page** | Prometheus, Grafana stack, tracing vendor. |

Language: **Python 3.12 backend and jobs, TypeScript clients** (D6). One backend language, matches geospatial and data work.

## 4. Data model

PostgreSQL with PostGIS. Keys are stable segment IDs. Lowercase snake case. Only the columns we need now; additions go through migrations.

```sql
-- Road graph projection and our vulnerability inventory
create table segment (
  segment_id    bigint primary key,           -- OSM way id + node pair hashed, stable across graph rebuilds
  osm_way_id    bigint not null,
  geom          geometry(LineString, 4326) not null,
  road_class    text not null,                -- motorway ... residential
  city_id       smallint not null,
  assessed      boolean not null default false  -- true only for inventory segments
);
create index on segment using gist (geom);

create table segment_static (
  segment_id     bigint primary key references segment,
  structure      text not null default 'none', -- underpass | low_bridge | culvert | dip | none
  lowest_elev_m  real,                          -- from best DEM available
  depression_m   real,                          -- local depression depth, may be null
  drain_dist_m   real,
  hotspot_count  smallint not null default 0,  -- historical events from lists and our labels
  base_logit     real not null,                -- calibrated static prior
  zone_id        integer not null references zone,
  cell_id        integer                        -- precomputed grid cell for rain joins
);

create table zone (                              -- drainage catchment or best proxy (ward, hobli, gauge Voronoi)
  zone_id   integer primary key,
  city_id   smallint not null,
  geom      geometry(MultiPolygon, 4326) not null,
  params    jsonb not null                      -- r_low, r_high, antecedent weight, per-structure overrides
);

-- Inputs
create table rain_obs (
  source text not null, zone_id integer not null, ts timestamptz not null,
  mm_5m real, mm_60m real, mm_24h real,
  primary key (source, zone_id, ts)
);
create table rain_fcst (
  source text not null, zone_id integer not null, issued timestamptz not null, valid timestamptz not null,
  mm_per_h real, ensemble_spread real,
  primary key (source, zone_id, issued, valid)
);
create table official_alert (                    -- SACHET CAP items, verbatim
  cap_id text primary key, sender text, event text, severity text, certainty text,
  onset timestamptz, expires timestamptz, area geometry(MultiPolygon, 4326), raw jsonb
);
create table evidence (
  evidence_id bigint generated always as identity primary key,
  segment_id bigint not null references segment,
  kind text not null,                           -- report | probe | sensor | camera | official
  ts timestamptz not null, expires timestamptz not null,
  depth_cm real, speed_ratio real, trust real not null,
  source_id text not null,                      -- rotating pseudonymous id or sensor id
  payload jsonb
);
create index on evidence (segment_id, ts desc);

-- Outputs
create table segment_risk (                      -- current state, one row per segment, class, horizon
  segment_id bigint not null references segment,
  vclass text not null,                         -- two_wheeler | car | ambulance | heavy
  horizon_min smallint not null,                -- 0, 30, 60, 120
  p_unusable real not null,
  depth_p50_cm real, depth_p90_cm real,
  state text not null,                          -- clear | watch | risky | impassable | unknown
  confidence text not null,                     -- low | medium | high
  evidence_age_s integer not null,
  model_version text not null,
  updated_at timestamptz not null,
  closed_since timestamptz, reopen_ok_since timestamptz,   -- hysteresis state
  primary key (segment_id, vclass, horizon_min)
);
create table segment_risk_history (like segment_risk including all, run_id bigint not null)
  partition by range (updated_at);

-- Human control and accountability
create table override (
  override_id bigint generated always as identity primary key,
  tenant_id integer not null, segment_id bigint not null references segment,
  action text not null,                         -- close | reopen | force_watch
  reason text not null, operator_id text not null, second_operator_id text,
  starts_at timestamptz not null default now(), expires_at timestamptz not null
);
create table audit_log (                         -- append-only: revoke update and delete, write via insert only
  audit_id bigint generated always as identity primary key,
  ts timestamptz not null default now(), actor text not null, action text not null,
  segment_id bigint, before jsonb, after jsonb, reason text
);
create table route_decision (                    -- retained one year, privacy-safe
  decision_id uuid primary key, ts timestamptz not null, tenant_id integer,
  vclass text, origin_cell integer, dest_cell integer,       -- coarse cells, not exact points
  depart_at timestamptz, model_version text,
  chosen jsonb, rejected jsonb, advisories jsonb, no_safe_route boolean
);
create table report (
  report_id uuid primary key, segment_id bigint, ts timestamptz not null,
  depth_class text, trust real, photo_ref text, status text   -- status: pending | verified | rejected | expired
);
create table source_health (
  source text primary key, last_ok timestamptz, last_error text, lag_s integer
);
create table tenant (
  tenant_id integer primary key, name text not null, kind text not null,   -- fleet | control_room | admin
  api_key_hash text, vehicle_profiles jsonb, rate_limit_rpm integer
);
```

Notes:
- `segment_risk` holds `4 classes x 4 horizons` rows per assessed segment. With 300 assessed segments per city this is tiny; the full-graph `segment` table is only for routing and map matching.
- The risk layer lives in its own tables keyed by segment ID so ODbL share-alike on OSM-derived roads does not reach it [U, COUNSEL, report 02].
- `audit_log` revokes `UPDATE` and `DELETE` from the application role. Backups go to a locked bucket.
- `route_decision` keeps coarse cells, not exact origin and destination, unless a tenant contract requires more.

## 5. Ingestion

One adapter per source. Each is a CLI command, idempotent (primary key on source and time), writes `source_health`, and exits non-zero on failure.

| Adapter | Cadence | Notes |
|---|---|---|
| SACHET CAP | 1 to 2 min | National and state RSS. Parse CAP 1.2, swap lat,lon to lon,lat, store polygons in `official_alert`, map to zones. Needs a server-side fetch because there is no CORS. District polygons only. Confirm commercial terms with NDMA or C-DOT [V feed, terms unverified, report 01]. |
| IMD API platform | 5 to 15 min | Register on day 1. Endpoint list and terms not visible to the researcher [report 01]. Fallback if terms block commercial use: SACHET plus open NWP. **No scraping of IMD pages or radar images** [COUNSEL, report 05]. [SPIKE S2] |
| Open NWP (GFS, ECMWF open data) | hourly | 6 to 72 h outlook. Open-Meteo paid tier for convenience if used. |
| IMERG Early, GSMaP NRT | 30 to 60 min | About 4 h latency [V]. Used for accumulation and antecedent wetness, bias-corrected against gauges. Not a trigger for the next hour. |
| City gauges | 5 to 15 min | KSNDMC (15 min) first [V, report 01]; Chennai GCC and TNSDMA and Mumbai IFLOWS need MoUs; TSDPS daily is open. |
| Fleet probes | stream, batched per minute | Speed bucket by segment and time bucket, rotating IDs, k-anonymity floor of 5 contributors. |
| Reports | stream | PWA, WhatsApp, API. Map matched, trust scored, de-duplicated. |
| Hotspot lists | one-off per city | BBMP 210 and traffic police 113 for Bengaluru; GCC 859 for Chennai [V counts, report 01]. Manually geocoded and snapped to segments [SPIKE S5]. |
| Sentinel-1 GFM | post-event | Labels only. Revisit 3 to 14 days, delivery within about 5 to 8 h [V]. |
| Google Floods API | daily | Apply to the waitlist now. Use as a 24 h prior if it covers Indian cities [U]. |

Source hierarchy for rain input per zone, best first: city gauges, IMD radar or nowcast, SACHET alert multiplier, open NWP, IMERG. A zone with no source newer than 30 minutes during an active alert is marked Unknown.

## 6. Scoring model

### 6.1 Principles
- Layered: static prior, rainfall trigger, evidence correction [report 04].
- Calibrated and documented rule layer first. An opaque model is harder to defend in a safety case [report 04].
- Probability and confidence are separate outputs.
- Spatial cross-validation only. No random splits [report 04, Chennai accuracy spread].

### 6.2 v0 formula (R0 and R1)

For segment `s`, vehicle class `c`, horizon `h`:

```
R(z, h)   = effective rainfall in zone z: observed last 60 min, blended with forecast mm/h out to h
g(R)      = clamp((R - r_low[z, structure]) / (r_high[z, structure] - r_low[z, structure]), 0, 1)
x(s,c,h)  = base_logit[s] + k_trigger * g(R(z,h)) + k_antecedent * A(z) + delta[c] + E(s,h)
p         = sigmoid(x)
```

- `base_logit` comes from structure (underpass, low bridge, dip), depression depth, drain distance and hotspot history. Initial values are expert-elicited with local control-room staff and then fit on events. **Initial parameter values are placeholders to be fit in the shadow season, not facts** [U].
- `A(z)` is antecedent wetness from the 24 h accumulation. `delta[c]` shifts by vehicle class from the profile table in PRD section 11.2.
- `E(s,h)` is the evidence term. It applies fully at `h=0` and decays toward 0 at later horizons.
- Depth quantiles at v0 are classed (wet, ankle, knee, vehicle-deep) from a lookup keyed by `p` and structure, not a hydrodynamic estimate. They carry low confidence.
- Confidence: starts from evidence freshness and source count, and is reduced by nowcast spread, by no source newer than 15 minutes in the zone, and by being outside the DEM and drain-mapped area.

### 6.3 v0 evidence rules

| Evidence | Effect |
|---|---|
| Official closure (traffic police or authority through the console or feed) | State = Impassable, `p = 1`, until expiry. Overrides the model. |
| 2 or more independent trusted reports within 15 min on the segment | `p = max(p, 0.6)` |
| Verified photo or sensor depth at or above the class "unusable" depth | `p = max(p, 0.9)` |
| Verified sensor or camera depth below the class "caution" depth, and rain below trigger | Cap `p` at 0.2, and start the reopen timer |
| Probe speed ratio below 0.4 of expected during rain, from at least 5 contributors | `+1.0` to logit (weak; v1 learns this) |

Evidence weight decays as `exp(-age / tau)` with `tau = 20 min` by default [EST]. A single report never closes a segment alone (FR-R8).

### 6.4 State mapping and hysteresis

```
state_from_p(p):     p < 0.10 clear;  0.10..0.30 watch;  0.30..0.50 risky;  >= 0.50 impassable
close:               p > 0.50  -> impassable, set closed_since
reopen:              p < 0.25 continuously for 10 min AND evidence age < 15 min -> then re-evaluate bands
stale:               evidence_age_s > 900  -> clear degrades to unknown
unassessed:          segment.assessed = false -> API returns assessed:false, no state
```

All thresholds live in configuration. Every state change writes a `segment_risk_history` row and an `audit_log` row with before and after.

### 6.5 Roadmap

| Stage | Method | Gate to advance |
|---|---|---|
| **v0** (now to Mar 2027) | Rule layer above, hotspot priors, rainfall thresholds, classed depth | Backtest on 3 or more events, POD and FAR reported, shadow season complete |
| **v1** (Apr 2027 to Mar 2028) | Spatial-CV static prior, per-zone trigger fit on events, Bayesian log-odds evidence with learned LLRs, simple physics design-storm library (CA or RIM2D) for depth bands | Calibration slope 0.8 to 1.2; shadow-mode monsoon complete |
| **v2** (2028 onward) | GNN or U-Net surrogates trained on calibrated physics (mSWE-GNN style), learned fusion, nowcast ensemble coupling, active learning from operator corrections | Beats v1 on leave-one-event-out and keeps calibration |

Physics scenario generation is offline only. RIM2D runs Berlin (892 km2) at 10 m in 8 min on GPUs [V, report 04]; we need a DEM, drains and calibration data we mostly do not have, so v1 uses design storms on 5 to 10 m grids where data exist.

## 7. Routing

### 7.1 Engine and instances
- **Valhalla**, self-hosted. It accepts live per-edge closures and speeds through a memory-mapped `traffic.tar` with no graph rebuild, per-request `exclude_polygons`, and Meili map matching [V, report 02].
- Three instances sharing read-only graph tiles, each with its own traffic overlay: `two_wheeler` (motor_scooter costing), `car` (auto), `ambulance` and `heavy` (auto or truck with relaxed access options). [SPIKE S1: confirm shared tiles with separate traffic overlays and the refresh time on an India graph.]
- Graph from the Geofabrik India OSM extract plus our attribute table. Segment to Valhalla edge ID mapping is computed at graph build and stored (`segment_edge` view or table) [SPIKE S1].

### 7.2 Overlay publication
After each score run the publish job writes only changed segments:
- Impassable for that class: edge speed 0 or closure flag.
- Risky or Watch: speed scaled by a safety factor so the router prefers alternatives, not forbids them.
- Unknown on an assessed segment: treated as Watch in rain, Clear otherwise, and always returned to the client as Unknown.
- The overlay for an instance uses the **maximum risk over the next 60 minutes** (conservative trip-window). Overlays swap atomically. Target: score-to-overlay under 2 minutes [EST, SPIKE S1].

### 7.3 Arrival-time validation (the safety loop)
Valhalla alone cannot check "risk when I arrive". After each route query the API validates:

```
route = valhalla(origin, dest, class, overlay=max60)
loop up to 3 times:
    for edge in route:  t_arrive = depart + cumulative_time(edge)
        p = interpolate_logit(segment_risk[edge.segment, class], horizons, t_arrive)
        if p >= class_exclude_threshold:  violations.add(edge.segment)
    if no violations: break
    route = valhalla(origin, dest, class, exclude_polygons=buffer(violations))
if still violating or no route: respond no_safe_route
```

- `class_exclude_threshold` defaults: citizen 0.2 to 0.3; ambulance 0.4 to 0.5 [EST, tune with backtests, report 04]. A tenant can override with a documented limit.
- The response includes `valid_until`: the earliest time any edge's state on the route is forecast to cross its threshold.
- The same validation runs on every live reroute check.
- A unit test with a segment forecast to close at t+40 min must reject a route that reaches it at t+45 and accept one that reaches it at t+25 (FR-RT2).
- **Revisit trigger:** if validation needs more than 3 iterations in more than 2% of queries, or p95 latency exceeds the budget, build the custom time-dependent A* in Rust or Go on the same graph [report 04]. Contraction hierarchies break under live weight changes; CCH is a research track [V, report 02].

### 7.4 Reroute logic
Server-side state per active trip (fleet or citizen with a session): current route, last suggestion time, last closed segments.
- Suggest a new route only if a segment ahead turns Impassable, or the new route saves at least max(5 min, 15%) of remaining time, or risk on the current route rises one band.
- Minimum 2 to 3 min between suggestions. Never reroute into a segment closed in the last 15 min.
- Commit zone: within about 300 m of a flooded segment with no turn-off, hold and warn.
- Citizens: PWA polls or receives push. Fleets: webhook or polling endpoint.

### 7.5 Emergency profile
- Input: origin, destination, vehicle profile (class and optional per-vehicle clearance override), dispatch time.
- Objective: P(arrival within golden-hour budget), with higher tolerance of shallow water and low tolerance of Unknown conditions [report 04].
- The console shows the route, the risk annotation and a confirm button. No auto-assignment in R1 (ADR-5).
- If no safe route exists the console escalates, suggests alternative modes (boat, high-clearance vehicle, foot relay) and shows the least-risk route with explicit risk.

### 7.6 Explanation
Every route response includes plain-language reasons built from template strings in the user's language: "Avoiding Silk Board underpass (water likely in about 25 min). 6 min longer." Plus data age and confidence. No jargon, no em-dashes (design rule).

## 8. APIs

REST, JSON, versioned `/v1`, OpenAPI 3.1 published. Times are RFC 3339 with offset `+05:30`. IDs are opaque strings.

### 8.1 Endpoints

| Method and path | Purpose | Auth |
|---|---|---|
| `GET /v1/risk?bbox=&h=60&vclass=car` | Segment states in a bounding box | API key or anonymous (rate limited, coarse) |
| `POST /v1/route` | Route with arrival-time validation | API key or anonymous (rate limited) |
| `POST /v1/routes/{id}/watch` | Subscribe to material-change alerts for a route | API key or device token |
| `POST /v1/reports` | Submit a flood report | Device token or API key |
| `POST /v1/overrides` | Close, reopen or force Watch | Console OIDC (operators) or tenant with override scope |
| `GET /v1/feed/closures.geojson` | Current Impassable and Risky segments, no personal data | API key |
| `GET /v1/feed/cap.xml` | CAP 1.2 feed of closures | API key |
| `POST /v1/webhooks` | Register signed webhooks | API key |
| `GET /v1/health` | Source health and model version | Public |

### 8.2 Route request and response

```json
POST /v1/route
{ "origin": {"lat": 12.9166, "lon": 77.6101},
  "destination": {"lat": 12.9352, "lon": 77.6245},
  "vclass": "two_wheeler",
  "depart_at": "2027-05-18T17:40:00+05:30",
  "profile": "citizen",
  "lang": "kn" }
```

```json
{ "decision_id": "c1f2...",
  "model_version": "v0.3.1",
  "no_safe_route": false,
  "valid_until": "2027-05-18T18:05:00+05:30",
  "routes": [
    { "kind": "safest", "eta_min": 31, "delta_min": 8,
      "worst_state": "watch", "data_age_s": 140,
      "reasons": ["Avoiding Madiwala underpass (water likely in about 25 min)."],
      "segments": [ {"segment_id": "88231", "assessed": true, "state": "watch",
                     "p": 0.18, "confidence": "medium", "evidence_age_s": 140} ],
      "geometry": "<encoded polyline>" },
    { "kind": "fastest", "eta_min": 23, "worst_state": "risky", "...": "..." } ],
  "guidance_when_no_route": null }
```

States in API responses are one of `clear|watch|risky|impassable|unknown`, plus `assessed: false` for segments outside coverage. **The API never returns a "safe" label.**

### 8.3 Webhook

Signed with an HMAC header, idempotent `event_id`, retries with backoff, at-least-once. Events: `segment.state_changed`, `route.invalidated`, `override.created`, `feed.degraded`.

### 8.4 Limits
Anonymous: low rate limit, coarse origins. Fleet keys: per-tenant limits and metering. All inputs validated at the boundary (coordinates inside the city polygon, vehicle class enum, size limits on photos and payloads).

## 9. Clients

Built to [research report 06](research/06-design-direction.md) (taste-skill, impeccable, apple-design). Summary of the technical contract:

| Surface | Stack and rules |
|---|---|
| **Citizen PWA** | React 19 and Vite. Shell at most 70 KB gzipped, with a text risk summary and routes before the map. MapLibre loads on idle as its own chunk with a text fallback. Service worker precaches shell, last snapshot and glyphs. Bottom sheet written in-house on Pointer Events and Motion springs (damping 1.0, response 0.3 to 0.4 s; `bounce 0.1` only on flick release), snaps at 96 px, 50% and 90% `dvh`, with a button alternative. No webfonts on Android: `system-ui` plus Noto per script with `src: local()` first. |
| **Dispatcher console** | Same tokens, `data-density` high. Dark default. Minimum 1366x768. Incident table virtualized. Forecast scrubber 0 to 6 h. Feed-health strip. Keyboard shortcuts. No translucent layers. |
| **WhatsApp bot** | Webhook service in the same API. Intent set is small: share location, set vehicle, "status", "route to X". Replies are templates under utility category outside the 24 h window. Language choice persists. |
| **SMS** | DLT-registered templates, pre-approved in Kannada, Hindi and English with variable slots for place names. Under 70 characters for Indic. |
| **Fleet SDK** | Thin client over the REST API. Not in R1 unless a partner needs it. |

Risk is encoded redundantly: color, icon, label and line style (never color alone). Tokens, motion rules, state copy and the stale-data banner behaviour come from report 06 sections C and D. Stale thresholds (5 and 15 minutes) are proposals to calibrate against real feed cadence [report 06].

Performance budgets are targets, not measurements. Verify on a real Moto G-class device with 2 to 3 GB RAM on slow 4G before G1 [SPIKE S6].

## 10. Alerting

- Trigger: a material change only (new Impassable on a saved or active route, or a reroute suggestion that meets 7.4). Cap at 3 alerts per user per hour.
- Channels: FCM push, WhatsApp utility template, SMS. Never marketing content in the same thread. Opt-in stored with timestamp.
- Official alerts from IMD, CWC and SDMA are passed through verbatim with source and time, and linked to SACHET. Our own alerts use different visual language from official CAP severity colours [report 05].
- We do not originate cell broadcast. Authorities can request alerts through SACHET.
- Pricing anchor: WhatsApp utility messages cost about Rs 0.13 each in India since 1 Jul 2025 [V, report 04]. One million alerts is about Rs 1.3 lakh [EST].
- Start DLT registration and WhatsApp Business onboarding in week 1. Entity approval takes about 2 to 7 working days once documents are ready [V, report 04]. Template approval timing is the schedule risk.
- Voice and IVR alerts fall under the TRAI Third Amendment (notified 18 Sep 2026): A2P voice calls must be pre-declared with CLIs [V, report 05]. IVR is **not** in R1.

## 11. Offline and resilience

| Failure | Behaviour |
|---|---|
| Backend down | CDN snapshot (GeoJSON or PMTiles, regenerated every 2 to 5 min) still renders the map. Clients show "conditions from HH:MM". |
| Feed down | Affected zones go Unknown after the staleness threshold. Console strip shows the source in red with its age. |
| User offline | Cached last risk snapshot, route graph tiles for the city, and last route. Rules-based fallback applies the static prior and last known closures in heavy rain with a clear stale label. SMS and WhatsApp text queries as low-bandwidth channels. |
| Region loss | Cross-region backups to Hyderabad. Static snapshot replicated. Documented cut-over runbook, rehearsed before each monsoon. Warm standby is a scale-up item. |
| Power or tower loss at the edge | Out of our control; cached state and SMS are the mitigation. |

Game-day drill before each monsoon, including control-room cut-over and cutting each feed in staging.

## 12. Security, privacy and compliance mapping

| Requirement | Design |
|---|---|
| DPDP consent and notice (duties start about 13/14 May 2027) [V, report 05] | Separate consent for foreground location, background location, crowd photos and sharing with authorities. Withdrawal as easy as consent. No account for citizens. |
| DPDP security (Rule 6) | Encryption in transit and at rest, access control, logs and monitoring, backups, processor contracts. |
| Retention (Rules 6, 8(3)) [COUNSEL] | Raw GPS kept days, not months. Audit and processing logs one year. Raw location separated from audit logs. |
| Breach | One runbook, three clocks: CERT-In 6 h, DPDP Board 72 h (detailed report), affected users without delay. Pre-drafted notices. |
| Children (s.9) | Age gate. 18 and over or neutral-age flow. No tracking of children. |
| Crowd photos | Strip EXIF, blur faces and plates server-side, keep only the derived label after verification, delete originals on schedule. |
| Location minimisation | On-device map matching where possible. Upload only (segment id, speed bucket, time bucket) with rotating random IDs. k-anonymity floor 5. |
| Residency | AWS Mumbai (ap-south-1) primary, Hyderabad (ap-south-2) backup [V regions exist, report 04]. Fine-resolution geospatial data stored and processed in India by an Indian entity [V, DST guidelines 2021, report 05]. |
| CERT-In | 180-day ICT logs inside India, NTP sync to NIC or NPL, annual third-party audit by an empanelled auditor [V, report 05]. |
| Boundaries | SoI boundary overlay; OSM admin boundaries stripped from the style; CI check on the style file and screenshots [report 02]. |
| UGC | Intermediary due diligence, grievance officer, takedown workflow, report-abuse button (FR-M5). |
| Secrets and keys | Managed secrets, rotation, per-tenant keys hashed in the database. |
| Supply chain | Pinned dependencies, lockfiles, SBOM generation in CI. |
| App security | Input validation at every boundary, rate limits, tenant isolation tests that fail closed, annual VAPT. |

## 13. Observability and SLOs

| SLO | Target [EST] |
|---|---|
| Rain input to published tile | p95 under 5 min |
| Evidence to state update | p95 under 60 s |
| Route API latency | p95 under 500 ms; ambulance profile under 300 ms |
| Alert dispatch (trigger to provider handoff) | p95 under 60 s |
| Static risk layer availability during declared monsoon alerts | 99.95% |
| Core API availability | 99.9% |

Metrics per adapter (lag, error rate), per score run (duration, segments changed), per route (iterations, validation violations, latency), per channel (sent, delivered, failed), and a model-quality panel (POD, FAR, calibration per class and lead time, updated after events). Alerts page the on-call for stale feeds, failed score runs, validation loop overflow and override-conflict spikes.

## 14. Infrastructure, environments and cost

| Item | MVP (1 to 3 cities) | Scale-up (10 or more cities) |
|---|---|---|
| Compute | 2 VMs of 8 vCPU and 32 GB: one for API and jobs, one for three Valhalla instances; second AZ for failover [V sizing, report 02] | 6 to 12 VMs of 16 vCPU behind a router, per-class overlays |
| Database | Managed PostgreSQL with PostGIS, Multi-AZ | Larger instance and read replica |
| Static | S3 and CloudFront for tiles and snapshots | Same, more edge cache |
| Messaging | WhatsApp utility, SMS, FCM pay-as-you-go | Dominant cost item at scale |
| Infra cost [EST] | about Rs 50,000 to 1 lakh per month (report 02) and about USD 2,000 to 4,000 per month (report 04); planning range **Rs 0.5 to 3.5 lakh per month** including messaging and headroom | USD 15,000 to 35,000 per month [report 04], or Rs 5 to 12 lakh per month plus data licences [report 02] |
| Largest cost risks | Probe-data licences, CCTV access, IMD and CWC data fees | Same |

Environments: `dev` (laptop with docker compose), `staging` (production shape, synthetic feeds and replayed events), `prod`. Terraform for infrastructure; images built in CI and pinned by digest. Migrations are forward-only with a tested rollback plan for data fixes.

## 15. Testing and evaluation

| Layer | What |
|---|---|
| Unit and property | Scoring, hysteresis, validation loop, retention jobs, k-anonymity floor. One small runnable check per non-trivial logic (ponytail rule). Property test: no more than one flip per 10 min on noisy series. |
| Replay | Stored events replayed through ingestion, scoring, routing and alerts. Same input gives same states. |
| Backtest | Leave-one-event-out and leave-one-city-out, spatial block cross-validation. Events: Bengaluru Sep 2022 and May 2025, Chennai Dec 2015 and Dec 2023, Mumbai 2005, 2021 and May 2025, Delhi Jun 2024 [events V, report 04]. Metrics: POD, FAR, CSI at 0, 30, 60, 180 min per class; Brier score and reliability; depth MAE where sensors exist; false-closure cost; missed-closure exposure; alert lead time; override rate. |
| Shadow | One full season of live predictions against observed events before any public closure output. R0 produces it. |
| Contract and integration | OpenAPI contract tests; webhook replay safety; tenant isolation. |
| Chaos | Kill each feed in staging; cut the database connection; stale clock. |
| Performance | k6 load test at 1,000 route requests per second against a staged India graph before G1 [SPIKE S1]. |
| Client | Playwright (Chromium) flows including offline and reduced motion; axe and Lighthouse CI against budgets; `impeccable detect` in CI; one real low-end Android device in the loop; Indic text rendering at 200% zoom. |
| Human | Usability tests with two-wheeler riders (rain, one hand), dispatchers on a shift simulation, and native review of all strings. |

Ground-truth tiers: control-room logs and traffic-police posts (high), verified crowd reports and sensors (medium), Groundsource news-derived events (low; 60% accurate on location and timing in Google's own review [V, report 04]), Sentinel-1 for post-event extents outside dense cores.

## 16. Safety case

Before G1:
1. Hazard log (HARA style): wrong clear, wrong closure, stale data, misrouted ambulance, spoofed reports, feed outage, override error, overdue reopen.
2. Documented assumptions: depth thresholds, data freshness, hotspot coverage, rain input quality.
3. Fail-safe defaults: Unknown means caution in rain; Not assessed is never green.
4. Human override with reason, expiry and audit.
5. Version-pinned model, release notes per change, kill switch to freeze outputs to "advisory off".
6. Incident runbook: preserve logs under legal hold, notify insurer, pull or flag the route and issue a correction, notify the authority, assess DPDP and CERT-In clocks, contact family through counsel, post-incident review and public model-change note [report 05].
7. Written responsibilities with each partner (MoU).
8. Insurance bound: technology E&O and cyber, with bodily-injury exclusions checked [U, COUNSEL].

## 17. Architecture decision records

| ADR | Decision | Why | Alternatives rejected |
|---|---|---|---|
| 1 | Road segment is the primary key, not H3 hex | Flooding is a property of a linear asset and its low point; routing needs edge weights [report 02] | H3 as primary |
| 2 | Valhalla plus arrival-time validation; custom A* only if validation fails | Live edge overlays, exclude polygons, one engine for all profiles, least code [report 02]; arrival-time logic is a small wrapper | Custom router first, GraphHopper, OSRM |
| 3 | Postgres only at MVP; Kafka and Redis deferred behind measured triggers | Ponytail ultra; volumes are modest; fewer parts to fail in a storm | Redpanda, Redis, Timescale |
| 4 | Rule-layer v0 before any ML | Little ground truth; easier safety case; ML needs labels we do not have | End-to-end ML first |
| 5 | Advisory only; ambulance assignments need dispatcher confirm | Liability and safety (Bareilly FIR precedent [V, report 05]) | Auto-rerouting |
| 6 | PWA and WhatsApp for citizens; no native app in R1 | Small shell, no install, SMS or WhatsApp links; PWA cannot do background location, so alerts come from server-side saved routes and push [V, report 04] | Native Android first |
| 7 | Self-hosted OSM tiles with SoI boundary overlay | Legal boundary depiction; cost; custom styling [V, report 02] | Google or Mappls tiles |
| 8 | AWS Mumbai primary, Hyderabad backup | India residency; MeitY-empanelled posture for government work [V, report 05] | GCP or Azure; multi-cloud |
| 9 | Geocoding via Ola free tier with written clarification, fallback Photon | Ola permits layering own content but bars ML and predictive analytics with its data [V, report 02]; we only consume geocodes, but we need written confirmation | Google (bars storage and non-Google maps), Mappls (terms unknown) |
| 10 | Five states plus a Not assessed flag | Unknown must never read as safe [report 06, report 05] | Binary closure |
| 11 | Hosted identity for console, hashed API keys for fleets | Avoid building identity | Self-hosted Keycloak at MVP |
| 12 | Python backend, TypeScript clients | One backend language; geospatial and data libraries | Node backend, Go |

## 18. Repository layout

```
/apps/api            FastAPI app and CLI jobs (ingest, score, publish, retention)
/apps/citizen        React PWA
/apps/console        React dispatcher console
/packages/ui         tokens, risk components, copy catalog (shared)
/infra               Terraform, docker compose, runbooks
/data                inventories (hotspots, underpasses), zone polygons, vehicle profiles (versioned)
/docs                this documentation
/tools               backtest harness, replay, boundary and style linters
```

PRODUCT.md and DESIGN.md (drop-in text in report 06 sections B and C) are created at repo root at init so `impeccable` commands have context.

## 19. Spikes (time-boxed, before dependent work)

| Spike | Question | Output | Timebox |
|---|---|---|---|
| S1 | Valhalla: shared tiles with per-class traffic overlays; segment to edge mapping; overlay refresh time; query latency at 1,000 rps on an India graph; validation loop iteration count | Go or no-go on ADR-2 and a benchmark report | 1 week |
| S2 | IMD API platform: endpoints, commercial terms, rate limits, cadence; or MoU path | Terms memo and fallback decision | 3 days plus waiting |
| S3 | SACHET: polygon to zone mapping; commercial redistribution terms; request a partner feed | Mapping tool and a letter to NDMA or C-DOT | 3 days plus waiting |
| S4 | KSNDMC: access method and licence for real-time gauges | Agreement path | 2 days plus waiting |
| S5 | Hotspot library: geocode and snap BBMP, traffic police and GCC lists to segments | Reusable pipeline and first inventory | 1 week |
| S6 | PWA shell budget and Indic rendering on a Moto G-class device | Measured budgets replacing targets | 3 days |
| S7 | WhatsApp BSP, DLT registration, template approval timeline | Real dates for G1 | Start now |
| S8 | Probe data: one fleet or ambulance telematics partner; AIS-140 access path | Feasibility note | Ongoing |

## 20. Scale path

| Trigger | Move |
|---|---|
| Postgres inserts or read latency miss SLO | Add Redis cache; then a queue (Redpanda or managed Kafka) |
| More than about 5 cities | Per-city partitions, per-tenant overlays, read replica |
| Validation loop overflow | Custom time-dependent A* service on the same graph |
| Labels from 2 seasons | Learned evidence fusion (v1), then surrogates (v2) |
| Government work needs it | MeitY-empanelled hosting posture, ISO 27001, GIGW 3.0 for government-branded deliverables, STQC audit |
| Fleet partners need a driver app | Native Android with foreground service, offline tiles, voice [report 04] |

## 21. Risks (technical)

| # | Risk | Mitigation |
|---|---|---|
| 1 | Valhalla overlay refresh too slow or class overlays unworkable | Spike S1 first; fallback GraphHopper custom areas or custom A* |
| 2 | Threshold uncertainty for Indian vehicles | Conservative defaults, field trials, fleet stall data, per-tenant overrides |
| 3 | Label scarcity and noise | Tiered labels, shadow season, spatial CV, control-room partnership |
| 4 | Convective nowcast skill | Carry spread into confidence; evidence correction; lean on gauges and radar |
| 5 | OSM attribute gaps in India (maxspeed on 1.9% of one route [V]) | Own segment table; field survey of underpasses ([Rs 3 to 8 lakh per city EST, report 02]) |
| 6 | DEM too coarse for micro-relief (FABDEM RMSE 3 to 6 m on Indian tests [V], non-commercial licence) | Use DEM as a prior only; local LiDAR where partners share it; GLO-30 baseline |
| 7 | Data licensing (IMD, CWC) | MoUs; no scraping; open and paid fallbacks |
| 8 | Ola or Google licence conflicts | Self-hosted engine and tiles; geocoding only; written clarification |
| 9 | ODbL share-alike boundary | Risk layer in separate tables [COUNSEL] |
| 10 | Template approval delays (DLT, WhatsApp) | Start in week 1 |

## 22. Open technical questions

1. Exact edge-ID mapping method between OSM segments and Valhalla tiles that survives graph rebuilds.
2. Whether Valhalla per-class overlays refresh within 2 minutes at India-graph scale.
3. IMD API data products: radar composites or point nowcasts, and cadence.
4. Whether SACHET offers third-party point-in-polygon queries.
5. How to fit `r_low` and `r_high` per zone with few labelled events.
6. Whether Pregnolato-type speed-depth curves hold for mixed Indian traffic [U, report 04].
7. How to deliver hospital reachability in the console without a hospital data feed.
8. Which state ERSS programme will pilot CAD integration, and the formal API route [none public, report 04].
