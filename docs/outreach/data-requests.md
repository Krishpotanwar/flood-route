# Data requests (drafts)

Draft v0.1, 2026-10-05. Five requests, 5a to 5e. **Nothing has been sent, registered or submitted.** The founder reviews, fills the [BRACKETS], and sends from a named person on company letterhead. Counsel reads every ask that touches redistribution or derived outputs (5a items 1 and 3, 5b, 5d item 4, 5e) before it goes. Not legal advice.

**Tags.** **[V url]** = I opened that official page this session. **[U]** = unverified: *secondary* = a news, vendor or community page I opened, *snippet* = search-result text only. URLs are written without `https://`. Contact details appear only where an official page showed them. Where it did not, the line says so and holds a [PLACEHOLDER].

## Before any of these goes out

- Attach a one-page concept note [PLACEHOLDER: founder writes it; the outline is in outreach-templates.md]. It must say pre-product, and must not state accuracy, partners, pilots or recognition we do not have.
- Sender block: [FOUNDER NAME], [DESIGNATION], [COMPANY LEGAL NAME], [CIN or "incorporation in progress"], [DPIIT recognition number, only if issued], [ADDRESS], [PHONE], [EMAIL].
- Standing commitments, repeated in each letter only if the founder agrees: follow the owner's terms, credit the owner, no scraping while a request is open, use data only for the stated purpose, store it in India, never imply endorsement, report corrections.
- Keep a log: date sent, to whom, reply, next step. Mirror results into data-terms-tracker.md.
- Accept a "no" politely. Do not ask a second office to get around the first.

---

## 5a. NDMA and C-DOT: SACHET partner CAP feed

**Who to address.**
- NDMA. The SACHET footer lists NDMA Control Room, NDMA Bhawan A-1, Safdarjung Enclave, New Delhi 110029; phone +91-11-26701728; email controlroom[at]ndma[dot]gov[dot]in (write it with @ and a dot when sending); fax +91-11-26701729 [V sachet.ndma.gov.in]. ndma.gov.in itself returned HTTP 503 to the fetcher, so no officer or division could be confirmed. **First step: phone or email the Control Room and ask which officer handles access to SACHET data by private parties.** A search result points to a Joint Advisor (IT and Communication) as a possible owner [U snippet]. Officer: [PLACEHOLDER].
- C-DOT, which builds and runs SACHET [V sachet.ndma.gov.in]. C-DOT Campus, Mehrauli, New Delhi 110030; email cdotweb[at]cdot[dot]in; Delhi +91-11-26598262 or 26802856; Bengaluru campus, Electronics City Phase 1, Bengaluru 560100, +91-80-28520050 [V cdot.in/home.htm]. C-DOT's own pamphlet lists a "CAP Alert Feed Generator" and a "Customised Dissemination Media Interface" [V cdot.in/cdotweb/assets/docs/products/dms/cap.pdf]. The contact page URL returned 404, so use the home-page email and phones. Officer: [PLACEHOLDER].

**What we already know.** The RSS channel says copyright "public domain" [V sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml]. The Website Policy states no copyright or commercial-use terms [V sachet.ndma.gov.in/WebsitePolicy]. Agencies must use ETag caching [V sachet.ndma.gov.in/docs/Integration_Guide_For_Agencies.pdf]. No API, key or registration page was seen. Feeds exist per state, for example Karnataka [V sachet.ndma.gov.in/cap_public_website/rss/rss_karnataka.xml].

**Exactly what we ask.**
1. Written confirmation that the public RSS and CAP XML may be read, stored and shown by a commercial service, with attribution, including alert text shown unchanged with agency, time and a link to SACHET.
2. Whether a registered agency or partner feed exists (higher limits, change notices, outage contact), how to apply, and what the technical agreement requires.
3. Permission to show our own model advisories next to official alerts, clearly labelled as FloodRoute and never as official.
4. A technical contact for outages and format changes, and notice before schema changes.
5. Optional: any location query or finer-than-district polygons. We can do point-in-polygon ourselves from the CAP XML polygons, so this is a convenience, not a blocker.

**What we offer.** Credit to NDMA, the issuing agency and SACHET on every alert. ETag and `If-None-Match` caching from the first request and a polling interval no faster than [PLACEHOLDER: set with NDMA]. Alert text never altered. No cell-broadcast origination (PRD FR-L4). Feed-health observations (gaps, latency) shared on request. Compliance with any conditions set.

