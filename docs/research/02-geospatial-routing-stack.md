# FloodRoute research 02: Geospatial, maps and routing stack for India

Date: 2026-10-05. Scope: road data, terrain/hydrology, routing engines, tiles, Indian geospatial law, data engineering.

**Tag convention.** `[V-n]` means verified against source n in the Sources list (fetched or surfaced in this session). `[U]` means unverified or recalled, so confirm before relying on it. All costs marked "EST" are my own arithmetic or assumptions, not quotes. Where a summarising tool paraphrased a page I say so.

## 0. Bottom line

1. Self-host the routing engine. No commercial API lets you inject per-edge flood risk. Google explicitly forbids mixing its route content with non-Google maps and caching it. Ola permits layering and combining your own content but bans use in ML/AI systems and open-database mixing. Mappls terms and pricing are not publicly retrievable.
2. OSM is workable for the road graph in the big cities, but India has thin attribute coverage (speed, surface, structures) and almost no tagging of flood-prone spots. FloodRoute must build its own "flood-vulnerable segment" layer.
3. The India-specific legal regime is liberal for a 100% Indian-owned startup, with two traps: the 1 m / 3 m accuracy threshold and boundary depiction.
4. Best-fit engine for risk-aware routing is Valhalla (edge-level live closures and speed overlays without rebuilding the graph, plus per-request exclusion polygons). GraphHopper is the runner-up. OSRM is fastest but least flexible.

## 1. Road network data

### 1.1 OSM and Overture

| Item | Finding | Tag |
|---|---|---|
| OSM attribute completeness in India | A HeiGIT study found maxspeed present on only 1.9% of the Hyderabad–Mumbai route versus ~43% for Germany. Missing attributes force engine defaults and large ETA errors. | [V-19] |
| Highway coverage | Manipur had ~68% of its national-highway network in OSM. Paid mapping (RMSI) upgraded "high priority roads" in major cities. | [V-19] [U on current state] |
| City-level quality (Mumbai, Chennai, Bengaluru, Hyderabad, Delhi, Kolkata) | No quantified per-city completeness found. Expect good geometry and connectivity in Tier-1 cores; weaker on lanes, surface, one-way, turn restrictions, and informal lanes. | [U] |
| Flood tagging | `flood_prone=yes` exists for the exact stretch likely to go under water. Docs say use it on short stretches (low tunnels, passages under bridges). `tunnel=culvert` on the waterway. Rare in India. | [V-18] |
| Structures | Overture's segment schema carries `road_flags` (tunnel, bridge), `road_surface`, `width_rules`, `access_restrictions`. OSM `bridge`, `tunnel`, `layer`, `tunnel=building_passage` are the source tags. | [V-22] |
| Overture transportation | Sources are OSM plus TomTom. Licence is ODbL. Distributed as GeoParquet and queryable with DuckDB. Release 2026-09-23.1 is current. | [V-21] [V-23] |
| Overture buildings | ODbL theme, incorporating Microsoft ML footprints (ODbL) and Google Open Buildings (CC BY 4.0). | [V-21] |

Implications:
- ODbL share-alike applies to derived road databases. Keep the risk layer as a separate table keyed by stable segment ID (a "collective" rather than derivative database). [U: confirm with counsel.]
- Plan a crowd-plus-field "underpass/culvert/low-bridge inventory" project per city. Seed it from the Mumbai traffic police list of 200+ flood spots [V-30], the BBMP/KSNDMC list of 210 flood-prone areas [V-31], and Chennai inundation points [V-28]. Contribute `flood_prone=yes` upstream where verified, since Indian OSM mappers are active.

### 1.2 Commercial map APIs

