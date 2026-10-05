# FloodRoute: Product Requirements Document

Version 0.1 draft, 2026-10-05. Owner: product. Status: awaiting decisions D1 to D10 in [00-brainstorm.md](00-brainstorm.md).
Evidence base: [research reports 01 to 06](research/). Tags: **[V]** verified in a source, **[U]** unverified, **[EST]** estimate. Technical detail lives in [TRD.md](TRD.md), sequencing in [PLAN.md](PLAN.md).

## 1. Summary

FloodRoute tells dispatched fleets, and the control rooms behind them, which roads will be impassable in the next one to two hours, and reroutes around them before the water arrives. Where maps say "heavy rain" and river agencies say "flood warning", FloodRoute says "avoid this underpass for the next 90 minutes, take this one instead". It is built for Indian cities, Indian vehicle classes and WhatsApp.

India only. First city: Bengaluru. First live window: the April to May 2027 pre-monsoon storms.

## 2. Problem

**Harm is concentrated in short bursts on specific road segments.**
- Faridabad, Sep 2024: two people died when an SUV entered a flooded underpass despite barricades and warnings [V, report 03].
- Gurugram, Jul to Aug 2026: about 300 schoolchildren stuck about 2 hours in 15 vehicles after about an hour of rain [V].
- Bengaluru, May 2025: 104 to 130 mm; Silk Board and Hosur Road flyover closed; 44 four-wheelers and 93 two-wheelers submerged or swept [V].
- Delhi, Jul 2024: three people drowned in a basement after 31.5 mm in 3 hours [V].

**No source shows street-level flooding today.** India's open data is rainfall, river stage and district-level alerts. The IMD, CWC, NDMA SACHET, iFLOWS-Mumbai, KSNDMC and Chennai systems are monitors, not routers [V, reports 01, 03]. Google Maps reports crowd-flagged floods after the fact. Google Flood Hub launched urban flash-flood forecasts on 12 Mar 2026 at a 20 km grid with 24 hour lead, with no road-level output [V].

**Dispatchers and fleet operators decide blind.** A 108 dispatcher, a traffic control room or a delivery platform has hotspot lists and radio calls, but no forward-looking view of which segment fails next and for which vehicle.

**What nobody offers:** predicted road-segment passability, per vehicle class, 30 to 180 minutes ahead, wired into routing and dispatch [report 03].

## 3. Goals and non-goals

### Goals (first 12 months)
1. **Predict:** beat the only public benchmark, US NWS flash-flood warnings at 22% recall and 44% precision [V], on chronic hotspot segments in Bengaluru. Target recall and precision both above 60% at 60 minutes lead [EST].
2. **Reroute:** give dispatchers and fleets routes that avoid segments likely to be impassable at arrival time, with explanations and honest uncertainty.
3. **Earn trust:** zero incidents of the system routing a vehicle into a segment it already marked closed. Every closure auditable.
4. **Earn revenue:** two paid pilots by Jul 2027 [EST].
5. **Be ready to expand:** repeatable city onboarding (hotspot library, data MoUs, calibration) for Mumbai and Gurugram in the 2027 south-west monsoon.

### Non-goals (first release)
- General-purpose navigation. We are a flood layer, not a Google Maps competitor.
- Automatic rerouting of ambulances without human confirmation.
- Publishing "official" warnings. We pass through IMD, CWC and SDMA alerts and label our own output as a model.
- City-wide hydrodynamic simulation, landslide or hill-road routing, riverine flood forecasting.
- Native iOS app, voice assistant, marketing site beyond one static page.

## 4. Users

| Persona | Job to be done | Pain today | Value we offer |
|---|---|---|---|
| **P1 Dispatcher** (108/102 operator, 112 ERSS, fire, NDRF, traffic control room, ICCC) | Send the right unit by a road that will still be open | Hotspot lists and radio calls, no forecast, no per-vehicle view | Console with forecast states, vehicle-aware routes, closure overrides with audit |
| **P2 Fleet operations lead** (delivery, cab, school bus, logistics) | Keep riders and drivers safe and ETAs honest in rain | Pay rain surges, lose riders and cargo, no segment-level warning | API and SDK: avoid-lists, safe routes, alerts |
| **P3 Rider or driver** (two-wheeler, car, auto, ambulance driver) | Know "do not enter" before committing, in rain, one-handed | Google shows traffic, not flooded underpasses ahead | WhatsApp bot, light PWA, voice, SMS |
| **P4 Administrator** (control room head, fleet safety, auditor) | Review decisions and accuracy afterwards | No record of why a road was closed or kept open | Audit log, accuracy report, exports |