**Fallback if refused or silent.** Keep reading the public feed under its "public domain" label with ETag, on counsel's view. If redistribution is unclear, show a link and a short source-labelled excerpt only. If NDMA says no commercial use, stop showing SACHET text to users, keep SACHET only as an internal trigger if permitted, and rely on the IMD API, open model data and KSNDMC.

**Draft letter.**

> Subject: Request for terms and a partner access route for SACHET CAP alerts
>
> Respected [Sir/Madam],
>
> I am [NAME] of [COMPANY LEGAL NAME], an early-stage team in [CITY] working on road-by-road advisories for heavy rain. We have not launched a product. We plan to show official SACHET alerts to users unchanged, with the issuing agency, the time and a link to SACHET, next to our own advisories. Ours will be labelled as a model, never as official.
>
> The SACHET RSS feed states "public domain", but we could not find a licence or terms page, and we do not want to assume. We request your written guidance on:
> 1. Whether the public RSS and CAP XML may be read, stored and shown by a commercial service, with attribution.
> 2. Whether a registered agency or partner feed exists, how to apply, and what the technical agreement requires.
> 3. A technical contact for outages and format changes.
> 4. Optionally, any location-based query or finer area polygons.
>
> We will follow the SACHET Integration Guide (ETag caching), will not alter alert text, and will not send cell-broadcast alerts. We would be glad to share feed-health observations and to follow any conditions you set.
>
> With thanks and respect,
> [SIGNATURE BLOCK]

---

## 5b. IMD: API platform and data supply

### Part 1. API platform, commercial terms

**Who to address.**
- Platform support. The Contact page lists sankar.nath@imd.gov.in and kavita.navria@imd.gov.in, phone 011-24344320, for "API access and portal support" [V api.imd.gov.in/public/contact.php].
- IMD's note names "Dr. Sankar Nath, Sc-E, IMD, New Delhi" as the nodal officer for organisations that want to use the APIs [V mausam.imd.gov.in/Forecast/marquee_data/API_doc.pdf]. The note is undated, so confirm he is still in post. The note also prints a mobile number; it is not copied here.
- For a formal letter: Director General of Meteorology [PLACEHOLDER: confirm title], India Meteorological Department, Mausam Bhawan, Lodhi Road, New Delhi 110003 [V mausam.imd.gov.in].

**Founder actions first (I have not done them).** Register at api.imd.gov.in/public/register.php with a company email (the page asks government users for gov.in, nic.in, cdot.in, cdac.in, nhai.org or icar.org.in addresses [V]). Read whatever terms appear after login. Note which of the 28 API categories open to a private account.

**What we already know.** 28 categories including nowcast, AWS and ARG data, warnings, radar imagery and lightning; the reference page shows no terms, rate limits, authentication or contact [V api.imd.gov.in/public/api_reference.html]. The platform's landing page also shows no terms [V api.imd.gov.in/]. Research 05 says the IMD note limits APIs to non-commercial use; the copy read here does not say that, so treat the position as unknown.

**Exactly what we ask.**
1. The written terms for using API data in a service that shows derived advisories to third parties (fleet operators, control rooms, the public by WhatsApp), including caching and attribution.
2. Which categories (nowcast, AWS and ARG, radar imagery, warnings) a private company may use, with refresh rate, rate limits, SLA and outage notices.
3. Any charges, or whether an MoU is the right route for operational use.
4. A named contact.

**What we offer.** Credit to IMD; IMD data labelled official and our output labelled a model; no scraping of any IMD page or image; compliance with the terms; and, if IMD wants it, a seasonal comparison of nowcasts with observed road impacts in the pilot area.

**Fallback.** SACHET alerts, open model data (GFS), IMERG, KSNDMC gauges, and Skymet only if needed. No routing dependence on IMD.

**Draft letter.**

> Subject: Request for commercial terms for the IMD API platform
>
> Respected [Dr. Nath / Sir/Madam],
>
> I am [NAME] of [COMPANY LEGAL NAME], an early-stage team in [CITY] working on road-by-road advisories for heavy rain. [We registered on api.imd.gov.in on [DATE] using [EMAIL].] We have not launched a product and will not use IMD data in one without your written agreement.
>
> IMD's note on the APIs asks organisations to follow IMD's terms and contact the nodal officer, but we could not find those terms. We request:
> 1. The terms for using API data in a service that shows derived advisories to third parties, including caching and attribution.
> 2. Which API categories (for example nowcast, AWS and ARG, radar imagery, warnings) a private company may use, with refresh rates, rate limits and outage notices.
> 3. Any charges, or whether an MoU is the right route.
> 4. A named contact for questions.
>
> We will label IMD data as official and our own output as a model, credit IMD, and not scrape IMD pages. If useful to IMD, we can share how nowcasts compare with observed road impacts in our pilot area.
>
> With thanks and respect,
> [SIGNATURE BLOCK]

