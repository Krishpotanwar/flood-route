# FloodRoute: Market, Users, Competition, Go-to-Market, Launch Cities

Research date: 2026-10-05. Tags: **[V url-key]** = seen in a fetched page or search-result text this session (key maps to the Sources list; many are secondary or news reports, and a few were read from search snippets only). **[U]** = unverified or recalled. **[EST]** = my own estimate or judgement, not sourced. No primary-source number below should be treated as audited.

---

## 1. Problem sizing

**National frame.** Floods kill roughly 1,600-1,700 people a year in India (NDMA-cited average 1,600; another compilation 1,671) and the average annual economic impact for 2011-2021 was about Rs 25,805 crore [V S1]. A World Bank figure of about US$9.8bn a year from extreme events, half from floods, circulates in secondary reporting [V S1, secondary]. These are all-flood numbers (riverine, landslide, urban). **No source found isolates road-related urban flood harm.** FloodRoute's addressable harm has to be built bottom-up from incidents (below) and from fleet/ambulance delay costs. That is a gap to close in the investor narrative [EST].

**Recent road-relevant events (2024-2026).**

| Event | Road/mobility harm | Source |
|---|---|---|
| Mumbai, 1-6 Jul 2026 | Santacruz recorded 805.6 mm in six days (about 94% of a normal July); city "at a standstill"; Mumbai-Pune expressway closed by landslides; open-manhole death | [V S2] |
| Mumbai, May 2025 | Earliest monsoon onset on record (26 May); record May rain | [V S3] |
| Gurugram, Jul-Aug 2026 | 3-hour strandings on Delhi-Gurgaon Expressway and Ambience Mall underpass; about 300 schoolchildren in ~15 vehicles (9 school buses) stuck ~2 h at Subhash Chowk; 50+ areas waterlogged after about an hour of rain | [V S4] |
| Surat/Gujarat, Jul 2026 | 500+ cars reportedly submerged; Surat-Navsari highway disrupted; state toll reported 31-35 | [V S5] |
| Pune, Jul and 28 Sep 2026 | Extreme spell (Dawdi 688 mm in 24 h to 7 Jul); about 1,560 rescued from Mula-Mutha; fresh waterlogging 28 Sep despite drainage spend; traffic police mapped 26 hotspots from 2025 emergency-call data | [V S6] |
| Kolkata, 22-24 Sep 2025 | 251.6 mm in 24 h, heaviest since 1988; 11 dead, mostly electrocution, 2 drowned; vehicles stranded | [V S7] |
| Faridabad underpass, Sep 2024 | Two bank employees died when an SUV entered a flooded underpass; police say barricades and warnings were ignored | [V S8] |
| Bengaluru, 18-20 May 2025 | 104-130 mm; Silk Board and Hosur Road flyover closed; 44 four-wheelers and 93 two-wheelers submerged or swept; 5 state rain deaths | [V S9] |
| Delhi, 28 Jul 2024 (Rajinder Nagar) | Three aspirants drowned in a coaching-centre basement after a drain burst (not a road death, but shows 30 mm-in-3-h lethality) | [V S10] |
| Delhi, Jul 2025 | Azad Market and Zakhira underpasses waterlogged; wall-collapse deaths | [V S11] |
| Chennai, Dec 2023 (Michaung) | 17+ deaths; TN loss above Rs 11,000 crore; about 500 mm/day | [V S12] |
| Wayanad, Jul 2024 | 400+ dead in landslides (hill-road context, outside launch scope) | [V S13] |
| Himachal, monsoon 2025 | 419 deaths since 20 Jun (182 in road accidents); 517 roads blocked | [V S14] |
| Punjab, Aug 2025 | About 1,400 villages, about 55 deaths; worst since 1988 | [V S15] |

**Ambulance harm.** I found incidents of patients dying when ambulances were blocked by fallen trees in Kerala (2026) and a patient carried 3 km on a cot past a flooded river in Bhopal [V S16], but **no systematic dataset of flood-caused ambulance delays**. Treat "ambulance delay" as a hypothesis to measure in pilot, not a sized market [U].

**Why timing matters.** Intense short bursts, not seasonal totals, are the killer: Delhi coaching centre (31.5 mm in 3 h), Gurugram (115 mm in two days or about an hour of rain) and Bengaluru (130 mm in 12 h). This favours nowcasting plus road-segment logic over seasonal risk maps.

