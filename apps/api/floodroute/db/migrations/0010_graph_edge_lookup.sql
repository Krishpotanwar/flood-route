-- 0010: bound each graph-edge lookup to assessed rows of its actual OSM way.
-- Forward-only: never change previously applied migrations.
set local role floodroute_migrator;

create index segment_assessed_osm_way_idx on segment (osm_way_id) where assessed;
