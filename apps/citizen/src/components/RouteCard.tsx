import React from "react";
import { PlannedRoute, RiskState } from "../types";

interface RouteCardProps {
  route: PlannedRoute;
  onStartTrip: () => void;
  isSimulating: boolean;
}

const STATE_LABELS: Record<RiskState, string> = {
  clear: "Clear",
  watch: "Watch",
  risky: "Risky",
  impassable: "Impassable",
  unknown: "Unknown",
};

export const RouteCard: React.FC<RouteCardProps> = ({
  route,
  onStartTrip,
  isSimulating,
}) => {
  const worstState = route.worst_state;

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <span style={{ fontSize: "var(--fr-text-2xl)", fontWeight: 700 }}>
            {route.eta_min} min
          </span>
          {route.delta_min !== undefined && route.delta_min > 0 && (
            <span style={{ marginLeft: "0.5rem", color: "var(--fr-ink-2)" }}>
              (+{route.delta_min} min detour)
            </span>
          )}
        </div>

        <span className="risk-badge" data-state={worstState}>
          {STATE_LABELS[worstState] || "Unknown"}
        </span>
      </div>

      {route.reasons.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {route.reasons.map((reason, idx) => (
            <p key={idx} style={{ margin: 0, fontSize: "var(--fr-text-sm)", color: "var(--fr-ink)" }}>
              {reason}
            </p>
          ))}
        </div>
      )}

      <div style={{ borderTop: "1px solid var(--hairline)", paddingTop: "0.75rem" }}>
        <span style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-ink-2)" }}>
          {route.segments.length} road segments monitored
        </span>
      </div>

      <button
        type="button"
        className="btn-primary"
        onClick={onStartTrip}
        style={{ marginTop: "0.5rem" }}
      >
        {isSimulating ? "Stop Navigation Simulation" : "Start Navigation Simulation"}
      </button>
    </div>
  );
};