---

## 2. Competitive landscape

| Player | What it does | What it does not do |
|---|---|---|
| **Google Maps** | Crowd-reported flood/fog alerts; India "highest number of flood-related alerts on Maps globally" in 2025; traffic-police partnerships in 18 cities for closures; 150,000 disruptions/day; NHAI closure data deal [V S17] | No predictive road-segment passability; reactive; no vehicle-class logic; no ambulance mode; not a dispatch tool |
| **Google Flood Hub** | Riverine forecasts for all India (CWC partnership; 115M alerts in 2021) [V S18]; **urban flash-flood forecasts launched 12 Mar 2026**: 24 h lead, but **20x20 km grids, not road-level**, India not named in launch post [V S19] | Cannot say which underpass floods. Comparison benchmark: US NWS flash-flood warnings 22% recall / 44% precision on same metric [V S19]. **This is the biggest strategic risk: Google may refine resolution in 2026-27** |
| **Waze / Apple Maps** | Not verified in India for flood-specific features | [U] Assumed no flood layer; Waze India share small [U] |
| **Mappls (MapmyIndia), Ola Maps** | Indian map/nav platforms; Ola Maps is OSM-based with Ola vehicle telemetry [V S20] | **No flood or waterlogging feature found in any source** [U]. Candidates to partner (API/licence) rather than fight |
| **Mumbai iFLOWS + BMC + Traffic Police** | MoES-BMC integrated flood warning; rain forecast at 500 m / 15 min; ward-level hazard [V S21]. Traffic police: 215 flood spots over 34 divisions, diversions from 145 spots [V S22]; BMC uses traffic CCTV (64 junctions) [V S22]; alerts via X (e.g., Andheri Subway closure at 1.5 ft) | Output is for officials/press; not a citizen or fleet routing product; no API found |
| **Bengaluru KSNDMC** (Megha Sandesha, Varunamitra) | 100 telemetric rain gauges, 12 weather stations, 105 drain water-level sensors; live inundation map; "Be Ready Bengaluru" WhatsApp group with BBMP, BMTC, traffic police [V S23] | Drain-level, not road passability; no routing. BBMP helpline 1533 and zone control rooms [V S9] |
| **Chennai Flood Monitor (TN govt/World Bank RTFF-SDSS)** | 117 rain gauges, 30 AWS, 185 water-level recorders, 58 gate sensors; street-level inundation forecasts for select areas (Nungambakkam, Velachery); public alerts [V S24]. IIT-Madras crowdsourced waterlogging portal and 7-day forecasts to GCC [V S25] | Coverage is pilot-scale; no routing |
| **Hyderabad GHMC/HYDRAA** | 913 waterlogging points identified (523 GHMC, 202 Cyberabad, 188 Malkajgiri), 150 monsoon emergency teams, 51 DRF units [V S26] | Operational response, no public/fleet routing product found |
| **Delhi Traffic Police/PWD/MCD** | 169 waterlogging-prone traffic hotspots, fixed pumps, GPS patrolling; LG-reported reduction to 65 sites [V S27] | Manual; social-media alerts; no API |
| **IMD Mausam/Damini/Sachet, NDMA Sachet** | National alerts (CAP-based) | [U] Not road-level; Damini is lightning. Useful as inputs (see doc 01) |
| **IIT Delhi (Aab Prahari app, Barapullah early warning)** | Crowdsourced flood reporting; drainage-network EWS pilot [V S28] | Academic pilots |
| **Skylark Drones, TerrAqua UAV (IIT Kanpur), Skymet** | Drone flood-prone mapping (Bengaluru, Vijayawada); inundation models; Skymet 6,000+ AWS, alerts [V S28] | No routing; Skymet B2B/media orientation. Skymet and Skylark are potential data partners |
| **Tomorrow.io** | Global weather API; India: Tata Power deal Sep 2024 [V S29] | No road-passability for India |
| **Floodbase (ex-Cloud to Street)** | Satellite flood intelligence, insurance focus, FEMA contract, Asia insurance-broker deal (Dec 2023) [V S29] | Not routing; post-event; insurer-oriented |
| **Fathom, Jupiter Intelligence, One Concern, Ambee, Rainmatter-backed climate startups** | Flood hazard/risk models for finance and real estate [U] | Static or portfolio-risk; not live routing. One Concern status unclear [U] |
| **Academic/open-source prototypes** | Flood-aware routing (YOLO + U-Net + elevation), satellite on-board flood monitoring using Bengaluru case, Malaysian flood-node nav apps [V S30] | Prototypes; no operational data feeds or India-scale deployment |
| **Fleet/logistics routing vendors** (e.g., weather-aware tools from global TMS vendors) | [U] Weather overlays, rarely road flooding | Not India-flood specific |