| Provider | Price (India) | Key terms for FloodRoute | Tag |
|---|---|---|---|
| Google Routes API | Billed in INR if India-eligible. Compute Routes: Essentials $1.50/1k (70k free/mo), Pro $3.00/1k (35k free), Enterprise $4.50/1k (7k free). Drops to $0.38/$0.75/$1.14 above 5M. Maps tiles/dynamic maps priced separately. | No avoid-area or custom-edge-weight parameter in the docs I read. Routes content must be shown on a Google Map [V-5]. "No use with non-Google maps" clause [V-4 §19.2]. No scraping, pre-fetching or storing [V-3]. Lat/lng cacheable 30 days only [V-4]. Content cannot train/fine-tune ML models [V-3]. "High Risk Activities" (death/serious injury) are excluded from use [V-3]. A blog claims emergency dispatch routing is barred; not found in the terms text [U]. | [V-1] [V-2] |
| Ola Maps (Krutrim) | First 100k events/month free; then Directions ₹0.199/req (100k–5M), ₹0.049 above 5M; Geocoding ₹0.099 then ₹0.025. Prepaid credits from 2026-09-01. (Tier figures extracted by a summarising tool.) | Terms permit layering and combining your own content with Ola content for derived routes if origins stay distinguishable (cl. VIII). Prohibits use with ML/AI systems incl. "predictive analytics" (cl. XV), exposing Ola data to open-database licences (cl. IX), "high-risk government decision making" (cl. VII), and derivative works (cl. XIII). Requires compliance with DST 2021 guidelines and correct boundaries. Rate-limit blocks at 150k/day. | [V-6] [V-7] |
| Mappls (MapmyIndia) | Public pricing not retrievable (JS-only pages; quotes via sales). Advertises 120+ APIs incl. 14+ routing, telematics, on-prem deployment. | Caching/storage/overlay terms not found. Mappls has sued Ola over map-data copying, so assume strict terms. | [V-40] [V-42] [U on all else] |
| HERE | Traffic coverage lists India Central/North/South; Deduce partnership for Indian roads (HERE claims top-30 city coverage). | Best-documented flow/incident feed. Per-call price not verified. | [V-33] [U on pricing] |
| TomTom | Traffic service launched India 2012-era; market share small. | Thin probe density likely. | [U] |
| Bhuvan / Survey of India | CartoDEM: ≥30 m free download; 10 m at base price; licence is single-user, internal use, excludes internet hosting. SoI offers free admin-boundary shapefiles and a political map shapefile (1:4M). | CartoDEM licence bars serving it online, so use it for internal analysis only. | [V-27] [V-37] |

Recommendation: do not build the core on any of these. Use Ola or Google only for geocoding/autocomplete and, if licensed, for ETA calibration or a "no-flood baseline", never as the routing substrate.

## 2. Terrain and hydrology

| Dataset | Notes | Tag |
|---|---|---|
| Copernicus GLO-30 | 30 m, free, open on AWS (`copernicus-dem-30m`). Includes building/tree bias. | [V-25] |
| FABDEM | Buildings/forests removed from GLO-30 and ML-corrected. Licence CC BY-NC-SA 4.0, so commercial use needs a Fathom licence. Indian DGPS test RMSE: Dehradun 5.96 m, Jaipur 2.77 m, Kendrapara (alluvial plain) 4.29 m, too coarse for underpass-depth work. | [V-24] |
| MERIT Hydro (incl. HAND) | Dual licence CC-BY-NC 4.0 / ODbL 1.0; ODbL requires derived data be public. | [V-26] |
| CartoDEM / Bhuvan | See §1.2 licence limits. | [V-27] |
| SRTM, NASADEM | Public domain, ~30 m. | [U] |
| City LiDAR | Hyderabad "One Map Hyd" LiDAR over ~2,050 km² (GHMC to ORR) in progress; Bengaluru KSNDMC building 2 m contour maps with BDA; none confirmed open. | [V-32] [V-31] |
| Drain networks | Chennai ward-level drain base maps at 1:5,000 and flood-hazard/inundation points on opencity.in; Bengaluru SWD maps exist but experts say no complete public rajakaluve GIS; Mumbai has OneMCGM GIS but no confirmed open drain layer. | [V-28] [V-29] |
| Land cover/soil | ESA WorldCover (CC BY 4.0, via Overture attribution), Dynamic World, SoilGrids. | [V-21] [U on others] |
| Buildings | Google Open Buildings (CC BY 4.0), Microsoft ML (ODbL). | [V-21] |

