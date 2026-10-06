import React, { useEffect, useState } from "react";
import { LatLon, VehicleClass } from "../types";

interface RouteFormProps {
  city?: string;
  onPlanRoute: (origin: LatLon, dest: LatLon, vclass: VehicleClass) => void;
  isLoading: boolean;
}

const CITY_PRESETS: Record<string, Record<string, LatLon>> = {
  bengaluru: {
    "Indiranagar 100ft Rd": { lat: 12.9719, lon: 77.6412 },
    "MG Road Metro": { lat: 12.9756, lon: 77.6066 },
    "Silk Board Junction": { lat: 12.9172, lon: 77.6228 },
    "Bellandur EcoSpace ORR": { lat: 12.9260, lon: 77.6762 },
    "Domlur Flyover": { lat: 12.9609, lon: 77.6387 },
    "Windsor Manor Underpass": { lat: 12.9982, lon: 77.5855 },
  },
  mumbai: {
    "BKC Kurla Corridor": { lat: 19.0656, lon: 72.8681 },
    "Dadar TT Circle": { lat: 19.0182, lon: 72.8436 },
    "Andheri Subway Link": { lat: 19.1197, lon: 72.8444 },
    "Milan Subway Santacruz": { lat: 19.0833, lon: 72.8425 },
    "South Mumbai Fort": { lat: 18.9322, lon: 72.8339 },
  },
  gurugram: {
    "Cyber City DLF Phase 2": { lat: 28.4950, lon: 77.0895 },
    "IFFCO Chowk": { lat: 28.4720, lon: 77.0725 },
    "Subhash Chowk Sohna Rd": { lat: 28.4311, lon: 77.0422 },
    "Hero Honda Chowk": { lat: 28.4389, lon: 77.0017 },
    "Golf Course Rd Genpact": { lat: 28.4550, lon: 77.1020 },
  },
};

export const RouteForm: React.FC<RouteFormProps> = ({
  city = "bengaluru",
  onPlanRoute,
  isLoading,
}) => {
  const currentPresets = CITY_PRESETS[city] || CITY_PRESETS.bengaluru;
  const presetKeys = Object.keys(currentPresets);

  const [originKey, setOriginKey] = useState<string>(presetKeys[0] || "");
  const [destKey, setDestKey] = useState<string>(presetKeys[2] || presetKeys[1] || "");
  const [vclass, setVclass] = useState<VehicleClass>("two_wheeler");

  useEffect(() => {
    const keys = Object.keys(CITY_PRESETS[city] || CITY_PRESETS.bengaluru);
    if (keys.length >= 2) {
      setOriginKey(keys[0]);
      setDestKey(keys[2] || keys[1]);
    }
  }, [city]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const origin = currentPresets[originKey];
    const dest = currentPresets[destKey];
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
          {presetKeys.map((name) => (
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
          {presetKeys.map((name) => (
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
