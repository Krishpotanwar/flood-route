# FloodRoute: Delivery Plan

Version 0.1 draft, 2026-10-05. Companion to [PRD.md](PRD.md) and [TRD.md](TRD.md). Tags: **[V]** verified, **[U]** unverified, **[EST]** estimate. Effort and budget numbers are my estimates and assume the defaults in [00-brainstorm.md](00-brainstorm.md) section 5 (D1 to D10).

## 1. Shape of the plan

The calendar is set by weather, not by us.

| Window | Weather | What it means |
|---|---|---|
| Oct to Dec 2026 | North-east monsoon (Chennai, Tamil Nadu, coastal Andhra Pradesh), late rains in Bengaluru [V, report 03] | Too late to ship a product. Enough time to ingest, run in shadow mode and collect labels. |
| Jan to Mar 2027 | Dry season | Build and sign design partners. |
| Apr to May 2027 | Pre-monsoon convective storms (Bengaluru May 2025 precedent [V]) | **First live pilot window.** This is the deadline that matters. |
| Jun to Sep 2027 | South-west monsoon (Mumbai, Pune, Gurugram) | Expansion and proof. |
| Oct to Dec 2027 | North-east monsoon | Chennai as a full city. |

Hard dates the plan must respect:
- DPDP consent, notice, security and breach duties begin about **13/14 May 2027** [V, report 05; [COUNSEL] to confirm any amendment]. They land in the middle of the pilot, so build to them from January.
- TRAI's Third Amendment on messaging was notified **18 Sep 2026**, with most provisions starting 30 to 90 days later [V, report 05]. It affects SMS templates and any voice alerts.
- DPDP Consent Manager rules start about 13 Nov 2026 [V]. Not needed for us.

## 2. Phases and gates

### Phase 0: Foundations and shadow ingestion (6 Oct to 30 Nov 2026)

Goal: prove we can ingest, score and log, and learn what customers will actually buy.

| Week | Work |
|---|---|
| 1 (6 to 12 Oct) | Confirm D1 to D10. Retain counsel. Start Indian entity setup and DPIIT recognition. Start DLT and WhatsApp BSP onboarding (S7). Register on IMD API platform (S2). Apply to Google Flood Hub API waitlist. Write to NDMA and C-DOT for a SACHET partner feed (S3). Initialise repo, CI, PRODUCT.md and DESIGN.md. Book 8 to 10 discovery interviews. |
| 2 to 3 | Ingestion adapters live in staging: SACHET, open NWP, IMERG, with `source_health`. Spike S1 (Valhalla). Spike S5 (hotspot geocoding) for Bengaluru and Chennai. Spike S4 (KSNDMC). Interviews begin. |
| 4 to 6 | v0 scoring running in shadow on Chennai and Bengaluru hotspot sets. Label capture from traffic-police posts, news and public complaints into an event log. Interviews continue. First backtest on historical events. |
| 7 to 8 | Gate G0 review. Choose design-partner candidates. Decide go or adjust on beachhead (D1). |

**Gate G0 (30 Nov):** shadow season produced a labelled event log; v0 backtest on at least 3 events with POD and FAR reported; counsel's view on advisory framing in hand; at least 6 interviews done and a ranked list of design-partner candidates; S1 returned go or an agreed fallback.

### Phase 1: Build R1 (1 Dec 2026 to 31 Mar 2027)

| Month | Platform and data | Product and design | Partnerships and compliance |
|---|---|---|---|
| Dec | Valhalla integration, overlay publisher, validation loop (TRD 7.3). Scoring v0 hardened and replayable. Bengaluru field survey of underpasses starts. | Console skeleton: situation board, incident table, map. Tokens and risk components. | Design-partner conversations to term sheets. KSNDMC access path. |
| Jan | Fleet API, webhooks, tenant isolation. Evidence ingestion (reports, probes with k-floor). Photo pipeline (EXIF strip, blur). | Closure override with audit. WhatsApp bot (Kannada and English). PWA shell. | Consent screens and notice drafted. Retention schedule. DPDP build begins. |
| Feb | Alerting channels. Decision log. Staleness behaviour end to end. | Route compare, live reroute, report flow. Offline mode. Kannada string review. | Design-partner MoU or letter of support signed. Safety case draft. Terms of Use and advisory wording reviewed by counsel. |
| Mar | Load test at 1,000 route requests per second. Replay of Bengaluru May 2025 event. Game-day 1. VAPT. | Usability tests (riders, dispatchers). Low-end device performance pass. | Insurance bound. Incident runbook rehearsed. Template approvals complete. |