**Beachhead:** P1 and P2 together. One 108 operator or traffic control room as a free mission anchor and data partner; one or two delivery or cab platforms as paying customers via API [EST, report 03]. Citizens (P3) arrive second, through WhatsApp.

Context all personas share: rain at night, wet screens, power cuts, patchy data, Hindi or a regional language first. Detail in `docs/research/06-design-direction.md` section B.

## 5. Product principles

1. **Advisory, not directive.** Wording is "likely flooded", "avoid if possible". The product never says "safe". It says "Clear as of 14:20".
2. **Unknown is a state.** Missing or stale data never renders as clear.
3. **Honest about source.** Every output is labelled Official (IMD, CWC, SDMA), FloodRoute model, or Crowd report. We never imitate official colour codes or CAP wording for our own predictions.
4. **Humans outrank the model.** An authority's closure or reopening overrides the model, with reason, expiry and audit entry.
5. **Works when everything else does not.** Weak phone, weak network, no app: SMS and WhatsApp reach people; cached state shows its age.
6. **Bias to caution, but fight alert fatigue.** Asymmetric thresholds and hysteresis; notify only on material change.
7. **Equity.** Do not push detour traffic through vulnerable wards without a cap.

## 6. Scope by release

| Release | When | What |
|---|---|---|
| **R0 Shadow** | Oct to Dec 2026 | Ingest feeds, score hotspot segments, log predictions against observed events. No public outputs. Bengaluru plus Chennai (NE monsoon labels). |
| **R1 Design-partner pilot** | Apr to Jun 2027 | Bengaluru. Console, fleet API, WhatsApp bot (Kannada and English), PWA, advisory mode. 1 control room plus 1 to 2 fleets. |
| **R2 Monsoon expansion** | Jun to Sep 2027 | Mumbai and Gurugram. Hybrid model (v1). Second wave of fleets. |
| **R3 NE monsoon** | Oct to Dec 2027 | Chennai as a full city. Self-serve fleet onboarding. |

Coverage in R1: the roughly 100 to 300 chronic hotspot segments and all underpasses in the pilot area, scored per vehicle class. The rest of the road graph is routed normally but marked **not assessed** (see FR-R5).

## 7. Functional requirements

IDs are stable. Priority: **M** must for R1, **S** should for R1, **C** could or later release. Each requirement has acceptance criteria (AC).

### 7.1 Risk intelligence

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-R1 | Score every inventory segment for P(unusable) per vehicle class at horizons 0, 30, 60, 120 min. | M | A scoring run completes and publishes within 5 min of new rain input (p95). A replay test on a stored event reproduces the same states. |
| FR-R2 | Five states per segment and class: Clear, Watch, Risky, Impassable, Unknown. | M | State thresholds are configuration, not code. Unknown shows whenever data is stale (see FR-R4) or the segment is outside model coverage. |
| FR-R3 | Hysteresis: close at P above 0.5, reopen only when P below 0.25 for at least 10 min with fresh evidence. | M | Test on a synthetic noisy series shows no more than one state flip per 10 min. [thresholds EST] |
| FR-R4 | Staleness: every segment state carries the age of its newest evidence. Over 15 min without refresh, Clear degrades to Unknown. | M | Cutting a feed in staging flips affected segments to Unknown within 1 scoring cycle after the threshold. [5 and 15 min are proposals] |
| FR-R5 | Coverage honesty: segments outside the inventory show **Not assessed**, never green. | M | Map and API return `assessed: false` for them. Console shows coverage % per city. |
| FR-R6 | Provide confidence (Low, Medium, High) separate from probability, driven by evidence freshness, number of independent sources and rainfall-nowcast spread. | M | Confidence appears in API, console tooltip and WhatsApp text on request. |
| FR-R7 | Depth and vehicle class: use the provisional vehicle profile table (section 11.2); editable per tenant and per vehicle. | M | Changing a profile changes states on the next run. Overrides logged. |
| FR-R8 | Corroboration rule: a crowd-driven "likely impassable" needs two independent reports within 15 min, one sensor or camera reading, or an official feed. | M | Single-report spam cannot close a segment. |
| FR-R9 | Learn from outcomes: store prediction, evidence and later-confirmed truth per segment event for calibration. | S | A backtest job produces POD, FAR, CSI and calibration slope per class and lead time. |

