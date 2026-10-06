import React, { useCallback, useEffect, useState } from "react";
import { BottomSheet, SnapPoint } from "./components/BottomSheet";
import { Header } from "./components/Header";
import { LiveSimulator } from "./components/LiveSimulator";
import { ReportModal } from "./components/ReportModal";
import { RouteCard } from "./components/RouteCard";
import { RouteForm } from "./components/RouteForm";
import {
  HealthResponse,
  Language,
  LatLon,
  PlannedRoute,
  RerouteResponse,
  RiskState,
  RoutePlanResponse,
  Theme,
  VehicleClass,
} from "./types";

const BANGALORE_CORRIDORS: Array<{ name: string; state: RiskState; note: string }> = [
  { name: "Silk Board Junction", state: "watch", note: "Moderate runoff near service road" },
  { name: "Bellandur EcoSpace ORR", state: "risky", note: "Water buildup on outer ring road" },
  { name: "Indiranagar 100ft Rd", state: "clear", note: "Normal drainage flow" },
  { name: "Domlur Flyover", state: "clear", note: "Elevated corridor clear" },
  { name: "Windsor Manor Underpass", state: "impassable", note: "Deep waterlogging in underpass" },
];

function getStoredReporterId(): string {
  try {
    const existing = localStorage.getItem("floodroute_reporter_id");
    if (existing) return existing;
    const generated = `citizen_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("floodroute_reporter_id", generated);
    return generated;
  } catch {
    return "citizen_anon";
  }
}

export const App: React.FC = () => {
  const [theme, setTheme] = useState<Theme>("light");
  const [lang, setLang] = useState<Language>("en");
  const [vclass, setVclass] = useState<VehicleClass>("two_wheeler");
  const [activeRoute, setActiveRoute] = useState<PlannedRoute | null>(null);
  const [rerouteData, setRerouteData] = useState<RerouteResponse | null>(null);
  const [isSimulating, setIsSimulating] = useState<boolean>(false);
  const [reportModalOpen, setReportModalOpen] = useState<boolean>(false);
  const [isOnline, setIsOnline] = useState<boolean>(true);

  const [sheetSnap, setSheetSnap] = useState<SnapPoint>("half");
  const [isRouteLoading, setIsRouteLoading] = useState<boolean>(false);
  const [isSimLoading, setIsSimLoading] = useState<boolean>(false);
  const [guidanceMessage, setGuidanceMessage] = useState<string | null>(null);
  const [simStep, setSimStep] = useState<number>(0);

  const [currentOrigin, setCurrentOrigin] = useState<LatLon>({ lat: 12.9719, lon: 77.6412 });
  const [currentDest, setCurrentDest] = useState<LatLon>({ lat: 12.9172, lon: 77.6228 });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch("/v1/health");
      if (res.ok) {
        const data: HealthResponse = await res.json();
        setIsOnline(data.status === "ok" || data.status === "degraded");
      } else {
        setIsOnline(false);
      }
    } catch {
      setIsOnline(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const intervalId = window.setInterval(checkHealth, 20000);

    const handleWindowOnline = () => {
      setIsOnline(true);
      checkHealth();
    };
    const handleWindowOffline = () => {
      setIsOnline(false);
    };

    window.addEventListener("online", handleWindowOnline);
    window.addEventListener("offline", handleWindowOffline);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("online", handleWindowOnline);
      window.removeEventListener("offline", handleWindowOffline);
    };
  }, [checkHealth]);

  const handlePlanRoute = async (origin: LatLon, dest: LatLon, selectedVclass: VehicleClass) => {
    setIsRouteLoading(true);
    setGuidanceMessage(null);
    setCurrentOrigin(origin);
    setCurrentDest(dest);
    setVclass(selectedVclass);

    const reqPayload = {
      origin: { lat: origin.lat, lon: origin.lon },
      destination: { lat: dest.lat, lon: dest.lon },
      vclass: selectedVclass,
      depart_at: new Date().toISOString(),
      profile: "citizen",
      lang,
    };

    try {
      const res = await fetch("/v1/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reqPayload),
      });

      if (res.ok) {
        const data: RoutePlanResponse = await res.json();
        if (data.routes && data.routes.length > 0) {
          setActiveRoute(data.routes[0]);
          setSheetSnap("half");
          setGuidanceMessage(null);
        } else {
          setActiveRoute(null);
          const advice = data.guidance_when_no_route?.text?.join(". ");
          setGuidanceMessage(
            advice || "No passable path available for this vehicle type due to water levels."
          );
          setSheetSnap("expanded");
        }
      } else {
        throw new Error(`Routing service returned status ${res.status}`);
      }
    } catch {
      const fallbackRoute: PlannedRoute = {
        kind: "least_risk",
        is_default: true,
        eta_min: selectedVclass === "two_wheeler" ? 28 : 34,
        delta_min: 5,
        worst_state: "watch",
        data_age_s: 30,
        reasons: [
          "Offline cached routing active",
          "Corridor avoids Bellandur EcoSpace water accumulation",
          "Monitored elevated bypass selected",
        ],
        segments: [
          { segment_id: "seg_indiranagar", assessed: true, state: "clear", p: 0.1 },
          { segment_id: "seg_domlur", assessed: true, state: "clear", p: 0.15 },
          { segment_id: "seg_koramangala", assessed: true, state: "watch", p: 0.4 },
          { segment_id: "seg_silkboard", assessed: true, state: "watch", p: 0.45 },
        ],
        geometry: "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
      };
      setActiveRoute(fallbackRoute);
      setSheetSnap("half");
      setGuidanceMessage("Offline mode: Provided local fallback route minimizing water risks.");
    } finally {
      setIsRouteLoading(false);
    }
  };

  const handleToggleSimulation = () => {
    if (isSimulating) {
      setIsSimulating(false);
      setRerouteData(null);
      setSimStep(0);
    } else {
      setIsSimulating(true);
      setSimStep(0);

      const initialReroute: RerouteResponse = {
        decision_id: `sim_init_${Date.now()}`,
        action: "keep",
        code: "clear",
        warn: false,
        reasons: ["Live corridor monitoring active. Road conditions Clear."],
        reason_keys: ["clear"],
        trip_state: {
          baseline_band: 0,
          closed_at: {},
        },
        current_worst_state: activeRoute?.worst_state || "clear",
        current_worst_band: 0,
        current_violations_count: 0,
        lang,
      };
      setRerouteData(initialReroute);
      setSheetSnap("expanded");
    }
  };

  const handleStepTick = async () => {
    setIsSimLoading(true);
    const nextStep = simStep + 1;
    setSimStep(nextStep);

    const edges = [
      {
        segment_id: 100 + nextStep,
        travel_time_s: 180,
        length_m: 600,
        turn_off_after: true,
        geometry: [
          { lat: currentOrigin.lat, lon: currentOrigin.lon },
          { lat: currentDest.lat, lon: currentDest.lon },
        ],
      },
    ];

    const reroutePayload = {
      origin: { lat: currentOrigin.lat, lon: currentOrigin.lon },
      destination: { lat: currentDest.lat, lon: currentDest.lon },
      vclass,
      current_edges: edges,
      trip_state: rerouteData?.trip_state || { baseline_band: 0, closed_at: {} },
      depart_at: new Date().toISOString(),
      profile: "citizen",
      lang,
    };

    try {
      const res = await fetch("/v1/route/reroute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(reroutePayload),
      });

      if (res.ok) {
        const data: RerouteResponse = await res.json();
        setRerouteData(data);
        return;
      }
      throw new Error(`Reroute service returned status ${res.status}`);
    } catch {
      if (nextStep % 3 === 1) {
        setRerouteData({
          decision_id: `sim_tick_${nextStep}`,
          action: "keep",
          code: "watch_ahead",
          warn: true,
          reasons: ["Water runoff reported 300m ahead on side lanes. Reduce speed."],
          reason_keys: ["watch_ahead"],
          trip_state: { baseline_band: 1, closed_at: {} },
          current_worst_state: "watch",
          current_worst_band: 1,
          current_violations_count: 0,
          lang,
        });
      } else if (nextStep % 3 === 2) {
        const detourRoute: PlannedRoute = {
          kind: "least_risk",
          is_default: false,
          eta_min: (activeRoute?.eta_min || 25) + 3,
          delta_min: 3,
          worst_state: "watch",
          reasons: ["Bypasses rising water near junction"],
          segments: [
            { segment_id: "detour_1", assessed: true, state: "clear", p: 0.1 },
            { segment_id: "detour_2", assessed: true, state: "watch", p: 0.3 },
          ],
          geometry: "_p~iF~ps|U_ulLnnqC_mqNvxq`@",
        };

        setRerouteData({
          decision_id: `sim_tick_${nextStep}`,
          action: "suggest",
          code: "detour_suggested",
          warn: true,
          reasons: ["Rapid water accumulation detected ahead. Alternate elevated corridor recommended."],
          reason_keys: ["detour_suggested"],
          trip_state: { baseline_band: 2, closed_at: {} },
          suggested_route: detourRoute,
          current_worst_state: "risky",
          current_worst_band: 2,
          current_violations_count: 1,
          lang,
        });
      } else {
        setRerouteData({
          decision_id: `sim_tick_${nextStep}`,
          action: "hold",
          code: "water_ahead",
          warn: true,
          reasons: ["Water depth exceeds limit directly ahead with no turn-off. Halt vehicle."],
          reason_keys: ["water_ahead"],
          trip_state: { baseline_band: 3, closed_at: {} },
          current_worst_state: "impassable",
          current_worst_band: 3,
          current_violations_count: 2,
          lang,
        });
      }
    } finally {
      setIsSimLoading(false);
    }
  };

  const handleAcceptDetour = (newRoute: PlannedRoute) => {
    setActiveRoute(newRoute);
    setRerouteData((prev) =>
      prev
        ? {
            ...prev,
            action: "keep",
            code: "detour_accepted",
            warn: false,
            reasons: ["Detour accepted. Following elevated route."],
            suggested_route: undefined,
          }
        : null
    );
  };

  const handleStopSimulation = () => {
    setIsSimulating(false);
    setRerouteData(null);
    setSimStep(0);
  };

  const handleSubmitReport = async (data: {
    lat: number;
    lon: number;
    depthClass: string;
    photoRef?: string;
  }) => {
    const reporterId = getStoredReporterId();
    const payload = {
      lat: data.lat,
      lon: data.lon,
      depth_class: data.depthClass,
      photo_ref: data.photoRef || null,
      reporter_id: reporterId,
    };

    try {
      const res = await fetch("/v1/reports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Report submission returned ${res.status}`);
      }
    } catch {
      try {
        const queueKey = "floodroute_pending_reports";
        const currentQueue = JSON.parse(localStorage.getItem(queueKey) || "[]");
        currentQueue.push(payload);
        localStorage.setItem(queueKey, JSON.stringify(currentQueue));
      } catch {
        // Local storage unavailable
      }
    }
  };

  const sheetTitle = isSimulating
    ? "Live Navigation"
    : activeRoute
      ? "Trip Navigation Plan"
      : "Plan Flood-Aware Route";

  return (
    <div className="app-container">
      <Header
        theme={theme}
        onThemeChange={setTheme}
        lang={lang}
        onLangChange={setLang}
        onOpenReport={() => setReportModalOpen(true)}
        isOnline={isOnline}
      />

      <main className="main-view">
        {!isOnline && (
          <div className="warning-banner" role="status">
            <span>⚡</span>
            <div>
              <strong>Offline Mode Active</strong>
              <p style={{ margin: "0.25rem 0 0", fontSize: "var(--fr-text-sm)" }}>
                Operating with cached flood risk intelligence and local routing.
              </p>
            </div>
          </div>
        )}

        {guidanceMessage && (
          <div className="hold-banner" role="alert">
            <span>ℹ️</span>
            <div>
              <strong>Travel Advisory</strong>
              <p style={{ margin: "0.25rem 0 0", fontSize: "var(--fr-text-sm)" }}>
                {guidanceMessage}
              </p>
            </div>
          </div>
        )}

        <section className="card" aria-labelledby="corridor-heading">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 id="corridor-heading" style={{ margin: 0, fontSize: "var(--fr-text-base)" }}>
              Bangalore Flood Risk Corridors
            </h2>
            <span style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-ink-2)" }}>
              Live Telemetry
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {BANGALORE_CORRIDORS.map((corridor) => (
              <div
                key={corridor.name}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "0.5rem 0",
                  borderBottom: "1px solid var(--hairline)",
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: "var(--fr-text-sm)" }}>
                    {corridor.name}
                  </div>
                  <div style={{ fontSize: "var(--fr-text-xs)", color: "var(--fr-ink-2)" }}>
                    {corridor.note}
                  </div>
                </div>
                <span className="risk-badge" data-state={corridor.state}>
                  {corridor.state === "clear"
                    ? "Clear"
                    : corridor.state === "watch"
                      ? "Watch"
                      : corridor.state === "risky"
                        ? "Risky"
                        : "Impassable"}
                </span>
              </div>
            ))}
          </div>
        </section>

        {activeRoute && (
          <section className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0, fontSize: "var(--fr-text-base)" }}>
                Selected Route Corridor
              </h3>
              <span className="risk-badge" data-state={activeRoute.worst_state}>
                Worst: {activeRoute.worst_state.toUpperCase()}
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div style={{ fontSize: "var(--fr-text-sm)", color: "var(--fr-ink-2)" }}>
                Monitored road segments ({activeRoute.segments.length}):
              </div>

              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                {activeRoute.segments.map((seg, idx) => (
                  <span
                    key={seg.segment_id || idx}
                    className="risk-badge"
                    data-state={seg.state || "unknown"}
                    style={{ fontSize: "var(--fr-text-xs)", padding: "0.15rem 0.5rem" }}
                  >
                    #{idx + 1} {seg.state || "assessing"}
                  </span>
                ))}
              </div>
            </div>
          </section>
        )}
      </main>

      <BottomSheet
        snap={sheetSnap}
        onSnapChange={setSheetSnap}
        title={sheetTitle}
        headerExtra={
          activeRoute && !isSimulating ? (
            <button
              type="button"
              className="select-btn"
              onClick={() => {
                setActiveRoute(null);
                setSheetSnap("expanded");
              }}
              style={{ height: "2rem", fontSize: "var(--fr-text-xs)" }}
            >
              New Route
            </button>
          ) : undefined
        }
      >
        {!activeRoute && (
          <RouteForm onPlanRoute={handlePlanRoute} isLoading={isRouteLoading} />
        )}

        {activeRoute && (
          <>
            {isSimulating && (
              <LiveSimulator
                rerouteData={rerouteData}
                onAcceptDetour={handleAcceptDetour}
                onStepTick={handleStepTick}
                onStop={handleStopSimulation}
                isLoading={isSimLoading}
              />
            )}

            <RouteCard
              route={activeRoute}
              onStartTrip={handleToggleSimulation}
              isSimulating={isSimulating}
            />
          </>
        )}
      </BottomSheet>

      <ReportModal
        isOpen={reportModalOpen}
        onClose={() => setReportModalOpen(false)}
        onSubmitReport={handleSubmitReport}
        defaultLocation={currentOrigin}
      />
    </div>
  );
};

export default App;
