import React, { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "./components/Header";
import { LiveSimulator } from "./components/LiveSimulator";
import { CITY_HOTSPOTS, MapView, STATUS_SYMBOLS } from "./components/MapView";
import { ReportModal } from "./components/ReportModal";
import { RouteCard } from "./components/RouteCard";
import { CITY_PRESETS, RouteForm } from "./components/RouteForm";
import type { ClosureSnapshot, HealthResponse, Language, LatLon, OfflineReportPayload, PlannedRoute, RerouteResponse, RiskState, RoutePlanResponse, Theme, VehicleClass } from "./types";
import { apiUrl, fetchClosureSnapshot, flushOfflineReports, formatConditionsAsOf, queueOfflineReport, tryRegisterBackgroundSync } from "./utils/offline";
import { createDemoRoute, createDemoStep } from "./utils/demo";

const STATUS_LABELS: Record<RiskState, string> = { clear: "Clear", watch: "Watch", risky: "Likely flooded", impassable: "Closed", unknown: "No recent data" };
const API_CONFIGURED = Boolean((import.meta as unknown as { env?: Record<string, string> }).env?.VITE_API_BASE_URL);

function getCityEndpoints(city: string): [LatLon, LatLon] {
  const places = Object.values(CITY_PRESETS[city] || CITY_PRESETS.bengaluru);
  return [places[0], places[2] || places[1]];
}

function getStoredReporterId(): string {
  try {
    const existing = localStorage.getItem("floodroute_reporter_id");
    if (existing) return existing;
    const generated = `citizen_${crypto.randomUUID()}`;
    localStorage.setItem("floodroute_reporter_id", generated);
    return generated;
  } catch { return "citizen_anon"; }
}

export const App: React.FC = () => {
  const [theme, setTheme] = useState<Theme>("light");
  const [lang, setLang] = useState<Language>("en");
  const [city, setCity] = useState("bengaluru");
  const [vclass, setVclass] = useState<VehicleClass>("two_wheeler");
  const [demoMode, setDemoMode] = useState(() => !API_CONFIGURED && new URLSearchParams(window.location.search).get("live") !== "1");
  const [activeRoute, setActiveRoute] = useState<PlannedRoute | null>(null);
  const [rerouteData, setRerouteData] = useState<RerouteResponse | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [isOnline, setIsOnline] = useState(false);
  const [snapshot, setSnapshot] = useState<ClosureSnapshot | null>(null);
  const [snapshotStale, setSnapshotStale] = useState(true);
  const [snapshotFromCache, setSnapshotFromCache] = useState(false);
  const [isRouteLoading, setIsRouteLoading] = useState(false);
  const [guidanceMessage, setGuidanceMessage] = useState<string | null>(null);
  const [simStep, setSimStep] = useState(0);
  const [currentOrigin, setCurrentOrigin] = useState<LatLon>(getCityEndpoints("bengaluru")[0]);
  const [currentDest, setCurrentDest] = useState<LatLon>(getCityEndpoints("bengaluru")[1]);
  const requestId = useRef(0);
  const demoModeRef = useRef(demoMode);
  const conditionsText = snapshot ? formatConditionsAsOf(snapshot.conditions_as_of) : "No recent road data";
  const cityName = { bengaluru: "Bengaluru", mumbai: "Mumbai", gurugram: "Gurugram" }[city] || "Bengaluru";

  useEffect(() => { document.documentElement.setAttribute("data-theme", theme); }, [theme]);
  useEffect(() => { document.documentElement.setAttribute("lang", lang); }, [lang]);

  const flushPendingReports = useCallback(async () => {
    await flushOfflineReports(async (report: OfflineReportPayload) => {
      if (demoModeRef.current) return false;
      try {
        const response = await fetch(apiUrl("/v1/reports"), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat: report.lat, lon: report.lon, depth_class: report.depth_class, photo_ref: report.photo_ref || null, reporter_id: report.reporter_id }),
          signal: AbortSignal.timeout(7000),
        });
        return response.ok;
      } catch { return false; }
    });
  }, []);

  useEffect(() => {
    if (demoMode) { setIsOnline(false); return; }
    let cancelled = false;
    const refresh = async () => {
      const [healthResult, snapshotResult] = await Promise.allSettled([
        fetch(apiUrl("/v1/health"), { signal: AbortSignal.timeout(7000) }).then(async (response) => {
          if (!response.ok) return false;
          const data: HealthResponse = await response.json();
          return data.status === "ok" || data.status === "degraded";
        }),
        fetchClosureSnapshot(city, vclass),
      ]);
      if (cancelled) return;
      const connected = healthResult.status === "fulfilled" && healthResult.value;
      setIsOnline(connected);
      if (snapshotResult.status === "fulfilled") {
        const result = snapshotResult.value;
        setSnapshot(result.snapshot);
        setSnapshotStale(result.isStale);
        setSnapshotFromCache(result.fromCache);
      } else { setSnapshot(null); setSnapshotStale(true); }
      if (connected) void flushPendingReports();
    };
    void refresh();
    const interval = window.setInterval(refresh, 30000);
    const onOffline = () => setIsOnline(false);
    const onMessage = (event: MessageEvent) => { if (event.data?.type === "FLUSH_OFFLINE_REPORTS") void flushPendingReports(); };
    window.addEventListener("online", refresh);
    window.addEventListener("offline", onOffline);
    navigator.serviceWorker?.addEventListener("message", onMessage);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.removeEventListener("online", refresh);
      window.removeEventListener("offline", onOffline);
      navigator.serviceWorker?.removeEventListener("message", onMessage);
    };
  }, [demoMode, city, vclass, flushPendingReports]);

  const resetJourney = () => {
    requestId.current += 1;
    setActiveRoute(null); setRerouteData(null); setIsSimulating(false); setSimStep(0); setGuidanceMessage(null); setIsRouteLoading(false);
  };
  const changeCity = (nextCity: string) => {
    resetJourney(); setCity(nextCity); setSnapshot(null); setSnapshotStale(true); setSnapshotFromCache(false); setIsOnline(false);
    const [origin, destination] = getCityEndpoints(nextCity);
    setCurrentOrigin(origin); setCurrentDest(destination);
  };
  const changeMode = (demo: boolean) => {
    demoModeRef.current = demo;
    resetJourney(); setDemoMode(demo); setSnapshot(null); setSnapshotStale(true); setSnapshotFromCache(false); setIsOnline(false);
  };

  const handlePlanRoute = async (origin: LatLon, destination: LatLon, vehicle: VehicleClass) => {
    const id = ++requestId.current;
    setIsRouteLoading(true); setGuidanceMessage(null); setCurrentOrigin(origin); setCurrentDest(destination); setVclass(vehicle);
    try {
      if (demoMode) {
        setActiveRoute(createDemoRoute(origin, destination, vehicle));
        return;
      }
      const response = await fetch(apiUrl("/v1/route"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ origin, destination, vclass: vehicle, depart_at: new Date().toISOString(), profile: "citizen", lang }),
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error("Route service unavailable");
      const data: RoutePlanResponse = await response.json();
      if (id !== requestId.current) return;
      setActiveRoute(data.routes?.[0] || null);
      if (!data.routes?.length) setGuidanceMessage(data.guidance_when_no_route?.text?.join(". ") || "No passable route was returned for this vehicle. Wait for conditions to improve.");
    } catch {
      if (id !== requestId.current) return;
      setActiveRoute(null);
      setGuidanceMessage("The route service could not be reached. Try again, or select Demo to explore a sample journey.");
    } finally { if (id === requestId.current) setIsRouteLoading(false); }
  };

  const handleStartSimulation = () => {
    setIsSimulating(true); setSimStep(0);
    setRerouteData({ decision_id: "demo-start", action: "keep", code: "demo_started", warn: false, reasons: ["Sample journey started. Advance the scenario to see a warning, detour and road closure."], reason_keys: [], trip_state: { baseline_band: 0, closed_at: {} }, current_worst_state: "watch", current_worst_band: 1, current_violations_count: 0, lang });
  };
  const handleStepTick = () => {
    const nextStep = simStep + 1;
    setSimStep(nextStep);
    setRerouteData(createDemoStep(nextStep, currentOrigin, currentDest, vclass, lang));
  };
  const handleAcceptDetour = (route: PlannedRoute) => {
    setActiveRoute(route);
    setRerouteData((previous) => previous ? { ...previous, action: "keep", code: "detour_accepted", warn: false, reasons: ["Sample detour accepted. The route on the map has changed."], suggested_route: undefined, current_worst_state: route.worst_state, current_worst_band: 1, current_violations_count: 0, trip_state: { ...previous.trip_state, baseline_band: 1 } } : null);
  };
  const handleStopSimulation = () => { setIsSimulating(false); setRerouteData(null); setSimStep(0); if (!demoMode) setActiveRoute(null); };

  const handleSubmitReport = async (data: { lat: number; lon: number; depthClass: string; photoRef?: string }) => {
    if (demoMode) return;
    const payload = { lat: data.lat, lon: data.lon, depth_class: data.depthClass, photo_ref: data.photoRef || null, reporter_id: getStoredReporterId() };
    if (isOnline) {
      let response: Response | undefined;
      try {
        response = await fetch(apiUrl("/v1/reports"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal: AbortSignal.timeout(7000) });
      } catch { /* Persist below when a send fails. */ }
      if (response?.ok) return;
      if (response && response.status >= 400 && response.status < 500 && response.status !== 429) {
        throw new Error("The report was rejected. Check the location and observation before retrying.");
      }
    }
    queueOfflineReport(payload);
    tryRegisterBackgroundSync();
  };

  const conditionRows = demoMode ? CITY_HOTSPOTS[city].map((road) => ({ name: road.name, state: road.severity, note: `Sample scenario: ${STATUS_LABELS[road.severity].toLowerCase()}` })) : (snapshot?.features || []).slice(0, 8).map((feature) => ({
    name: `Road segment ${feature.properties.segment_id}`,
    state: snapshotStale ? "unknown" as const : feature.properties.state,
    note: snapshotStale ? "Last observation is out of date" : `${feature.properties.road_class || "Road"} / ${feature.properties.structure || "At grade"}`,
  }));

  return (
    <div className="app-container" id="top">
      <a className="skip-link" href="#planner">Skip to route planner</a>
      <Header theme={theme} onThemeChange={setTheme} lang={lang} onLangChange={setLang} city={city} onCityChange={changeCity} onOpenReport={() => setReportModalOpen(true)} isOnline={isOnline} />
      <main>
        <section className="hero section-shell" aria-labelledby="hero-title">
          <p className="eyebrow">Flood-aware routing for Indian cities</p>
          <h1 id="hero-title">KNOW THE ROAD.<br />BEFORE YOU GO.</h1>
          <p className="hero-description">Plan around flooded roads.<br className="mobile-break" /> See when conditions change.</p>
          <div className="hero-actions"><a className="btn-primary" href="#planner">Plan a route <span aria-hidden="true">↗</span></a><a className="text-link" href="#how-it-works">See how it works</a></div>
          <p className="hero-caption">Built for the journey. Prepared for the rain.</p>
        </section>

        <section className="planner-section section-shell" id="planner" aria-labelledby="planner-title">
          <div className="section-heading">
            <div><p className="eyebrow">Your journey / {cityName}</p><h2 id="planner-title">A route with context.</h2><p>See the detour. Understand the road ahead.</p></div>
            <div className="mode-control" role="group" aria-label="Road data mode"><button type="button" aria-pressed={demoMode} onClick={() => changeMode(true)}>Demo</button><button type="button" aria-pressed={!demoMode} onClick={() => changeMode(false)}>Live data</button></div>
          </div>
          <div className="workspace-status" role="status"><span className="status-indicator" aria-hidden="true" /><span>{demoMode ? "Interactive demo. Routes and conditions are illustrative." : isOnline ? `${snapshotFromCache ? "Cached road data" : "API connected"}. ${conditionsText}.` : `API unavailable. ${snapshot ? conditionsText : "No live road data available"}.`}</span></div>
          {!demoMode && snapshotStale && snapshot && <p className="warning-banner" role="status">Road observations are out of date. Showing unknown status until fresh data arrives.</p>}
          <div className="planner-workspace">
            <div className="planner-map"><MapView theme={theme} city={city} vclass={vclass} snapshot={demoMode || isSimulating || snapshotStale ? null : snapshot} origin={currentOrigin} destination={currentDest} activeRoute={activeRoute} rerouteData={rerouteData} isSimulating={isSimulating} simStep={simStep} totalSimSteps={6} demoMode={demoMode || isSimulating} /></div>
            <aside className="planner-panel" aria-label="Journey planner">
              <div className="planner-panel-header"><div><p className="eyebrow">{isSimulating ? "Sample scenario" : "Your trip"}</p><h3>{isSimulating ? "See what changes." : activeRoute ? "Ready to explore." : "Where are you going?"}</h3></div>{activeRoute && <button className="btn-icon" type="button" onClick={resetJourney} aria-label="Plan a new journey">↺</button>}</div>
              <div className="planner-panel-content">
                {guidanceMessage && <p className="warning-banner" role="alert">{guidanceMessage}</p>}
                {!activeRoute && <RouteForm key={city} city={city} onPlanRoute={handlePlanRoute} isLoading={isRouteLoading} />}
                {activeRoute && !isSimulating && <RouteCard route={activeRoute} onStartTrip={handleStartSimulation} isSimulating={false} demoMode={demoMode} />}
                {isSimulating && <LiveSimulator rerouteData={rerouteData} onAcceptDetour={handleAcceptDetour} onStepTick={handleStepTick} onStop={handleStopSimulation} isLoading={false} demoMode />}
                <p className="planner-note">{demoMode || isSimulating ? "Sample scenario, not navigation guidance. No live road assessments are used." : "Road conditions can change. Unknown data does not mean a road is clear."}</p>
              </div>
            </aside>
          </div>
          <div className="planner-caption"><span>{cityName} / {demoMode || isSimulating ? "Sample scenario" : "Road observations"}</span><button type="button" className="text-link" onClick={() => setReportModalOpen(true)}>Report a road condition <span aria-hidden="true">↗</span></button></div>
        </section>

        <section className="conditions-section section-shell" id="conditions" aria-labelledby="conditions-title">
          <div className="section-heading"><div><p className="eyebrow">Conditions with context</p><h2 id="conditions-title">Know what changed.</h2><p>A road status. Its source. Its last update.</p></div><p className="data-caption">{demoMode ? "Sample data / not live" : conditionsText}</p></div>
          <div className="conditions-table" role="region" aria-label={`${cityName} road conditions`} tabIndex={0}>
            <table><thead><tr><th scope="col">Road</th><th scope="col">Status</th><th scope="col">Context</th><th scope="col">Source</th></tr></thead><tbody>
              {conditionRows.map((road) => <tr key={road.name}><th scope="row">{road.name}</th><td><span className="condition-status" data-state={road.state}><span aria-hidden="true">{STATUS_SYMBOLS[road.state]}</span>{STATUS_LABELS[road.state]}</span></td><td>{road.note}</td><td className="data-caption">{demoMode ? "Sample scenario" : snapshotFromCache ? "Cached snapshot" : "Road snapshot"}</td></tr>)}
              {!conditionRows.length && <tr><td colSpan={4} className="empty-conditions">No recent road observations are available. Select Demo to explore sample conditions.</td></tr>}
            </tbody></table>
          </div>
        </section>

        <section className="how-section section-shell" id="how-it-works" aria-labelledby="how-title">
          <div className="section-heading"><div><p className="eyebrow">From awareness to action</p><h2 id="how-title">Three steps. A clearer journey.</h2></div></div>
          <ol className="how-steps"><li><span className="step-number">01</span><h3>Choose your journey.</h3><p>Select your city, vehicle and destination. Road passability depends on what you drive.</p></li><li><span className="step-number">02</span><h3>Understand the conditions.</h3><p>Check closures, warnings and data freshness. No recent data is always shown as unknown.</p></li><li><span className="step-number">03</span><h3>Adapt as things change.</h3><p>Try the scenario: rising water, a suggested detour, then a road closure. Keep the decision in your hands.</p></li></ol>
        </section>
        <section className="closing-section section-shell"><h2>One less unknown.<br />Before you head out.</h2><a className="btn-primary" href="#planner">Try the route planner <span aria-hidden="true">↗</span></a></section>
      </main>
      <footer className="site-footer section-shell"><a href="#top" className="brand-wordmark">FLOODROUTE<span aria-hidden="true">↗</span></a><p>Flood-aware journeys. India.</p><span className="data-caption">Hackathon prototype / 2026</span></footer>
      <ReportModal isOpen={reportModalOpen} onClose={() => setReportModalOpen(false)} onSubmitReport={handleSubmitReport} defaultLocation={currentOrigin} demoMode={demoMode} isOnline={isOnline} />
    </div>
  );
};
