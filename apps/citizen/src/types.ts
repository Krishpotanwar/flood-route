export type VehicleClass = "two_wheeler" | "car" | "ambulance" | "heavy";

export type RiskState = "clear" | "watch" | "risky" | "impassable" | "unknown";

export type Theme = "light" | "dark" | "sunlight" | "hc" | "hc-dark";

export type Language = "en" | "hi" | "kn" | "ta" | "te";

export interface LatLon {
  lat: number;
  lon: number;
}

export interface SegmentRiskSummary {
  segment_id: string;
  assessed: boolean;
  state?: RiskState;
  p?: number;
  confidence?: string;
  over_limit?: boolean;
}

export interface PlannedRoute {
  kind: "fastest" | "safest" | "least_risk";
  is_default: boolean;
  eta_min: number;
  delta_min?: number;
  worst_state: RiskState;
  data_age_s?: number;
  reasons: string[];
  segments: SegmentRiskSummary[];
  geometry: string;
}

export interface GuidanceAction {
  id: string;
  tel?: string;
}

export interface RouteGuidance {
  keys: string[];
  text: string[];
  actions: GuidanceAction[];
}

export interface RoutePlanResponse {
  decision_id: string;
  model_version: string;
  no_safe_route: boolean;
  valid_until?: string;
  routes: PlannedRoute[];
  guidance_when_no_route?: RouteGuidance;
  lang: string;
}

export interface TripStatePayload {
  last_suggestion_at?: string;
  baseline_band: number;
  closed_at: Record<string, string>;
}

export interface RerouteResponse {
  decision_id: string;
  action: "keep" | "suggest" | "hold";
  code: string;
  warn: boolean;
  reasons: string[];
  reason_keys: string[];
  trip_state: TripStatePayload;
  suggested_route?: PlannedRoute;
  current_worst_state?: RiskState;
  current_worst_band: number;
  current_violations_count: number;
  lang: string;
}

export interface HealthResponse {
  status: string;
  db_ok: boolean;
  model_version: string;
  sources: Record<string, { last_ok?: string; last_error?: string; lag_s?: number }>;
}

export interface ClosureFeature {
  type: "Feature";
  geometry: {
    type: string;
    coordinates: any;
  };
  properties: {
    segment_id: number;
    osm_way_id: number;
    road_class: string;
    state: RiskState;
    p_unusable: number;
    structure: string;
  };
}

export interface ClosureSnapshot {
  type: "FeatureCollection";
  stale?: boolean;
  snapshot_version: string;
  city: string;
  city_id: number;
  vclass: VehicleClass;
  bbox: [number, number, number, number];
  generated_at: string;
  conditions_as_of: string;
  feature_count: number;
  features: ClosureFeature[];
  etag?: string;
}

export interface CityInfo {
  city_id: number;
  name: string;
  display_name: string;
  state: string;
  bbox: [number, number, number, number];
  center: [number, number]; // [lat, lon]
}

export interface OfflineReportPayload {
  id?: string;
  lat: number;
  lon: number;
  depth_class: string;
  photo_ref?: string | null;
  reporter_id: string;
  queued_at: string;
}