**Gate G1 (late Mar, go live in April):** safety case signed; game-day passed; DLT and WhatsApp templates approved; partner MoU or letter of support; DPDP notice and consent live; insurance bound; runbook rehearsed; zero open high-severity defects.

### Phase 2: Bengaluru pilot (1 Apr to 30 Jun 2027)

- Advisory mode only. Dispatcher confirm required for ambulance assignments.
- Weekly review with the design partner: overrides, near-misses, alert volume, false closures.
- 13/14 May: DPDP duties start. Compliance must already be live.
- After each storm: labelled-event update, calibration report, model-change note.
- End of phase: seasonal accuracy report (POD, FAR, lead time, override rate, calibration) and the first paid-pilot conversation.

**Contingency:** if no design partner signs by March, run the pilot in **observer mode**: publish predictions and overrides to interested partners without routing, and keep collecting labels. This keeps the season from being lost.

### Phase 3: Expansion (1 Jun to 30 Sep 2027)

- **Mumbai:** hotspot library (BMC 386 to 498 spots, traffic police 215 flood spots [V, reports 01, 03]), IFLOWS and X-band radar MoU pursuit, second language Marathi.
- **Gurugram or Delhi-NCR:** underpass inventory, Haryana jurisdiction first, Hindi.
- Start v1 hybrid model once spatial cross-validation beats v0.
- Target: 2 paid pilots by July [EST, PRD].

**Gate G2:** R1 metrics at or near target; zero routed-into-closed incidents; at least one paying pilot.

### Phase 4: Chennai and consolidation (1 Oct to 31 Dec 2027)

- Chennai as a full city for the north-east monsoon, using the shadow-mode labels collected in 2026 and the best-instrumented sensor network in the country [V, report 01].
- Self-serve fleet onboarding. v1 evidence fusion with learned likelihoods.
- Decide on funding, headcount and the next three cities.

Gate G3 (public closure outputs without a human in the loop) is **not** in 2027.

## 3. Workstreams and epics

Sizes are person-weeks [EST]. S is under 2, M is 2 to 5, L is 6 to 12.

| Workstream | Epic | Covers | Size | Starts |
|---|---|---|---|---|
| **Data and model** | Ingestion adapters (SACHET, IMD, NWP, IMERG, gauges) | FR-E4 | M | Wk 2 |
| | Hotspot and underpass inventory pipeline | FR-R5 | M | Wk 2 |
| | v0 scoring and hysteresis | FR-R1 to R4, R6 to R8 | L | Wk 3 |
| | Backtest and calibration harness | FR-R9 | M | Wk 4 |
| | Field survey of underpasses (contract) | FR-R5 | L (Rs 3 to 8 lakh [EST]) | Dec |
| | v1 hybrid model | roadmap | L | Jun 2027 |
| **Platform and routing** | Valhalla spike and integration, overlays, validation loop | FR-RT1 to RT7 | L | Wk 2 |
| | API, tenancy, webhooks, feeds | FR-A1 to A4 | M | Dec |
| | Decision log, audit, retention jobs | FR-C4, FR-M1, M3 | M | Jan |
| | Infra, CI, observability, DR runbook | TRD 11 to 14 | M | Wk 1 |
| **Clients and design** | Tokens, risk components, copy catalog | design report | M | Wk 3 |
| | Dispatcher console | FR-C1 to C7 | L | Dec |
| | Citizen PWA and report flow | FR-P2, P3, P6, P7 | L | Jan |
| | WhatsApp bot and SMS | FR-P1, P4 | M | Jan |
| | Voice guidance | FR-P5 | S | Mar |
| **Partnerships and government** | Discovery interviews (8 to 10) | PRD 13 | M | Wk 1 |
| | Design-partner MoU (control room plus fleet) | PRD 13 | M, long lead | Dec |
| | KSNDMC, BBMP, traffic police data access | PRD 14 | M, long lead | Wk 2 |
| | IMD and CWC licence path | report 01 | M, long lead | Wk 1 |
| **Legal and compliance** | Entity, DPIIT, DLT, WhatsApp Business | report 05 | M | Wk 1 |
| | DPDP build (consent, retention, breach) | FR-M2, M3 | M | Jan |
| | Terms, advisory wording, liability review | PRD principle 1 | M | Dec |
| | Safety case, insurance, runbook | TRD 16 | M | Feb |
| | VAPT and CERT-In readiness | TRD 12 | S | Mar |
| **Quality** | Replay, chaos, load, usability, device tests | TRD 15 | M | Dec onward |

