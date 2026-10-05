-- 0001: core schema, from docs/TRD.md section 4 with its defects fixed.
-- Forward-only: never edit this file once applied anywhere (migrate.py refuses on a checksum change).
-- First apply needs a role that may create the postgis extension (a superuser or managed-service
-- equivalent), unless infra has installed postgis already: then "if not exists" makes it a no-op.
--
-- Fixes against the TRD draft:
--   * zone is created before segment_static, which references it.
--   * segment_risk_history cannot be "like segment_risk including all": that copies a primary key without
--     the partition key, which PostgreSQL rejects. It gets its own key (partition key plus run_id).
--   * Enumerations, probabilities and non-negative measures are CHECK constrained. Float checks also
--     reject NaN and Infinity (a bare ">= 0" accepts both, and a NaN from a parsed feed is easy to produce).
--   * Missing foreign keys added (override and route_decision to tenant, rain_* to zone, report to segment).
--   * Columns FR-M1 needs for reconstructing a decision (vclass, model_version) are NOT NULL.

create extension if not exists postgis;

-- ---------------------------------------------------------------- road graph projection and inventory

create table zone (                              -- drainage catchment or best proxy (ward, hobli, gauge Voronoi)
  zone_id  integer primary key,
  city_id  smallint not null,
  geom     geometry(MultiPolygon, 4326) not null,
  params   jsonb not null                        -- r_low, r_high, antecedent weight, per-structure overrides
);
create index on zone using gist (geom);

create table segment (
  segment_id  bigint primary key,                -- OSM way id + node pair hashed, stable across graph rebuilds
  osm_way_id  bigint not null,
  geom        geometry(LineString, 4326) not null,
  road_class  text not null,                     -- motorway ... residential (open OSM vocabulary, not enumerated)
  city_id     smallint not null,
  assessed    boolean not null default false     -- true only for inventory segments
);
create index on segment using gist (geom);

create table segment_static (
  segment_id     bigint primary key references segment,
  structure      text not null default 'none'
                 check (structure in ('underpass', 'low_bridge', 'culvert', 'dip', 'none')),
  lowest_elev_m  real check (lowest_elev_m > '-Infinity' and lowest_elev_m < 'Infinity'),
  depression_m   real check (depression_m >= 0 and depression_m < 'Infinity'),
  drain_dist_m   real check (drain_dist_m >= 0 and drain_dist_m < 'Infinity'),
  hotspot_count  smallint not null default 0 check (hotspot_count >= 0),
  base_logit     real not null check (base_logit > '-Infinity' and base_logit < 'Infinity'),
  zone_id        integer not null references zone,
  cell_id        integer                         -- precomputed grid cell for rain joins
);

-- ---------------------------------------------------------------- inputs

create table rain_obs (
  source   text not null,
  zone_id  integer not null references zone,
  ts       timestamptz not null,
  mm_5m    real check (mm_5m >= 0 and mm_5m < 'Infinity'),
  mm_60m   real check (mm_60m >= 0 and mm_60m < 'Infinity'),
  mm_24h   real check (mm_24h >= 0 and mm_24h < 'Infinity'),
  primary key (source, zone_id, ts)
);

create table rain_fcst (
  source           text not null,
  zone_id          integer not null references zone,
  issued           timestamptz not null,
  valid            timestamptz not null,
  mm_per_h         real check (mm_per_h >= 0 and mm_per_h < 'Infinity'),
  ensemble_spread  real check (ensemble_spread >= 0 and ensemble_spread < 'Infinity'),
  primary key (source, zone_id, issued, valid)
);

create table official_alert (                    -- SACHET CAP items, verbatim (so CAP vocabulary is not constrained)
  cap_id     text primary key,
  sender     text,
  event      text,
  severity   text,
  certainty  text,
  onset      timestamptz,
  expires    timestamptz,
  area       geometry(MultiPolygon, 4326),
  raw        jsonb
);
create index on official_alert using gist (area);

create table evidence (
  evidence_id  bigint generated always as identity primary key,
  segment_id   bigint not null references segment,
  kind         text not null check (kind in ('report', 'probe', 'sensor', 'camera', 'official')),
  ts           timestamptz not null,
  expires      timestamptz not null,
  depth_cm     real check (depth_cm >= 0 and depth_cm < 'Infinity'),
  speed_ratio  real check (speed_ratio >= 0 and speed_ratio < 'Infinity'),
  trust        real not null check (trust between 0 and 1),
  source_id    text not null,                    -- rotating pseudonymous id or sensor id
  payload      jsonb,
  constraint evidence_expires_after_ts check (expires > ts)
);
create index on evidence (segment_id, ts desc);

-- ---------------------------------------------------------------- outputs

create table segment_risk (                      -- current state: one row per segment, class, horizon
  segment_id      bigint not null references segment,
  vclass          text not null check (vclass in ('two_wheeler', 'car', 'ambulance', 'heavy')),
  horizon_min     smallint not null check (horizon_min in (0, 30, 60, 120)),
  p_unusable      real not null check (p_unusable between 0 and 1),
  depth_p50_cm    real check (depth_p50_cm >= 0 and depth_p50_cm < 'Infinity'),
  depth_p90_cm    real check (depth_p90_cm >= 0 and depth_p90_cm < 'Infinity'),
  state           text not null check (state in ('clear', 'watch', 'risky', 'impassable', 'unknown')),
  confidence      text not null check (confidence in ('low', 'medium', 'high')),
  evidence_age_s  integer not null check (evidence_age_s >= 0),
  model_version   text not null,
  updated_at      timestamptz not null,
  closed_since    timestamptz,                   -- hysteresis state
  reopen_ok_since timestamptz,
  primary key (segment_id, vclass, horizon_min),
  constraint segment_risk_depth_order check (depth_p50_cm <= depth_p90_cm)
);

