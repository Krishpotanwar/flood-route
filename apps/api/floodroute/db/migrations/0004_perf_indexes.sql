-- 0004: performance indexes for spatial risk queries and validation loops.
-- Solves sequential scan bottleneck on segment_risk table under concurrent load.
-- TRD Section 3 and 13 SLOs: risk bbox p95 < 100ms.
set local role floodroute_migrator;

create index if not exists segment_risk_vclass_horizon_seg_idx
  on segment_risk (vclass, horizon_min, segment_id);
