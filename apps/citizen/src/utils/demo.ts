import type { Language, LatLon, PlannedRoute, RerouteResponse, VehicleClass } from "../types.ts";
import { encodePolyline, latLonToCoords } from "./polyline.ts";

// ponytail: schematic demo paths, connect Valhalla for road-following navigation.
export function createDemoRoute(origin: LatLon, destination: LatLon, vehicle: VehicleClass, detour = false): PlannedRoute {
  for (const point of [origin, destination]) {
    if (!Number.isFinite(point.lat) || !Number.isFinite(point.lon) || Math.abs(point.lat) > 90 || Math.abs(point.lon) > 180) {
      throw new Error("Choose valid start and destination coordinates.");
    }
  }
  const offset = detour ? 0.008 : 0.003;
  const middle: LatLon = {
    lat: (origin.lat + destination.lat) / 2 + offset,
    lon: (origin.lon + destination.lon) / 2 + offset,
  };
  return {
    kind: "least_risk",
    is_default: true,
    eta_min: (vehicle === "two_wheeler" ? 28 : 34) + (detour ? 3 : 0),
    delta_min: detour ? 8 : 5,
    worst_state: "watch",
    reasons: [detour ? "Sample detour around rising water." : "Sample route avoiding a closed road.", "Illustrative route and travel time. Not navigation guidance."],
    segments: [
      { segment_id: "demo-1", assessed: false, state: "clear" },
      { segment_id: "demo-2", assessed: false, state: "watch" },
      { segment_id: "demo-3", assessed: false, state: "clear" },
      { segment_id: "demo-4", assessed: false, state: "watch" },
    ],
    geometry: encodePolyline([latLonToCoords(origin), latLonToCoords(middle), latLonToCoords(destination)], 6),
  };
}

export function createDemoStep(step: number, origin: LatLon, destination: LatLon, vehicle: VehicleClass, lang: Language): RerouteResponse {
  const stage = step % 3;
  return {
    decision_id: `demo-step-${step}`,
    action: stage === 1 ? "keep" : stage === 2 ? "suggest" : "hold",
    code: stage === 1 ? "watch_ahead" : stage === 2 ? "detour_suggested" : "water_ahead",
    warn: true,
    reasons: [stage === 1 ? "Sample scenario: water is rising on a road ahead." : stage === 2 ? "Sample scenario: take the suggested detour around rising water." : "Sample scenario: the road ahead is closed. Stop before the flooded section."],
    reason_keys: [stage === 1 ? "watch_ahead" : stage === 2 ? "detour_suggested" : "water_ahead"],
    trip_state: { baseline_band: stage === 1 ? 1 : stage === 2 ? 2 : 3, closed_at: {} },
    current_worst_state: stage === 1 ? "watch" : stage === 2 ? "risky" : "impassable",
    current_worst_band: stage === 1 ? 1 : stage === 2 ? 2 : 3,
    current_violations_count: stage === 1 ? 0 : 1,
    lang,
    ...(stage === 2 ? { suggested_route: createDemoRoute(origin, destination, vehicle, true) } : {}),
  };
}