### Part 2. Data supply (historical), written permission

**Who to address.** National Data Centre, IMD, Pune: data.service@imd.gov.in; +91 (20) 25572 255, office hours 10 am to 5 pm [V dsp.imdpune.gov.in]. Enrolment is by account on the same portal (founder action).

**What we already know.** Private companies are Category C, "Commercial": "100 % Data Charges applicable"; enrolment needs an identity card and a Certificate of Undertaking [V dsp.imdpune.gov.in/home_categories.php]. GST of 18% is extra; payment follows a charge letter and is non-refundable; data "must not be shared with third parties" [V mausam.imd.gov.in/patna/mcdata/Data_Supply_Procedure(ENGLISH).pdf]. The Undertaking says: use only for the purpose asked (cl. 1); own use, not passed to any party or media "in part or in full" without prior written approval (cl. 2); acknowledgement (cl. 4); not put on the internet or a portal (cl. 5) [V mausam.imd.gov.in/lucknow/docs/Certificate_Of_Undertaking.pdf]. **So buying data does not by itself let us serve it, or anything built directly from it, to users.** We must ask.

**Exactly what we ask.**
1. A station list and a price estimate for [PLACEHOLDER: hourly and daily rainfall, Bengaluru-area stations, years].
2. Before buying, written confirmation under Undertaking clauses 2 and 5 that we may (a) train and test an internal model on the data, and (b) publish outputs derived from it, such as a per-road risk state, through an API, WhatsApp and a console, without publishing any raw IMD data.
3. If (b) is not allowed, which uses are.

**What we offer.** Acknowledgement of IMD in every report (cl. 4); no raw IMD data published; 100% charges plus GST.

**Fallback.** If derived outputs are refused: use IMD data only for internal research, serve nothing derived from it, and calibrate on ERA5, IMERG and KSNDMC instead. [COUNSEL] decides where "derived" ends.

**Draft letter.**

> Subject: Request for written permission under the Certificate of Undertaking, clauses 2 and 5
>
> Respected Sir/Madam,
>
> [COMPANY LEGAL NAME] intends to enrol as a Commercial (Category C) user of the IMD Data Service Portal for [DATA, STATIONS, YEARS]. We would use it to calibrate a road-flooding advisory model. Before buying, we ask for written confirmation of how clauses 2 and 5 of the Certificate of Undertaking apply:
> (a) May we use the data to train and test an internal model?
> (b) May we publish outputs derived from the data, such as a per-road risk state, through an API, WhatsApp and a console, without publishing any raw IMD data?
> (c) If not, which uses are permitted?
>
> We will acknowledge IMD as the source (clause 4) and pay the full charges and GST. Please also share a price estimate for the data above.
>
> With thanks and respect,
> [SIGNATURE BLOCK]

---

## 5c. KSNDMC: real-time rain gauge access

**Who to address.** Director, Karnataka State Natural Disaster Monitoring Centre, KSNDMC Campus, Major Sandeep Unnikrishnan Road, Near Attur Layout, Yelahanka, Bengaluru 560064; phone +91 080 67355000; emails Director@ksndmc.org and dmc.kar@gmail.com, as published [V ksndmc.org]. The VarunMitra helpdesk uses the same number [V ksndmc.org/en/Activities/VarunMitra].

**What we already know.** 6,505 rain gauges and 935 weather stations, read every 15 minutes (rainfall amount and intensity, temperature, humidity, wind) [V ksndmc.org/en/Activities/Weather]. The same page has no information on API access, data sharing, request procedure or terms [V same]. The public subscription offers a morning SMS, HRA, HIRA (50 mm per hour alerts for the BBMP area), lightning and wind alerts [V ksndmc.org/en/Home/Subscribe]. KSNDMC lists nine MoUs, including with Bengaluru Smart City Ltd, ISRO's Space Applications Centre and NCMRWF [V ksndmc.org/kn/Downloads/MemorandumOfUnderstanding]. The site has a "BBMP Dashboard" and a "Query Interface" whose terms were not visible [V ksndmc.org/]. Research 01's gauge counts are older than the site's current text.

