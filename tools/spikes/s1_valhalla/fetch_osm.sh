#!/usr/bin/env bash
# Fetch the BBBike "Southern Zone" India extract (contains Bengaluru) into $OSM_DIR, atomically.
# Skips if already present. Geofabrik and Overpass are blocked in the agent sandbox; BBBike is not.
set -euo pipefail
OSM_DIR="${OSM_DIR:?set OSM_DIR to the cache dir, e.g. <scratchpad>/osm}"
URL="https://data.bbbike.org/osm/pbf/region/asia/india/southern-zone.osm.pbf"
OUT="$OSM_DIR/southern-zone.osm.pbf"
mkdir -p "$OSM_DIR"
if [ -s "$OUT" ]; then echo "present: $OUT"; exit 0; fi
TMP="$OSM_DIR/.southern-zone.osm.pbf.part.$$"
trap 'rm -f "$TMP"' EXIT
curl -fL --retry 5 --retry-delay 5 -o "$TMP" "$URL"
[ -s "$OUT" ] && { echo "another process finished first: $OUT"; exit 0; }
mv "$TMP" "$OUT"   # same filesystem, so rename is atomic
echo "wrote $OUT"