Critical path: the long-lead items are the design-partner MoU, data access (KSNDMC, IMD), template approvals and the underpass survey. Start them in the first two weeks. Engineering has slack; partnerships and approvals do not.

## 4. Team and budget (assumptions to confirm: D5)

### Team, 4 to 6 people [EST]

| Role | Focus |
|---|---|
| Product and partnerships lead (founder) | Customers, partners, government, pricing |
| Backend and geospatial engineer | Ingestion, scoring, routing, API, infra |
| Frontend and design engineer | Console, PWA, tokens, WhatsApp flows |
| Data scientist with hydrology exposure (part-time or advisor to start) | Priors, calibration, backtest, v1 model |
| Field and operations (contract) | Underpass survey, partner coordination |
| Counsel (retained, part-time) | DPDP, liability, data licences, MoUs |

Optional later: a second backend engineer and a safety or reliability lead before G1 if budget allows.

### Non-staff budget, phases 0 to 2 (about 9 months, Oct 2026 to Jun 2027) [EST, my arithmetic]

| Item | Low (Rs lakh) | High (Rs lakh) | Basis |
|---|---|---|---|
| Cloud and infra | 5 | 30 | Planning range Rs 0.5 to 3.5 lakh per month (TRD 14) over 9 months; early months run well below the top of the range |
| Field survey, Bengaluru | 3 | 8 | Report 02 estimate |
| Legal and counsel | 5 | 10 | Placeholder, get a quote |
| Insurance (E&O, cyber) | 2 | 5 | Placeholder, get a quote |
| VAPT and audit | 3 | 6 | Placeholder, get a quote |
| Data purchases (IMD historical, optional Skymet) | 3 | 10 | IMD charges plus 18% GST [V, report 01] |
| Messaging pilot volume | 1 | 3 | About Rs 0.13 per WhatsApp utility message [V] |
| Devices and testing | 1 | 2 | Low-end Android handsets, test SIMs |
| Travel and discovery | 2 | 3 | Interviews, partner meetings |
| **Total** | **25** | **77** | Excludes salaries. Legal, insurance and audit lines are placeholders until quoted. |

Revenue assumptions in the PRD are hypotheses, not budget lines.

## 5. Milestones

| Date | Milestone |
|---|---|
| 12 Oct 2026 | Decisions D1 to D10 confirmed; counsel retained; IMD, SACHET, Google, DLT, WhatsApp requests filed |
| 31 Oct | Ingestion live in staging; S1, S3, S5 reports done; 5 interviews done |
| 30 Nov | **G0**: shadow log, backtest, partner shortlist |
| 31 Dec | Valhalla integration working end to end in staging; console skeleton |
| 31 Jan 2027 | Fleet API and WhatsApp bot in staging; DPDP build in progress |
| 28 Feb | Design-partner MoU signed; safety case draft |
| 31 Mar | **G1**: safety case, game-day, approvals, insurance |
| 1 Apr | Live advisory pilot in Bengaluru |
| 13/14 May | DPDP main duties start; compliance live |
| 30 Jun | Seasonal accuracy report; Mumbai and Gurugram prep done |
| 31 Jul | Two paid pilots (target) |
| 30 Sep | **G2** review |
| 1 Oct | Chennai full-city start |

