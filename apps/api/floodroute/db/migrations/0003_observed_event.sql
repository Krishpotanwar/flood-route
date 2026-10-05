-- 0003: shadow-season label log and run registry (PLAN Phase 0, gate G0 backtests).
-- Runs as the migrator so the new tables are owned correctly. The default privileges from 0002
-- then give floodroute_app DML on them.
set local role floodroute_migrator;

-- One row per score run, shadow or live, so every history row points at the model version and the
-- thresholds that produced it. config_hash is the hash of the effective configuration (all thresholds
-- live in configuration, TRD 6.4).
create table shadow_run (
  run_id         bigint generated always as identity primary key,
  started_at     timestamptz not null default now(),
  model_version  text not null,
  config_hash    text not null,
  notes          text
);

-- 0001 could not reference shadow_run, which did not exist yet. Adding the FK here is possible on the
-- partitioned table and cascades to every partition (all empty at this point).
alter table segment_risk_history
  add constraint segment_risk_history_run_id_fkey foreign key (run_id) references shadow_run (run_id);

-- Ground-truth labels for backtests and the shadow season (research 04 section 4, TRD 15).
-- Every row says where it came from and how far to trust it. Rows may be captured before they are
-- placed: backtests use rows with a segment_id or a location, and the rest wait for geocoding.
-- note holds no personal data. source_url can identify the author of a public post, which is personal
-- data under DPDP: [COUNSEL] before social or crowd URLs are stored beyond the shadow season.
create table observed_event (
  event_id     bigint generated always as identity primary key,
  city_id      smallint not null,
  observed_at  timestamptz not null,
  location     geometry(Point, 4326),
  segment_id   bigint references segment,
  kind         text not null check (kind in ('flooded', 'impassable', 'stalled_vehicle', 'cleared', 'other')),
  depth_class  text check (depth_class in ('wet', 'ankle', 'knee', 'vehicle_deep')),
  source_kind  text not null
               check (source_kind in ('traffic_police', 'control_room', 'news', 'social', 'crowd', 'sensor', 'camera')),
  -- high: control-room logs and traffic-police posts. medium: verified crowd reports and sensors.
  -- low: news-derived events (Groundsource was 60% accurate on place and time). The DB only blocks
  -- the clearly wrong direction, noisy sources promoted above low. Everything else is the capture tool's call.
  label_tier   text not null check (label_tier in ('high', 'medium', 'low')),
  source_url   text,
  note         text,
  created_at   timestamptz not null default now(),
  constraint observed_event_noisy_source_is_low check (source_kind not in ('news', 'social') or label_tier = 'low')
);
create index on observed_event (city_id, observed_at);
create index on observed_event (segment_id, observed_at) where segment_id is not null;
create index on observed_event using gist (location) where location is not null;
