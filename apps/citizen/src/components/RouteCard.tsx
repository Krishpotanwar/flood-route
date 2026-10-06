import React from "react";
import { PlannedRoute, RiskState } from "../types";

interface RouteCardProps {
  route: PlannedRoute;
  onStartTrip: () => void;
  isSimulating: boolean;
  demoMode?: boolean;
}

export const STATE_LABELS: Record<RiskState, string> = {
  clear: "Clear",
  watch: "Watch",
  risky: "High risk",
  impassable: "Impassable",
  unknown: "Unassessed",
};

export const RouteCard: React.FC<RouteCardProps> = ({
  route,
  onStartTrip,
  isSimulating,
  demoMode = false,
}) => {
  const worstState = route.worst_state;
  const knownCount = route.segments.filter((segment) => segment.assessed && segment.state != null && segment.state !== "unknown").length;
  const age = route.data_age_s;
  const dataAge = age !== undefined && Number.isFinite(age) && age >= 0
    ? `${age < 60 ? Math.round(age) + "s" : Math.ceil(age / 60) + " min"} old`
    : "Age unavailable";

  return (
    <div className="card route-card" aria-live="polite">
      <p className="eyebrow">{demoMode ? "Sample journey" : "Route assessment"}</p>
      <div className="route-summary">
        <div>
          <span className="route-time">
            {route.eta_min} <span>min</span>
          </span>
          {route.delta_min !== undefined && route.delta_min > 0 && (
            <p className="field-hint">+{route.delta_min} min to avoid higher risk</p>
          )}
        </div>

        <span className="risk-badge" data-state={worstState}>
          {STATE_LABELS[worstState] || "Unknown"}
        </span>
      </div>

      {route.reasons.length > 0 && (
        <div className="route-reasons">
          {route.reasons.map((reason, idx) => (
            <p key={idx}>
              {reason}
            </p>
          ))}
        </div>
      )}

      <div className="route-meta">
        <span>{knownCount} / {route.segments.length} segments with known status</span>
        <span>{demoMode ? "Illustrative conditions" : `Data: ${dataAge}`}</span>
      </div>

      <button
        type="button"
        className="btn-primary"
        onClick={onStartTrip}
        aria-pressed={isSimulating}
      >
        {isSimulating ? "Stop journey simulation" : "Preview journey simulation"}
        <span aria-hidden="true">{isSimulating ? "×" : "→"}</span>
      </button>
    </div>
  );
};
