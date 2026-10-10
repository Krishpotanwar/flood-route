import test from "node:test";
import assert from "node:assert/strict";
import {
  CITIES_MAP,
  getCityCenter,
  getCityCenterCoords,
  getCityDisplayName,
} from "./cities.ts";

test("getCityDisplayName returns correct names and defaults to Bengaluru", () => {
  assert.strictEqual(getCityDisplayName("bengaluru"), "Bengaluru");
  assert.strictEqual(getCityDisplayName("mumbai"), "Mumbai");
  assert.strictEqual(getCityDisplayName("gurugram"), "Gurugram");
  assert.strictEqual(getCityDisplayName("BENGALURU"), "Bengaluru");
  assert.strictEqual(getCityDisplayName("unknown_city"), "Bengaluru");
  assert.strictEqual(getCityDisplayName(""), "Bengaluru");
});

test("getCityCenterCoords returns valid lon/lat tuples", () => {
  const coords = getCityCenterCoords("mumbai");
  assert.deepStrictEqual(coords, [72.8777, 19.076]);
  const defaultCoords = getCityCenterCoords("invalid");
  assert.deepStrictEqual(defaultCoords, [77.5946, 12.9716]);
});

test("getCityCenter returns LatLon object", () => {
  const center = getCityCenter("bengaluru");
  assert.strictEqual(center.lat, 12.9716);
  assert.strictEqual(center.lon, 77.5946);
});

test("CITIES_MAP contains all expected cities", () => {
  assert.ok("bengaluru" in CITIES_MAP);
  assert.ok("mumbai" in CITIES_MAP);
  assert.ok("gurugram" in CITIES_MAP);
});