## 6. Plan risks

| # | Risk | Likelihood and impact | Response |
|---|---|---|---|
| 1 | Design partner does not sign by March | Medium, high | Observer mode pilot; keep labels flowing; widen to a second control room or fleet |
| 2 | IMD or CWC data terms block commercial use | Medium, high | SACHET and open NWP first; pursue MoU; budget for paid historical data; never scrape |
| 3 | KSNDMC or BBMP data access slow | Medium, medium | Public view and SMS alert subscription as a stopgap [V, report 01]; Skymet as a paid fallback |
| 4 | Valhalla spike fails (overlay refresh or class overlays) | Low to medium, medium | GraphHopper custom areas or custom A* with the same validation loop |
| 5 | Shadow season yields few labelled events (Bengaluru may see few heavy events in Oct to Dec) | Medium, medium | Chennai shadow mode; historical events via public records; extend shadow into April |
| 6 | Template approvals (DLT, WhatsApp) slip | Medium, medium | Start week 1; fall back to in-app and push only |
| 7 | DPDP or TRAI timing changes | Medium, low to medium | Build to the stricter reading; counsel updates monthly |
| 8 | Google ships finer-resolution flood forecasts or a Maps flood layer | Medium, high | Own segment ground truth, dispatcher workflow, local data deals; ship R1 on time |
| 9 | A harm incident occurs in pilot | Low, very high | Advisory mode, human confirm, insurance, runbook, kill switch |
| 10 | Team is smaller than assumed | Medium, high | Cut list below |

### Cut list if capacity is short (cut from the bottom first)

1. Voice guidance (FR-P5)
2. Rider mode (FR-P7)
3. SMS channel (FR-P4)
4. CAP feed (FR-A3)
5. Equity cap (FR-RT9)
6. Webhooks, keep polling (FR-A2)
7. PWA, keep WhatsApp and console

Never cut: staleness and Unknown handling, Not assessed flag, human override with audit, decision log, consent and retention, source labelling, advisory wording, kill switch.

## 7. What I need from you

Please confirm or change these defaults (full list in [00-brainstorm.md](00-brainstorm.md)):

1. **D1 Beachhead:** Bengaluru. Alternative: Mumbai (stronger proof, slower government).
2. **D2 First customer:** delivery or cab platform plus one control room as design partner.
3. **D3 Advisory only in 2027.**
4. **D4 Entity:** Indian-owned and controlled.
5. **D5 Team and runway:** 4 to 6 people for 9 months.
6. **D7 Cloud:** AWS Mumbai and Hyderabad.

Then I can start the repo skeleton, the ingestion adapters and spike S1.

## 8. First 10 days

1. Confirm decisions above.
2. Retain counsel; book the first call on DPDP, liability and data licences.
3. File: IMD API registration, NDMA and C-DOT SACHET request, Google Flood Hub API waitlist, DLT and WhatsApp BSP onboarding.
4. Create the repo skeleton from TRD section 18, CI with lint, type check and the small runnable checks.
5. Stand up SACHET and open-NWP ingestion in staging.
6. Run spike S1 with a Bengaluru graph.
7. Collect and geocode the BBMP (210), traffic police (113) and GCC (859) lists [V counts, report 01].
8. Send interview requests: EMRI or ZHL, Bengaluru Traffic Police (ASTraM), BBMP, KSNDMC, and fleet ops or safety leads at delivery, cab and school-bus operators.
9. Draft the vehicle-profile trial plan: ask fleet partners for stall data.
10. Write the shadow-mode event log schema and start logging.
