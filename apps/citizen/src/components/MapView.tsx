import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { Feature, LineString } from "geojson";
import { LatLon, PlannedRoute, RerouteResponse, RiskState, Theme } from "../types";
import {
  calculateBounds,
  decodePolyline,
  latLonToCoords,
  sampleCoordinateAlongLine,
} from "../utils/polyline";

export interface MapViewProps {
  theme: Theme;
  origin: LatLon;
  destination: LatLon;
  activeRoute: PlannedRoute | null;
  rerouteData?: RerouteResponse | null;
  isSimulating?: boolean;
  simStep?: number;
  totalSimSteps?: number;
  onSelectLocation?: (type: "origin" | "destination", coords: LatLon) => void;
}

interface Hotspot {
  id: string;
  name: string;
  coords: [number, number]; // [lon, lat]
  severity: RiskState;
}

const BENGALURU_HOTSPOTS: Hotspot[] = [
  { id: "silk_board", name: "Silk Board Junction", coords: [77.6228, 12.9172], severity: "watch" },
  { id: "bellandur", name: "Bellandur EcoSpace ORR", coords: [77.6848, 12.926], severity: "risky" },
  { id: "windsor", name: "Windsor Manor Underpass", coords: [77.5873, 12.9965], severity: "impassable" },
  { id: "indiranagar", name: "Indiranagar 100ft Rd", coords: [77.6412, 12.9719], severity: "clear" },
  { id: "domlur", name: "Domlur Flyover", coords: [77.638, 12.961], severity: "clear" },
];

