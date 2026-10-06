-- 0005: enterprise webhooks and route material-change watch subscriptions (TRD 8.1, 8.3, 10).
-- Runs as the migrator so new tables inherit floodroute_migrator ownership and
-- default privileges give floodroute_app DML.
set local role floodroute_migrator;

create table webhook_subscription (
  subscription_id  uuid primary key,
  tenant_id        integer references tenant,
  target_url       text not null check (target_url ~ '^https?://'),
  secret           text not null check (length(secret) >= 16),
  events           text[] not null check (cardinality(events) > 0),
  is_active        boolean not null default true,
  created_at       timestamptz not null default now()
);
create index on webhook_subscription (tenant_id) where is_active;

create table webhook_delivery (
  delivery_id      uuid primary key,
  subscription_id  uuid not null references webhook_subscription on delete cascade,
  event_id         uuid not null,
  event_type       text not null,
  payload          jsonb not null,
  status           text not null check (status in ('success', 'failed', 'pending')),
  status_code      integer,
  attempt          integer not null default 1 check (attempt >= 1),
  delivered_at     timestamptz,
  error_message    text
);
create index on webhook_delivery (subscription_id, delivered_at desc);

create table route_watch (
  watch_id           uuid primary key,
  decision_id        uuid references route_decision on delete cascade,
  device_token       text,
  tenant_id          integer references tenant,
  vclass             text not null check (vclass in ('two_wheeler', 'car', 'ambulance', 'heavy')),
  segments           bigint[] not null check (cardinality(segments) > 0),
  baseline_states    jsonb not null,
  alert_channel      text not null check (alert_channel in ('fcm', 'whatsapp', 'sms', 'webhook')),
  contact_target     text not null,
  alerts_sent_count  integer not null default 0 check (alerts_sent_count >= 0),
  last_alert_at      timestamptz,
  expires_at         timestamptz not null,
  is_active          boolean not null default true,
  created_at         timestamptz not null default now(),
  constraint route_watch_expires_after_create check (expires_at > created_at)
);
create index on route_watch (is_active, expires_at);