**HAND feasibility.** HAND from 30 m DEMs works for river-fed and coastal flooding but is weak for pluvial (rain-on-pavement) flooding, which dominates Indian urban road failures. Flat metro terrain (Chennai, Kolkata, Mumbai coast) and DEM errors of 3–6 m exceed the micro-relief that decides whether an underpass floods. Treat HAND and a topographic wetness index as priors only. Segment risk should be driven by (a) known flood-point history, (b) structure type (underpass, low bridge, dip), (c) local depression depth from the best DEM available, (d) real-time rainfall and gauges (other research track), and (e) user and agency reports as ground truth. [U: my judgement, supported by the DEM accuracy findings above.]

## 3. Routing engines

| Capability | Valhalla | GraphHopper | OSRM | pgRouting / ORS |
|---|---|---|---|---|
| Per-request avoid areas | `exclude_polygons`, `exclude_locations` [V-12] | Custom model with GeoJSON `areas`, `priority multiply_by 0` [V-16] | `exclude` by road class only; no polygons [V-15] | pgRouting via SQL cost edits; ORS has avoid_polygons [U] |
| Live closures / speeds without graph rebuild | Yes: dynamic speeds in separate memory-mapped `traffic.tar` [V-13]; closures excluded by default, `ignore_closures` and `closure_factor` options [V-12] | Flexible mode only; custom models require `ch.disable` (slower) [V-16]. LM mode limits weight decreases [V-16] | CSV speed/turn-penalty file; MLD `osrm-customize` is the fast path (reported ~1 min North America) [V-14] [U on timing] | pgRouting: UPDATE cost columns; slow on large graphs [U] |
| Time-dependent | `date_time` types, predicted speeds [V-12] | Limited [U] | No | No [U] |
| Risk-aware (soft) cost | Scale speed in traffic tile; costing options per request | Priority multipliers per request/area | Edge duration/rate in CSV (`edge_rate`) [V-14] | Arbitrary SQL cost |
| Emergency profile | No dedicated profile in docs read; emulate with `auto`/`truck`/`taxi` plus `ignore_non_vehicular_restrictions`, `ignore_access` [V-12] | Custom profile via custom model [V-16] | Separate Lua profile means separate dataset [U] | Custom |
| Licence | MIT [U] | Apache 2.0 [U-supported by search] | BSD-2 [U] | GPL [U] |

- **CCH** (Customizable Contraction Hierarchies) gives the best theoretical fit for "weights change every few minutes": customization is "well below a second" in the original paper on continental road networks, with queries 2–4× faster than CRP. [V-17] RoutingKit implements it but offers no turn-by-turn, map matching or India-ready service layer, so it is a scale-up research option, not an MVP choice.
- Valhalla 2.5-minute-class refresh: write closure/speed changes straight into `traffic.tar` for the affected edge IDs. Hard closures set speed 0 or closure flag; soft risk lowers speed with a safety margin.
- **Vehicle-class depth thresholds** (hatchback ~15–20 cm, SUV, ambulance, bus): none of the engines natively models water depth. Encode as per-class traffic tiles or as a risk score → vehicle-specific penalty applied at query time. In Valhalla a pragmatic approach is a small number of vehicle-class "views": write one speed/closure overlay per class, or pass `exclude_polygons` for the vehicle-specific must-avoid set. [U: design suggestion.]
- **Probabilistic cost**: compute expected-delay cost = P(impassable at ETA-arrival time) × detour penalty, using predicted risk at arrival time (not now). Use time-dependent segment risk forecasts with a 0–3 h horizon, update the overlay every 5–15 min, and run a second pass with a risk-averse quantile for ambulances. [U: design.]
- **Latency and scale.** OSRM reports sub-millisecond to single-digit-ms on continental graphs with CH [U via search snippets]; MLD is ~5× slower per query but supports quick re-customization [U via snippet]. Valhalla and GraphHopper flexible mode typically run tens of ms per route [U]. Plan on benchmarking India-wide with a 1k-request/s load test before committing.
- **Self-host footprint** [U]: Geofabrik India extract is a few GB of PBF; Valhalla India tiles are tens of GB; a 8 vCPU / 32 GB VM is enough for a 3-city MVP, with replicas behind a load balancer for scale.
- **Map matching**: Valhalla's Meili and OSRM `match` both exist [U]. Use Valhalla Meili against the same graph to snap crowd reports and vehicle probes to the same edge IDs.

