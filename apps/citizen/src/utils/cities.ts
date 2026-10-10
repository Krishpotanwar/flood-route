import type { LatLon } from "../types";

export interface CityDefinition {
  name: string;
  displayName: string;
  centerCoords: [number, number]; // [lon, lat]
  center: LatLon;
}

export const CITIES_MAP: Record<string, CityDefinition> = {
  bengaluru: {
    name: "bengaluru",
    displayName: "Bengaluru",
    centerCoords: [77.5946, 12.9716],
    center: { lat: 12.9716, lon: 77.5946 },
  },
  mumbai: {
    name: "mumbai",
    displayName: "Mumbai",
    centerCoords: [72.8777, 19.0760],
    center: { lat: 19.0760, lon: 72.8777 },
  },
  gurugram: {
    name: "gurugram",
    displayName: "Gurugram",
    centerCoords: [77.0266, 28.4595],
    center: { lat: 28.4595, lon: 77.0266 },
  },
};

export function getCityDisplayName(city: string): string {
  const norm = (city || "").trim().toLowerCase();
  return CITIES_MAP[norm]?.displayName || "Bengaluru";
}

export function getCityCenterCoords(city: string): [number, number] {
  const norm = (city || "").trim().toLowerCase();
  return CITIES_MAP[norm]?.centerCoords || CITIES_MAP.bengaluru.centerCoords;
}

export function getCityCenter(city: string): LatLon {
  const norm = (city || "").trim().toLowerCase();
  return CITIES_MAP[norm]?.center || CITIES_MAP.bengaluru.center;
}
