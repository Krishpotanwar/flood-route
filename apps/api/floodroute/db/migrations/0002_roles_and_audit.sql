-- 0002: roles, grants and the append-only audit_log.
-- floodroute_migrator owns every object. floodroute_app gets DML only (audit_log: INSERT and SELECT).
-- First apply must run as a superuser (or equivalent) so it can create roles and hand over ownership.
-- Later migrations run as floodroute_migrator, or as a role that can SET ROLE to it, and start with
-- "set local role floodroute_migrator" so new objects have the right owner. tests/db checks this.
-- Roles are NOLOGIN here: the platform sets LOGIN and passwords out of band. No secrets in migrations.

do $$
declare r text;
begin
  foreach r in array array['floodroute_migrator', 'floodroute_app'] loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin', r);
    end if;
  end loop;
end $$;

grant usage, create on schema public to floodroute_migrator;
grant usage on schema public to floodroute_app;

-- Hand everything the bootstrap user created (tables, partitions, schema_migrations) to the migrator.
-- PostGIS tables are extension members and stay where they are.
do $$
declare r record;
begin
  for r in
    select c.oid::regclass as rel
    from pg_class c
    where c.relnamespace = 'public'::regnamespace
      and c.relkind in ('r', 'p')
      and c.relowner = (select oid from pg_roles where rolname = current_user)
      and not exists (select 1 from pg_depend d where d.objid = c.oid and d.deptype = 'e')
  loop
    execute format('alter table %s owner to floodroute_migrator', r.rel);
  end loop;
end $$;
alter function ensure_risk_history_partitions(integer) owner to floodroute_migrator;

-- Tables created from now on (by the migrator) are readable and writable by the app automatically.
alter default privileges for role floodroute_migrator in schema public
  grant select, insert, update, delete on tables to floodroute_app;

grant select, insert, update, delete on
  zone, segment, segment_static, rain_obs, rain_fcst, official_alert, evidence,
  segment_risk, segment_risk_history, override, route_decision, report, source_health, tenant
  to floodroute_app;

revoke all on function ensure_risk_history_partitions(integer) from public;
grant execute on function ensure_risk_history_partitions(integer) to floodroute_app;

-- audit_log: grants say INSERT and SELECT only. The trigger is the second lock, so a grants mistake
-- still fails closed. ENABLE ALWAYS keeps it firing under session_replication_role = replica.
-- The table owner can still drop the trigger or the table: that is DDL, and is the migrator's to audit.
-- Retention (Rule 8(3), at least one year, then erase) is therefore never a DML path. Erasing old rows
-- is a deliberate act by the migrator (partition the table by month first, or disable the trigger).
-- ponytail: audit_log is one plain table. Design the erasure path before its first rows are a year old.
revoke all on audit_log from floodroute_app;
grant select, insert on audit_log to floodroute_app;

set local role floodroute_migrator;

create function audit_log_append_only() returns trigger language plpgsql as $$
begin
  raise exception 'audit_log is append-only: % refused', tg_op using errcode = 'insufficient_privilege';
end $$;

create trigger audit_log_append_only before update or delete or truncate on audit_log
  for each statement execute function audit_log_append_only();
alter table audit_log enable always trigger audit_log_append_only;
