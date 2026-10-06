import React from "react";
import { PlannedRoute, RerouteResponse } from "../types";

interface LiveSimulatorProps {
  rerouteData: RerouteResponse | null;
  onAcceptDetour: (newRoute: PlannedRoute) => void;
  onStepTick: () => void;
  onStop: () => void;
  isLoading: boolean;
}

export const LiveSimulator: React.FC<LiveSimulatorProps> = ({
  rerouteData,
  onAcceptDetour,
  onStepTick,
  onStop,
  isLoading,
}) => {
  if (!rerouteData) return null;

  const isHold = rerouteData.action === "hold";
  const isSuggest = rerouteData.action === "suggest";

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--fr-accent)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: "var(--fr-text-base)" }}>Live Navigation Active</h3>
        <button
          type="button"
          className="select-btn"
          onClick={onStop}
          style={{ height: "2rem", padding: "0 0.5rem" }}
        >
          End Trip
        </button>
      </div>

      {isHold && (
        <div className="hold-banner">
          <span>🛑</span>
          <div>
            <strong>Water Immediately Ahead</strong>
            <p style={{ margin: "0.25rem 0 0", fontSize: "var(--fr-text-sm)" }}>
              {rerouteData.reasons[0] ||
                "Water is just ahead and there is no turn-off. Slow down and be ready to stop."}
            </p>
          </div>
        </div>
      )}

      {isSuggest && (
        <div className="warning-banner">
          <span>⚠️</span>
          <div style={{ flex: 1 }}>
            <strong>Detour Recommended</strong>
            <p style={{ margin: "0.25rem 0 0.5rem", fontSize: "var(--fr-text-sm)" }}>
              {rerouteData.reasons[0] ||
                "A road ahead may be flooded. Switch to the new route?"}
            </p>
            {rerouteData.suggested_route && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => onAcceptDetour(rerouteData.suggested_route!)}
                style={{ minHeight: "2.5rem", width: "100%", fontSize: "var(--fr-text-sm)" }}
              >
                Accept Detour ({rerouteData.suggested_route.eta_min} min)
              </button>
            )}
          </div>
        </div>
      )}

      {!isHold && !isSuggest && rerouteData.warn && (
        <div className="warning-banner">
          <span>⚠️</span>
          <div>
            <strong>Caution Ahead</strong>
            <p style={{ margin: "0.25rem 0 0", fontSize: "var(--fr-text-sm)" }}>
              {rerouteData.reasons[0] ||
                "A road ahead may be flooded. Slow down and stay alert."}
            </p>
          </div>
        </div>
      )}

      {!isHold && !isSuggest && !rerouteData.warn && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span className="risk-badge" data-state={rerouteData.current_worst_state || "clear"}>
            Route Clear
          </span>
          <span style={{ fontSize: "var(--fr-text-sm)", color: "var(--fr-ink-2)" }}>
            No flooding detected on upcoming road segments.
          </span>
        </div>
      )}

      <button
        type="button"
        className="btn-secondary"
        onClick={onStepTick}
        disabled={isLoading}
        style={{ marginTop: "0.5rem" }}
      >
        {isLoading ? "Checking Next Segment..." : "Simulate Next Position Tick"}
      </button>
    </div>
  );
};
