-- 0007: scoring-evidence columns and nullable risk age (audit fix batch 1).
-- Runs as the migrator so new objects inherit floodroute_migrator ownership and
-- the 0002 default privileges keep floodroute_app DML on the altered tables.
-- Forward-only: never edit this file once applied anywhere.
set local role floodroute_migrator;

-- Score C1: the evidence table had nowhere to store verification or contributor
-- counts, so the DB loader built every Evidence with verified=False and
-- contributors=None and the depth/probe rules could never fire on DB runs.
-- Writers populate these (crowd verification, probe aggregation); the loader
-- maps them through.
alter table evidence
  add column verified boolean not null default false;
alter table evidence
  add column contributors integer check (contributors >= 0);

-- Audit provenance (db I5, owned half): crowd evidence that moves segment risk
-- must trace back to its report. Nullable: sensor/camera rows have no report.
-- The report-path insert that fills this column rides with the api batch.
alter table evidence
  add column report_id uuid references report (report_id);

-- Score I5: unknown evidence age was stored as 0 (fresh-looking) because the
-- column was NOT NULL. Unknown is now NULL; the >= 0 CHECK still holds
-- (NULL passes a CHECK) on segment_risk and every history partition.
alter table segment_risk
  alter column evidence_age_s drop not null;
alter table segment_risk_history
  alter column evidence_age_s drop not null;