### 7.2 Routing

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-RT1 | Given origin, destination, vehicle class and departure time, return a primary route and one or more alternates with per-segment state at arrival time. | M | Response includes `valid_until`, worst-segment state and data age. |
| FR-RT2 | Check each edge against risk at its **arrival time**, not request time. | M | A test with a closure forecast at t+40 min rejects a route that reaches the segment at t+45 and accepts one that reaches it at t+25. |
| FR-RT3 | Never return a route through a segment in Impassable for that class as the default. If no safe route exists, say so and return shelter-in-place guidance and a least-risk route clearly marked. | M | No-safe-route response contains `no_safe_route: true`, guidance text, 112 action. |
| FR-RT4 | Show fastest and safest side by side with delta ("8 min longer, avoids 2 flooded roads"). Safest is preselected when fastest has Risky or Impassable segments. | M | Delta and worst-segment badge in every response. |
| FR-RT5 | Reroute triggers: a segment ahead turns Impassable; or the new route saves at least max(5 min, 15%) of remaining time; or risk on the current route rises one band. Minimum 2 to 3 min between suggestions. | M | Replay of a live trace produces no more than one suggestion per dwell window. |
| FR-RT6 | Commit zones: within about 300 m of a flooded segment with no turn-off, hold the route and warn instead of flipping. | S | Covered by a replay test. |
| FR-RT7 | Never reroute into a segment closed in the last 15 min. | M | Covered by a test. |
| FR-RT8 | Emergency profile: ambulance, fire and boat or high-clearance profiles, with golden-hour objective and lower tolerance of unknown conditions. Dispatcher confirms before the assignment is sent. | M | Console requires an explicit confirm. No auto-assign in R1. |
| FR-RT9 | Equity cap: limit rerouted flow per street and apply a vulnerability penalty layer. | C | Fairness report by ward income band, produced per season. |
| FR-RT10 | Deep link out to Google Maps with forced waypoints for users who will not leave it. | S | Link opens with detour waypoints. A note shows the outside app does not know about flooding. |

### 7.3 Dispatcher console

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-C1 | Situation board: feed health per source with age, active warnings, incident table, map with forecast scrubber (0 to 6 h, 15 min steps). | M | Works on 1366x768. Scrubber has step buttons as a non-drag alternative. |
| FR-C2 | Vehicle assignment: propose units by class and flood-safe ETA; flag when a route degrades after assignment ("Route changed") until acknowledged. | M | Flag clears only on acknowledge. |
| FR-C3 | Closure override: close, reopen or force Watch with required reason and required expiry (default 2 h) and an impact preview ("affects n active routes"). Undo toast. Arterials need a second operator. | M | Every override appears in the audit log. Expiry reverts to model state. |
| FR-C4 | Audit log: append-only record of operator, action, segment, reason, expiry, before and after, with filters and export. | M | Cannot be edited or deleted through the UI or API. |
| FR-C5 | Keyboard operation (J/K rows, A assign, C closure, Esc). | S | All primary actions are reachable without a pointer. |
| FR-C6 | Data-age chips and feed-health strip always visible. | M | Cut a feed in staging and the strip shows it within 1 cycle. |
| FR-C7 | Per-source labelling: Official, Model, Crowd. | M | Each segment detail lists contributing sources with age. |

### 7.4 Fleet API

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-A1 | REST API: risk by bbox and horizon, route, reports, overrides (for tenants allowed), closure feed. | M | OpenAPI spec published. p95 route latency under 500 ms, ambulance under 300 ms [EST]. |
| FR-A2 | Webhooks for closure and risk-change events, signed, idempotent, with retries. | M | A replayed webhook is safe to process twice. |
| FR-A3 | GeoJSON closure feed and a CAP 1.2 feed without personal data. | S | CAP feed validates against the CAP schema. |
| FR-A4 | Tenant isolation, API keys, usage metering, per-tenant vehicle profiles. | M | Cross-tenant read test fails closed. |
| FR-A5 | Rider SDK or deep-link component for delivery partner apps. | C | Pilot partner can show the alert in their rider app. |

