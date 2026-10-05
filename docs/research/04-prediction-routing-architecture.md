# FloodRoute research 04: Prediction, Routing Science and System Architecture

Date: 2026-10-05. Scope: India urban flash flooding first, plus riverine and hill-road hazards.
Tags: [V url] means I saw the claim on that page or search snippet in this session. [U] means recalled or my own inference, unverified. Where a fetch failed I say so. Cost figures are my estimates, not quotes.

## 0. Executive summary

1. No single model will give reliable road-level flood depth in Indian cities. Build layers: a static prior (terrain and drainage), a rainfall-triggered threshold or surrogate layer, and a live evidence layer (probe speeds, crowd reports, CCTV, sensors) fused by Bayesian updating. Output per segment, per vehicle class, per forecast time step: P(unusable), depth quantiles, and a confidence score.
2. The research gap is data, not algorithms. Surrogate-model papers train on hydrodynamic simulations, which need a city DEM, drainage network and calibration data. Most Indian cities lack these in open form. Google's Groundsource (news-derived flood records) and probe-speed data are the realistic ground truth.
3. Google already forecasts urban flash floods up to 24 h ahead in Flood Hub. The product is coarse and area-level, not road-segment or depth. FloodRoute's moat is the segment-level, vehicle-class, routing-integrated layer with local evidence.
4. Routing should be time-dependent and risk-aware: each edge is checked against the forecast at the time of arrival, not the time of request. Re-routing needs asymmetric hysteresis to avoid flapping.
5. Architecture must degrade gracefully. Static risk tiles on a CDN, cached client state, and SMS/WhatsApp/cell-broadcast fallbacks matter more than a clever model during a storm.

## 1. Prediction approaches

### 1.1 Method comparison

