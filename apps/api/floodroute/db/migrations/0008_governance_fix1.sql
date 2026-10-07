-- 0008: kill-switch and history hardening (audit fix batch 1).
-- Runs as the migrator. Forward-only: never edit this file once applied anywhere.
set local role floodroute_migrator;

-- DB C2/M1 (owned half): a kill switch row whose scope disagrees with its id
-- columns (global carrying ids, tenant/city with the wrong or missing id) is
-- an operator error the DB used to accept. Tenant/city routing consultation
-- rides with the api batch; this CHECK keeps the stored rows unambiguous.
alter table kill_switch
  add constraint kill_switch_scope_ids_check check (
    (scope = 'global' and tenant_id is null and city_id is null)
    or (scope = 'tenant' and tenant_id is not null and city_id is null)
    or (scope = 'city' and city_id is not null and tenant_id is null)
  );

-- DB I2 (owned half): scoring history is the backtest record. The app only
-- ever INSERTs and SELECTs it (score/db.py persist path); UPDATE and DELETE
-- had no code path and no trigger, so a buggy worker or leaked credential
-- could rewrite history undetectably. Narrow the app grant to INSERT/SELECT.
-- Access through the parent name is what the app uses; partitions keep their
-- own ACLs for direct access, which no app path uses.
revoke update, delete on segment_risk_history from floodroute_app;
