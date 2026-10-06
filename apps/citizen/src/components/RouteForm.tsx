import React, { useState } from "react";
import { LatLon, VehicleClass } from "../types";

interface RouteFormProps {
  onPlanRoute: (origin: LatLon, dest: LatLon, vclass: VehicleClass) => void;
  isLoading: boolean;
}

const PRESETS: Record<string, LatLon> = {
  "Indiranagar 100ft Rd": { lat: 12.9719, lon: 77.6412 },
  "MG Road Metro": { lat: 12.9756, lon: 77.6066 },
  "Silk Board Junction": { lat: 12.9172, lon: 77.6228 },
  "Bellandur EcoSpace ORR": { lat: 12.9260, lon: 77.6762 },
  "Domlur Flyover": { lat: 12.9609, lon: 77.6387 },
  "Windsor Manor Underpass": { lat: 12.9982, lon: 77.5855 },
};

export const RouteForm: React.FC<RouteFormProps> = ({ onPlanRoute, isLoading }) => {
  const [originKey, setOriginKey] = useState<string>("Indiranagar 100ft Rd");
  const [destKey, setDestKey] = useState<string>("Silk Board Junction");
  const [vclass, setVclass] = useState<VehicleClass>("two_wheeler");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const origin = PRESETS[originKey];
    const dest = PRESETS[destKey];
    if (origin && dest) {
      onPlanRoute(origin, dest, vclass);
    }
  };

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="segmented-row">
        <button
          type="button"
          className={`segmented-btn ${vclass === "two_wheeler" ? "active" : ""}`}
          onClick={() => setVclass("two_wheeler")}
        >
          🛵 Two-Wheeler
        </button>
        <button
          type="button"
          className={`segmented-btn ${vclass === "car" ? "active" : ""}`}
          onClick={() => setVclass("car")}
        >
          🚗 Car
        </button>
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="origin-select">
          Start Location
        </label>
        <select
          id="origin-select"
          className="text-input"
          value={originKey}
          onChange={(e) => setOriginKey(e.target.value)}
        >
          {Object.keys(PRESETS).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="dest-select">
          Destination
        </label>
        <select
          id="dest-select"
          className="text-input"
          value={destKey}
          onChange={(e) => setDestKey(e.target.value)}
        >
          {Object.keys(PRESETS).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      <button type="submit" className="btn-primary" disabled={isLoading}>
        {isLoading ? "Checking Route..." : "Check Flood-Aware Route"}
      </button>
    </form>
  );
};
