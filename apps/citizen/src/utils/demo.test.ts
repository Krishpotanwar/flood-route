import test from "node:test";
import assert from "node:assert/strict";
import { createDemoRoute, createDemoStep } from "./demo.ts";
import { decodePolyline } from "./polyline.ts";

test("demo routes stay at the selected Indian endpoints and scenario shows a detour then a closure", () => {
  for (const [origin, destination] of [
    [{ lat: 12.9719, lon: 77.6412 }, { lat: 12.9172, lon: 77.6228 }],
    [{ lat: 19.0656, lon: 72.8681 }, { lat: 19.1197, lon: 72.8444 }],
    [{ lat: 28.495, lon: 77.0895 }, { lat: 28.4311, lon: 77.0422 }],
  ]) {
    const route = createDemoRoute(origin, destination, "car");
    const points = decodePolyline(route.geometry, 6);
    assert.deepEqual(points[0], [origin.lon, origin.lat]);
    assert.deepEqual(points.at(-1), [destination.lon, destination.lat]);
    assert.ok(points.every(([lon, lat]) => lon > 68 && lon < 90 && lat > 8 && lat < 35));
    assert.equal(route.data_age_s, undefined);
    assert.ok(route.segments.every((segment) => !segment.assessed));
    assert.equal(createDemoStep(1, origin, destination, "car", "en").action, "keep");
    const detour = createDemoStep(2, origin, destination, "car", "en");
    assert.equal(detour.action, "suggest");
    assert.notEqual(detour.suggested_route?.geometry, route.geometry);
    assert.equal(createDemoStep(3, origin, destination, "car", "en").action, "hold");
  }
  assert.throws(() => createDemoRoute({ lat: NaN, lon: 77 }, { lat: 12, lon: 77 }, "car"));
});