### White space

1. **Road-segment passability prediction (30-180 min ahead), not rain or river forecasts.** Every government system forecasts rain, river or drain level; Google's flash-flood product is 20 km. Nobody maps rain to "this underpass is impassable for a hatchback in 40 minutes."
2. **Vehicle-class-aware decisions.** An ambulance with high clearance, a two-wheeler, a school bus and a sedan have different depth thresholds.
3. **Continuous rerouting for dispatched fleets**, ingestible by 108/112 CAD and traffic control rooms. Government dashboards are monitors, not routers.
4. **Fusion layer** over fragmented city sensors (KSNDMC, Chennai, iFLOWS), CCTV, crowd reports and Google/Ola traffic probes. Each city owns data silos and nobody sells the glue.
5. **Delivery over WhatsApp/SMS/IVR** and to gig fleets through APIs, where Google Maps is a poor fit for emergency or fleet policies.

Threats to the white space: Google (Flood Hub resolution plus Maps reporting); Ola Maps/Mappls adding "flood avoid"; state NICs building in-house dashboards [EST].

---

## 3. Users, personas, jobs-to-be-done

| Persona | Core job | Willingness to pay | Buying path | Notes |
|---|---|---|---|---|
| **108/102 ambulance operators and dispatchers** | Pick a route that will not strand a patient | Low per vehicle; budget sits with state NHM contracts [EST] | B2B2G: operators are private (EMRI Green Health Services 14,445 ambulances, about 33,652 emergencies/day; ZHL; BVG) [V S31] | Highest mission value; highest liability |
| **112 ERSS control rooms** | Dispatch nearest unit by safe road | Low, slow | State home dept/police; ERSS live in 27 States/UTs; CAG notes 101/108/181 not fully integrated [V S32] | Integration through CAD is key and political |
| **Fire brigade, NDRF/SDRF, municipal** | Position pumps and boats before failure; reach callers | Medium (disaster funds) | SDMA/municipal; NDMF for mitigation | Wants "where will it flood next," not only routing |
| **Traffic police control rooms, ICCC** | Decide closures/diversions early; tell the public | Medium | City ICCC (all 100 smart-city ICCCs operational; mission closed 31 Mar 2025, states told to absorb them) [V S33] | They already hold hotspot lists (Mumbai 215, Delhi 169, Pune 26) |
| **Delivery platforms** (Swiggy, Zomato, Blinkit, Zepto) and gig riders | Keep riders safe and ETAs honest during rain | **High** (surge/rain-allowance cost, rider safety, brand risk) | Direct B2B API or SDK; fast | NITI: 7.7M gig workers 2020-21, 23.5M by 2029-30 [V S34]. Platforms already pay rain surge and monitor riders in waterlogged areas [V S35] |
| **Cab/auto (Uber, Ola, Rapido)** | Avoid stranded trips and cancellations | Medium-high | B2B API | Navigation owned by Google/Ola Maps [U] |
| **School bus operators** | Avoid trapped children (Gurugram, Mumbai tree-on-bus) | Medium; needs fleet ops integration | Schools and RTO-linked operators | Emotive, strong PR |
| **Logistics fleets, hospital transport** | Protect cargo and schedules | Medium | B2B SaaS | |
| **Dialysis/chronic patients, hospitals** | Reach scheduled care during forecast storms | Low direct | NGO/CSR/hospital | Compelling pilot story |
| **Commuters (2W, car)** | Know "do not enter" before committing | **Very low ARPU**; large reach | Free via WhatsApp; monetise via data or partners | Distribution and trust engine |
| **Insurers (motor)** | Reduce flood claims (vehicle stalling/water ingress) | Medium; claims proof is long | Pilot with a motor insurer | Floodbase-style insurer products exist; motor angle is [U] |