function isWebGLSupported(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(
      window.WebGLRenderingContext &&
        (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch {
    return false;
  }
}

function getRouteColor(state: RiskState): string {
  switch (state) {
    case "clear":
      return "#059669";
    case "watch":
      return "#d97706";
    case "risky":
      return "#ea580c";
    case "impassable":
      return "#dc2626";
    default:
      return "#2563eb";
  }
}

function getTileUrl(theme: Theme): string {
  if (theme === "dark" || theme === "hc-dark") {
    return "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}@2x.png";
  }
  return "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
}

export const MapView: React.FC<MapViewProps> = ({
  theme,
  origin,
  destination,
  activeRoute,
  rerouteData,
  isSimulating = false,
  simStep = 0,
  totalSimSteps = 10,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const originMarkerRef = useRef<maplibregl.Marker | null>(null);
  const destMarkerRef = useRef<maplibregl.Marker | null>(null);
  const vehicleMarkerRef = useRef<maplibregl.Marker | null>(null);
  const hotspotMarkersRef = useRef<maplibregl.Marker[]>([]);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [useFallback, setUseFallback] = useState<boolean>(false);
  const [showHotspots, setShowHotspots] = useState<boolean>(true);

  // Decoded route coordinates [lon, lat]
  const routeCoords = useMemo<Array<[number, number]>>(() => {
    if (!activeRoute?.geometry) return [];
    return decodePolyline(activeRoute.geometry, 6);
  }, [activeRoute?.geometry]);

  // Suggested detour route coordinates
  const detourCoords = useMemo<Array<[number, number]>>(() => {
    if (!rerouteData?.suggested_route?.geometry) return [];
    return decodePolyline(rerouteData.suggested_route.geometry, 6);
  }, [rerouteData?.suggested_route?.geometry]);

  // Interpolated vehicle position along polyline
  const vehiclePosition = useMemo<[number, number] | null>(() => {
    if (!isSimulating || routeCoords.length === 0) return null;
    const progress = totalSimSteps > 0 ? Math.min(1.0, simStep / totalSimSteps) : 0;
    return sampleCoordinateAlongLine(routeCoords, progress);
  }, [isSimulating, routeCoords, simStep, totalSimSteps]);

  // Check WebGL support and initialize MapLibre
  useEffect(() => {
    if (!mapContainerRef.current) return;

    if (!isWebGLSupported()) {
      setUseFallback(true);
      return;
    }

    try {
      const tileUrl = getTileUrl(theme);
      const map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: {
          version: 8,
          sources: {
            "raster-tiles": {
              type: "raster",
              tiles: [tileUrl],
              tileSize: 256,
              attribution: "OpenStreetMap contributors",
            },
          },
          layers: [
            {
              id: "raster-layer",
              type: "raster",
              source: "raster-tiles",
              minzoom: 0,
              maxzoom: 19,
            },
          ],
        },
        center: [77.62, 12.95],
        zoom: 12,
        attributionControl: false,
      });

      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");

      map.on("load", () => {
        setMapLoaded(true);
      });

      mapInstanceRef.current = map;

      return () => {
        map.remove();
        mapInstanceRef.current = null;
        setMapLoaded(false);
      };
    } catch {
      setUseFallback(true);
    }
  }, [theme]);

  // Manage Origin and Destination Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    // Origin marker
    if (!originMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "marker-pin origin";
      el.textContent = "A";
      el.setAttribute("aria-label", "Route Origin");
      originMarkerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([origin.lon, origin.lat])
        .addTo(map);
    } else {
      originMarkerRef.current.setLngLat([origin.lon, origin.lat]);
    }

    // Destination marker
    if (!destMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "marker-pin destination";
      el.textContent = "B";
      el.setAttribute("aria-label", "Route Destination");
      destMarkerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([destination.lon, destination.lat])
        .addTo(map);
    } else {
      destMarkerRef.current.setLngLat([destination.lon, destination.lat]);
    }
  }, [destination.lat, destination.lon, mapLoaded, origin.lat, origin.lon]);

  // Manage Vehicle Simulation Marker
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    if (isSimulating && vehiclePosition) {
      if (!vehicleMarkerRef.current) {
        const el = document.createElement("div");
        el.className = "vehicle-sim-marker";
        el.textContent = "📍";
        el.setAttribute("aria-label", "Current Vehicle Location");
        vehicleMarkerRef.current = new maplibregl.Marker({ element: el })
          .setLngLat(vehiclePosition)
          .addTo(map);
      } else {
        vehicleMarkerRef.current.setLngLat(vehiclePosition);
      }
    } else if (vehicleMarkerRef.current) {
      vehicleMarkerRef.current.remove();
      vehicleMarkerRef.current = null;
    }
  }, [isSimulating, mapLoaded, vehiclePosition]);

  // Manage Hotspot Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    // Clear old hotspot markers
    hotspotMarkersRef.current.forEach((m) => m.remove());
    hotspotMarkersRef.current = [];

    if (showHotspots) {
      BENGALURU_HOTSPOTS.forEach((spot) => {
        const el = document.createElement("div");
        el.className = "marker-pin hotspot";
        el.setAttribute("data-state", spot.severity);
        el.title = `${spot.name} (${spot.severity.toUpperCase()})`;
        el.textContent = "!";

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat(spot.coords)
          .addTo(map);
        hotspotMarkersRef.current.push(marker);
      });
    }
  }, [mapLoaded, showHotspots]);

  // Manage Live Closures GeoJSON Layer from API feed
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    const closuresSourceId = "closures-geojson";
    const closuresLayerId = "closures-line-layer";

    if (!showHotspots) {
      if (map.getLayer(closuresLayerId)) map.removeLayer(closuresLayerId);
      if (map.getSource(closuresSourceId)) map.removeSource(closuresSourceId);
      return;
    }

    let isSubscribed = true;
    fetch("/v1/feed/closures.geojson?vclass=car")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!isSubscribed || !data || !mapInstanceRef.current) return;
        const currentMap = mapInstanceRef.current;
        const existing = currentMap.getSource(closuresSourceId) as
          | maplibregl.GeoJSONSource
          | undefined;
        if (existing) {
          existing.setData(data);
        } else {
          currentMap.addSource(closuresSourceId, {
            type: "geojson",
            data,
          });
          currentMap.addLayer({
            id: closuresLayerId,
            type: "line",
            source: closuresSourceId,
            layout: {
              "line-join": "round",
              "line-cap": "round",
            },
            paint: {
              "line-color": "#dc2626",
              "line-width": 4,
              "line-opacity": 0.85,
            },
          });
        }
      })
      .catch(() => {
        // Ignore offline network failure for live closures
      });

    return () => {
      isSubscribed = false;
    };
  }, [mapLoaded, showHotspots]);

  // Update Route Polyline Layers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded) return;

    const sourceId = "route-geojson";
    const casingLayerId = "route-casing-layer";
    const lineLayerId = "route-line-layer";

    const detourSourceId = "detour-geojson";
    const detourLayerId = "detour-line-layer";

    // 1. Update Active Route
    if (routeCoords.length > 0) {
      const geojson: Feature<LineString> = {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: routeCoords,
        },
      };

      const existingSource = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
      if (existingSource) {
        existingSource.setData(geojson);
      } else {
        map.addSource(sourceId, {
          type: "geojson",
          data: geojson,
        });

        // Background dark casing
        map.addLayer({
          id: casingLayerId,
          type: "line",
          source: sourceId,
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": "#0f172a",
            "line-width": 8,
            "line-opacity": 0.8,
          },
        });

        // Foreground colored route
        map.addLayer({
          id: lineLayerId,
          type: "line",
          source: sourceId,
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": getRouteColor(activeRoute?.worst_state || "clear"),
            "line-width": 5,
          },
        });
      }

      // Update line color if already added
      if (map.getLayer(lineLayerId)) {
        map.setPaintProperty(
          lineLayerId,
          "line-color",
          getRouteColor(activeRoute?.worst_state || "clear")
        );
      }

      // Fit bounds to active route
      const bounds = calculateBounds(routeCoords);
      if (bounds) {
        map.fitBounds(bounds, {
          padding: { top: 60, bottom: 220, left: 40, right: 40 },
          maxZoom: 15,
          duration: 1000,
        });
      }
    } else {
      if (map.getLayer(lineLayerId)) map.removeLayer(lineLayerId);
      if (map.getLayer(casingLayerId)) map.removeLayer(casingLayerId);
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    }

    // 2. Update Detour Route (if suggested)
    if (detourCoords.length > 0) {
      const detourGeojson: Feature<LineString> = {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: detourCoords,
        },
      };

      const existingDetourSource = map.getSource(detourSourceId) as
        | maplibregl.GeoJSONSource
        | undefined;
      if (existingDetourSource) {
        existingDetourSource.setData(detourGeojson);
      } else {
        map.addSource(detourSourceId, {
          type: "geojson",
          data: detourGeojson,
        });

        map.addLayer({
          id: detourLayerId,
          type: "line",
          source: detourSourceId,
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": "#2563eb",
            "line-width": 4,
            "line-dasharray": [2, 2],
          },
        });
      }
    } else {
      if (map.getLayer(detourLayerId)) map.removeLayer(detourLayerId);
      if (map.getSource(detourSourceId)) map.removeSource(detourSourceId);
    }
  }, [activeRoute?.worst_state, detourCoords, mapLoaded, routeCoords]);

  // Recenter Handler
  const handleRecenter = useCallback(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (routeCoords.length > 0) {
      const bounds = calculateBounds(routeCoords);
      if (bounds) {
        map.fitBounds(bounds, {
          padding: { top: 60, bottom: 220, left: 40, right: 40 },
          maxZoom: 15,
          duration: 600,
        });
        return;
      }
    }

    // Recenter between origin and destination
    map.flyTo({
      center: [(origin.lon + destination.lon) / 2, (origin.lat + destination.lat) / 2],
      zoom: 12,
      duration: 600,
    });
  }, [destination.lat, destination.lon, origin.lat, origin.lon, routeCoords]);

  // Zoom Handlers
  const handleZoomIn = () => {
    mapInstanceRef.current?.zoomIn();
  };

  const handleZoomOut = () => {
    mapInstanceRef.current?.zoomOut();
  };

  // Graceful SVG Vector Fallback when WebGL is unavailable
  if (useFallback) {
    const bMinLon = 77.52;
    const bMaxLon = 77.72;
    const bMinLat = 12.86;
    const bMaxLat = 13.04;

    const project = (coord: [number, number]): [number, number] => {
      const x = ((coord[0] - bMinLon) / (bMaxLon - bMinLon)) * 600;
      const y = (1 - (coord[1] - bMinLat) / (bMaxLat - bMinLat)) * 500;
      return [x, y];
    };

    const originSvg = project(latLonToCoords(origin));
    const destSvg = project(latLonToCoords(destination));
    const pathD =
      routeCoords.length > 0
        ? routeCoords
            .map((c, i) => {
              const pt = project(c);
              return `${i === 0 ? "M" : "L"} ${pt[0]} ${pt[1]}`;
            })
            .join(" ")
        : `M ${originSvg[0]} ${originSvg[1]} L ${destSvg[0]} ${destSvg[1]}`;

    const vehicleSvg = vehiclePosition ? project(vehiclePosition) : null;

    return (
      <div className="map-viewport">
        <div className="map-fallback">
          <svg className="map-fallback-svg" viewBox="0 0 600 500">
            {/* Base grid */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="var(--hairline)" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="600" height="500" fill="url(#grid)" />

            {/* Bangalore Hotspots */}
            {showHotspots &&
              BENGALURU_HOTSPOTS.map((spot) => {
                const pt = project(spot.coords);
                return (
                  <g key={spot.id} transform={`translate(${pt[0]}, ${pt[1]})`}>
                    <circle r="8" fill={getRouteColor(spot.severity)} opacity="0.8" />
                    <text
                      y="16"
                      textAnchor="middle"
                      fontSize="9"
                      fill="var(--fr-ink-2)"
                      fontWeight="bold"
                    >
                      {spot.name.split(" ")[0]}
                    </text>
                  </g>
                );
              })}

            {/* Route Polyline */}
            <path
              d={pathD}
              fill="none"
              stroke="#0f172a"
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity="0.7"
            />
            <path
              d={pathD}
              fill="none"
              stroke={getRouteColor(activeRoute?.worst_state || "clear")}
              strokeWidth="4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />

            {/* Origin Pin */}
            <g transform={`translate(${originSvg[0]}, ${originSvg[1]})`}>
              <circle r="12" fill="#059669" stroke="#ffffff" strokeWidth="2" />
              <text y="4" textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="bold">
                A
              </text>
            </g>

            {/* Destination Pin */}
            <g transform={`translate(${destSvg[0]}, ${destSvg[1]})`}>
              <circle r="12" fill="#2563eb" stroke="#ffffff" strokeWidth="2" />
              <text y="4" textAnchor="middle" fill="#ffffff" fontSize="10" fontWeight="bold">
                B
              </text>
            </g>

            {/* Vehicle Simulation Dot */}
            {vehicleSvg && (
              <g transform={`translate(${vehicleSvg[0]}, ${vehicleSvg[1]})`}>
                <circle r="14" fill="#2563eb" opacity="0.35" />
                <circle r="7" fill="#2563eb" stroke="#ffffff" strokeWidth="2" />
              </g>
            )}
          </svg>
        </div>

        <div className="map-controls-floating">
          <button
            type="button"
            className="map-ctrl-btn"
            onClick={() => setShowHotspots(!showHotspots)}
            data-active={showHotspots}
            title="Toggle Flood Hotspots"
            aria-label="Toggle Flood Hotspots"
          >
            ⚠️
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="map-viewport">
      <div ref={mapContainerRef} className="map-container" />

      {/* Floating Action Controls */}
      <div className="map-controls-floating">
        <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleRecenter}
          title="Recenter Map"
          aria-label="Recenter Map"
        >
          🎯
        </button>
        <button
          type="button"
          className="map-ctrl-btn"
          onClick={() => setShowHotspots(!showHotspots)}
          data-active={showHotspots}
          title="Toggle Flood Hotspots"
          aria-label="Toggle Flood Hotspots"
        >
          ⚠️
        </button>
        <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleZoomIn}
          title="Zoom In"
          aria-label="Zoom In"
        >
          +
        </button>
        <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleZoomOut}
          title="Zoom Out"
          aria-label="Zoom Out"
        >
          -
        </button>
      </div>
    </div>
  );
};