## 4. Tiles and rendering

- **Stack**: MapLibre GL (client) + PMTiles on object storage + Protomaps basemap. Protomaps' own calculator shows ~$11.45/month for 625k monthly sessions on Cloudflare R2/Workers versus $3,640 on Google Maps for equivalent traffic. [V-34] Use OpenFreeMap (free, no key, commercial allowed) as a zero-ops fallback for the demo. [V-35]
- **Offline**: PMTiles range-reads from a bundled/downloaded city file work in MapLibre Native and web service workers [U]; Organic Maps and OsmAnd offer OSM-based offline apps but cannot receive live risk overlays. For low-connectivity, ship a per-city PMTiles pack (~100–400 MB, EST) plus a compact risk-segment delta (GeoParquet/FlatGeobuf or protobuf) pushed over SMS-friendly small payloads, with last-known-risk shown with a "stale since HH:MM" label.
- **India-correct borders**: OSM follows "on the ground" control, which differs from India's legal depiction in Kashmir/Ladakh/Arunachal; the OSM community acknowledges the disagreement and openstreetmap.in serves custom Indian-boundary tiles. [V-20] The 2021 guidelines say SoI-published maps or SoI digital boundary data are the standard for political maps. [V-9 cl. xiii] Ola's terms also require correct external boundaries. [V-7] Action: strip OSM admin boundaries (admin_level 2–4) from the style and draw the SoI boundary layer, including coastline/EEZ-safe generalisation; legal review of every release.

## 5. Indian geospatial law

| Topic | Rule | Tag |
|---|---|---|
| 2021 DST Guidelines (15 Feb 2021) | No prior approval, clearance, or licence for collection, generation, dissemination, storage, publication or digitisation of geospatial data and maps within India; self-certification. | [V-9] |
| Accuracy threshold | 1 m horizontal and 3 m vertical. Finer data can be created/owned only by Indian entities and stored/processed in India; foreign or foreign-controlled entities may only license it for serving customers in India via APIs that do not let data pass through their servers; no resale. | [V-9 cl. iv, vii–ix] |
| Mobile mapping / street-view | Terrestrial mobile mapping and street-view surveys permitted only to Indian entities, regardless of accuracy. | [V-9 cl. vi(b)] |
| Negative list | A list of sensitive attributes (not areas) that cannot be marked on any map; DST to notify. There is explicitly no list of prohibited areas. | [V-9 cl. iii] |
| Boundaries | SoI boundary data is the standard for political maps. | [V-9 cl. xiii] |
| National Geospatial Policy 2022 | Notified 28 Dec 2022; liberalises access, replaces 2005 map policy, vision to 2035, creates GDPDC. DST describes it as a landmark democratisation in 2026. | [V-10] |
| Geospatial Information Regulation Bill 2016 | Draft proposed fines Rs 1–100 crore and up to 7 years for wrong depiction/unauthorised acquisition; drew heavy criticism; the 2021 guidelines replaced the licensing regime it sought to codify. Final status of the bill: not enacted, as I understand it. | [V-11] [U on status] |

Startup implications:
- Keep the entity Indian-owned and controlled, or fine-grained data (sub-metre LiDAR, mobile mapping) becomes licence-only. If foreign investment arrives, re-check this.
- Using Copernicus-class 30 m DEMs is below the threshold and unconstrained. A city LiDAR DEM with ≤3 m vertical accuracy must be stored on Indian servers (AWS ap-south-1 or equivalent). [V-9 cl. ix]
- Do your own field surveys (drone, dashcam) only through the Indian entity; do not outsource capture to a foreign vendor.
- Never publish a map or screenshot with a non-SoI boundary. Build a CI check on the style file.
- The "restricted vicinity" regime now sits in the negative-attribute list rather than area bans; monitor DST notifications. [V-9]

## 6. Spatial indexing and data engineering