### Beachhead decision

**B2G alone is the wrong first step:** long cycles, low ARPU, high liability if an ambulance is rerouted wrongly. **B2C alone** has no revenue and competes head-on with Google Maps. **Beachhead recommendation [EST]: dispatched fleets**, meaning (a) one 108 operator or traffic-police control room as a free or near-free mission anchor and data partner, and (b) one or two delivery/cab platforms as paying customers via API. This gives revenue in 3-6 months, field validation with real routes, and a credible safety story for later city sales. Citizens come second through WhatsApp.

---

## 4. Indian UX and distribution context

| Factor | Finding | Implication |
|---|---|---|
| WhatsApp | 550M+ monthly users in India; about 96% of smartphone users [V S36, secondary] | Primary citizen channel; bot with location share |
| Android | About 90% of mobiles [V S36, secondary] | Android-first; light PWA fallback |
| Connectivity in floods | [U] Mobile towers often fail at peak; power cuts | SMS (cell broadcast and plain SMS) and IVR fallbacks; precache last known risk map; "no data" must degrade to the last good state with a timestamp |
| Languages | Hindi, Marathi, Tamil, Telugu, Kannada, Bengali, Malayalam, Gujarati, Assamese | Voice and icons first; launch city dictates 2 languages (Bengaluru: Kannada + English/Hindi) |
| 112 India app | Panic button with location to ERSS [V S32] | Integration point (sending a hazard layer or routing hint into CAD) is politically easier than a competing app |
| Google Maps default | Dominant for drivers; 18-city traffic-police partnerships [V S17] | Do not fight for default. Ship (1) own console for dispatchers, (2) deep-link out to Google Maps with waypoint-forced detours, (3) data feed to Ola Maps/Mappls |
| Trust/liability | Faridabad: barricades and police warnings were ignored [V S8] | Alerts must be vivid, local-language, voice-capable, and blocking inside navigation, not just a banner |

---

## 5. Business model and procurement

**Channels.** GeM (launched 2016; registers start-ups, no upfront empanelment for sellers per GeM-related sources) [V S37]. Smart-city ICCCs exist in all 100 cities but the Mission closed on 31 Mar 2025; operating budgets are shifting to state and municipal control [V S33]. Funding for flood mitigation: Urban Flood Risk Mitigation Programme (UFRMP) from the National Disaster Mitigation Fund: Phase-I Rs 3,075.65 crore (Ahmedabad, Bengaluru, Chennai, Hyderabad, Kolkata, Mumbai, Pune), Phase-II Rs 2,444.42 crore (11 cities incl. Guwahati, Patna, Trivandrum); projects in all seven Phase-I cities are being implemented [V S38]. UFRMP is mostly capex (drains, conveyance); the Aug 2026 summary does not mention early-warning software [V S38]. SDRF corpus is Rs 1,28,122 crore for 2021-26 [V S39]; whether it can fund software is unclear (use limited to relief and up to 10% for local disasters) [V S39]; the next Finance Commission cycle starts FY27 [U].

**Revenue lines (all estimates [EST], to test in pilots).**

| Customer | Product | Price anchor [EST] | Sales cycle [EST] |
|---|---|---|---|
| Delivery/cab platform | API plus rider-app SDK, per city | Rs 15-60 lakh/yr per platform-city, or Rs 20-100 per active rider/month | 2-6 months |
| Ambulance operator (state contract) | Dispatcher console and routing hints | Rs 5-25 lakh/yr per state, bundled | 6-12 months |
| City traffic police/ICCC | Predictive hotspot and diversion console | Rs 30 lakh-1.5 crore/yr per city; below GeM direct-purchase limits for pilots [U thresholds] | 9-18 months |
| Maps platform | Data licence | Rs 10-50 lakh/yr, with upside by MAU | 4-9 months |
| Insurer | Claims-avoidance alerts and portfolio risk | Pilot Rs 10-30 lakh | 6-12 months |
| CSR / NGO | Citizen WhatsApp and IVR channels | Grants | 3-6 months |

Pricing is intentionally low-confidence: no verified India pricing for comparable flood-routing software was found. Validate with 8-10 customer interviews before the pitch.

---

## 6. Launch city selection