### 7.5 Citizen channels

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-P1 | WhatsApp bot (Kannada and English at launch; Hindi added for Gurugram and Delhi). User shares location, picks vehicle, gets status, best alternative and data age. | M | A text query returns an answer in under 5 s on 3G-class latency. |
| FR-P2 | PWA: language, vehicle chips, map, route compare, live reroute, report flow. No account. | M | Shell at most 70 KB gzipped. LCP 2.5 s on a Moto G-class device on slow 4G [EST budget from report 06]. |
| FR-P3 | Report a flood in three taps with a depth tile, location prefilled, photo optional, offline queue. | M | Works offline, shows queue status, never blocks on login. |
| FR-P4 | SMS fallback with DLT-registered templates (under 70 characters for Indic): one fact, one action. | S | Template approval done before pilot. |
| FR-P5 | Voice guidance for critical phrases in launch languages, with prerecorded fallback. | S | Plays on a low-end Android phone with no TTS voice installed. |
| FR-P6 | Offline: cached last risk snapshot and last route, with timestamp. | M | Airplane-mode test shows "offline, conditions from 14:20". |
| FR-P7 | Rider mode (suggested above walking speed, never forced): fewer controls, 56 px targets, voice first, no text entry. | S | Usability test with two-wheeler riders. |

### 7.6 Alerts

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-L1 | Alert users only on material change: new Impassable on a saved route, or a reroute suggestion that meets FR-RT5. | M | No more than 3 alerts per user per hour in a replayed storm. |
| FR-L2 | Channels: push, WhatsApp utility template, SMS, in-app banner. Never marketing content in alert threads. | M | Template category set to utility. Opt-in recorded. |
| FR-L3 | Pass through official IMD, CWC and SDMA alerts verbatim with source and time, and link to SACHET. | M | Official alerts are visibly distinct from model alerts. |
| FR-L4 | Do not originate cell-broadcast alerts. Authorities can request them through SACHET. | M | No cell-broadcast code path in the product. |
| FR-L5 | Alert wording follows the content rules in design research section C.12, in each user's language first and English second. | M | Copy audit passes. |

### 7.7 Evidence and reports

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-E1 | Accept reports from the PWA, WhatsApp and API, map-matched to segments, with trust score, de-duplication and expiry. | M | A duplicate within 2 min does not double count. |
| FR-E2 | Photo handling: strip EXIF, blur faces and number plates server-side, keep only a derived label after verification, delete originals after a defined short period. | M | A test image with a face and plate is blurred. Originals purge on schedule. |
| FR-E3 | Fleet probe ingestion (speed buckets by segment and time) from partner fleets, k-anonymity floor (default 5 contributors per segment interval). | S | Segments below the floor ignore probe evidence. |
| FR-E4 | Gauge, nowcast and alert ingestion adapters with per-source health. | M | A failing adapter alarms within 2 cycles and is shown in the console strip. |

### 7.8 Administration, tenancy and compliance

| ID | Requirement | Pri | Acceptance criteria |
|---|---|---|---|
| FR-M1 | Decision log: store inputs, model version and advisories shown for every route decision, keep one year, privacy-safe. | M | A route decision can be reconstructed from its log record. |
| FR-M2 | Consent and notice screens: separate foreground location, background location, crowd photos and sharing with authorities. Withdrawal as easy as consent. | M | Each toggle works independently. |
| FR-M3 | Data retention schedule: raw GPS short-lived, audit and processing logs one year, deletion jobs. | M | Retention job runs in staging with evidence of deletion. |
| FR-M4 | Accuracy report per tenant and city, per season. | S | Exports POD, FAR, lead time, override rate. |
| FR-M5 | Grievance and correction channel, with a named grievance officer, for crowd content and wrong closures. | M | Complaint flow tested end to end. |

## 8. Non-functional requirements

| Area | Requirement |
|---|---|
| Safety | Hazard log (HARA style), fail-safe defaults (unknown means caution in rain), version-pinned models, incident runbook. Safety case signed off before R1 live. |
| Freshness | Rain to tile p95 under 5 min. Evidence to state update p95 under 60 s. Alert dispatch p95 under 60 s. |
| Latency | Route API p95 under 500 ms; ambulance p95 under 300 ms [EST]. |
| Availability | Static risk snapshot 99.95% during declared monsoon alerts. Core services 99.9% [EST]. |
| Degraded mode | If the backend is down, the CDN snapshot and cached client state still work. If feeds are down, states degrade to Unknown. |
| Accessibility | WCAG 2.2 AA minimum, AAA for risk text. Targets 48 px (56 px emergency). Reduced motion, reduced transparency, forced colours. |
| Language | English, Kannada at launch; Hindi next; then Marathi, Tamil, Telugu, Bengali, Malayalam, Gujarati, Assamese as cities open. Native review of every string. |
| Performance | Citizen shell at most 70 KB gzipped; risk payload at most 20 KB first load and 5 KB deltas [targets from report 06, unmeasured]. |
| Privacy | DPDP Act 2023 and Rules 2025. Consent as the baseline; s.7(f) and s.7(h) as supplements for declared events and SOS only [COUNSEL]. On-device matching where possible, rotating IDs, short retention. |
| Security | Encryption in transit and at rest, access logs, CERT-In 180-day logs in India, 6-hour incident reporting, annual VAPT by an empanelled auditor. |
| Residency | India-hosted. Fine-resolution geospatial data (finer than 1 m horizontal or 3 m vertical) stored and processed in India by an Indian entity. |
| Boundary compliance | Survey of India boundaries on every map and screenshot, with a CI check. |

