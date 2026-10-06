# FloodRoute: Hazard and Weather Data Sources for India

Research date: 2026-10-05. Tagging convention: **[V url]** means the claim was seen in a fetched or searched page at that URL during this research. **[U]** means recalled or inferred and not verified here. Several primary government sites (indiawris.gov.in, api.imd.gov.in/api_reference.html, IMD data-supply PDF, Bhuvan) returned errors or thin pages to the fetcher, so their endpoint-level details are marked [U] and must be confirmed by hand before engineering commitments.

## 0. Bottom line

1. **No public source observes road-level or street-level inundation at scale.** Everything open is rainfall (observed or forecast), river stage, or coarse alerts. FloodRoute's road-risk layer has to be built by joining rainfall and nowcasts with its own terrain, drainage and hotspot model. City hotspot lists and FloodRoute's own incident feedback supply the ground truth.
2. **Flash-flood timescales (30-120 min) are only met by four inputs:** IMD radar and nowcast (about 3 h horizon), dense city rain-gauge networks (KSNDMC 15-min, Chennai/Mumbai telemetry), SACHET alerts (minutes, but district polygons), and FloodRoute's own crowd and probe signals. Satellite rainfall is a 4 h to 14 h-latency backstop. SAR flood maps are for after-event validation.
3. **Licensing is the main day-1 hazard.** Hydromet data from IMD and CWC is under cost-recovery regimes, so "free to view" is not "free to redistribute in a commercial product". GODL-India datasets are explicitly commercial-friendly, but most live feeds are not published under GODL.
4. **Government infrastructure reliability is a real risk.** CWC's flood-forecast site was down for more than a week at the start of the 2026 monsoon **[V https://sandrp.in/2026/06/11/cwc-flood-forecast-website-failure-at-start-of-2026-monsoon-season/]**. Treat every official feed as best-effort and build redundancy.

---

## 1. IMD (India Meteorological Department, MoES)