**Scoring method [EST].** 1-5 per criterion from the evidence above; weights: severity/frequency 20, hotspot data availability 20, government digital maturity/open data 15, ICCC/control-room presence 10, traffic density/user base 15, smartphone/WhatsApp 5, partner access 15. Scores are my judgement from the cited evidence, not measured.

| City | Sev | Data | Gov digital | ICCC | Traffic | Phone | Partners | **Weighted** |
|---|---|---|---|---|---|---|---|---|
| **Bengaluru** | 4 | 4 | 4 | 4 | 5 | 5 | 5 | **4.35** |
| **Mumbai** | 5 | 4 | 4 | 5 | 5 | 5 | 3 | **4.35** |
| Delhi-NCR / Gurugram | 4 | 4 | 3 | 4 | 5 | 5 | 4 | 4.05 |
| Chennai | 5 | 4 | 4 | 4 | 4 | 4 | 3 | 4.05 |
| Hyderabad | 3 | 4 | 4 | 4 | 4 | 5 | 4 | 3.85 |
| Surat | 4 | 3 | 4 | 4 | 3 | 4 | 3 | 3.50 |
| Ahmedabad | 3 | 3 | 4 | 4 | 4 | 4 | 3 | 3.45 |
| Pune | 3 | 3 | 3 | 3 | 4 | 4 | 3 | 3.20 |
| Kolkata | 4 | 2 | 2 | 3 | 4 | 4 | 2 | 2.90 |
| Kochi | 3 | 2 | 3 | 3 | 2 | 4 | 3 | 2.70 |
| Guwahati | 4 | 2 | 2 | 2 | 2 | 3 | 2 | 2.45 |
| Patna | 3 | 2 | 2 | 2 | 3 | 3 | 2 | 2.10 |

Key evidence behind scores: Bengaluru has public telemetric sensors and a live inundation map [V S23], hotspot lists, repeated road closures [V S9], plus the densest concentration of delivery, cab and map-platform customers (Swiggy, Rapido, Uber India, Ola Maps; HQs [U]). Mumbai has the most severe and best-instrumented system but crowded incumbents (iFLOWS, traffic police, Google) and high political friction [V S21, S22]. Chennai has the richest open sensor network [V S24] and an active NE monsoon right now. Delhi-NCR has the clearest fatality-per-incident road story (underpasses) but split jurisdiction (Delhi, Haryana, UP) [V S8, S27]. Hyderabad has a large hotspot inventory and houses the original 108 operator [V S26, S31].

**Recommendation.**

* **Beachhead: Bengaluru.** It ties with Mumbai on score; tie-breakers: (1) the most B2B revenue customers in one place, (2) KSNDMC open telemetry and a WhatsApp-based coordination culture, (3) less incumbent routing competition than Mumbai, (4) pre-monsoon thunderstorms in April-May 2027 and NE rains in Oct-Nov give two live-test windows, (5) a founder-reachable ecosystem.
* **Next 1: Mumbai** (SW monsoon, onset early June; 2025 onset was 26 May [V S3]). Needs government partnerships but offers the strongest proof of impact.
* **Next 2: Delhi-NCR, starting with Gurugram** (delivery HQs, underpass deaths, Haryana jurisdiction simpler than the whole NCR) for the Jul-Sep 2027 monsoon.
* **Chennai: opportunistic "live lab" in shadow mode, Nov-Dec 2026.** The NE monsoon runs Oct-Dec; there is not enough time to ship a product, but ingesting the Chennai flood monitor and logging predicted versus observed closures gives free validation data. Re-evaluate as a full city for Oct 2027.

**Monsoon calendar and build timeline (from 5 Oct 2026).**

| Window | Relevance | Plan |
|---|---|---|
| Oct-Dec 2026 | NE monsoon (Chennai, TN, coastal AP, also late rains Bengaluru) | Ingest data; shadow-mode predictions; collect labelled floods (crowd reports, traffic-police alerts, CCTV) |
| Jan-Mar 2027 | Dry season | Build routing engine and dispatcher console; sign 1-2 design-partner fleets and one control room; legal and liability review |
| Apr-May 2027 | Pre-monsoon convective storms (Bengaluru May 2025 event) | **First live Bengaluru pilot**; ambulance and delivery fleets in advisory mode |
| Jun-Sep 2027 | SW monsoon (Mumbai, Gurugram, Pune) | Mumbai and Gurugram pilots; measure KPIs |
| Oct-Dec 2027 | NE monsoon | Chennai |