**Primary key = road segment, not hex.** Flooding is a property of a linear asset and its low point; routing needs edge-level weights. H3 is an optional secondary aggregation index; under the ponytail-ultra dependency rule, skip it in the MVP and use a precomputed segment-to-grid-cell column in PostGIS instead. H3 res 9 averages 0.105 km², res 10 0.015 km². [V-36] Suggested scheme:

| Layer | Key | Store | Refresh |
|---|---|---|---|
| Static segment attributes (class, structure, lowest elevation, historical flood count, drain proximity) | stable segment ID (OSM way ID + node pair, or Overture GERS ID [V-21]) | PostGIS + GeoParquet snapshot | nightly/weekly |
| Rainfall nowcast/forecast grid | grid cell (H3 res 8–9 later) | Postgres table | 5–15 min |
| Segment risk score P(impassable at t+Δ), Δ ∈ {0, 30, 60, 120} min | segment ID | Postgres table → engine overlay | 5–15 min |
| User/agency reports and probe-derived speed drops | segment ID after map-matching | Postgres + stream | continuous |

Pipeline (EST latency): rainfall/gauge ingest → SQL scoring job on cron (precomputed segment-to-grid join; DuckDB only if analytics outgrow Postgres) → write only changed segments → patch Valhalla `traffic.tar` / GraphHopper custom areas / OSRM CSV → atomic reload. A 3-city MVP (~2–3 million segments) rescored in under a minute is plausible on one machine because the join is table lookups, not geometry. [U: estimate.] DuckDB spatial + GeoParquet is directly supported by Overture's tooling. [V-23]