**Exactly what we ask.**
1. A machine-readable feed (API, file push or similar) of the 15-minute gauge and station data for the Bengaluru area, with station metadata and locations.
2. An archive of the same data for [PLACEHOLDER: 2019 to 2026] for calibration.
3. Written terms: storage, use in a commercial service, derived outputs, credit.
4. Whether HIRA and HRA alerts and the drain water-level data can be shared.
5. The MoU or agreement route KSNDMC prefers, and a technical contact.

**What we offer.** Credit on every output. Station health flags (stuck, missing or stale gauges) back to KSNDMC. A seasonal note on how 15-minute rainfall intensity related to road closures in the pilot area. Free during the pilot. No scraping of the website while this is open.

**Fallback.** Public views and the SMS alerts for internal reading only; the OpenCity station list (labelled "Other (Public Domain)" [V data.opencity.in/dataset/groups/karnataka-telemetric-weather-stations-and-rain-gauges]); the IMD API or paid IMD data; IMERG and GFS; Skymet as a paid last resort. Without KSNDMC, rain input for Bengaluru degrades, and the TRD source hierarchy must show that honestly.

**Draft letter.**

> Subject: Request for machine-readable access to KSNDMC rain gauge data for Bengaluru
>
> Respected Director,
>
> I am [NAME] of [COMPANY LEGAL NAME], an early-stage team in Bengaluru working on road-by-road advisories for heavy rain, starting with underpasses and chronic waterlogging spots. We have not launched a product. KSNDMC's 15-minute data is the best rainfall evidence for the city, and we would like to use it responsibly.
>
> We request:
> 1. A machine-readable feed of the 15-minute rain gauge and weather station data for the Bengaluru area, with station locations.
> 2. An archive of the same data for [YEARS], for calibration.
> 3. Written terms covering storage, use in a commercial service, derived outputs and credit to KSNDMC.
> 4. Whether the HIRA alerts and drain water-level data can be shared.
> 5. The MoU or agreement route KSNDMC prefers.
>
> In return we will credit KSNDMC on all outputs, flag stuck or stale stations, and share each season how rainfall intensity related to road closures in the pilot area. We will not scrape the website while this is pending.
>
> With thanks and respect,
> [SIGNATURE BLOCK]

---

## 5d. GBA (formerly BBMP) and Bengaluru Traffic Police: hotspot and underpass lists

