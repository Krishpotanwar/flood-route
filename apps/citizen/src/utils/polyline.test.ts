import { test } from "node:test";
import assert from "node:assert";
import {
  calculateBounds,
  decodePolyline,
  encodePolyline,
  latLonToCoords,
  sampleCoordinateAlongLine,
} from "./polyline.ts";

test("decodePolyline handles empty or invalid strings", () => {
  assert.deepStrictEqual(decodePolyline(""), []);
  // @ts-expect-error test invalid type
  assert.deepStrictEqual(decodePolyline(null), []);
});

test("calculateBounds returns correct min/max bounds", () => {
  assert.strictEqual(calculateBounds([]), null);

  const coords: Array<[number, number]> = [
    [77.6, 12.9],
    [77.7, 12.8],
    [77.5, 13.0],
  ];

  const bounds = calculateBounds(coords);
  assert.ok(bounds);
  if (!bounds) throw new Error("bounds is null");
  assert.strictEqual(bounds[0][0], 77.5); // minLon
  assert.strictEqual(bounds[0][1], 12.8); // minLat
  assert.strictEqual(bounds[1][0], 77.7); // maxLon
  assert.strictEqual(bounds[1][1], 13.0); // maxLat
});

test("sampleCoordinateAlongLine handles bounds and interpolation", () => {
  const coords: Array<[number, number]> = [
    [77.0, 12.0],
    [77.0, 14.0],
  ];

  assert.strictEqual(sampleCoordinateAlongLine([], 0.5), null);

  const start = sampleCoordinateAlongLine(coords, 0.0);
  assert.ok(start);
  if (!start) throw new Error("start is null");
  assert.strictEqual(start[0], 77.0);
  assert.strictEqual(start[1], 12.0);

  const mid = sampleCoordinateAlongLine(coords, 0.5);
  assert.ok(mid);
  if (!mid) throw new Error("mid is null");
  assert.strictEqual(mid[0], 77.0);
  assert.strictEqual(mid[1], 13.0);

  const end = sampleCoordinateAlongLine(coords, 1.0);
  assert.ok(end);
  if (!end) throw new Error("end is null");
  assert.strictEqual(end[0], 77.0);
  assert.strictEqual(end[1], 14.0);
});

test("latLonToCoords converts object to GeoJSON tuple", () => {
  const tuple = latLonToCoords({ lat: 12.9716, lon: 77.5946 });
  assert.deepStrictEqual(tuple, [77.5946, 12.9716]);
});

test("encodePolyline and decodePolyline round-trip accuracy", () => {
  const original: Array<[number, number]> = [
    [77.6228, 12.9172], // Silk Board
    [77.6412, 12.9719], // Indiranagar
    [77.6848, 12.926], // Bellandur EcoSpace
  ];

  const encoded = encodePolyline(original, 6);
  assert.ok(encoded.length > 0);

  const decoded = decodePolyline(encoded, 6);
  assert.strictEqual(decoded.length, original.length);

  for (let i = 0; i < original.length; i++) {
    assert.ok(Math.abs(decoded[i][0] - original[i][0]) < 1e-5);
    assert.ok(Math.abs(decoded[i][1] - original[i][1]) < 1e-5);
  }
});