---

## 7. Success metrics and candidate wedge MVP

**Metrics (targets are estimates [EST]).**

| Layer | Metric | Benchmark / target |
|---|---|---|
| Prediction | Precision/recall for "road segment impassable within 60 min" | Beat the only public benchmark: Google/NWS flash-flood warnings at 22% recall / 44% precision [V S19]; aim for recall above 60% and precision above 60% on hotspot roads in the pilot city |
| Lead time | Median warning before closure | 30-60 min at launch |
| Ops | Share of dispatched trips rerouted that avoided a flooded segment; avoided strandings | Measure per 1,000 trips |
| Time | Average ETA saved vs fleet baseline during rain | Pilot-defined; report median and p90 |
| Safety | Zero "routed into a closed road" incidents | Hard guardrail |
| Adoption | Active fleets, dispatcher daily logins, WhatsApp opt-ins | 2 fleets and 1 control room by May 2027 |
| Revenue | Paid pilots | 2 by Jul 2027 |

**Candidate wedge MVP: "Bengaluru Underpass and Hotspot Go/No-Go for Dispatchers".**
1. Cover the roughly top 100-200 chronic hotspot segments and all underpasses (traffic-police and BBMP lists) rather than the full road graph.
2. Per segment: status (clear, caution, avoid) for 60/120 min, with a vehicle-class threshold and a confidence level.
3. Delivery: dispatcher web console, REST API for fleets, WhatsApp bot (Kannada/English), and Google Maps waypoint deep links.
4. Inputs: KSNDMC telemetry, IMD/nowcasts, traffic probes, CCTV/crowd reports, hotspot history (see doc 01).
5. Explicit advisory-only mode in 2027; no automatic rerouting of ambulances without human confirmation.

---

## Recommended positioning statement

> **FloodRoute tells dispatched fleets, and the control rooms behind them, which roads will be impassable in the next hour, and reroutes around them before the water arrives. Where maps say "heavy rain" and rivers say "flood warning," FloodRoute says "avoid this underpass for the next 90 minutes, take this one instead," built for Indian cities, vehicle classes, and WhatsApp.**

---

## Top risks

1. **Google closes the gap.** Flash-flood forecasting launched March 2026 at 20 km; Maps already leads on user flood reports. Mitigation: own road-segment ground truth, dispatcher workflow and Indian-agency data deals Google cannot easily sign.
2. **Liability** if an advisory misroutes an ambulance or school bus. Mitigation: advisory mode, human-in-loop, clear terms, insurance, auditable logs.
3. **Ground-truth scarcity.** Few labelled road-flood events; hotspot lists are static and manual. Mitigation: shadow-mode season, crowd/CCTV/traffic-police labelling.
4. **Data access.** Government sensors (iFLOWS, KSNDMC) may not offer APIs or licences. Mitigation: MoUs; start from public feeds.
5. **Government sales cycle** and budget mismatch (UFRMP funds capex; SDRF eligibility unclear). Mitigation: lead with B2B revenue.
6. **Seasonality:** revenue concentrated in 3-4 months; connectivity failure during the event itself.
7. **Accuracy bar:** false alarms train users to ignore alerts; misses destroy trust.

## Open questions

* Is there any dataset on flood-caused ambulance delay (108 operator logs, EMRI)? Ask EMRI/ZHL directly.
* Do Mappls or Ola Maps have an unpublished flood layer or an appetite to license one? (Not verified.)
* Does Google's flash-flood product cover Indian cities, and at what resolution by 2027?
* Which agencies in Bengaluru will give API or MoU access (KSNDMC, BBMP, BTP/ASTraM, BMTC)?
* What are real delivery-platform costs of rain (surge, cancellations, rider injuries) to set price anchors?
* Can SDRF, NDMF or state mitigation budgets pay for software subscriptions; what do GeM thresholds currently allow?
* Does the 16th Finance Commission cycle change SDRF/NDMF terms from FY27?
* What are legal norms on advisories that influence ambulance routes (MHA ERSS guidelines, state 108 contracts)?

---

## Sources (key to tags)