## 9. Success metrics

Targets are estimates until the shadow season produces baselines.

| Layer | Metric | R1 target | Source |
|---|---|---|---|
| Prediction | Recall and precision for "impassable within 60 min" on hotspot segments | Both above 60% | Beat NWS 22% recall and 44% precision [V, report 03] |
| Prediction | POD / FAR on hotspot set | POD at least 0.7, FAR at most 0.4 | Report 04 |
| Prediction | Calibration slope | Between 0.8 and 1.2 | Report 04 |
| Prediction | Median alert lead time | Above 20 min, goal 30 to 60 | Reports 03, 04 |
| Safety | Vehicles routed through a segment already marked Impassable | **Zero** (hard guardrail) | PRD goal 3 |
| Safety | Missed-closure exposure (trips through a truly unusable segment) | Reported per season, trend to zero | Report 04 |
| Operations | Operator override rate of model closures | Trend metric, reviewed monthly | Report 04 |
| Operations | Avoided strandings per 1,000 dispatched trips; median and p90 ETA saved vs baseline in rain | Baseline set in pilot | Report 03 |
| Adoption | Active fleets, dispatcher daily logins, WhatsApp opt-ins | 2 fleets and 1 control room by May 2027 | Report 03 |
| Revenue | Paid pilots | 2 by Jul 2027 | Report 03 |
| Trust | Alerts per user per hour in a storm | At most 3 | FR-L1 |

**North-star candidate:** trips rerouted around a segment later confirmed impassable, per 1,000 dispatched trips in rain.

## 10. Release gates

| Gate | Entry to | Must be true |
|---|---|---|
| G0 | Start building R1 (Dec 2026) | Shadow season produced a labelled event log; v0 backtest on at least 3 events with POD and FAR reported; legal review of advisory framing complete. |
| G1 | Go live with a design partner (Apr 2027) | Safety case signed; game-day drill passed; DLT and WhatsApp templates approved; MoU or letter of support from the partner; DPDP notice and consent flows live; insurance bound; incident runbook rehearsed. |
| G2 | Add cities (Jun 2027) | R1 metrics at or near target; zero routed-into-closed incidents; at least one paying pilot. |
| G3 | Public closure outputs without a human in the loop | Not in 2027. Requires a full season of calibration and counsel sign-off. |

## 11. Reference definitions

### 11.1 States

| State | Meaning | Default P(unusable) band [EST, tune] |
|---|---|---|
| Clear | Fresh data, low risk | below 0.10 |
| Watch | Water may rise | 0.10 to 0.30 |
| Risky | Likely flooded | 0.30 to 0.50 |
| Impassable | Closed or flooded now | above 0.50 (reopen below 0.25 with fresh evidence for 10 min) |
| Unknown | No recent data, or outside coverage | n/a |

### 11.2 Provisional vehicle profiles

No Indian vehicle-depth guidance was found. These are conservative defaults to replace after field trials [report 04].

| Class | Caution | Unusable | Basis |
|---|---|---|---|
| Pedestrian or child | 10 cm | 15 to 20 cm, or velocity above 1 m/s | [U] |
| Two-wheeler | 10 cm | 15 to 20 cm | [U] needs local trials |
| Auto-rickshaw | 10 cm | 20 cm | [U] |
| Hatchback or sedan | 15 cm | 30 cm | Partial [V]; some guidance says avoid above 10 cm |
| SUV | 25 cm | 40 cm | [U] |
| Standard ambulance | 15 cm | 20 cm in flowing water | [V] Australian guidance |
| Bus, truck, fire appliance | 30 cm | 50 cm | [V] Australian guidance |

A hidden-hazard flag applies above a depth floor for any vehicle (open manholes, electric hazards).

## 12. Business model

All numbers are estimates to test in 8 to 10 customer interviews before any pitch [report 03].

