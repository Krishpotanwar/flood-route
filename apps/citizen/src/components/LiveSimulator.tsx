import React from "react";
import { PlannedRoute, RerouteResponse } from "../types";
import { STATE_LABELS } from "./RouteCard";

interface LiveSimulatorProps {
  rerouteData: RerouteResponse | null;
  onAcceptDetour: (newRoute: PlannedRoute) => void;
  onStepTick: () => void;
  onStop: () => void;
  isLoading: boolean;
  demoMode?: boolean;
}

export const LiveSimulator: React.FC<LiveSimulatorProps> = ({
  rerouteData,
  onAcceptDetour,
  onStepTick,
  onStop,
  isLoading,
  demoMode = false,
}) => {
  if (!rerouteData) return null;

  const isHold = rerouteData.action === "hold";
  const isSuggest = rerouteData.action === "suggest";
  const state = rerouteData.current_worst_state || "unknown";

  return (
    <div className="card simulator-card" aria-busy={isLoading}>
      <div className="route-summary">
        <div>
          <p className="eyebrow">{demoMode ? "Demo scenario" : "Journey preview"}</p>
          <h3>Simulation active</h3>
        </div>
        <button
          type="button"
          className="text-link"
          onClick={onStop}
          disabled={isLoading}
        >
          End preview
        </button>
      </div>

      {isHold && (
        <div className="hold-banner" role="status">
          <div>
            <strong>Stop: high water ahead</strong>
            <p>
              {rerouteData.reasons[0] ||
                "Water is just ahead and there is no turn-off. Slow down and be ready to stop."}
            </p>
          </div>
        </div>
      )}

      {isSuggest && (
        <div className="warning-banner" role="status">
          <div>
            <strong>A lower-risk detour is available</strong>
            <p>
              {rerouteData.reasons[0] ||
                "A road ahead may be flooded. Switch to the new route?"}
            </p>
            {rerouteData.suggested_route && (
              <button
                type="button"
                className="btn-primary"
                onClick={() => onAcceptDetour(rerouteData.suggested_route!)}
                disabled={isLoading}
              >
                Accept detour · {rerouteData.suggested_route.eta_min} min <span aria-hidden="true">↗</span>
              </button>
            )}
          </div>
        </div>
      )}

      {!isHold && !isSuggest && rerouteData.warn && (
        <div className="warning-banner" role="status">
          <div>
            <strong>Use caution ahead</strong>
            <p>
              {rerouteData.reasons[0] ||
                "A road ahead may be flooded. Slow down and stay alert."}
            </p>
          </div>
        </div>
      )}

      {!isHold && !isSuggest && !rerouteData.warn && (
        <div className="route-meta" role="status">
          <span className="risk-badge" data-state={state}>
            {STATE_LABELS[state]}
          </span>
          <span>
            {rerouteData.reasons[0] || (state === "clear"
              ? "No current warning on assessed upcoming segments."
              : "Check the assessed road conditions before continuing.")}
          </span>
        </div>
      )}

      <div className="simulator-actions">
        <button
          type="button"
          className="btn-secondary"
          onClick={onStepTick}
          disabled={isLoading}
        >
          {isLoading ? "Checking next position…" : demoMode ? "Next demo scenario →" : "Check next simulated position →"}
        </button>
        <p className="field-hint">A preview of warnings and rerouting; verify local conditions before travel.</p>
      </div>
    </div>
  );
};