-- Monthly partitions on updated_at, plus a default partition so a late or mistimed write never fails.
-- No foreign key to segment (history must outlive graph rebuilds); run_id gets its FK in 0003.
create table segment_risk_history (
  like segment_risk including constraints,
  run_id bigint not null,
  primary key (segment_id, vclass, horizon_min, updated_at, run_id)
) partition by range (updated_at);

create table segment_risk_history_default partition of segment_risk_history default;

-- Ensures partitions exist for the current month and the next months_ahead months. Months are India
-- calendar months (IST). Rows that already landed in the default partition for a month are moved into
-- its new partition, so a missed run cannot wedge later runs. Returns the number of partitions created.
-- SECURITY DEFINER so the app role can call it without holding DDL rights (owner is set in 0002).
-- ponytail: creates partitions only. Dropping old ones waits for a retention policy for history.
create function ensure_risk_history_partitions(months_ahead integer default 3) returns integer
language plpgsql security definer set search_path = public, pg_temp as $$
declare
  m     date := date_trunc('month', now() at time zone 'Asia/Kolkata')::date;
  part  text;
  lo    timestamptz;
  hi    timestamptz;
  made  integer := 0;
begin
  if months_ahead is null or months_ahead not between 0 and 24 then
    raise exception 'months_ahead must be between 0 and 24, got %', months_ahead;
  end if;
  perform pg_advisory_xact_lock(hashtext('ensure_risk_history_partitions'));
  for i in 0..months_ahead loop
    part := 'segment_risk_history_' || to_char(m, 'YYYY_MM');
    if to_regclass('public.' || part) is null then
      lo := m::timestamp at time zone 'Asia/Kolkata';
      hi := (m + interval '1 month') at time zone 'Asia/Kolkata';
      execute format('create table %I (like segment_risk_history including all)', part);
      execute format('with moved as (delete from segment_risk_history_default'
                     ' where updated_at >= %L and updated_at < %L returning *)'
                     ' insert into %I select * from moved', lo, hi, part);
      execute format('alter table segment_risk_history attach partition %I for values from (%L) to (%L)',
                     part, lo, hi);
      made := made + 1;
    end if;
    m := (m + interval '1 month')::date;
  end loop;
  return made;
end $$;

select ensure_risk_history_partitions(3);

-- ---------------------------------------------------------------- human control and accountability

create table tenant (
  tenant_id         integer primary key,
  name              text not null,
  kind              text not null check (kind in ('fleet', 'control_room', 'admin')),
  api_key_hash      text unique,                 -- hash only; the unique index is the auth lookup path
  vehicle_profiles  jsonb,
  rate_limit_rpm    integer check (rate_limit_rpm > 0)
);

create table override (
  override_id         bigint generated always as identity primary key,
  tenant_id           integer not null references tenant,
  segment_id          bigint not null references segment,
  action              text not null check (action in ('close', 'reopen', 'force_watch')),
  reason              text not null check (length(btrim(reason)) > 0),
  operator_id         text not null,
  second_operator_id  text,
  starts_at           timestamptz not null default now(),
  expires_at          timestamptz not null,      -- required: an override never lasts forever (FR-C3)
  constraint override_expires_after_start check (expires_at > starts_at),
  constraint override_two_people check (second_operator_id is distinct from operator_id)  -- two people means two
);
create index on override (segment_id, expires_at);

create table audit_log (                         -- append-only, enforced in 0002; no foreign keys on purpose
  audit_id    bigint generated always as identity primary key,
  ts          timestamptz not null default now(),
  actor       text not null,
  action      text not null,
  segment_id  bigint,
  before      jsonb,
  after       jsonb,
  reason      text
);
create index on audit_log (ts desc);

create table route_decision (                    -- retained one year, privacy-safe (FR-M1)
  decision_id    uuid primary key,
  ts             timestamptz not null,
  tenant_id      integer references tenant,
  vclass         text not null check (vclass in ('two_wheeler', 'car', 'ambulance', 'heavy')),
  origin_cell    integer,                        -- coarse cells, never exact points
  dest_cell      integer,
  depart_at      timestamptz,
  model_version  text not null,
  chosen         jsonb,
  rejected       jsonb,
  advisories     jsonb,
  no_safe_route  boolean not null default false
);
create index on route_decision (ts);             -- age-based retention deletes

create table report (
  report_id   uuid primary key,
  segment_id  bigint references segment,        -- null until map matched
  ts          timestamptz not null,
  depth_class text check (depth_class in ('wet', 'ankle', 'knee', 'vehicle_deep')),
  trust       real check (trust between 0 and 1),
  photo_ref   text,
  status      text not null default 'pending' check (status in ('pending', 'verified', 'rejected', 'expired'))
);

create table source_health (
  source      text primary key,
  last_ok     timestamptz,
  last_error  text,
  lag_s       integer
);