* S1 factly.in, Average annual economic impact of floods: https://factly.in/data-average-annual-economic-impact-due-to-floods-is-more-than-rs-25000-crores-after-the-year-2010 ; FLAME University summary: https://www.flame.edu.in/in-the-media/climate-change-catastrophic-floods-highlight-need-for-urgent-mitigation-efforts
* S2 Mumbai Jul 2026: https://www.latestly.com/india/news/mumbai-latest-news-today-on-july-3rd-2026-monsoon-fury-fatal-incidents-andheri-fire-7501761.html/amp ; https://www.rustourismnews.com/2026/07/06/heavy-monsoon-rains-bring-mumbai-to-a-standstill/
* S3 Mumbai May 2025 onset: https://www.deccanherald.com/amp/story/india%2Fmaharashtra%2Fmumbai-breaks-century-old-record-as-rains-mark-attendance-with-a-bang-3557782
* S4 Gurugram 2026: https://www.businesstoday.in/latest/trends/story/7-minutes-journey-took-one-and-a-half-hour-gurugram-rains-leave-commuters-stranded-for-hours-547337-2026-08-05 ; https://www.etvbharat.com/en/state/hour-long-rain-inundates-gurugram-major-traffic-snarl-as-5-km-jam-on-expressway-triggers-chaos-enn26082407957
* S5 Surat/Gujarat 2026: https://www.latestly.com/india/news/surat-latest-news-today-on-july-26th-2026-flood-aftermath-casualties-relief-efforts-7532318.html
* S6 Pune: https://www.punekarnews.in/?p=238846 ; https://www.thebridgechronicle.com/pune/pune-roads-flooded-drainage-civic-lapses-agn97 ; https://navbharatlive.com/maharashtra/pune/mula-mutha-river-pune-floods-ekta-nagar-evacuation-tree-safety-plan-updates-1850849.html
* S7 Kolkata Sep 2025: https://www.newsonair.gov.in/death-toll-due-to-rain-related-incidents-in-kolkata-adjoining-areas-increases-to-11 ; https://scroll.in/latest/1086868/kolkata-heavy-rainfall-causes-severe-waterlogging-schools-closed
* S8 Faridabad underpass: https://www.tribuneindia.com/news/haryana/faridabad-drowning-suv-driver-ignored-warning-barricades-claim-cops ; https://ianslive.in/two-killed-after-suv-sinks-in-waterlogged-underpass-in-faridabad--20240914110037
* S9 Bengaluru May 2025 and BBMP control rooms: https://www.tribuneindia.com/news/india/rain-continues-to-batter-bengaluru-death-toll-climbs-to-5 ; https://thesouthfirst.com/news/overnight-rains-cause-widespread-waterlogging-in-bengaluru-traffic-advisory-issued
* S10 Rajinder Nagar: https://scroll.in/latest/1071295/three-upsc-aspirants-drown-in-flooded-basement-of-delhi-coaching-centre
* S11 Delhi Jul 2025: https://www.theweek.in/wire-updates/national/2025/07/29/del68-ld-delhi-rains.html
* S12 Michaung: https://en.wikipedia.org/wiki/Cyclone_Michaung
* S13 Wayanad: https://en.wikipedia.org/wiki/2024_Wayanad_landslides
* S14 Himachal 2025: https://thenewsmill.com/2025/08/himachal-monsoon-199-dead-including-108-in-rain-linked-disasters-and-91-in-road-accidents-says-seoc/ and search results on 419 deaths/517 roads (dynamitenews, sundayguardianlive)
* S15 Punjab 2025: https://en.wikipedia.org/wiki/2025_Punjab,_India_floods
* S16 Ambulance incidents: https://keralakaumudi.com/en/kerala/general/transportation-stalled-as-tree-falls-on-road-in-heavy-rain-patient-in-ambulance-dies-1763204 ; https://www.freepressjournal.in/bhopal/65-year-old-carried-3-km-on-cot-as-flooded-river-blocks-ambulance-in-bhopal
* S17 Google Maps India alerts (Nov 2025): https://blog.google/intl/en-in/products/explore-communicate/google-maps-in-india-keeping-you-informed-with-new-safety-disruption-alerts/
* S18 Google Flood Hub (riverine): https://blog.google/innovation-and-ai/products/expanding-our-ml-based-flood-forecasting/
* S19 Google urban flash flood (12 Mar 2026): https://research.google/blog/protecting-cities-with-ai-driven-flash-flood-forecasting/
* S20 Ola Maps: https://www.olakrutrim.com/ola-maps-products
* S21 iFLOWS Mumbai: https://vikaspedia.in/social-welfare/disaster-management-1/state-of-the-art-flood-warning-system-for-mumbai ; https://inc42.com/?p=213383
* S22 Mumbai Traffic Police and CCTV: https://www.governancenow.com/news/regular-story/mumbai-gets-cctvs-signals-monitor-water-logging ; https://togethervcan.in/?p=5051 (date of the 215-spot figure not confirmed)
* S23 KSNDMC apps: https://www.thenewsminute.com/amp/story/karnataka/govt-launches-two-apps-give-real-time-info-rainfall-urban-flooding-bengaluru-126047 ; https://citizenmatters.in/bengalurus-flood-alert-system-good-for-rescue-not-prevention/
* S24 Chennai Flood Monitor: https://chennaifloodmonitor.tn.gov.in/Master/AboutUs
* S25 IIT-Madras Chennai crowdsourcing: https://citizenmatters.in/iitm-team-log-flood-water-levels-chennai-residents-forecasting/
* S26 Hyderabad: https://www.siasat.com/913-waterlogging-points-identified-across-hyderabad-3500216/
* S27 Delhi Traffic Police: https://www.theweek.in/wire-updates/national/2025/05/31/des72-dl-monsoon-traffic.html ; https://www.newkerala.com/news/a/delhi-lg-reviews-traffic-management-monsoon-preparedness-kanwar-489.htm (169 to 65 claim from search snippet; year not confirmed)
* S28 ThePrint on drones, IIT Delhi, Skymet: https://theprint.in/ground-reports/indian-cities-iits-tech-startups-drone-urban-flooding/2711171/
* S29 Tomorrow.io/Tata Power and Floodbase: https://www.meteorologicaltechnologyinternational.com/news/data/tata-power-partners-with-tomorrow-io-for-enhanced-weather-forecasting-in-india.html ; https://www.businesswire.com/news/home/20230303005369/en/Floodbase-Selected-to-Provide-a-National-Near-Real-Time-Flood-Intelligence-System-for-the-Federal-Emergency-Management-Agency-FEMA
* S30 Flood-aware routing research: https://export.arxiv.org/abs/2405.02868 ; https://mdpi-res.com/d_attachment/water/water-15-01417/article_deploy/water-15-01417.pdf
* S31 108 operators and fleet: https://emri.in/?p=1499 ; https://en.wikipedia.org/wiki/108_(emergency_telephone_number)
* S32 ERSS/112: https://112.gov.in/about ; https://cag.gov.in/uploads/download_audit_report/2024/06-Chapter-III-069b809d2b80a42.67132610.pdf
* S33 Smart Cities Mission/ICCC: https://visionias.in/current-affairs/news-today/2025-03-31/schemes-in-news/smart-cities-mission-scm-deadline-ended-on-march-31-2025 ; https://therealtytoday.com/news/trending/union-government-directs-states-to-integrate-smart-cities-assets-into-urban-governance/
* S34 NITI Aayog gig report: https://www.niti.gov.in/sites/default/files/2022-06/Policy_Brief_India%27s_Booming_Gig_and_Platform_Economy_27062022.pdf
* S35 Delivery in rain: https://www.thequint.com/amp/story/south-india/bengaluru-floods-delivery-workers-face-problems-e-commerce-shipments-delayed ; https://knnindia.co.in/news/newsdetails/sectors/others/heavy-rains-disrupt-food-delivery-and-quick-commerce-businesses-in-north-india
* S36 WhatsApp/Android India (secondary, low-grade): https://hyperleap.ai/blog/whatsapp-statistics-india-2026 ; https://webcertain.com/site/knowhowAmp/Indian-Mobile-And-Apps-Market-Revealed/kb1285
* S37 GeM: https://jamshedpur.nic.in/service/gem-portal/ ; https://echai.ventures/startingup/selling-to-government
* S38 UFRMP (PIB summary, 12 Aug 2026): https://superkalam.com/current-affairs/12-08-2026/urban-flood-risk-mitigation-programme-c5638fd6-25f7-44cb-a71e-eca5b6a3bfe0
* S39 SDRF: https://laex.in/prelims-fact-sheet/state-disaster-response-fund-sdrf/
