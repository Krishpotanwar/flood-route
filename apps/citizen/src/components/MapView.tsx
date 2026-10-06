import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import mapWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Feature, FeatureCollection, LineString } from "geojson";
import { ClosureSnapshot, LatLon, PlannedRoute, RerouteResponse, RiskState, Theme, VehicleClass } from "../types";
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
  city?: string;
  vclass?: VehicleClass;
  snapshot?: ClosureSnapshot | null;
  demoMode?: boolean;
}

interface Hotspot {
  id: string;
  name: string;
  coords: [number, number]; // [lon, lat]
  severity: RiskState;
}

maplibregl.setWorkerUrl(mapWorkerUrl);
export const STATUS_SYMBOLS: Record<RiskState, string> = { clear: "✓", watch: "◷", risky: "!", impassable: "⊘", unknown: "?" };

export const CITY_HOTSPOTS: Record<string, Hotspot[]> = {
  bengaluru: [
    { id: "silk_board", name: "Silk Board Junction", coords: [77.6228, 12.9172], severity: "watch" },
    { id: "bellandur", name: "Bellandur EcoSpace ORR", coords: [77.6848, 12.926], severity: "risky" },
    { id: "windsor", name: "Windsor Manor Underpass", coords: [77.5873, 12.9965], severity: "impassable" },
    { id: "indiranagar", name: "Indiranagar 100ft Rd", coords: [77.6412, 12.9719], severity: "clear" },
    { id: "domlur", name: "Domlur Flyover", coords: [77.638, 12.961], severity: "unknown" },
  ],
  mumbai: [
    { id: "milan_subway", name: "Milan Subway Santacruz", coords: [72.8425, 19.0833], severity: "impassable" },
    { id: "andheri_subway", name: "Andheri Subway", coords: [72.8444, 19.1197], severity: "impassable" },
    { id: "kings_circle", name: "King's Circle / Gandhi Market", coords: [72.8575, 19.0303], severity: "risky" },
    { id: "hindmata", name: "Hindmata Junction Dadar", coords: [72.8433, 19.0117], severity: "watch" },
    { id: "bkc_mithi", name: "BKC Mithi River Outfall", coords: [72.8681, 19.0656], severity: "unknown" },
  ],
  gurugram: [
    { id: "subhash_chowk", name: "Subhash Chowk Sohna Rd", coords: [77.0422, 28.4311], severity: "risky" },
    { id: "rajiv_chowk", name: "Rajiv Chowk Underpass NH48", coords: [77.0319, 28.4556], severity: "impassable" },
    { id: "hero_honda", name: "Hero Honda Chowk Underpass", coords: [77.0017, 28.4389], severity: "impassable" },
    { id: "narsinghpur", name: "Narsinghpur Express Corridor", coords: [76.9833, 28.4167], severity: "watch" },
    { id: "khandsa", name: "Khandsa Badshahpur Drain Breach", coords: [76.9944, 28.4278], severity: "unknown" },
  ],
};

const CITY_COORDS: Record<string, [number, number]> = {
  bengaluru: [77.5946, 12.9716],
  mumbai: [72.8777, 19.0760],
  gurugram: [77.0266, 28.4595],
};