**Incident feeds.** No India-wide DATEX II or GTFS-like incident standard was found. Practical inputs: your own report API (JSON, GeoJSON with segment ID and TTL), city control-room feeds by MoU (Bengaluru's ASTraM already tracks congestion every 15 min and ambulance delays >120 s [V-38]), and Google's closure information sharing with eight Indian cities (reported; not usable as a feed for you) [U]. Define an internal schema loosely modelled on DATEX II SituationRecord (location, cause, validity start/end, severity).

**Live probe data, what is realistic:**
- Google/Mappls/Ola traffic: not redistributable and not obtainable as raw probes under the terms read above [V-3] [V-7]. Use only inside their own routing/ETA response.
- HERE traffic: commercial feed with India coverage [V-33]; price needs a quote.
- Telematics fleets (logistics, school buses, ambulances under AIS-140 VLTD): the most realistic probe source for a startup; sign data-sharing MoUs with fleet operators and ambulance services (108/102). AIS-140 data access specifics [U].
- FASTag: IHMCL data monetisation is being designed and privacy concerns are documented; treat as not available to a startup in the MVP window [V-39].
- Own app users: opt-in anonymous location pings, the realistic day-one source. Privacy under DPDP Act 2023 needs consent flows [U].

## 7. Cost estimates (EST, INR at ~₹85–90/$, my arithmetic)

| Item | MVP (3 cities, pilot) | Scale-up (10+ cities, 100k+ MAU) |
|---|---|---|
| Routing (Valhalla, 2 AZ) | 1–2 VMs 8 vCPU/32 GB: ₹25–50k/mo | 6–12 VMs 16 vCPU: ₹2–5 lakh/mo |
| PostGIS (+ cron worker; Redis/queue only at scale) | ₹15–30k/mo | ₹1–3 lakh/mo |
| Tiles (PMTiles + CDN) | ₹1–5k/mo, anchored on [V-34] | ₹10–40k/mo |
| Geocoding/autocomplete (Ola or Google) | Within free tiers (Ola 100k free [V-6]) | ~₹0.1–0.2 per request; at 5M geocodes/mo ≈ ₹5 lakh using Ola list price [V-6] |
| Commercial routing API comparison | n/a | 10M routes/mo: Google Pro ≈ $18.75k (5M×$3/1k + 5M×$0.75/1k) [V-1, EST arithmetic]; Ola ≈ ₹12.2 lakh (4.9M×₹0.199 + 5M×₹0.049) [V-6, EST arithmetic] |
| Traffic probe licence (HERE/telematics) | ₹0 (own app + 1–2 fleets) | Quote needed [U] |
| Field survey of underpasses (per city) | ₹3–8 lakh | ₹1–2 crore total |
| **Total infra** | **≈ ₹50–100k/mo** | **≈ ₹5–12 lakh/mo** + data licences |

Note: Google's lower India pricing applies only to customers with India billing and primary usage. [V-2]

## 8. Recommendations

### (a) Recommended MVP stack and why
- **Graph**: India OSM extract (Geofabrik, [U]) plus FloodRoute's own segment-attribute table keyed by OSM way/node IDs; Overture only for cross-checking buildings/roads (ODbL kept separate).
- **Engine**: Valhalla, self-hosted, with `traffic.tar` overlay refreshed every 5–15 min, `exclude_polygons` for per-request avoid zones, Meili for map matching. Why: edge-level live closures with no rebuild [V-13], per-request polygons [V-12], MIT licence [U], and one engine for both citizen and emergency profiles.
- **Risk layer (ponytail ultra applied: fewest dependencies)**: one Postgres/PostGIS instance holding one segment table. Score in plain SQL on a cron (5–15 min); a rainfall grid joins by a precomputed segment-to-cell column. No Redis, Kafka, DuckDB or H3 library until a profiler or a real scale need says so. Upgrade path: H3 when multi-city aggregation is needed; DuckDB/GeoParquet for offline analytics only; Redis only if Postgres read latency measurably fails.
- **Terrain**: GLO-30 plus city LiDAR where official partners share it; no FABDEM in production without a licence.
- **Tiles**: MapLibre + Protomaps PMTiles on R2, SoI boundary layer, per-city offline packs.
- **Geocoding**: Ola Maps free tier, with the Ola ToS check on your risk-scoring use (see risks).
- **Probes**: own app plus 1–2 fleet/ambulance telematics MoUs.

### (b) Scale-up stack
Valhalla fleet behind a router with per-vehicle-class overlays, optional CCH/RoutingKit research track for sub-second weight refresh, a queue (Kafka or a managed equivalent) only once report/probe volume outgrows Postgres inserts (not before), HERE or negotiated fleet probes, Indian-region cloud only (to satisfy the finer-than-threshold storage rule), Mappls/Ola enterprise agreements for geocoding and ETA benchmarking, city MoUs for drain/LiDAR/gauge data, an automated boundary-compliance CI step.

### (c) Top 5 risks
1. **Licence conflicts**: Ola bars ML/AI and open-database mixing; Google bars non-Google maps, storage, ML training; OSM/Overture ODbL share-alike. Mixing sources wrongly can force disclosure or termination.
2. **Boundary depiction non-compliance**: OSM-derived tiles differ from India's legal depiction; penalties in the withdrawn 2016 draft show the political sensitivity, and platform terms demand compliance. [V-11] [V-7]
3. **Tagging/graph gaps**: low attribute completeness [V-19] and few flood tags [V-18] mean wrong "passable" decisions, a life-safety liability.
4. **Pluvial flood prediction skill at street scale** with 30 m DEMs and no drain network data [V-24] [V-29]; false negatives are dangerous and false positives erode trust.
5. **Life-safety liability and dependence on closed providers**: Google "High Risk Activities" exclusion [V-3], Ola's "high-risk government decision making" clause [V-7]; the emergency-vehicle use case needs contractual and disclaimer design.

### (d) Open questions
- Exact Mappls API pricing, caching, overlay and emergency-use terms (obtain written quote).
- Whether Ola's cl. XV "predictive analytics" ban covers a flood-risk model that merely consumes Ola geocodes (get written clarification or avoid).
- Which cities will share LiDAR, drain GIS, and gauge data, and under what licence/MoU?
- Are DST negative-list attributes relevant to flood-asset layers (for example drain outfalls near critical infrastructure)?
- Can ambulance services (108/102) share AIS-140 or app telematics in near real time?
- OSM ODbL boundary: is a segment-keyed risk table a collective or derivative database? Legal opinion needed.
- Benchmarks: Valhalla traffic-tile refresh time and latency on an India-wide graph; GraphHopper alternative under 1k rps.
- Whether FABDEM commercial licensing is worth the cost versus local LiDAR.

## Sources

1. https://developers.google.com/maps/billing-and-pricing/pricing-india
2. https://developers.google.com/maps/billing-and-pricing/india
3. https://cloud.google.com/maps-platform/terms
4. https://cloud.google.com/maps-platform/terms/maps-service-terms
5. https://developers.google.com/maps/documentation/routes/policies
6. https://maps.olakrutrim.com/pricing
7. https://maps.olakrutrim.com/legal-docs/terms-conditions-2026.pdf
8. https://maps.olakrutrim.com/krutrim/docs
9. https://dst.gov.in/sites/default/files/Final%20Approved%20Guidelines%20on%20Geospatial%20Data.pdf
10. https://dst.gov.in/national-geospatial-policy-2022-marked-landmark-reform-democratized-access-geospatial-data
11. https://www.gisresources.com/india-the-geospatial-information-regulation-bill-2016/
12. https://valhalla.github.io/valhalla/api/route/api-reference/
13. https://mapzen.com/blog/speed-tiles/
14. https://github.com/Project-OSRM/osrm-backend/wiki/Traffic
15. https://raw.githubusercontent.com/Project-OSRM/osrm-backend/master/docs/http.md
16. https://raw.githubusercontent.com/graphhopper/graphhopper/master/docs/core/custom-models.md
17. https://arxiv.org/pdf/1402.0402
18. https://wiki.openstreetmap.org/wiki/Key:flood_prone
19. https://heigit.org/openstreetmap-data-as-a-basis-for-routing-how-well-does-it-really-work/
20. https://community.openstreetmap.org/t/new-changes-to-disputed-areas-indian-claims-over-kashmir/92543 and https://wiki.openstreetmap.org/wiki/Border_policy
21. https://docs.overturemaps.org/attribution/
22. https://docs.overturemaps.org/schema/reference/transportation/segment/
23. https://docs.overturemaps.org/getting-data/
24. https://sciforum.net/paper/view/13368 (FABDEM India RMSE); https://zenodo.org/records/14511570 (FABDEM licence, via search)
25. https://registry.opendata.aws/copernicus-dem/
26. https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1
27. https://www.nrsc.gov.in/nrscnew/Dataproducts_Thematic_cartodem.php
28. https://data.opencity.in/dataset/chennai-flooding-data
29. https://data.opencity.in/dataset/bengaluru-stormwater-drains-maps/issues and https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fbengaluru%2Fexperts-want-govt-data-public-2080504
30. https://togethervcan.in/?p=4997
31. https://www.gisresources.com/karnataka-to-identify-flood-prone-areas-with-new-maps-and-geo-apps/ and https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fbengaluru%2Fbbmp-identifies-210-flood-prone-areas-across-bengaluru-844483.html
32. https://gisresources.com/hyderabad-cm-orders-lidar-survey-to-prevent-encroachments-on-water-bodies/ and https://therealtytoday.com/news/technology/telangana-government-implements-lidar-survey-for-detailed-one-map-hyd-project/
33. https://docs.here.com/traffic-api/docs/here-traffic-api-v7-coverage-information and https://www.autocarpro.in/news-national/here-tech-deduce-technologies-partner-to-provide-intelligent-mobility-solution-for-indian-roads-56254
34. https://docs.protomaps.com/deploy/cost
35. https://openfreemap.org
36. https://h3geo.org/docs/core-library/restable
37. https://onlinemaps.surveyofindia.gov.in/AboutPortal.aspx
38. https://www.deccanherald.com/india/karnataka/bengaluru/bengaluru-police-launch-astram-all-you-need-to-know-about-the-app-2849148
39. https://www.boomlive.in/decode/nhai-one-vehicle-one-fastag-toll-reform-or-privacy-red-flag-24192
40. https://about.mappls.com/api/
42. https://www.digit.in/news/apps/ola-electric-gets-legal-notice-from-mapmyindia-for-copying-data-for-its-own-map-service.html/amp/