| Source | What it provides | Resolution / latency | Access | Terms | FloodRoute use |
|---|---|---|---|---|---|
| **IMD API Management Platform** (api.imd.gov.in) | "Unified gateway" for real-time observations, forecasts, warnings, specialized bulletins; categories include city forecasts, nowcast, rainfall, marine, warnings **[V https://api.imd.gov.in/]** | Not stated on landing page | Account creation required **[V https://api.imd.gov.in/]**. Endpoint list sits on an api_reference page that returned 404 to the fetcher. | Licensing, rate limits, commercial terms **not visible** [U] | Primary candidate for official nowcast and warnings. Register on day 1 and read the terms. |
| **Station and district nowcast** (mausam.imd.gov.in) | District-wise and station-wise nowcast warnings, hosted per Met Centre **[V https://mausam.imd.gov.in/imd_latest/contents/stationwise-nowcast-warning_mc.php?id=35]**. SACHET items quote "Next 3 hours" validity **[V https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml]**. | About 3 h horizon, district/station level. Refresh interval about 3-hourly [U]. | Web pages (scrape) or the same warnings via SACHET CAP | Scraping IMD pages has unclear terms [U] | Trigger for "rain intensity about to spike" over a city. Too coarse for roads, so use as a prior. |
| **Doppler Weather Radar (DWR)** | 47 DWRs operating, 87% area coverage (Jan 2026) **[V https://moes.gov.in/sites/default/files/PIB2220209.pdf via search summary]**. A July 2026 summary says 50 **[V https://superkalam.com/current-affairs/24-07-2026/parliament-question-implementation-of-mission-mausam-b5c020f2-c126-4825-841c-28cd79701157]**. Plan: 73 by 2025-26 and 126 under Mission Mausam, with X-band additions in Pune, Kolkata, the North-East and other places **[V https://www.impriindia.com/?p=64563]**. | C-band ~250 km range, 10-min scans [U]. | IMD publishes radar imagery per station page, e.g. Mumbai **[V https://mausam.imd.gov.in/mumbai/index_radar.php]**. Raw volumetric data requires a data request [U]. | Imagery on a public site is not licensed for redistribution [U] | The best 30-120 min rain signal. Scraping composites is brittle, so pursue an official feed. |
| **Mumbai urban X-band radar network** | Four X-band polarimetric radars (Panvel, Vasai-Virar, Vile Parle, Kalyan-Dombivli), dedicated 14 Sep 2024 **[V https://tropmet.res.in/other-pdfs/Press-release-MESONET-14Sept2024.pdf via search summary]** | High-res, minutes [U] | IITM/MoES. No public API seen. | MoU-only [U] | Mumbai-specific MoU target. |
| **AWS / ARG network** | About 1,008-1,083 AWS **[V https://www.thehitavada.com//Encyc/2025/8/31/mission-mausam.html]**. ARG count was 1,382 in 2023 **[V https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/jan/doc2025114485401.pdf via search summary]**. About 200 more Agro-AWS planned in 2026. 50 AWS each planned in 2026 for Delhi, Mumbai, Chennai, Pune **[V same hitavada/PIB results]**. | Hourly or sub-hourly, near real time [U]. National density is about one per ~2,000 sq km, far too sparse for urban flash floods. | Public IMD pages and the API platform | Unclear | Calibration anchor for satellite and radar rain. The planned urban AWS will help from 2027 monsoon. |
| **Gridded rainfall** | 0.25 deg daily gridded rainfall, 1901-present, with a provisional real-time daily product **[V https://imdlib.readthedocs.io/en/latest/Usage.html and https://cran.r-universe.dev/imdR/doc/imdR-introduction.html]** | 0.25 deg (~25 km), daily, revised later | Download via imdlib (Python) or imdR from IMD Pune | Research-oriented. Commercial redistribution unclear [U]. | Antecedent-wetness index only. Not for flash floods. |
| **NWP (NCUM, GFS, WRF)** | NCMRWF/IMD models feed IFLOWS-Mumbai **[V https://www.drishtiias.com/daily-updates/daily-news-analysis/iflows-mumbai-flood-warning-system/print_manually]** | NCUM about 12 km global, city WRF about 1-3 km [U] | NCMRWF data via request [U]. Open GFS from NOAA is free. | GFS is public domain [U] | Use GFS/ECMWF open data for 6-72 h outlook. Treat IMD NWP as an MoU upgrade. |
| **Apps (Mausam, Meghdoot, Damini, UMANG)** | Consumer apps for forecasts, agromet advisories, lightning **[V https://mausam.imd.gov.in/imd_latest/contents/stationwise-nowcast-warning_mc.php?id=35 search summary]** | n/a | No documented public API | Reverse-engineering apps is a legal and stability risk | Competitors and channels, not data sources. |
| **Historical station data** | Hourly, daily, monthly and extreme-value data from NDC Pune, chargeable. GST of 18% added. Registration at dsp.imdpune.gov.in **[V https://mausam.imd.gov.in/patna/mcdata/Data_Supply_Procedure(ENGLISH).pdf via search summary]** | Station | Paid request form | Commercial users pay | Buy for model training in launch cities. Budget needed. |

**Key point on IMD:** the official channel for commercial products is paid or MoU-based. The api.imd.gov.in platform is new and promising but its commercial terms are unconfirmed.

---

## 2. CWC and India-WRIS (rivers)

| Item | Detail |
|---|---|
| Network | 1,543 hydrological observation stations and 360 flood-forecast stations (201 level, 159 inflow) across 20 basins in 27 states/UTs, per a CWC presentation of 2 May 2026 **[V https://sandrp.in/2026/06/11/cwc-flood-forecast-website-failure-at-start-of-2026-monsoon-season/]** |
| Portals | FF site ffs.india-water.gov.in, C-Floods inundation portal inf.cwc.gov.in (listed only three rivers), 7-day advisory aff.india-water.gov.in (stale April 2026 content in June), nwic.gov.in (down on 11 Jun 2026) **[V same SANDRP article]** |
| Reliability | FF site down from about 5 June to 10 June 2026, then slow, with incomplete inflow/outflow data **[V same]**. Incorrect HFL value reported on 26 May 2026. |
| India-WRIS | Dashboards for rainfall, river level/discharge, reservoirs, groundwater, soil moisture. Excel/graph downloads **[V https://affairscloud.com/ministry-of-jal-shakti-launched-a-new-version-of-the-india-water-resources-information-system]**. A semi-automated API is reported in secondary sources **[V search summary only; endpoints not verified]**. The portal returned HTTP 503 to the fetcher. |
| Data policy | Hydro-Met Data Dissemination Policy 2013: Indian non-commercial users get classified hydro data free. **Indian commercial and foreign users pay Rs 75,000 per site per year** for classified data. Region-III data is unclassified, and reservoir levels, water quality, groundwater and meteorological data are unclassified for all regions **[V https://cwc.gov.in/sites/default/files/hddp2013.pdf via search summary]**. Whether the policy has been revised since 2013 is unknown [U]. |
| SACHET | CWC flood alerts ("Severe flood situation" river updates) appear in the national CAP feed **[V rss_india.xml]** |

**Use:** riverine and tank/lake backwater context for cities on rivers (Mithi, Adyar/Cooum, Yamuna, Brahmaputra tributaries). Not useful for pluvial street flooding. Stage data comes at hourly or slower cadence and the portal is unreliable at the worst moments, so cache aggressively and never make routing depend on it.

---

## 3. NDMA, SACHET and state portals

| Item | Detail |
|---|---|
| What | National CAP 1.2 alert platform built by C-DOT for NDMA, aggregating IMD, CWC, INCOIS, GSI, SDMAs, FSI, DGRE **[V https://thejeshgn.com/2025/05/28/common-alerting-protocol-cap-in-the-indian-context/]** |
| Access | **Public RSS feeds at country and state level.** Country feed is https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml. State feeds follow a `rss_<state>.xml` pattern. Each item links to a CAP 1.2 XML via `.../FetchXMLFile?identifier=...` **[V https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml and thejeshgn post]** |
| Observed behaviour | Fetch on 2026-10-05 returned 100 items, newest 19:48 GMT on 5 Oct 2026. Issuers included IMD regional centres, Andhra Pradesh SDMA and CWC. Languages: English, Hindi, Telugu, Marathi, Bengali, Kannada, Malayalam, Odia. Category "Met". Typical text: "Next 3 hours", thunderstorm, "Wind speeds 30-60 kmph" **[V same]** |
| Limits | District-level polygons only, no lat/lon point query, no CORS (needs a server-side proxy) **[V thejeshgn]**. Polygon coordinates are lat,lon, so swap for GeoJSON. |
| Terms | No licence statement found. Treat as public-interest data with attribution, and confirm with NDMA for commercial redistribution [U]. |
| State portals | State SDMAs (KSDMA, ASDMA, OSDMA etc.) publish alerts through SACHET. Assam's FRIMS is a damage-reporting app built by ASDMA with UNICEF, with no public API found **[V https://sentinelassam.com/cities/guwahati-city/flood-reporting-system-goes-digital-in-assam-537584 search summary]**. Kerala added 51 AWS in 2026 for KSDMA with data sharing planned **[V https://www.onmanorama.com/news/kerala/2026/08/15/kerala-adds-51-automatic-weather-stations-to-boost-real-time-disaster-monitoring.html]**. |

**Use:** SACHET is the one free, structured, official, near-real-time feed that works on day 1. Poll every 1-2 minutes, parse CAP, map polygons to FloodRoute risk zones, and use it as an escalation multiplier and as the alert to push to users. It is not a road-risk signal by itself.

---

## 4. NRSC / ISRO (Bhuvan, NDEM, Bhoonidhi)

- NRSC is mandated to map flood inundation in near real time using optical and SAR from national and international satellites, and has done so since 1995. Products go to MHA, NDMA, SDMAs and state remote sensing centres through NDEM and Bhuvan **[V https://www.nrsc.gov.in/sites/default/files/pdf/DMSP/SatelliteBasedAnalysis_FloodMappingandMonitoringinUP_30112022.pdf via search summary]**.
- Flood Hazard Zonation Atlases exist for Assam (updated with 1998-2023 data), Bihar, Odisha, West Bengal and Andhra Pradesh, and UP is in progress **[V https://www.nrsc.gov.in/nrscnew/assets/pdf/Flood_Hazard_Zonation_Atlas_of_Assam_using_multi_sensor_satellite_data1998_2023.pdf]**.
- Access: Bhuvan viewing is public. NDEM is restricted to government users. Whether Bhuvan flood layers offer WMS/WFS for commercial reuse is unverified [U]. Bhoonidhi (satellite data archive) needs registration [U].
- Resolution and latency: event-driven, hours to days after acquisition. Coverage is riverine and floodplain-focused, not urban.
- **Use:** static hazard prior for riverine states and an after-event label source. Not a nowcasting input.

---

## 5. Global and open sources

| Source | Resolution / latency | Access and terms | Verdict for FloodRoute |
|---|---|---|---|
| **NASA GPM IMERG** | 0.1 deg (~10 km), 30-min. Early about 4 h, Late about 12-14 h, Final about 2.5 months **[V https://gpm.nasa.gov/data/imerg]** (page dated 2020, so recheck current version/latency) | PPS GeoTIFF/FTP needs free registration. Earthdata for Giovanni **[V same]**. NASA data is open [U]. | Best free satellite rain backstop. 4 h latency is useless for tracking a 60-min cell but good for accumulations and gauge bias-correction. |
| **JAXA GSMaP NRT** | 0.1 deg, hourly, 4 h latency **[V https://www.cpc.ncep.noaa.gov/products/janowiak/gsmap_description.html]** | Free registration with JAXA [U] | Second satellite rain source for cross-check. |
| **ERA5 / ERA5-Land** | ERA5T about 5 days latency. ERA5-Land 9 km **[V https://climate.copernicus.eu/key-update-climate-dataset-brings-data-five-days-behind-real-time; https://www.ecmwf.int/en/era5-land]** | Copernicus licence replaced by **CC-BY 4.0 on 2 July 2025**, attribution required, commercial use allowed **[V https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464]** | Historical climatology and soil-moisture training features. Not real time. |
| **Open-Meteo** | Aggregates ECMWF, NOAA, DWD, JMA and others. Highest-res coverage is Europe and North America. **No IMD model listed** **[V https://open-meteo.com/en/features#terms]** | Free for non-commercial use. Commercial use needs a paid plan. | Cheap forecast API for prototyping. Commercial use needs the paid plan from the start. |
| **MET Norway Locationforecast** (api.met.no) | Point-forecast NWP (Locationforecast 2.0 compact JSON), hourly series, 6-72 h lead. Global coverage driven by ECMWF/MEPS. Refreshes every 1-3 h. | Free under **CC BY 4.0** and **NLOD 2.0** (Norwegian Licence for Open Government Data). Commercial use explicitly permitted with attribution ("Data from MET Norway"). Technical terms: mandatory identifying User-Agent with contact URL/email, max 20 req/s rate limit, coordinates truncated to <= 4 decimals (5+ returns 403), strict Expires header caching. | **Primary operational forecast feed.** Zero API fees, open commercial licence, no GRIB2 binary decoding overhead. Validated and live in FloodRoute scoring pipeline. |
| **GloFAS (Copernicus)** | v4.0 at 0.05 deg (~5 km), probabilistic river discharge **[V https://civil-protection-knowledge-network.europa.eu/stories/copernicus-emergencys-upgraded-early-warning-system-floods]** | Free, via the CEMS Early Warning Data Store under CC-BY **[V ECMWF forum post above]** | Large-river context only. Not urban. |
| **Copernicus GFM (Sentinel-1)** | Flood maps typically within 5 h of acquisition, all scenes processed within 8 h. Global revisit 3-14 days **[V https://global-flood.emergency.copernicus.eu/news/223-gfm-now-includes-data-from-sentinel-1c/ and https://european-flood.emergency.copernicus.eu/sites/default/files/2021-10/2021_CEMS_GFM_Introduction.pdf]**. SAR performs poorly in dense urban areas and under canopy **[V https://un-spider.org/node/13456 search summary]** | Free | Post-event validation and floodplain mapping. Not a live urban signal. |
| **Google Flood Hub / Floods API** | Riverine forecasts covering India with CWC partnership **[V https://www.moneylife.in/article/google-flood-forecasting-system-now-live-in-entire-india/65581.html]**. Over 100 countries, 700M people, 7-day lead **[V https://blog.google/innovation-and-ai/products/expanding-flood-forecasting-coverage-helping-partners/]**. **Urban flash flood product (Groundsource), announced March 2026: 24 h lead, 20x20 km grid, population density over 100/sq km, no flood depth or street-level forecasts, rural excluded** **[V https://research.google/blog/protecting-cities-with-ai-driven-flash-flood-forecasting/]**. | API was a waitlist pilot **[V Google blog]**. Terms and pricing not published there. India-specific urban coverage is unconfirmed. | Useful as a 24 h city-level prior. At 20 km it cannot discriminate roads. Apply for API access early. |
| **Microsoft Planetary Computer** | Hosts Sentinel-1/2, ERA5, DEMs (Copernicus DEM, NASADEM) [U] | Free STAC access [U] | Convenient for DEM, HAND and land-cover pipelines. |

---

## 6. City-level systems

| City | What exists | Access reality |
|---|---|---|
| **Mumbai** | IFLOWS-Mumbai (MoES with MCGM): 7 modules, 165-station rain gauge network from IITM/BMC/IMD, 6-72 h flood-prone area forecasts plus 3-6 h nowcast, ward-level info **[V https://www.drishtiias.com/daily-updates/daily-news-analysis/iflows-mumbai-flood-warning-system/print_manually]**. X-band radar network (above). BMC counts rose to 498 waterlogging spots (+10%) with 547 dewatering pumps **[V https://www.freepressjournal.in/amp/mumbai/bmc-boosts-dewatering-pumps-to-547-mithi-river-desilting-pending-as-waterlogging-spots-rise-10]**. A BMC list of 386 flooding spots with works at 312 also appears in coverage. | MoU-only for IFLOWS feeds [U]. Hotspot lists are obtainable from BMC disclosures and news. |
| **Chennai** | RTFF & SDSS operational since October 2025, about Rs 107 crore, 4,974 sq km, ARGs, AWS, water-level recorders and gate sensors for Adyar, Cooum, Kosasthalaiyar and Kovalam basins **[V https://currentaffairs.adda247.com/chennai-becomes-first-city-to-launch-real-time-flood-forecasting-system/ via search summary]**. GCC lists 859 waterlogging-prone areas, 306 severe **[V https://citizenmatters.in/how-is-chennai-preparing-to-tackle-the-rains search summary]**. ICCC command centre. NCCR developed ward-level flood warning **[V https://thewire.in/environment/nccr-develops-warning-system-for-flooding-in-chennai-with-ward-level-detail]**. | Best-instrumented city. A GCC/TNSDMA MoU is the highest-value pilot target. |
| **Bengaluru** | KSNDMC: solar/GPRS telemetric rain gauges at all 5,625 gram panchayats (every ~25 sq km) and weather stations at all 747 hoblis (~250 sq km), data every 15 min, includes rainfall intensity **[V https://ksndmc.org/en/Activities/Weather]**. BBMP: 210 flood-prone areas, 166 resolved by May 2025. Traffic police: 113 waterlogging spots **[V https://www.theweek.in/wire-updates/national/2025/05/26/mes18-ka-flood-bbmp.html search summary]**. | KSNDMC offers public viewing and SMS alert subscription **[V https://ksndmc.org/en/Home/Subscribe]**. Bulk or API redistribution needs agreement [U]. Gauge density within the city is the best of any state. |
| **Hyderabad** | TSDPS publishes daily weather data from 584-589 stations, with 2018-2025 datasets on AIKosh under the Open Government License, and a listing describing them as non-commercial **[V https://aikosh.indiaai.gov.in/home/datasets/details/telangana_weather_data_2023_2025.html]**. 141 identified waterlogging points **[V https://www.siasat.com/after-rains-splash-hyderabad-hydraa-chief-inspects-flood-prone-areas-3226325/ search summary]**. HYDRAA/GHMC/DRF coordinate response. | Daily historical data is open. Real-time feed is unverified [U]. Licence wording conflicts (OGL vs non-commercial), so ask. |
| **Delhi** | PWD flood control room with a helpline and WhatsApp bot. 45 prone locations under 179 CCTV cameras. 448 hotspots mapped from traffic police data for 2023-2025. 167 pump houses, 11 fully automatic with sensors. 71 points with coordination issues between PWD and MCD **[V https://www.theweek.in/wire-updates/national/2025/06/19/des66-dl-pwd-waterlogging.html and https://dailypioneer.com/news/4-waterlogging-hotspot-underpasses-stay-open-amid-rain-pwd-minister-reviews-operations]**. 50 new IMD AWS planned in 2026. | Hotspot lists are semi-public. CCTV and sensor streams are MoU-only. |
| **Kerala** | About 150 IMD AWS/rain gauges plus 51 new KSDMA AWS (2026) **[V https://www.onmanorama.com/news/kerala/2026/08/15/kerala-adds-51-automatic-weather-stations-to-boost-real-time-disaster-monitoring.html]**. | Data sharing with agencies is planned. |
| **Assam** | FRIMS for impact reporting. Daily reporting window 15 May-15 Oct **[V https://affairscloud.com/assam-became-the-1st-indian-state-to-adopt-an-online-flood-reporting-system]**. | No public API found. |

---

## 7. Crowd, IoT and private sources

| Source | Notes |
|---|---|
| **Smart City ICCC sensors and CCTV** | Chennai ICCC receives flood and waterlogging alerts. Delhi PWD watches 45 sites with 179 CCTVs. These are municipal assets and access is MoU-only. CCTV-based water detection is a strong later-stage signal [U]. |
| **Skymet** | Reported 6,500+ and later 7,500+ AWS across India, funded by long-term state contracts **[V https://agfundernews.com/india-skymet-raises-series-c and search summary]**. Commercial data licence only. A realistic paid fallback for ground truth. |
| **Vehicle probe speed data** | Not verified here. Likely sources: Google/TomTom/HERE/Mappls (MapmyIndia) via commercial licence, fleet telematics via partnerships [U]. Probe-speed drops are the best direct road-impact signal and an essential validation label. |
| **FloodRoute own crowd reports** | App users flagging blocked roads, plus ambulance and fire GPS traces. Cold-start problem in new cities. |
| **Weather-hobbyist networks** | Weather Underground/Netatmo style PWS coverage in India is thin [U]. Low priority. |

---

## 8. Historical waterlogging hotspot lists

| City | Published figure | Source |
|---|---|---|
| Mumbai | 386 (BMC) to 498 spots, with 200 listed by traffic police in earlier years | [V FPJ links above; https://togethervcan.in/?p=4997] |
| Chennai | 859 prone, 306 severe | [V citizenmatters search summary] |
| Delhi | 448 mapped hotspots (traffic police data), 45 under CCTV | [V theweek / dailypioneer] |
| Bengaluru | 210 flood-prone (BBMP), 113 (traffic police) | [V theweek / deccanherald search summary] |
| Hyderabad | 141 points | [V siasat/deccanherald search summary] |

Most lists are PDF, news or RTI outputs, not machine-readable. Expect manual geocoding of each list. Lists are biased to known chronic spots and under-represent newly built corridors. They are best used as model priors and for validation, and to seed alert zones.

---

## 9. What is realistic on day 1 vs after MoU

| Capability | Day 1 (no MoU) | After MoU |
|---|---|---|
| Rain nowcast | SACHET CAP, IMD API platform (if terms allow), scraped radar imagery (legally grey), IMERG/GSMaP | Direct DWR/X-band volumetric data, IMD city WRF |
| Gauges | KSNDMC public view, TSDPS daily, IMD pages, Skymet (paid) | Municipal telemetry (Chennai, Mumbai IFLOWS, GHMC) at 5-15 min |
| Rivers | Public CWC/India-WRIS views and bulletins (cache, don't redistribute) | CWC feed and classified-site data under the policy fee |
| Inundation truth | Sentinel-1 GFM, user reports, probe speeds | NRSC NDEM maps, CCTV, underpass sensors |
| Hotspots | Published and news-based lists | Traffic police and municipal GIS layers |

**Latency vs flash-flood timescale (30-120 min):**
- Under 15 min: municipal telemetry (KSNDMC 15-min; sensors), user reports, probe speeds.
- 15-60 min: IMD radar and SACHET CAP issued as "Next 3 hours" alerts.
- 3-14 h: IMERG Early/Late, GSMaP NRT, GFM SAR.
- 24 h or more: Google urban flash flood (20 km), GloFAS, NWP.

---

## 10. Recommendation

### (a) Ranked MVP data stack

1. **SACHET CAP feeds** (national plus state), free, structured, and live now. Escalation and user-alert trigger.
2. **IMD API platform and nowcast pages**, with registration done immediately and terms read. Primary official nowcast. Fall back to SACHET if terms block commercial use.
3. **Open NWP (GFS and ECMWF open data, with Open-Meteo paid tier for convenience)** for 6-72 h outlook.
4. **IMERG Early plus GSMaP NRT**, gauge-bias-corrected where gauges exist, for accumulation and antecedent wetness.
5. **City gauges via the fastest MoU or public view:** KSNDMC (Bengaluru), then Chennai GCC/TNSDMA, then Mumbai IFLOWS/BMC, then TSDPS (Hyderabad).
6. **FloodRoute terrain and drainage model** (Copernicus DEM, OSM roads/underpasses, land cover from Planetary Computer) combined with **city hotspot lists** as priors.
7. **FloodRoute crowd reports and probe speeds** as the feedback and calibration loop.
8. **Google Flood Hub/Floods API** (apply to the waitlist) and **GloFAS** for riverine context. **Sentinel-1 GFM** for post-event labels only.

### (b) Top 5 risks and gaps

1. **No street-scale ground truth.** Satellite and gauge data cannot say which road is underwater. Without probe or crowd data the model is rainfall-to-hotspot lookup only.
2. **Licensing and redistribution.** IMD data is chargeable for commercial use (plus 18% GST). CWC charges commercial users Rs 75,000 per site per year for classified data. IMD API, SACHET and radar imagery terms are unconfirmed.
3. **Official infrastructure fragility.** CWC FF, C-Floods and NWIC failed or lagged at the start of the 2026 monsoon. Expect outages in peak events.
4. **Latency and sparsity vs 30-120 min events.** Satellite products lag 4-14 h. National AWS density is far too low. Only a few cities (Bengaluru, Chennai, Mumbai) have dense telemetry, and radar is not equal in coverage everywhere.
5. **Coverage unevenness.** Tier-2/3 cities, the North-East and hill states have weak gauges and radar. Google's urban product is 20 km and skips rural areas. SAR is weak in dense urban cores.

### (c) Open questions

1. What are the exact commercial terms, endpoints, rate limits and refresh cadence of api.imd.gov.in? Does it expose radar composites or point nowcasts?
2. Can SACHET data be redistributed commercially, and does NDMA offer a partner API with point-in-polygon queries?
3. Does the CWC/India-WRIS API exist as a documented public endpoint, and is the 2013 policy fee still current?
4. Is Google's urban flash flood forecast live for Indian cities, and what are the Floods API terms and pricing?
5. Who owns IFLOWS-Mumbai and Chennai RTFF data (MoES, IITM, NCCR, municipal bodies), and what is the MoU path and timeline?
6. Is the KSNDMC real-time feed available as an API, and under what licence?
7. What vehicle-probe vendor gives India road-level speeds at acceptable cost and redistribution rights?
8. What are the legal constraints on scraping IMD radar imagery and station pages?
9. What data-protection and procurement rules apply to ambulance, fire and NDRF operational integration?

---

## Sources

- IMD API platform: https://api.imd.gov.in/
- IMD station-wise nowcast example: https://mausam.imd.gov.in/imd_latest/contents/stationwise-nowcast-warning_mc.php?id=35
- IMD Mumbai radar page: https://mausam.imd.gov.in/mumbai/index_radar.php
- IMD data supply procedure: https://mausam.imd.gov.in/patna/mcdata/Data_Supply_Procedure(ENGLISH).pdf
- Mission Mausam DWR summary: https://superkalam.com/current-affairs/24-07-2026/parliament-question-implementation-of-mission-mausam-b5c020f2-c126-4825-841c-28cd79701157
- MoES PIB (DWR coverage): https://moes.gov.in/sites/default/files/PIB2220209.pdf
- AWS/Mission Mausam: https://www.thehitavada.com//Encyc/2025/8/31/mission-mausam.html
- PIB 2025 document (ARG counts): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/jan/doc2025114485401.pdf
- IITM Mumbai urban radar press release: https://tropmet.res.in/other-pdfs/Press-release-MESONET-14Sept2024.pdf
- imdlib docs: https://imdlib.readthedocs.io/en/latest/Usage.html
- imdR: https://cran.r-universe.dev/imdR/doc/imdR-introduction.html
- SANDRP on CWC site failure: https://sandrp.in/2026/06/11/cwc-flood-forecast-website-failure-at-start-of-2026-monsoon-season/
- CWC Hydromet Data Dissemination Policy 2013: https://cwc.gov.in/sites/default/files/hddp2013.pdf
- India-WRIS launch coverage: https://affairscloud.com/ministry-of-jal-shakti-launched-a-new-version-of-the-india-water-resources-information-system
- SACHET national RSS: https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml
- SACHET in the Indian context: https://thejeshgn.com/2025/05/28/common-alerting-protocol-cap-in-the-indian-context/
- NRSC flood mapping UP: https://www.nrsc.gov.in/sites/default/files/pdf/DMSP/SatelliteBasedAnalysis_FloodMappingandMonitoringinUP_30112022.pdf
- NRSC Assam atlas: https://www.nrsc.gov.in/nrscnew/assets/pdf/Flood_Hazard_Zonation_Atlas_of_Assam_using_multi_sensor_satellite_data1998_2023.pdf
- NASA IMERG: https://gpm.nasa.gov/data/imerg
- GSMaP description: https://www.cpc.ncep.noaa.gov/products/janowiak/gsmap_description.html
- ERA5T latency: https://climate.copernicus.eu/key-update-climate-dataset-brings-data-five-days-behind-real-time
- ERA5-Land: https://www.ecmwf.int/en/era5-land
- Copernicus CC-BY switch: https://forum.ecmwf.int/t/cc-by-licence-to-replace-licence-to-use-copernicus-products-on-02-july-2025/13464
- Open-Meteo: https://open-meteo.com/en/features#terms
- GloFAS upgrade: https://civil-protection-knowledge-network.europa.eu/stories/copernicus-emergencys-upgraded-early-warning-system-floods
- Copernicus GFM: https://global-flood.emergency.copernicus.eu/news/223-gfm-now-includes-data-from-sentinel-1c/ ; https://european-flood.emergency.copernicus.eu/sites/default/files/2021-10/2021_CEMS_GFM_Introduction.pdf
- UN-SPIDER flood mapping: https://un-spider.org/node/13456
- Google flood expansion: https://blog.google/innovation-and-ai/products/expanding-flood-forecasting-coverage-helping-partners/
- Google urban flash flood: https://research.google/blog/protecting-cities-with-ai-driven-flash-flood-forecasting/
- Google India coverage: https://www.moneylife.in/article/google-flood-forecasting-system-now-live-in-entire-india/65581.html
- IFLOWS-Mumbai: https://www.drishtiias.com/daily-updates/daily-news-analysis/iflows-mumbai-flood-warning-system/print_manually
- BMC waterlogging spots: https://www.freepressjournal.in/amp/mumbai/bmc-boosts-dewatering-pumps-to-547-mithi-river-desilting-pending-as-waterlogging-spots-rise-10
- Chennai RTFF: https://currentaffairs.adda247.com/chennai-becomes-first-city-to-launch-real-time-flood-forecasting-system/
- Chennai NCCR: https://thewire.in/environment/nccr-develops-warning-system-for-flooding-in-chennai-with-ward-level-detail
- Chennai preparations: https://citizenmatters.in/how-is-chennai-preparing-to-tackle-the-rains
- KSNDMC weather: https://ksndmc.org/en/Activities/Weather ; https://ksndmc.org/en/Home/Subscribe
- Bengaluru flood-prone areas: https://www.theweek.in/wire-updates/national/2025/05/26/mes18-ka-flood-bbmp.html
- TSDPS data on AIKosh: https://aikosh.indiaai.gov.in/home/datasets/details/telangana_weather_data_2023_2025.html
- Delhi PWD: https://www.theweek.in/wire-updates/national/2025/06/19/des66-dl-pwd-waterlogging.html ; https://dailypioneer.com/news/4-waterlogging-hotspot-underpasses-stay-open-amid-rain-pwd-minister-reviews-operations
- Kerala AWS: https://www.onmanorama.com/news/kerala/2026/08/15/kerala-adds-51-automatic-weather-stations-to-boost-real-time-disaster-monitoring.html
- Assam FRIMS: https://affairscloud.com/assam-became-the-1st-indian-state-to-adopt-an-online-flood-reporting-system
- Skymet: https://agfundernews.com/india-skymet-raises-series-c
- GODL-India / NDSAP overview: https://en.wikipedia.org/wiki/National_Data_Sharing_and_Accessibility_Policy