| Customer | Product | Price anchor [EST] | Sales cycle [EST] |
|---|---|---|---|
| Delivery or cab platform | API and rider SDK, per city | Rs 15 to 60 lakh per year per platform-city, or Rs 20 to 100 per active rider per month | 2 to 6 months |
| Ambulance operator (state contract) | Console and routing hints | Rs 5 to 25 lakh per year per state | 6 to 12 months |
| City traffic police or ICCC | Predictive hotspot and diversion console | Rs 30 lakh to 1.5 crore per year per city | 9 to 18 months |
| Maps platform | Data licence | Rs 10 to 50 lakh per year | 4 to 9 months |
| Insurer | Claims-avoidance alerts | Pilot Rs 10 to 30 lakh | 6 to 12 months |
| CSR or NGO | Citizen WhatsApp and IVR | Grants | 3 to 6 months |

Seasonality: revenue concentrates in 3 to 4 months. Contracts should be annual with a retained monitoring fee.

## 13. Go-to-market summary

1. **Discovery (Oct to Nov 2026):** 8 to 10 interviews: EMRI or ZHL (108), Bengaluru Traffic Police (ASTraM), BBMP, KSNDMC, and fleet safety or ops leads at delivery, cab and school-bus operators.
2. **Design partners (Dec 2026 to Mar 2027):** one control room, one to two fleets, written MoU or letter of support. Offer partners override rights, no exclusivity on government data, open accuracy reporting, and a clear processor and fiduciary split.
3. **Pilot (Apr to Jun 2027):** advisory mode, weekly review with the partner.
4. **Expand (Jun 2027 onward):** Mumbai (government-led, slower) and Gurugram (delivery HQs, underpass deaths). Chennai as a full city in Oct 2027.

## 14. Dependencies and assumptions

- IMD API platform access with commercial terms, or an IMD MoU. Fallback: SACHET plus open NWP and satellite rain [report 01].
- KSNDMC data access for Bengaluru (public view today; API or licence unconfirmed) [report 01].
- BBMP and traffic police hotspot lists and underpass inventories [V lists exist; machine-readable status unknown].
- At least one fleet or ambulance telematics partner for probe data.
- Indian legal entity; DPIIT recognition; DLT and WhatsApp Business onboarding.
- Assumes the DPDP main duties start about 13/14 May 2027 [V, report 05; [COUNSEL] to confirm].

## 15. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | A user or vehicle is harmed after following a route (Bareilly FIR precedent) | High | Advisory framing, human-in-loop for ambulances, safety case, logs, insurance, runbook |
| 2 | Google closes the gap (finer flash-flood forecasts, Maps flood layer) | High | Segment-level ground truth, dispatcher workflow, local data deals, speed |
| 3 | No ground truth, weak labels | High | Shadow season, crowd and probe evidence, control-room labels, spatial cross-validation |
| 4 | Data licensing (IMD and CWC chargeable; terms unclear) | High | MoUs, SACHET and open data first, no scraping |
| 5 | Over-alerting then ignored, or misses destroy trust | High | Hysteresis, calibrated thresholds, show uncertainty |
| 6 | Government sales cycles and budget mismatch | Medium | Lead with B2B revenue; government as anchor partner |
| 7 | Connectivity and power loss at peak | Medium | CDN snapshot, offline client, SMS and WhatsApp |
| 8 | DPDP, CERT-In, TRAI compliance gaps | Medium | Build to the rules now; checklist in report 05 |
| 9 | Crowd data abuse | Medium | Corroboration, reputation, rate limits |
| 10 | Convective nowcast skill is low (0.15 at 2 h in one Indian study [V, unconfirmed paper]) | Medium | Carry uncertainty, evidence correction |

## 16. Open questions

1. IMD API commercial terms and refresh cadence (report 01).
2. Whether NDMA or C-DOT gives third parties a SACHET feed with commercial rights.
3. Whether Google's urban flash-flood product covers Indian cities, and at what resolution by 2027.
4. Real passable depths for Indian two-wheelers and autos; a fleet partner could supply stall data.
5. Which Bengaluru agencies will give API or MoU access (KSNDMC, BBMP, traffic police, BMTC).
6. Whether routine heavy-rain waterlogging counts as a "disaster" under DPDP s.7(h) [COUNSEL].
7. Whether crowd-driven "road closed" labels count as warnings under the Disaster Management Act [COUNSEL].
8. Flood-caused ambulance delay data from 108 operators.
9. Which probe-data vendor gives India road-level speeds at acceptable cost and rights.
10. Whether a segment-keyed risk table is a collective or derivative database under ODbL [COUNSEL].