function isWebGLSupported(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function getTileUrl(): string {
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
  city = "bengaluru",
  vclass = "car",
  snapshot = null,
  demoMode = false,
}) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<maplibregl.Map | null>(null);
  const loadedMapRef = useRef<maplibregl.Map | null>(null);
  const originMarkerRef = useRef<maplibregl.Marker | null>(null);
  const destMarkerRef = useRef<maplibregl.Marker | null>(null);
  const vehicleMarkerRef = useRef<maplibregl.Marker | null>(null);
  const hotspotMarkersRef = useRef<maplibregl.Marker[]>([]);

  const [mapLoaded, setMapLoaded] = useState<boolean>(false);
  const [useFallback, setUseFallback] = useState<boolean>(false);
  const [showHotspots, setShowHotspots] = useState<boolean>(true);
  const [mapError, setMapError] = useState<string | null>(null);
  const dark = theme === "dark" || theme === "hc-dark";
  const routeColor = dark ? "#f4f4f0" : "#111111";
  const routeCasing = dark ? "#111111" : "#ffffff";
  const hotspots = demoMode ? CITY_HOTSPOTS[city] || CITY_HOTSPOTS.bengaluru : [];
  const closures = !demoMode && snapshot?.city === city && snapshot.vclass === vclass
    ? snapshot
    : null;
  const closureLines = useMemo(() => (closures?.features || []).flatMap((feature) => {
    const coordinates: unknown = feature.geometry.coordinates;
    const lines = feature.geometry.type === "LineString"
      ? [coordinates]
      : feature.geometry.type === "MultiLineString" && Array.isArray(coordinates)
        ? coordinates
        : [];
    return lines.filter((line): line is Array<[number, number]> =>
      Array.isArray(line) && line.length > 1 && line.every((point) =>
        Array.isArray(point) && point.length >= 2 && Number.isFinite(point[0]) && Number.isFinite(point[1])
      )
    );
  }), [closures]);

  // Reposition map when city changes and no active route
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map || activeRoute) return;
    const center = CITY_COORDS[city] || CITY_COORDS.bengaluru;
    map.flyTo({ center, zoom: 12 });
  }, [city, mapLoaded, activeRoute]);

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
    if (useFallback) return;
    if (!mapContainerRef.current) return;

    if (!isWebGLSupported()) {
      setUseFallback(true);
      return;
    }

    try {
      setMapLoaded(false);
      setMapError(null);
      const tileUrl = getTileUrl();
      const map = new maplibregl.Map({
        container: mapContainerRef.current,
        style: {
          version: 8,
          sources: {
            "raster-tiles": {
              type: "raster",
              tiles: [tileUrl],
              tileSize: 256,
              attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            },
          },
          layers: [
            {
              id: "raster-layer",
              type: "raster",
              source: "raster-tiles",
              minzoom: 0,
              maxzoom: 19,
              paint: { "raster-saturation": -1, "raster-brightness-max": dark ? 0.45 : 1 },
            },
          ],
        },
        center: CITY_COORDS[city] || CITY_COORDS.bengaluru,
        zoom: 12,
        attributionControl: false,
      });

      map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");

      map.on("load", () => {
        if (mapInstanceRef.current === map) {
          loadedMapRef.current = map;
          setMapLoaded(true);
        }
      });
      map.on("error", () => {
        if (mapInstanceRef.current === map) {
          setMapError("Map tiles unavailable. Use the schematic view to continue.");
        }
      });

      const loadTimer = window.setTimeout(() => {
        if (!map.loaded()) setMapError("Map loading slowly. Schematic view is available.");
      }, 8000);
      const observer = new ResizeObserver(() => map.resize());
      observer.observe(mapContainerRef.current);

      mapInstanceRef.current = map;

      return () => {
        window.clearTimeout(loadTimer);
        observer.disconnect();
        originMarkerRef.current?.remove();
        destMarkerRef.current?.remove();
        vehicleMarkerRef.current?.remove();
        hotspotMarkersRef.current.forEach((marker) => marker.remove());
        originMarkerRef.current = null;
        destMarkerRef.current = null;
        vehicleMarkerRef.current = null;
        hotspotMarkersRef.current = [];
        map.remove();
        mapInstanceRef.current = null;
        loadedMapRef.current = null;
        setMapLoaded(false);
      };
    } catch {
      setUseFallback(true);
    }
  }, [theme, useFallback]);

  // Manage Origin and Destination Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map) return;

    // Origin marker
    if (!originMarkerRef.current) {
      const el = document.createElement("div");
      el.className = "marker-pin origin";
      el.textContent = "A";
      el.style.background = routeColor;
      el.style.color = routeCasing;
      el.style.borderColor = routeCasing;
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
      el.style.background = routeColor;
      el.style.color = routeCasing;
      el.style.borderColor = routeCasing;
      el.setAttribute("aria-label", "Route Destination");
      destMarkerRef.current = new maplibregl.Marker({ element: el })
        .setLngLat([destination.lon, destination.lat])
        .addTo(map);
    } else {
      destMarkerRef.current.setLngLat([destination.lon, destination.lat]);
    }
  }, [destination.lat, destination.lon, mapLoaded, origin.lat, origin.lon, routeColor, routeCasing]);

  // Manage Vehicle Simulation Marker
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map) return;

    if (isSimulating && vehiclePosition) {
      if (!vehicleMarkerRef.current) {
        const el = document.createElement("div");
        el.className = "vehicle-sim-marker";
        el.textContent = "●";
        el.style.background = routeColor;
        el.style.color = routeCasing;
        el.style.borderColor = routeCasing;
        el.style.boxShadow = "none";
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
  }, [isSimulating, mapLoaded, vehiclePosition, routeColor, routeCasing]);

  // Manage Hotspot Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map) return;

    // Clear old hotspot markers
    hotspotMarkersRef.current.forEach((m) => m.remove());
    hotspotMarkersRef.current = [];

    if (showHotspots && demoMode) {
      const spots = CITY_HOTSPOTS[city] || CITY_HOTSPOTS.bengaluru;
      spots.forEach((spot) => {
        const el = document.createElement("div");
        el.className = "marker-pin hotspot";
        el.setAttribute("data-state", spot.severity);
        el.title = `${spot.name}: ${spot.severity} (demo scenario)`;
        el.setAttribute("aria-label", el.title);
        const hazard = spot.severity === "risky" || spot.severity === "impassable";
        el.style.background = hazard ? "#e61919" : routeColor;
        el.style.color = hazard ? "#ffffff" : routeCasing;
        el.textContent = STATUS_SYMBOLS[spot.severity];

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat(spot.coords)
          .addTo(map);
        hotspotMarkersRef.current.push(marker);
      });
    }
  }, [mapLoaded, showHotspots, city, demoMode, routeColor, routeCasing]);

  // Manage Live/Snapshot Closures GeoJSON Layer
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map) return;

    const closuresSourceId = "closures-geojson";
    const closuresLayerId = "closures-line-layer";

    if (!showHotspots || !closures || closureLines.length === 0) {
      if (map.getLayer(closuresLayerId)) map.removeLayer(closuresLayerId);
      if (map.getSource(closuresSourceId)) map.removeSource(closuresSourceId);
      return;
    }

    const applyData = (data: FeatureCollection<LineString>) => {
      const existing = map.getSource(closuresSourceId) as
        | maplibregl.GeoJSONSource
        | undefined;
      if (existing) {
        existing.setData(data);
      } else {
        map.addSource(closuresSourceId, {
          type: "geojson",
          data,
        });
        map.addLayer({
          id: closuresLayerId,
          type: "line",
          source: closuresSourceId,
          layout: {
            "line-join": "round",
            "line-cap": "round",
          },
          paint: {
            "line-color": "#e61919",
            "line-width": 4,
            "line-opacity": 0.85,
          },
        });
      }
    };

    applyData({
      type: "FeatureCollection",
      features: closureLines.map((line) => ({
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: line },
      })),
    });
  }, [mapLoaded, showHotspots, closures, closureLines]);

  // Update Route Polyline Layers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map || !mapLoaded || loadedMapRef.current !== map) return;

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
            "line-color": routeCasing,
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
            "line-color": routeColor,
            "line-width": 5,
          },
        });
      }

      // Update line color if already added
      if (map.getLayer(lineLayerId)) {
        map.setPaintProperty(
          lineLayerId,
          "line-color",
          routeColor
        );
      }

      // Fit bounds to active route
      const bounds = calculateBounds(routeCoords);
      if (bounds) {
        map.resize();
        map.fitBounds(bounds, {
          padding: { top: 80, bottom: 110, left: 55, right: 80 },
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
            "line-color": routeColor,
            "line-width": 4,
            "line-dasharray": [2, 2],
          },
        });
      }
    } else {
      if (map.getLayer(detourLayerId)) map.removeLayer(detourLayerId);
      if (map.getSource(detourSourceId)) map.removeSource(detourSourceId);
    }
  }, [detourCoords, mapLoaded, routeCoords, routeColor, routeCasing]);

  // Recenter Handler
  const handleRecenter = useCallback(() => {
    const map = mapInstanceRef.current;
    if (!map || loadedMapRef.current !== map) return;

    if (routeCoords.length > 0) {
      const bounds = calculateBounds(routeCoords);
      if (bounds) {
        map.fitBounds(bounds, {
          padding: { top: 80, bottom: 110, left: 55, right: 80 },
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

  const center = CITY_COORDS[city] || CITY_COORDS.bengaluru;
  const bounds = calculateBounds([
    [center[0] - 0.025, center[1] - 0.025],
    [center[0] + 0.025, center[1] + 0.025],
    latLonToCoords(origin), latLonToCoords(destination),
    ...routeCoords, ...detourCoords,
    ...hotspots.map((spot) => spot.coords), ...closureLines.flat(),
  ])!;
  const lonSpan = bounds[1][0] - bounds[0][0];
  const latSpan = bounds[1][1] - bounds[0][1];
  const project = (coord: [number, number]): [number, number] => [
    75 + ((coord[0] - bounds[0][0]) / lonSpan) * 750,
    65 + (1 - (coord[1] - bounds[0][1]) / latSpan) * 470,
  ];
  const path = (coords: Array<[number, number]>) => coords.map((coord, index) => {
    const point = project(coord);
    return `${index === 0 ? "M" : "L"} ${point[0]} ${point[1]}`;
  }).join(" ");
  const originSvg = project(latLonToCoords(origin));
  const destinationSvg = project(latLonToCoords(destination));
  const vehicleSvg = vehiclePosition ? project(vehiclePosition) : null;

  return (
    <div className="map-viewport">
      {useFallback ? (
        <div className="map-fallback">
          <svg className="map-fallback-svg" viewBox="0 0 900 600" role="img" aria-label={`${city} schematic showing trip endpoints${activeRoute ? ", planned route" : ""}${detourCoords.length ? " and suggested detour" : ""}`}>
            <defs>
              <pattern id="map-grid" width="50" height="50" patternUnits="userSpaceOnUse">
                <path d="M 50 0 L 0 0 0 50" fill="none" stroke="var(--hairline)" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="900" height="600" fill="var(--fr-canvas)" />
            <rect width="900" height="600" fill="url(#map-grid)" />
            <text x="32" y="568" fontSize="11" fill="var(--fr-ink-2)">{bounds[0][0].toFixed(3)}° E / {bounds[0][1].toFixed(3)}° N</text>
            {showHotspots && closureLines.map((line, index) => (
              <path key={index} d={path(line)} fill="none" stroke="#e61919" strokeWidth="5" />
            ))}
            {routeCoords.length > 1 && (
              <>
                <path d={path(routeCoords)} fill="none" stroke={routeCasing} strokeWidth="10" strokeLinecap="round" strokeLinejoin="round" />
                <path d={path(routeCoords)} fill="none" stroke={routeColor} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
              </>
            )}
            {detourCoords.length > 1 && <path d={path(detourCoords)} fill="none" stroke={routeColor} strokeWidth="4" strokeDasharray="9 7" />}
            {showHotspots && hotspots.map((spot) => {
              const point = project(spot.coords);
              return (
                <g key={spot.id} transform={`translate(${point[0]}, ${point[1]})`}>
                  <title>{`${spot.name}: ${spot.severity} (demo scenario)`}</title>
                  <circle r="9" fill={spot.severity === "risky" || spot.severity === "impassable" ? "#e61919" : routeColor} stroke={routeCasing} strokeWidth="2" />
                  <text y="4" textAnchor="middle" fontSize="12" fill={spot.severity === "risky" || spot.severity === "impassable" ? "#ffffff" : routeCasing}>{STATUS_SYMBOLS[spot.severity]}</text>
                  <text y="27" textAnchor="middle" fontSize="12" fill="var(--fr-ink)">{spot.name.split(" ").slice(0, 2).join(" ")}</text>
                </g>
              );
            })}
            {([["A", originSvg], ["B", destinationSvg]] as const).map(([label, point]) => (
                <g key={label} transform={`translate(${point[0]}, ${point[1]})`}>
                  <circle r="16" fill={routeColor} stroke={routeCasing} strokeWidth="3" />
                  <text y="5" textAnchor="middle" fill={routeCasing} fontSize="13" fontWeight="700">{label}</text>
                </g>
            ))}
            {vehicleSvg && (
              <g transform={`translate(${vehicleSvg[0]}, ${vehicleSvg[1]})`}>
                <circle r="18" fill={routeColor} opacity="0.2" />
                <circle r="8" fill={routeColor} stroke={routeCasing} strokeWidth="3" />
              </g>
            )}
          </svg>
        </div>
      ) : <div ref={mapContainerRef} className="map-container" />}

      <div className="map-status">
        <span>{useFallback ? "Schematic view" : "Street map"}</span>
        <span>{demoMode ? "Demo scenario" : closures ? "Closure snapshot" : "No closure data"}</span>
      </div>
      {useFallback && <p className="map-empty-status">Schematic only. Not a street navigation map.</p>}
      {mapError && !useFallback && (
        <div className="map-empty-status" role="status">
          {mapError} <button type="button" className="select-btn" onClick={() => setUseFallback(true)}>Use schematic</button>
        </div>
      )}
      <div className="map-legend">
        <span>A Start</span><span>B Destination</span>
        <span>{demoMode ? "Red: demo conditions" : "Red: reported closures"}</span>
        {detourCoords.length > 0 && <span>Dashed: suggested detour</span>}
      </div>

      {/* Floating Action Controls */}
      <div className="map-controls-floating">
        {!useFallback && <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleRecenter}
          title="Recenter Map"
          aria-label="Recenter Map"
        >
          ◎
        </button>}
        <button
          type="button"
          className="map-ctrl-btn"
          onClick={() => setShowHotspots(!showHotspots)}
          data-active={showHotspots}
          aria-pressed={showHotspots}
          title="Toggle road conditions"
          aria-label="Toggle road conditions"
        >
          !
        </button>
        {!useFallback && <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleZoomIn}
          title="Zoom In"
          aria-label="Zoom In"
        >
          +
        </button>}
        {!useFallback && <button
          type="button"
          className="map-ctrl-btn"
          onClick={handleZoomOut}
          title="Zoom Out"
          aria-label="Zoom Out"
        >
          −
        </button>}
        <button type="button" className="map-ctrl-btn" onClick={() => setUseFallback((current) => !current)} title={useFallback ? "Switch to street map" : "Switch to schematic view"} aria-label={useFallback ? "Switch to street map" : "Switch to schematic view"}>
          {useFallback ? "Map" : "⌗"}
        </button>
      </div>
    </div>
  );
};