**Who to address.**
- Greater Bengaluru Authority. News and encyclopedia sources say GBA replaced BBMP in 2025, with five city corporations (Central, East, North, South, West) [U snippet: en.wikipedia.org/wiki/Greater_Bengaluru_Authority]. Its site gba.karnataka.gov.in and bbmp.gov.in both returned HTTP 503, so no office or email was confirmed. Addressee: [PLACEHOLDER: Chief Commissioner's office, and the storm water drain wing; confirm names on the GBA site].
- Bengaluru Traffic Police. Official site not reachable (HTTP 503). Addressee: [PLACEHOLDER: Joint Commissioner of Police (Traffic); confirm office and email on the BTP site]. ASTraM is BTP's traffic platform [U snippet: arcadis.com/en/projects/asia/india/transforming-bengaluru-traffic-with-the-astram-initiative/].

**What we already know.** OpenCity hosts three KML files from BBMP (locations vulnerable to flooding, a flood-prone map, low-lying areas), data source KSRSAC, updated 27 Nov 2025, licence label "Other (Public Domain)" [V data.opencity.in/dataset/flooding-locations-in-bengaluru-urban]. That label is OpenCity's, not the publisher's. Counts reported in news: 210 BBMP flood-prone areas and 113 traffic-police waterlogging spots [U, research 01]. No underpass inventory in machine-readable form was seen.

**Exactly what we ask of GBA.**
1. The current list of flood-prone and low-lying locations with coordinates (KML, GeoJSON or CSV).
2. An inventory of underpasses, subways, culverts and low bridges: name, road, coordinates, pump or gauge presence, known closures.
3. Waterlogging complaint or closure logs with date, time and place for the last [PLACEHOLDER: N] seasons, with no personal data.
4. Permission to use these in a commercial service, keep a cleaned and geocoded copy, and publish a derived risk layer; and which licence applies.
5. A named officer.

**Exactly what we ask of BTP.**
1. The waterlogging hotspot list with road names or coordinates.
2. ASTraM waterlogging events with time, place and duration, aggregated or de-identified.
3. Diversion or closure SOPs for flood spots, if shareable.
4. Permission for use in a pilot, and a named contact in the ASTraM team.

**What we offer.** A cleaned, de-duplicated, geocoded copy of each list returned to the owner. A short accuracy note each season. Credit. No cost. We will not publish their lists as closure statements. Any `flood_prone` contribution to OpenStreetMap only with their written permission and counsel's view.

**Fallback.** Use the OpenCity KML internally (counsel to confirm the licence), geocode published PDFs and news lists by hand (spike S5), commission the underpass field survey (Rs 3 to 8 lakh [EST, PLAN]) through the Indian entity, and verify spots with the pilot partners.

**Draft letter to GBA.**

> Subject: Request for flood-prone location and underpass lists in machine-readable form
>
> Respected [Chief Commissioner / Special Commissioner],
>
> I am [NAME] of [COMPANY LEGAL NAME], an early-stage team in Bengaluru working on road-by-road advisories for heavy rain. We have not launched a product. We found the flood-prone location files (KML on OpenCity, updated November 2025) and would prefer to use current official data.
>
> We request:
> 1. The current list of flood-prone and low-lying locations with coordinates.
> 2. An inventory of underpasses, subways, culverts and low bridges with road names, coordinates and any pump or gauge details.
> 3. Waterlogging complaint or closure logs with time and place, without personal data, for the last [N] seasons.
> 4. Your permission to use these in a commercial service and to keep a cleaned, geocoded version, and the licence that applies.
> 5. A named officer for questions.
>
> In return we will give back a cleaned and geocoded copy of your lists, a short accuracy note each season, and credit to the Authority. We will not publish your lists as closure statements.
>
> With thanks and respect,
> [SIGNATURE BLOCK]

**Draft letter to BTP.** Same opening. Items: hotspot list; ASTraM waterlogging events with time, place and duration (aggregated); diversion SOPs if shareable; permission for pilot use; named contact. Same offer.

---

## 5e. CWC and India-WRIS: terms query

**Who to address.** The concerned field Chief Engineer of CWC, per the policy as quoted in search results [U snippet]. cwc.gov.in returned HTTP 401 and indiawris.gov.in HTTP 503, so no office, address or email was verified. Addressee: [PLACEHOLDER]. Send this only if a river-fed city needs the data. Bengaluru's road flooding is mostly rain on pavement, so this is low priority.

**What we already know.** Only search-result text of the policy: unclassified data is free; classified data for Indian commercial and foreign users costs Rs 75,000 per site per year, is non-transferable and may not be reproduced in reports; 2013 and 2018 versions are both cited [U snippet]. CWC's forecast site failed for days at the start of the 2026 monsoon [U secondary, research 01].

**Exactly what we ask (a terms query, not a data request).**
1. Which hydro-meteorological data dissemination policy is in force, and a copy.
2. Whether unclassified India-WRIS data may be used and redistributed in a commercial advisory service with attribution, and whether a documented API exists.
3. Whether real-time forecast and inundation data are classified or unclassified.
4. For classified data, the current price and whether derived outputs may be published.
5. Any guidance on caching and request rates, given portal outages.

**What we offer.** Credit; caching to reduce load; outage observations.

**Fallback.** SACHET carries CWC alerts [V per research 01, feed seen]. Google Flood Hub is limited to non-commercial use today [V sites.research.google/gr/floodforecasting/resources/]. GloFAS under CC BY [U, research 01]. Routing never depends on CWC.

**Draft letter.**

> Subject: Query on terms for using CWC and India-WRIS data in a commercial advisory service
>
> Respected [Sir/Madam],
>
> I am [NAME] of [COMPANY LEGAL NAME], an early-stage team in [CITY] working on road advisories for heavy rain. We have not launched a product and want to understand the terms before using any CWC data. We request:
> 1. A copy of the data dissemination policy now in force.
> 2. Whether unclassified India-WRIS data may be used and redistributed in a commercial service with attribution, and whether a documented API exists.
> 3. Whether real-time forecast and inundation data are classified.
> 4. For classified data, the current price and whether derived outputs may be published.
>
> We will credit CWC, cache to reduce load, and follow the terms you confirm.
>
> With thanks and respect,
> [SIGNATURE BLOCK]
