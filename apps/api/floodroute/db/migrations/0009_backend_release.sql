-- 0009: close partition ACL bypasses and index crowd-report provenance.
-- Forward-only: 0007 and 0008 may already be applied; never rewrite them.
set local role floodroute_migrator;

create index evidence_report_id_idx on evidence (report_id) where report_id is not null;

-- Direct partition access must preserve the parent's append-only app grants.
do $$
declare part record;
begin
  for part in select relid::regclass as relation from pg_partition_tree('segment_risk_history') loop
    execute format('revoke update, delete on table %s from floodroute_app', part.relation);
  end loop;
end $$;

-- The migrator's default table grants include UPDATE/DELETE. Revoke them on
-- every new partition before attachment; keep the existing movement/locking.
create or replace function ensure_risk_history_partitions(months_ahead integer default 3)
returns integer language plpgsql security definer set search_path = public, pg_temp as $$
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
      execute format('revoke update, delete on table %I from floodroute_app', part);
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