| Approach | What it gives | Data needs | Evidence on accuracy | Fit for India MVP |
|---|---|---|---|---|
| (a) Static susceptibility: HAND, TWI, depressions/sinks, hotspot ML | Where water collects; no timing | DEM (CartoDEM/FABDEM/lidar), land cover, hotspot labels | Chennai RF studies report 65-70% [V https://link.springer.com/article/10.1007/s11356-023-29132-1 via search snippet] to 95% [V search snippet, irjet/slideshare, weak source]. The spread suggests unreliable validation. Random point splits inflate scores through spatial autocorrelation [U] | Yes, as prior only. Never as the sole decision signal |
| (b) Rainfall thresholds per segment (I-D, antecedent) | Trigger timing | Segment flood-event labels plus gauge or radar rainfall | No Indian road-segment threshold study found. Generic I-D thresholds are well established for landslides and flash floods [U] | Yes for v0/v1. Fit per drainage zone, not per street |
| (c) ML surrogates of hydrodynamic sims (U-Net, GNN, LSTM) | Depth maps in seconds | Hundreds of sims per domain. Needs a physics model first | Norfolk LSTM/GRU predict street flooding in 11 s vs 4-6 h for TUFLOW, on ~17,000 segments [V https://www.odu.edu/article/rolling-the-deep-norfolk-street-flooding-predicted-seconds-machine-learning-models]. mSWE-GNN: over 700x speed-up, depth MAE 0.05-0.12 m, CSI 87.7% at 0.05 m, trained on 60 synthetic sims, one fine-tuning sample for a new domain [V https://nhess.copernicus.org/articles/25/335/2025/]. The 0.12 m MAE is comparable to the 15-30 cm thresholds that matter, so uncertainty must be explicit | v2. Only after v1 physics gives training data |
| (d) Physics: HEC-RAS 2D, LISFLOOD-FP, TUFLOW, SWMM, RIM2D, CA (CADDIES) | Depth, velocity, timing | DEM, buildings, roughness, drainage network, calibration | RIM2D: whole of Berlin (892 km2) 48 h event in 8 min at 10 m, 34 min at 5 m, ~5.5 h at 2 m on 8 A100 GPUs [V https://nhess.copernicus.org/articles/26/85/2026/]. CA models: 5-20x faster than industry software with 98-99% extent accuracy [V https://ore.exeter.ac.uk/repository/handle/10871/23991 via search snippet] | Use as an offline scenario generator (design storms, 10 m grid), not live for 10 cities |
| (e) Rainfall nowcasting | Rain input, 0-6 h | Radar mosaics, satellite, gauges | DGMR: 5-90 min lead, preferred by experts in 89% of cases [V https://www.mindspore.cn/mindearth/docs/en/stable/nowcasting/DgmrNet.html]. NowcastNet: up to 3 h [V same search result set]. MetNet-3: 24 h, 1-4 km, 2-min steps, better CRPS than ENS [V https://research.google/blog/metnet-3-a-state-of-the-art-neural-weather-model-available-in-google-products/]. Aardvark: end-to-end, station forecasts to 10 days, but not a convective nowcaster [V https://www.turing.ac.uk/news/publications/end-end-data-driven-weather-prediction]. An Indian NE-monsoon radar ensemble study reports 2 h skill of 0.65 (tropical storms), 0.5 (stratiform), 0.15 (convective) [V search snippet, exact paper not confirmed]. IMD urban nowcasts for 117 cities, POD 61% (2014) to 91% (2023) [V https://downtoearth.org.in/news/met-department-moves-from-weather-forecasting-to-nowcasting-40175] | Consume IMD nowcast, radar, and an optional global product. Convective skill is the bottleneck, so carry ensembles or uncertainty |
| (f) Observation assimilation | Ground truth in the loop | See 1.3 | See 1.3 | Core of the product |
| (g) Google Groundsource and Flood Hub | News-derived events; 24 h urban flash flood forecast | Public | See 1.2 | Use as label source and benchmark |

Note on MetNet-3 and Aardvark: public availability of MetNet-3 for India outside Google products is not confirmed [U]. Plan around IMD radar, IMD gridded rainfall and an open ML nowcaster you can run, such as DGMR-style models retrained on Indian radar [U].

### 1.2 What Google has built

- Groundsource: Gemini extracts flood events from news in 80 languages into 2.6 million records across 150+ countries since 2000, openly downloadable (Zenodo). Manual review: 60% accurate on both location and timing, 82% practically useful. It captured 85-100% of GDACS severe events for 2020-2026 [V https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/].
- A model trained on it forecasts urban flash floods up to 24 h ahead in Flood Hub, launched March 2026 [V https://blog.google/innovation-and-ai/technology/research/gemini-help-communities-predict-crisis/ and https://citizen.digital/article/google-unveils-flood-hub-tool-to-predict-urban-flash-floods-n379075]. The blog does not state grid size, inputs, depth output or India specifics. Assume area-level, probability-style, no depth, no road network [U]. Check the Flood Hub UI for Indian cities before pitching.
- Implication: news-derived labels are noisy (40% imprecise), biased to reported and populated places, and weak on segment-level precision. Good for training priors and regional benchmarking, not for segment-level ground truth.
- India government context: iFLOWS-Mumbai (MoES with BMC) offers 3-day inundation estimates, 3-6 h nowcasts, 160+ observatories, 500 m / 15 min rainfall [V https://vikaspedia.in/social-welfare/disaster-management-1/state-of-the-art-flood-warning-system-for-mumbai]. A press report after Aug 2020 questioned whether it helped in that event [V https://www.pressreader.com/india/hindustan-times-st-mumbai/20200807/281702617059948, headline only]. Position FloodRoute as complementary and integrate rather than compete.

### 1.3 Observation sources

| Source | Strength | Weakness |
|---|---|---|
| Probe/fleet speeds (taxi, bus, 2W delivery, own app) | Continuous, covers all roads. Shenzhen floating-car algorithm: 68-90% detection, 1.5-2% false alarms [V https://scholars.cityu.edu.hk/en/publications/identification-of-urban-road-waterlogging-using-floating-car-data/ via search snippet] | Speed drops also come from congestion. Must condition on rain and expected speed. Needs fleet partnerships |
| Crowd reports (app, WhatsApp, Waze-style) | Cheap, fast | Norfolk study: 71.7% of Waze flood reports judged trustworthy by a model [V https://www.odu.edu/article/rolling-the-deep-norfolk-street-flooding-predicted-seconds-machine-learning-models]. Needs trust scoring, de-duplication and expiry |
| CCTV and photo depth estimation | Direct depth. ~11 cm RMSE from a single social-media image [V https://arxiv.org/abs/2007.06749]. VLM street-image depth estimation, MAE under 1 cm on synthetic 0-40 cm data [V https://arxiv.org/abs/2603.17108, synthetic only] | Camera access (Smart City ICCC), night and rain optics. Synthetic results will not transfer cleanly |
| IoT water-level sensors | Ground truth for calibration | Capex and vandalism. Deploy 20-50 at known hotspots, not city-wide |
| Sentinel-1 SAR | Free, wide area | Urban shadow/layover, smooth surfaces and roughness errors, unsuitable alone in cities. Revisit around 6 days at best, and data arrives within 3 h of observation [V https://www.mdpi.com/2072-4292/13/22/4511 and search snippets]. Use post-event for labels, not live closures |
| Social media text | Early signal | Low precision, geocoding errors. Use as a weak prior |
| Municipal complaint and control-room logs | Authoritative labels | Access varies by city |

### 1.4 Recommended layered model

For segment s, vehicle class c, and arrival time t:

1. Static prior: p0(s) from HAND/TWI/sink depth, underpass flag, drain proximity, historical events (Groundsource plus municipal hotspot lists). Output a calibrated base logit.
2. Rainfall trigger: effective rainfall R(s, t) = nowcast plus recent gauge/radar rainfall with antecedent decay, per drainage-catchment zone. A learned or tabulated function maps R to a logit shift per zone. At v2, replace with surrogate depth quantiles.
3. Evidence correction in log-odds: logit p(s,t) = logit p_prior+trigger + sum over evidence i of w_i * LLR_i * decay(age_i), with spatial spreading along hydrologically connected segments (same sink or underpass). Choose each LLR from a validated detection and false-alarm rate (probe: Shenzhen-type TPR/FPR once locally estimated). A Kalman or particle-filter variant is the v2 path [U].
4. Depth: carry quantiles (p10/p50/p90). P(unusable for c) = P(depth > d_c) plus a velocity and hazard term.
5. Confidence: separate from probability. Based on evidence freshness, number of independent sources, model domain coverage (is this segment inside the DEM/drain-mapped area?), and rainfall nowcast spread. Show "low confidence" to users. Route as if p is the upper bound for safety-critical classes [U].

Avoid heavy dependence on a single learned model before you have local labels. A calibrated, documented rule layer is easier to defend in a safety case than an opaque net.

## 2. Defining "road unusable"

Depth is a proxy. Velocity, open manholes, debris and electric hazards also matter. Open manholes in waterlogged Indian roads are a documented local killer [U]. Add a "hidden hazard" flag for any segment with depth above a floor, regardless of vehicle ability.

| Vehicle class | Suggested "caution" | Suggested "unusable" | Basis |
|---|---|---|---|
| Pedestrian / child | 10 cm | 15-20 cm or any velocity above 1 m/s | [U] industry practice, tune to local guidance |
| Two-wheeler | 10 cm | 15-20 cm | [U] No authoritative source found. Engine air intake and exhaust height drive this. Verify with local trials and mechanic and delivery-fleet data |
| Hatchback / sedan | 15 cm | 30 cm | 0.3 m is treated as severe flooding with vehicle speed set to zero in a model using the Pregnolato function [V https://arxiv.org/pdf/2609.16963 via search snippet]. Some guidance says avoid anything above 10 cm [V search snippet, ems/UK sources] |
| SUV | 25 cm | 40 cm | [U] Floating instability reported above 0.38 m depth [V https://journals.utm.my/jurnalteknologi/article/view/11198 via search snippet] |
| Auto-rickshaw | 10 cm | 20 cm | [U] Low ground clearance |
| Standard ambulance | 15 cm | 20 cm in flowing water | [V https://www.ipcn.nsw.gov.au/sites/default/files/2025-04/L250331_BrisbaneGrove_Questions_on_Notice_Applicant_Response%20redacted_0.pdf via search snippet] (Australian guidance) |
| Large truck / bus / fire appliance | 30 cm | 50 cm | Large vehicles expected to traverse above 0.5 m [V same NSW document] |

Notes:
- Pregnolato et al. (2017, Transportation Research Part D 55:67-81) relate standing-water depth to vehicle speed, fitted to video and literature data, R2 = 0.95 [V https://doi.org/10.1016/j.trd.2017.06.020 via search snippets]. I could not extract the equation (PDF and publisher fetches failed). Cite the paper, re-derive speeds locally rather than reuse its UK-based curve.
- Stability limit values for car-type vehicles are expressed as depth x velocity, with test values of 0.0144-0.0168 m2/s for one vehicle and 0.36-0.69 m2/s in other studies. These values differ by orders of magnitude, so treat as method-dependent [V search snippets: UNSW WRL TR2017-07, Springer s11069-013-0889-2]. Use depth with a velocity cap for steep roads and culverts.
- Indian guidance: NDMA 2010 Urban Flooding guidelines exist [V https://sdma.goa.gov.in/sites/default/files/2022-05/management_urban_flooding.pdf] but I found no road-depth-vs-vehicle thresholds in them. Gap: needs a field study with Indian vehicles (two-wheelers, autos, low-floor buses).
- Emergency profiles: ambulances (patient comfort, time cost of false closure is high), fire (high clearance, can accept deeper water), NDRF/SDRF boats and high-clearance trucks. Maintain a profile table editable by the dispatcher with per-vehicle overrides (for example a specific high-clearance ambulance).
- Present three states per segment: open, caution (slow, optional), closed. Binary closure makes users distrust the map. Pregnolato's point is that roads degrade gradually rather than switch off [V search snippet of the paper abstract].

## 3. Risk-aware routing

### 3.1 Formulation

- Graph: OSM-derived with underpass, culvert, bridge and elevation attributes. City graphs are small enough (order 10^5 to 10^6 edges [U]) for an in-memory time-dependent A* or Dijkstra that answers in milliseconds.
- Edge cost: travel_time(depth, class) + lambda * risk_penalty, with hard exclusion when P(unusable at ETA) exceeds a class threshold. Citizen default threshold 0.2-0.3, ambulance 0.4-0.5 [U, tune with backtests].
- Time-dependent: when expanding an edge, compute the arrival time and query p(s, t_arrival) from the forecast grid. This makes a route valid over the trip and not just at departure. Return valid_until for the route.
- Reliable routing: the literature poses the reliable a priori shortest path (RASP) and alpha-reliable path problems, maximising on-time probability or minimising cost with a probability constraint [V https://transportation.tech.northwestern.edu/docs/research/core-topics/transportation-network-modeling-and-planning/Nie-Nelson_ReliableRouting1.pdf and search snippets]. For flood risk, I recommend a simplified chance constraint: route reliability = product of (1 - p_edge) over edges with a correlation guard (take the max of the product and a bound based on the worst single edge), because flood failures are strongly spatially correlated [U].
- Path-level policy: prefer a route with no segment above caution, even if slower, up to a detour budget (for example 1.5x or 15 min [U]). Beyond the budget, show the safe route with its cost and the fastest route with its risk, then let the user choose.
- Evacuation and flood-aware routing precedent: Inoue et al. 2018 real-time evacuation routing with 25 m real-time 2D flood analysis [V search snippet, Kyoto DPRI]. A 2026 JIMO paper couples emergency vehicles and drones with a speed function of inundation depth [V https://www.aimspress.com/article/doi/10.3934/jimo.2026136].
- Routing engines: GraphHopper supports custom models and per-request edge changes [V https://discuss.graphhopper.com/t/dynamically-update-edges/8203 via search]. Contraction hierarchies break under live weight changes, so OSRM CH is a poor fit, though OSRM MLD may be acceptable [V mailing list snippets, U for MLD]. My recommendation: custom time-dependent A* service in Rust or Go on the graph, with the risk grid memory-mapped. Valhalla or GraphHopper as a fallback.

### 3.2 Re-route triggers and hysteresis

- Asymmetric thresholds: close a segment when p > 0.5 (or lower for ambulances), reopen only when p < 0.25 for at least 10 minutes with fresh evidence. Segment state changes are logged.
- Switch the user's route only if (a) a segment ahead on the current route turns closed, (b) the new route saves at least max(5 min, 15%) of remaining time, or (c) risk on the current route rises one band. Minimum dwell of 2-3 min between suggestions. Never re-route into a segment that was closed in the last 15 min.
- Commit zones: once within roughly 300 m of a flooded segment with no turn-off, hold the route and warn rather than flip.
- Notify only on material change. Alert fatigue kills compliance.

### 3.3 Emergency vehicles

- Dispatcher-integrated: API takes origin, destination, vehicle profile, dispatch time, returns primary and alternate routes with risk annotations and a valid_until time. Dispatcher can pin closures or reopenings, which override the model with an expiry and an audit trail.
- Objective: P(arrival within golden-hour budget) not mean ETA. Use risk-aware cost with higher tolerance of shallow water but low tolerance of unknown conditions.
- Hospital reachability: also compute which hospitals are reachable, not only the nearest.

### 3.4 Explaining and the no-safe-route case

- Explain in plain language, for example: "Avoiding Andheri Subway (water about 40 cm, closed since 14:10). +9 min." Show a confidence label and age of evidence ("2 reports 6 min ago").
- If no safe route: state that clearly, do not output a risky route as the default. Show options: wait (with forecast "likely to clear in ~X min, low confidence"), move to higher ground or the nearest safe building, avoid underpasses and low-lying parking, never drive into moving water. Offer one-tap 112 and share-location. Offer a vehicle-abandon warning for cars stalled in water [U].
- For ambulances with no safe route: escalate to the dispatcher, suggest alternative modes (boat, high-clearance vehicle, foot relay), show the least-risk route with explicit risk.

## 4. Evaluation

Ground truth candidates: Groundsource events (noisy labels, V above), municipal waterlogging complaints and traffic-police posts [U], Google/Waze/probe speed anomalies, CCTV annotations, post-event surveys, Sentinel-1 flood extents (non-urban areas especially), and your own validated crowd reports. Build a labelled event library per city with a confidence tier.

Backtest events: Chennai Dec 2015 and Dec 2023 (Cyclone Michaung), Mumbai 26 July 2005 (944 mm in 24 h [V https://vajiramandravi.com/current-affairs/urban-flooding-in-india/]), Mumbai 26 May 2025 (135 mm in 24 h at Colaba, heaviest May rain in 107 years, monsoon 16 days early [V https://thelogicalindian.com/mumbai-records-135-mm-rain-heaviest-may-downpour-in-107-years-red-alert-issued-travel-disrupted/]), Bengaluru Sept 2022 (131 mm overnight on 5 Sept, 2022 wettest year on record, hotspots on Sarjapur Road, ORR Bellandur, Whitefield [V deccanherald/thenewsminute search results]), Delhi June 2024 (228.1 mm in 24 h [V vajiramandravi page]).

| Metric | Definition | Target for v1 [U, tune] |
|---|---|---|
| Segment POD / FAR / CSI | At lead times 0, 30, 60, 180 min, per vehicle class | POD at least 0.7, FAR at most 0.4 on hotspot set |
| Brier score and reliability diagram | Calibration of P(unusable) | Slope between 0.8 and 1.2 |
| Depth error | MAE and exceedance of class thresholds | MAE under 10 cm where sensors exist |
| False-closure cost | Extra minutes and km per rerouted trip, plus closure-hours | Report distribution, not just mean |
| Missed-closure exposure | Trips routed through a truly unusable segment | Zero tolerance ambition, report counts |
| Alert lead time | Time between alert and first observed unusable state | Median above 20 min |
| Operator override rate | Share of model closures overridden | Trend metric |

Method: leave-one-event-out and leave-one-city-out, spatial block cross-validation (no random splits, given the Chennai spread above), and a shadow period of one full monsoon before public closures. Evaluate separately for rainfall regime (convective vs cyclonic).

Asymmetry: a missed closure can kill. A false closure costs minutes, but chronic false closures push users to ignore the app and eventually into flooded roads. Use class-specific cost ratios (citizen about 1:10 to 1:20, ambulance weighted toward fewer false closures on arterials) [U], and show uncertainty rather than hide it.

Safety case: hazard log (HARA-style), documented assumptions (thresholds, data freshness), fail-safe default (unknown equals caution in rain), human override with expiry and audit log, clear user disclaimers that conditions can change, incident review process, version-pinned models. Pre-agree responsibilities with the municipal and police counterparts in writing.

## 5. System architecture

### 5.1 Reference architecture (text diagram)

```
 INGEST                       STREAM / PROCESS                 STATE & SERVE                CHANNELS
 IMD radar/AWS/nowcast  --\                                   +-------------------+
 Gauges, IoT sensors   ----\                                  | PostGIS (graph,   |      Citizen PWA / Android
 Fleet/probe speeds    -----> Redpanda or NATS JetStream -->  |  segments, events)|----> (map, route, alerts)
 App + WhatsApp reports ---/   topics: rain, probe, report,   | TimescaleDB/      |
 CCTV depth service    ---/    sensor, closure-events         |  ClickHouse (TS)  |----> Ambulance/driver app
 Groundsource/news     --/            |                       | Redis (live seg   |
 Municipal complaints  -/             v                       |  state, p/depth/  |----> Dispatcher dashboard
                               Stream workers (Flink or       |  conf per class)  |      (112/ERSS/ICCC iframe,
                               Python/Rust consumers):        +--------+----------+       webhook, CAP feed)
                                - map-matching, dedupe               |
                                - evidence scoring + trust           v                    Alerting service
                                - Bayesian segment update     Risk grid + tiles       FCM push, WhatsApp BA,
                                - nowcast to rain features    (PMTiles/MVT on CDN,    SMS (DLT), IVR, SACHET/CAP
                                       |                       regenerate every 2-5 min)
                                       v                              |
                               Model serving (ONNX/Triton)            v
                               static prior, trigger, surrogate  Routing service (time-dependent A*,
                                                                  vehicle profiles, hysteresis state)
 Offline: physics scenario library (HEC-RAS/RIM2D/CA), training, backtests, calibration
 Resilience: multi-AZ, second region, static snapshot to CDN + object store, client cache, SMS fallback
```

### 5.2 Component choices

| Concern | Choice | Notes |
|---|---|---|
| Streaming | Redpanda (Kafka API, single binary) or NATS JetStream for MVP. Managed Kafka (MSK, Confluent) at 10 cities | [U] Choose by team skills. Volume is modest: probe pings dominate |
| Stores | PostgreSQL+PostGIS for graph and events, TimescaleDB or ClickHouse for time series, Redis for current segment state | [U] |
| Tiles | Vector tiles from PostGIS (Martin/pg_tileserv) or pre-baked PMTiles on a CDN for the risk layer | [U] Static files survive backend outage |
| Stream processing | Start with Python/Rust consumers. Flink only if windowed joins at scale | [U] |
| Model serving | ONNX Runtime on CPU for threshold and Bayesian layers, GPU only for nowcast or surrogate batch jobs | [U] |
| Caching | Segment state in Redis, route cache keyed by (OD cell, profile, risk version), invalidated on closure events | [U] |

### 5.3 Alerting channels (India specifics)

- WhatsApp Business: since 1 July 2025, per-message pricing. India: marketing Rs 0.86, utility Rs 0.13, authentication Rs 0.13, service free. Free inside the 24-hour customer service window [V https://support.myoperator.com/portal/en/kb/articles/whatsapp-has-shifted-to-per-message-pricing-effective-july-1-2025-based-on-message-categories-and-your-recipient-s-country-in-india-there-are-three-paid-categories]. Alerts initiated outside the window need approved templates.
- SMS: requires DLT registration of entity, sender header and every content template. Template scrubbing blocks mismatches. Since May 2025 headers get a category suffix. Entity approval takes about 2-7 working days, and only Indian entities can register [V https://www.telerivet.com/blog/india-sms-compliance-trai-dlt-registration-and-tcccpr-guide]. Start registration in week 1 with pre-approved flood templates in several languages, with variable slots for place names.
- Official channel: SACHET (CAP-based, run by C-DOT for NDMA) delivers geo-targeted SMS, cell broadcast, apps and other media, operational in all states and UTs, sources alerts from IMD, NDMA, SDMAs and INCOIS [V https://sachet.ndma.gov.in/ and https://ddm.andamannicobar.gov.in/CAPSACHET]. A nationwide cell broadcast test ran on 2 May 2026 [V https://taxguru.in/corporate-law/india-deploys-mobile-alert-system-due-rising-disaster-preparedness.html, date from search snippet, verify]. FloodRoute should feed requests to the authority rather than self-publish public warnings [U].
- Push (FCM) for app users, IVR for feature phones and elderly users, and local-language voice.

### 5.4 Hosting and resilience

- India-hosted options: AWS Mumbai (ap-south-1 [U]) and Hyderabad (ap-south-2, 3 AZs) [V https://aws.amazon.com/blogs/aws/now-open-the-30th-aws-region-asia-pacific-hyderabad-region-in-india]; GCP Mumbai (asia-south1 [U]) and Delhi (asia-south2, 3 zones) [V https://cloudprice.net/gcp/regions/asia-south2]; Azure Central/South India including Pune [U]. Pick one provider, two regions (for example Mumbai plus Hyderabad), warm standby. Keeping data inside India also eases government customer procurement and the DPDP Act 2023 obligations [U].
- The real failure point is last-mile: towers lose power, fibre gets cut, users lose data. Design for it:
  - Client caches the last risk tiles, route graph for the city, and the last route. Rules-based local fallback: if offline and it is raining heavily, apply the static prior and last known closures with a clear "offline, stale by N min" label.
  - Static snapshot (GeoJSON/PMTiles) published to CDN and object storage every few minutes, so the map works even if core services are down.
  - SMS and WhatsApp text queries as low-bandwidth channels, for example "ROUTE from X to Y" returning a compact text answer [U].
  - Dual ingest paths, local buffering at edge collectors, idempotent event replay.
  - Game-day drills before each monsoon, including control-room cut-over.

### 5.5 SLOs and cost envelope

| SLO | Target [U] |
|---|---|
| Risk layer freshness (rain to tile) | p95 under 5 min |
| Route API latency | p95 under 500 ms (ambulance under 300 ms) |
| Availability of static risk layer | 99.95% during declared monsoon alerts |
| Alert dispatch latency (trigger to FCM/WhatsApp handoff) | p95 under 60 s |
| Evidence ingest to state update | p95 under 60 s |

Cost (my estimates, excluding staff and data licences):
- 1-city MVP: roughly USD 2,000-4,000/month cloud (small Kubernetes or VM set, managed Postgres, Redis, CDN, no GPU) plus messaging. At the V rate of Rs 0.13 per utility WhatsApp message, 1 million alert messages is about Rs 1.3 lakh. SMS is typically more costly per message and varies by gateway [U].
- 10 cities: roughly USD 15,000-35,000/month, dominated by messaging, a shared GPU batch pool for nowcast or surrogates, and data licences. Multi-tenant per city partitions help.
- Largest cost risks are probe data licences and CCTV access, not compute.

### 5.6 Integration with 112/ERSS, CAD and ICCC

- ERSS is the national 112 system developed by C-DAC as total service provider, with CAD and GIS mapping [V https://wayanad.keralapolice.gov.in/page/erss]. I found no public CAD API specification. Integration looks to be state-by-state through the state 112 programme. Bihar integrated its 102 ambulance call centre with 112 using APIs [V https://www.pressreader.com/india/hindustan-times-ranchi/20240416/281689734854076]. Plan a pilot MoU with one state first.
- Patterns, in order of effort: (1) read-only dashboard embed (iframe or link) for dispatchers and ICCC operators, (2) GeoJSON/WMS-style road-closure feed and a CAP 1.2 feed (CAP is the standard SACHET uses), (3) signed webhooks for closure and risk-change events, (4) route API called from CAD with vehicle profile, (5) two-way status: dispatcher closure overrides and unit locations. Keep (1)-(3) free of PII so approvals are simpler [U].

## 6. Mobile and client

| Decision | Recommendation |
|---|---|
| Citizen app | PWA first: opens from a WhatsApp or SMS link, no install, small size. Limit: PWAs cannot obtain location in the background or run geofences when closed [V https://lists.w3.org/Archives/Public/public-whatwg-archive/2016Dec/0006.html, still an unimplemented request per search results]. So alerts for "your usual route" must come from server-side saved routes and push, not live tracking |
| Driver and ambulance app | Native Android (Kotlin): foreground service for navigation, background location during active trips, offline maps and tiles. Target low-end devices and Android Go [U] |
| Battery and data | Adaptive GPS sampling, batched uploads, delta tiles, vector tiles under about 100 KB per view [U], no continuous tracking outside active navigation |
| Voice | On-device TTS in Hindi, Tamil, Kannada, Marathi, Bengali, Telugu and English. Short phrases ("Water ahead. Turn left in 200 metres."). Never require screen interaction while moving, and suppress low-priority notifications while driving [U] |
| Privacy | On-device map-matching. Upload only (segment id, speed bucket, time bucket) with random rotating IDs. k-anonymity floor (for example 5 contributors per segment-interval before it counts as evidence), and short retention (days). Explicit opt-in consent for contribution, consistent with DPDP Act 2023 [U]. Aggregate fleet data under contracts that forbid re-identification |

## 7. Model roadmap

| Stage | Method | Data required | Output | Gate to advance |
|---|---|---|---|---|
| v0 (month 0-3) heuristic | Hotspot list from municipal and news data, plus HAND/TWI and underpass flags, rainfall thresholds from IMD forecast and nowcast category (for example orange/red alert plus gauge rainfall), manual depth classes | DEM, OSM, hotspot list (100-300 segments per city), rainfall feed, 1-2 monsoons of event notes | Caution/closed flag per hotspot, no depth | Backtest on 3+ events. POD and FAR reported |
| v1 (month 3-12) hybrid | Static prior ML (spatial CV) plus per-zone rainfall trigger fitted to events, Bayesian evidence updating from probe speed, crowd and CCTV, simple physics scenario library (CA or RIM2D design storms) to give depth bands | DEM at 5-10 m or better, buildings, drainage network where available, 50-200 labelled events per city, probe speed history, 20-50 sensors | P, depth quantiles, confidence, per class | Calibration slope 0.8-1.2, shadow-mode monsoon complete |
| v2 (year 2+) learned | GNN or U-Net surrogate trained on physics sims (mSWE-GNN style, fine-tune per city), learned fusion of evidence, nowcast ensemble coupling, active learning from corrections | Hundreds of sims per city, calibrated hydraulic model, 2+ seasons of labels, sensor network | Real-time depth maps and ensembles | Beats v1 on leave-one-event-out and keeps calibration |

## 8. Top risks

1. Threshold uncertainty: no Indian vehicle-depth guidance found. Field trials needed. Mitigate with conservative defaults and class profiles.
2. Label scarcity and noise (Groundsource 60% exact accuracy, news bias). Mitigate with tiered labels and municipal partnerships.
3. Convective nowcast skill is low (0.15 in the one Indian study seen). Mitigate with wide uncertainty and evidence correction.
4. Over-alerting and alert fatigue, then trust collapse. Mitigate with hysteresis and calibrated thresholds.
5. Liability and legal risk if users are directed into hazards. Mitigate with a safety case, disclaimers and MoUs.
6. Connectivity and power loss at the worst moment. Mitigate with offline and SMS paths.
7. Data access (probe fleets, CCTV, CAD) depends on slow government and corporate processes.
8. Crowd-report abuse and spam. Mitigate with trust scoring and rate limits.
9. DLT/WhatsApp template approval delays before monsoon. Start early.
10. Competing official systems (iFLOWS, Flood Hub, city apps). Mitigate by integrating.

## 9. Open questions

- Does Flood Hub's urban flash flood product cover Indian cities, at what resolution, and can its output be licensed or consumed via API?
- Which city offers the best first DEM, drain network and complaint log (Chennai GCC, BMC, BBMP/GBA, GHMC)?
- What are real passable depths for Indian two-wheelers and autos? Can a fleet partner supply stall data?
- Are Pregnolato-type speed-depth curves valid for mixed Indian traffic?
- Which state 112/ERSS programme will pilot CAD integration, and what is the formal API access route?
- IMD radar coverage claims conflict (47 operating in one source, 126 by November 2025 in another [V https://moes.gov.in/sites/default/files/PIB2117832.pdf and search snippet, unresolved]). Verify the radar and data-sharing arrangements per city.
- Can the MetNet-3 or comparable nowcasts be accessed for India, or must IMD radar plus an open model be used?
- Regulatory view on a private entity publishing closure advisories versus passing alerts through SACHET.

## Sources

- Groundsource: https://research.google/blog/introducing-groundsource-turning-news-reports-into-data-with-gemini/
- Google blog on Groundsource: https://blog.google/innovation-and-ai/technology/research/gemini-help-communities-predict-crisis/
- Flood Hub urban expansion: https://citizen.digital/article/google-unveils-flood-hub-tool-to-predict-urban-flash-floods-n379075
- Pregnolato et al. 2017: https://doi.org/10.1016/j.trd.2017.06.020 ; full text https://research-information.bris.ac.uk/ws/files/191868409/Full_text_PDF_final_published_version_.pdf
- Transport resilience (0.3 m rule): https://arxiv.org/pdf/2609.16963
- mSWE-GNN: https://nhess.copernicus.org/articles/25/335/2025/
- Norfolk ML surrogates: https://arxiv.org/abs/2307.14185 ; https://www.odu.edu/article/rolling-the-deep-norfolk-street-flooding-predicted-seconds-machine-learning-models
- RIM2D Berlin: https://nhess.copernicus.org/articles/26/85/2026/
- CADDIES/CA: https://ore.exeter.ac.uk/repository/handle/10871/23991
- Nowcasting: https://www.mindspore.cn/mindearth/docs/en/stable/nowcasting/DgmrNet.html ; https://arxiv.org/pdf/2407.11317 ; https://research.google/blog/metnet-3-a-state-of-the-art-neural-weather-model-available-in-google-products/ ; https://www.turing.ac.uk/news/publications/end-end-data-driven-weather-prediction
- IMD nowcasting: https://downtoearth.org.in/news/met-department-moves-from-weather-forecasting-to-nowcasting-40175 ; https://moes.gov.in/sites/default/files/PIB2117832.pdf
- iFLOWS-Mumbai: https://vikaspedia.in/social-welfare/disaster-management-1/state-of-the-art-flood-warning-system-for-mumbai ; https://www.pressreader.com/india/hindustan-times-st-mumbai/20200807/281702617059948
- Chennai susceptibility ML: https://link.springer.com/article/10.1007/s11356-023-29132-1
- Probe-speed waterlogging: https://scholars.cityu.edu.hk/en/publications/identification-of-urban-road-waterlogging-using-floating-car-data/
- Flood depth from images: https://arxiv.org/abs/2007.06749 ; https://arxiv.org/abs/2603.17108
- SAR urban limits: https://www.mdpi.com/2072-4292/13/22/4511
- Vehicle stability: https://www.unsw.edu.au/content/dam/pdfs/engineering/civil-environmental/water-research-laboratory/publications/WRL-TR2017-07-Vehicle-Stability-Testing-for-Flood-Flows.pdf ; https://link.springer.com/article/10.1007/s11069-013-0889-2 ; https://journals.utm.my/jurnalteknologi/article/view/11198
- Ambulance and large-vehicle depths: https://www.ipcn.nsw.gov.au/sites/default/files/2025-04/L250331_BrisbaneGrove_Questions_on_Notice_Applicant_Response%20redacted_0.pdf
- NDMA urban flooding guidelines: https://sdma.goa.gov.in/sites/default/files/2022-05/management_urban_flooding.pdf
- Reliable routing: https://transportation.tech.northwestern.edu/docs/research/core-topics/transportation-network-modeling-and-planning/Nie-Nelson_ReliableRouting1.pdf
- Flood-aware emergency routing: https://www.aimspress.com/article/doi/10.3934/jimo.2026136
- GraphHopper dynamic edges: https://discuss.graphhopper.com/t/dynamically-update-edges/8203
- Event data: https://vajiramandravi.com/current-affairs/urban-flooding-in-india/ ; https://thelogicalindian.com/mumbai-records-135-mm-rain-heaviest-may-downpour-in-107-years-red-alert-issued-travel-disrupted/ ; https://www.thenewsminute.com/article/bengaluru-flooded-after-rains-traffic-advisory-issued-people-asked-stay-home-167536
- SACHET and cell broadcast: https://sachet.ndma.gov.in/ ; https://ddm.andamannicobar.gov.in/CAPSACHET ; https://taxguru.in/corporate-law/india-deploys-mobile-alert-system-due-rising-disaster-preparedness.html
- ERSS: https://wayanad.keralapolice.gov.in/page/erss ; https://www.pressreader.com/india/hindustan-times-ranchi/20240416/281689734854076
- DLT: https://www.telerivet.com/blog/india-sms-compliance-trai-dlt-registration-and-tcccpr-guide
- WhatsApp pricing: https://support.myoperator.com/portal/en/kb/articles/whatsapp-has-shifted-to-per-message-pricing-effective-july-1-2025-based-on-message-categories-and-your-recipient-s-country-in-india-there-are-three-paid-categories
- Cloud regions: https://aws.amazon.com/blogs/aws/now-open-the-30th-aws-region-asia-pacific-hyderabad-region-in-india ; https://cloudprice.net/gcp/regions/asia-south2
- PWA background geolocation: https://lists.w3.org/Archives/Public/public-whatwg-archive/2016Dec/0006.html
