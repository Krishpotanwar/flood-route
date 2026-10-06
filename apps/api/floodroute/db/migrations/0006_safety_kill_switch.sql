-- 0006: safety case emergency kill switch and advisory freeze state (TRD 16).
-- Runs as the migrator so new tables inherit floodroute_migrator ownership and
-- default privileges give floodroute_app DML.
set local role floodroute_migrator;

create table kill_switch (
  switch_id            uuid primary key,
  tenant_id            integer references tenant,
  scope                text not null check (scope in ('global', 'tenant', 'city')),
  city_id              smallint,
  is_active            boolean not null default true,
  reason               text not null check (length(reason) >= 5),
  operator_id          text not null,
  second_operator_id   text,
  engaged_at           timestamptz not null default now(),
  disengaged_at        timestamptz,
  notes                text
);
create index on kill_switch (is_active, scope);
