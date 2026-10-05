# FloodRoute: Legal, Regulatory, Compliance and Government Partnership (India)

Research date: 2026-10-05. Product-planning research, **not legal advice**; items marked **[COUNSEL]** need an Indian lawyer before launch.
Tag convention: `[VERIFIED Sx]` = I opened or saw the source in this session (Sources list below says primary or secondary); `[UNVERIFIED/recalled]` = from memory or a search snippet I could not open. No section numbers are given unless seen in a source.

## 0. Bottom line

1. **DPDP is the central design constraint, and its big obligations start 13/14 May 2027.** Build to them now. Continuous location plus crowd photos makes us a data fiduciary handling sensitive-in-practice data. A breach carries a penalty up to Rs 250 crore. [VERIFIED S3]
2. **Nothing found bars a private party from publishing flood risk or road-condition advisories. But two things limit us.**
   - Government stance: only IMD, CWC and SDMAs are "authorised" alert sources, and private forecasts carry no official weight.
   - Criminal law: circulating a *false* disaster alarm that causes panic is an offence. [VERIFIED S8, S12]
3. **Liability is the sleeper risk.** In the Nov 2024 Bareilly bridge deaths, an FIR named a Google Maps regional manager along with PWD engineers. Treat "advisory, not directive" as a product-design requirement, not just a disclaimer. [VERIFIED S14]
4. **IMD data has real licence traps.** AWS/ARG portal access was cut in May 2025, IMD says AWS data is not for commercial use, and its free APIs are "non-commercial" and need its approval. [VERIFIED S9, S7 and search snippet]
5. **Government sales run through the DPIIT startup relaxations, MeitY-empanelled cloud, CERT-In audits and GIGW 3.0.** The Smart Cities Mission ended 31 Mar 2025, so ICCCs now depend on state and municipal budgets. [VERIFIED S18]

## 1. DPDP Act 2023 and DPDP Rules 2025

**Status.** The Rules were notified in Nov 2025. The PIB note says 14 Nov, while most commentary says 13 Nov. [VERIFIED S3] Commencement under Rule 1: [VERIFIED S1]

| Date | What starts |
|---|---|
| Notification (Nov 2025) | Rules 1, 2, 17 to 21: Board constitution, definitions |
| One year on (~13 Nov 2026) | Rule 4: Consent Manager registration |
| 18 months on (~13/14 May 2027) | Rules 3, 5 to 16, 22, 23: notice, consent, security, breach, rights, retention, children, SDF duties, cross-border |

- Commentary says MeitY floated compressing the SDF window to 12 months in Jan 2026. As of my searches, **no amending notification was found.** [UNVERIFIED/recalled, S21] **[COUNSEL]** to confirm the exact dates and any amendment.
- Penalty ceilings: Rs 250 crore for failing reasonable security safeguards. Up to Rs 200 crore each for breach non-notification and children's-data violations. Up to Rs 50 crore for other violations. [VERIFIED S3]

**Obligations that bite FloodRoute**

| Topic | Rule or section | Design implication |
|---|---|---|
| Consent and notice | Rule 3 (18-month tranche); notice must be separate, plain, purpose-specific [VERIFIED S3] | Granular in-app consent: (a) foreground location, (b) background location, (c) crowd photos, (d) sharing with authorities. Withdrawal must be as easy as giving consent. |
| Disaster legitimate use | s.7(h): processing "for taking measures to ensure safety of, or provide assistance or services to, any individual during any disaster", with "disaster" as in DMA 2005 s.2(d). s.7(f): medical emergency. [VERIFIED S2] | Do **not** make s.7(h) the baseline. A routine waterlogging day may not be a "disaster". Use consent as the base. Treat s.7(h) and s.7(f) as a supplement for declared events and for passing location to 108/112. **[COUNSEL]** on the threshold. |
| Security safeguards | Rule 6: encryption/masking/tokens, access control, logs and monitoring, backups, processor contracts, **retain logs and personal data for one year** [VERIFIED S1] | Build the audit-log and key-management stack now. |
| Retention | Rule 8(3): processing logs, traffic data and personal data kept **at least 1 year** (for Seventh Schedule purposes), then erased [VERIFIED S1] | This pulls against data minimisation. Keep raw GPS trails short-lived and keep minimal audit/processing logs for one year. **[COUNSEL]** on whether raw location counts as the "logs" Rule 8(3) means. |
| Breach | Rule 7: tell each affected user "without delay". Tell the Board without delay, with a detailed report within **72 hours** (extendable by the Board). [VERIFIED S1] | Run in parallel with the CERT-In 6-hour clock (section 6). Pre-draft user notices. |
| Children | s.9: verifiable parental consent. **s.9(3): no tracking or behavioural monitoring of children** [VERIFIED S2]. Schedule exemptions exist, e.g. real-time location of a child for safety [VERIFIED S1] | Age-gate. The exemption covers tracking a child, not a general routing app. Default to 18+ or a neutral-age flow. |
| SDF | Notified by the Centre under s.10 on volume and sensitivity. Duties: DPIA, independent audit, algorithmic assessment, India-based DPO [VERIFIED S2; details secondary S22] | Plausible at scale given continuous location. Plan a DPIA anyway. |
| Cross-border | Rule 15 and s.16 negative-list model: transfers allowed unless restricted; Rule 15 lets the Centre impose conditions on making data available to foreign states [VERIFIED S1]. No restricted-country list found as of mid-2026 [UNVERIFIED/recalled, secondary] | Host in India. Government tenders require it anyway (section 6). |
| Processors | s.8(1): fiduciary stays responsible for processors [VERIFIED S2] | Contracts with SMS, cloud and maps vendors. |
| Consent Managers | Registered from Nov 2026; Indian companies [VERIFIED S3] | Optional. No need to integrate at MVP. |

**Design implications**
- **Continuous location:**
  - Prefer on-device routing.
  - Upload coarse or aggregated cells for crowd-flow.
  - Rotate pseudonymous IDs.
  - Delete trails within days unless the user opts into history.
  - Treat aggregated, k-anonymous flow data as non-personal. **[COUNSEL]** to confirm the anonymisation standard.
- **Crowd photos:**
  - Strip EXIF on upload.
  - Blur faces and number plates server-side.
  - Store only the derived "water depth / passable" label after verification.
  - Keep originals for a short, defined period.
- **108/112 integration:** share location only on user-initiated SOS, or under s.7(f) and s.7(h) logic. Write a data-sharing agreement per state. A state ERSS is a separate fiduciary or authority.
- **Government as customer:** if a municipal body or SDMA is the fiduciary and we are its processor, the Rules' processor and security obligations flow down by contract. The State's own processing may rest on s.7(b) or (c). [VERIFIED S2]

## 2. Disaster Management Act 2005, NDMA and alerts

**Who warns**
- SACHET is the NDMA/C-DOT CAP-based platform. Alert-generating agencies are IMD, CWC, INCOIS, DGRE and FSI. Authorising agencies are the 36 SDMAs. Disseminators are telcos, GAGAN/NavIC, TV, radio, sirens and others. [VERIFIED S8, S23]
- SACHET offers an RSS feed to subscribing agencies such as news agencies. **No third-party API terms were published on the page.** [VERIFIED S8] Request formal CAP feed access through NDMA/C-DOT.
- Cell Broadcast (DoT, built by C-DOT) is being integrated with SACHET. A nationwide test ran in mid-2025. [VERIFIED S24] Private parties cannot originate cell broadcasts. Only authorised agencies can.

**Restrictions on private parties**

| Item | Finding |
|---|---|
| Statute | No provision found barring private flood or road advisories. |
| **s.54 DMA** | Making or circulating a false alarm or warning about a disaster or its severity, leading to panic, is punishable by up to one year or a fine. [VERIFIED secondary S12] |
| s.51 DMA | Non-compliance with government directions is an offence (up to one year or a fine; up to two years if loss of life results). [VERIFIED secondary S12] Do not contradict an official closure or direction. |
| IMD stance | Official actions interface with IMD assessments; private agency forecasts have "no bearing" on official follow-up. [UNVERIFIED/recalled: seen only as a search snippet of an MoES reply, S11] |
| Precedent | Kerala paid Skymet, Earth Networks and IBM in a 2020 one-year pilot, and Google works with CWC under an MoU on flood forecasting and alerts. So private involvement is accepted when government is the buyer or partner. [VERIFIED S10, S15] |

**Product rules this implies**
- Label every alert with its source and time: "Official (IMD/CWC/SDMA)" versus "FloodRoute model" versus "Crowd report".
- Never use official-looking colour codes or CAP-style wording for our own predictions.
- Use probabilistic language and show confidence.
- Give authorities a one-click override/closure feed that outranks our model.
- Pass through official SDMA/IMD alerts verbatim and link to SACHET.

**NDMA guidance.** The 2010 urban flooding guidelines call for urban flooding cells at state nodal departments and ULBs, a city flood plan, real-time hydromet networks, and traffic-signal integration for critical underpasses. [VERIFIED S16, secondary] This is the hook for municipal MoUs. A specific NDMA CAP-integration rulebook for private apps was not found. [UNVERIFIED]

**IMD data policy**
- Paid data is "for own use", with no onward transmission, no internet or portal posting and no electronic redistribution. [VERIFIED S9 snippet]
- IMD APIs are free for non-commercial use only, and organisations must contact IMD's nodal officer and follow its terms. [VERIFIED S7]
- The AWS/ARG public portal was locked in ~May 2025. IMD cited misuse risk and a commercial-use prohibition. Access now needs a request stating purpose, scope and intended use. [VERIFIED secondary S9]
- **Implication:** do not scrape IMD. Sign an IMD/CWC/SDMA data-sharing MoU for commercial use. Cross-check against open or paid sources (see doc 01). **[COUNSEL]** on redistribution rights for derived products.

## 3. Liability for advice-giving

- **Precedent.** The Bareilly case (Nov 2024): a car followed navigation onto a broken bridge, three died, and an FIR named the Google Maps regional manager plus PWD engineers. Google removed the route. [VERIFIED S14] Expect criminal complaints, not just civil claims, after any fatality.
- **Consumer Protection Act 2019.** "Service" excludes services rendered free of charge. [VERIFIED secondary S17] Therefore:
  - A free consumer tier may fall outside CPA "deficiency in service", but a court could still treat ad- or data-funded use as consideration. **[COUNSEL]**
  - Paid, B2B and B2G tiers are squarely covered.
  - The unfair-contract concept in s.2(46) limits aggressive disclaimers and unilateral termination. [VERIFIED secondary S17]
  - Product liability provisions cover "product service providers". Whether pure software qualifies is uncertain. [UNVERIFIED]
- **Criminal negligence.** BNS s.106 (death by negligence, up to five years) is the likely hook. [VERIFIED secondary S19] Disclaiming it is not enforceable.
- **Tort and contract.** Indian courts apply a common-law duty of care. Exclusion clauses face public-policy limits under the Contract Act. [UNVERIFIED/recalled] **[COUNSEL]**
- **Motor Vehicles Act 1988.** Drivers remain responsible for safe driving. [UNVERIFIED/recalled] Use voice and glance-able UI, no interaction while moving, and a "do not enter flooded road" warning.

**Controls**
1. **Advisory, not directive.** Wording: "likely flooded", "avoid if possible", never "safe".
2. **Unknown is a state.** Show "no recent data" and never green-by-default.
3. **Bias to caution.** Penalise uncertain segments in routing. Never route through a segment with a recent "impassable" report.
4. **Staleness TTLs.** Show report age and decay confidence.
5. **Log every routing decision** (inputs, model version, advisories shown) for one year. This serves Rule 6/8(3) and incident defence. Keep the logs privacy-safe.
6. **Terms of Use.** Plain-language limitation, an acknowledgement at first use, and emergency numbers (112, 108) surfaced.
7. **Insurance:** tech E&O or professional indemnity, cyber, and media or content liability. Confirm exclusions for bodily injury and "advice" with the broker. [UNVERIFIED/recalled]
8. **Incident runbook** if a user is harmed after following a route:
   - Preserve logs under legal hold.
   - Notify the insurer.
   - Pull or flag the route and issue a correction.
   - Notify the authority and, if personal data was involved, assess the DPDP and CERT-In clocks.
   - Contact the family through counsel.
   - Run a post-incident review and publish a model-change note.

## 4. Geospatial rules

- **DST Guidelines, 15 Feb 2021** [VERIFIED S4, primary]
  - There is no prior approval, licence or security clearance for collecting, creating or publishing geospatial data and maps within India. Compliance is by self-certification.
  - Map data finer than the thresholds (1 m horizontal, 3 m vertical) can only be created or owned by **Indian entities** and must be stored and processed in India.
  - Foreign or foreign-controlled companies may license fine-resolution data from Indian entities, **only via APIs that don't let the data pass through the licensee's servers**, with no re-use or resale.
  - Political maps of India must follow **Survey of India (SoI)** boundary standards.
  - The Government encourages crowdsourced map building.
- **National Geospatial Policy 2022** (notified 28 Dec 2022) replaced the 2005 Map Policy and is consistent with this liberalisation. [VERIFIED secondary S25]
- **Geospatial Information Regulation Bill 2016** (heavy fines for wrongly depicting India) was a draft. I found no enactment. [VERIFIED secondary S26; status UNVERIFIED]

**Implications**
- **Self-hosted OSM:** allowed. Ensure the basemap's India boundary layer follows SoI (for example, Kashmir and Arunachal depiction). Use an SoI-conformant boundary overlay and remove disputed OSM boundary tags. **[COUNSEL]**
- **Foreign map vendors:** acceptable at coarse resolution. For sub-metre road or flood-depth data, the Indian-entity rule applies. Check the vendor's India-licence structure.
- **Own high-resolution flood-depth or elevation products:** hold them on Indian servers. Own an Indian entity.
- Include a self-certification statement in the compliance file.

## 5. Telecom and messaging

| Channel | Rule | Action |
|---|---|---|
| SMS | TCCCPR 2018 requires DLT registration of entity, header and template. Message classes: transactional, service-implicit, service-explicit, promotional. [VERIFIED secondary S27] Since 11 Dec 2024, SMS from chains not registered with the access provider is rejected. [VERIFIED secondary S27] | Register as a principal entity; register alert templates. Keep alerts strictly informational; do not mix promotions. |
| Amended TCCCPR | **Third Amendment Regulations notified 18 Sep 2026.** [VERIFIED S6, primary] Key items: A2P voice calls (autodialer, robocall, prerecorded) must be **pre-declared** to the TSP with CLIs, and undeclared calls are treated as UCC. Misuse of headers and templates is penalised. Enquiry-based commercial messages are limited to seven days. Most provisions start 30 days after publication, some at 60 or 90. | **IVR/voice alerts are directly affected.** Declare A2P use and CLIs. Use the regulated number series. **[COUNSEL]** on the exact commencement dates and the treatment of government or safety messages. |
| WhatsApp | Utility templates must be non-promotional and essential to a process; billed per template since 1 Jul 2025 (India utility ~Rs 0.13, marketing ~Rs 0.86). Opt-in is required. [VERIFIED secondary S28] | Collect opt-in in-app. Keep alerts in the utility category. Never send marketing in the same thread. |
| Cell broadcast | Only authorised agencies via SACHET/DoT. [VERIFIED S24] | Integrate by consuming and amplifying official alerts, not by originating. |
| Telecom Act 2023 | s.20 lets Centre and State take over or prioritise networks during a public emergency including disaster management. Rules on prior consent for "specified messages" (marketing) and DND registers are enabled by the Act. [VERIFIED secondary S29] | Monitor the rules. Low direct impact on us. |

## 6. Security and regulatory

| Item | Requirement | Note |
|---|---|---|
| **CERT-In Directions (28 Apr 2022)** | Report listed incidents within **6 hours** of noticing them. Maintain ICT logs for a rolling **180 days within Indian jurisdiction**. Sync clocks to NIC/NPL NTP. [VERIFIED S5, primary] | Reportable incidents include attacks via malicious or fake mobile apps and cloud-computing compromises. [VERIFIED S5] Run one incident runbook with three clocks: CERT-In 6h, DPDP Board 72h, users without delay. |
| CERT-In audit policy | Guidelines of 25 Jul 2025 call for at least annual third-party audits by CERT-In-empanelled auditors. [VERIFIED secondary S30] | Budget annual VAPT and audit from launch. |
| MeitY cloud empanelment | Government workloads normally must run on MeitY-empanelled CSPs with data resident in India; STQC audits the CSP. [VERIFIED secondary S31] | Host on an empanelled cloud region from day one. |
| GIGW 3.0 | Government websites and apps need WCAG 2.1 AA, with STQC-empanelled labs certifying. Certificate is valid up to three years. [VERIFIED secondary S32] | Needed if we deliver a government-branded portal or app. Also supports RPwD Act duties. [UNVERIFIED/recalled for RPwD detail] Build to WCAG 2.1 AA now. |
| IT Act s.79 and Intermediary Rules 2021 | Crowd reports make us a UGC intermediary. Safe harbour depends on due diligence, a grievance officer, and takedown on valid orders. Rule 3 timelines were tightened by the 2025 amendments (for example 72 hours on removal complaints). [VERIFIED secondary S33; exact terms UNVERIFIED] | Publish rules for user content. Appoint a grievance officer. Give one-tap reporting and removal. Track whether any significant-intermediary thresholds apply. **[COUNSEL]** |
| ISO 27001, IS 17428 | ISO 27001 is a common tender expectation. [VERIFIED secondary S31] IS 17428 (privacy information management) is recalled as a tender or STQC reference. [UNVERIFIED/recalled] | Start ISO 27001 prep at pilot stage. |

## 7. Government partnership and procurement

| Route | What I found | Timing |
|---|---|---|
| DPIIT recognition | Recognised startups are exempt from prior experience, prior turnover and EMD in public procurement (GFR rules cited), only where the tender document says so. [VERIFIED secondary S34] | Recognition takes weeks. [UNVERIFIED/recalled] |
| GeM and Startup Runway | Startup Runway offers startups access to government buyers. [VERIFIED secondary S34] | Seller onboarding takes weeks. [UNVERIFIED/recalled] |
| Smart Cities and ICCCs | Mission officially closed 31 Mar 2025. ICCCs persist as municipal assets. Ongoing O&M funding was not confirmed. [VERIFIED secondary S18] | Sell to the city or the state, not "to the Mission". |
| State and city challenges | "Yes Bengaluru" (grants up to Rs 25 lakh, solutions executed with BBMP and others) [VERIFIED secondary S35]. K-GIS 2026 showed flood citizen-reporting projects. [VERIFIED secondary S35] Similar Chennai and Mumbai programmes: not verified. | Challenges run on annual cycles. [UNVERIFIED] |
| 112 ERSS | State-level systems built with C-DAC as the designated provider. API integrations exist, such as Bihar's 102 ambulance line. [VERIFIED secondary S36] | Needs a per-state MoU with the state police ERSS. Expect long timelines. [UNVERIFIED/recalled] |
| Open data | GODL-India permits commercial use and derivatives with attribution. Applies to shareable, non-sensitive, publicly funded government data. [VERIFIED secondary S37] | Immediate |
| Others | MeitY Startup Hub, NIDM/NDMA innovation programmes, state SDMA pilots. iDEX is defence-oriented and probably irrelevant. [UNVERIFIED/recalled] | Check current calls. |

**Typical sequence (all [UNVERIFIED/recalled])**
1. Free pilot or letter of support in one ward or city (2 to 4 months).
2. MoU with the municipal corporation, DDMA or SDMA (3 to 9 months).
3. Paid pilot via GeM or limited tender, using the startup relaxation (6 to 12 months).
4. State-wide or ERSS integration (12 to 24 months).

**What to offer partners**
- A data-sharing agreement that lets the authority see and override closures.
- No exclusive claim on government-owned data.
- Open reporting of alert accuracy.
- A clear processor/fiduciary split.

## 8. Ethics and fairness

These are design principles, not legal requirements. India-specific rules for routing fairness were not found. [UNVERIFIED]
- **Equity:**
  - Avoid pushing detour traffic through informal settlements, low-lying poorer wards or narrow lanes.
  - Add a cap on rerouted flow per street and a "vulnerability layer" as a routing penalty.
  - Audit the routing outcome by ward income band.
- **Crowd-data abuse:**
  - Use reputation scores, device attestation and rate limits.
  - Require corroboration (multiple independent reports, a sensor, or an official feed) before a closure shows as "likely impassable".
  - Handle spoofed-GPS brigading. Treat malicious false reports as a possible s.54 DMA and BNS s.353 issue and warn in terms. [VERIFIED secondary S12, S19]
- **Transparency:** a "why this route" explanation, data-source labels, confidence, published model-performance notes, and a public grievance and correction channel.
- **Human override:** authorities can close, open or pin roads and issue messages. Their input always outranks the model. An emergency-vehicle mode must be configured with the authority's SOPs and must never block civilian evacuation routes without official instruction.
- **Accessibility and language:** WCAG 2.1 AA, regional languages, voice, and low-bandwidth modes.

## 9. Compliance checklist by phase

| Phase | Must do |
|---|---|
| **MVP / pilot** | Incorporate an Indian entity; DPIIT recognition; privacy notice, consent screens and age gate; Indian hosting (empanelled cloud); encryption, access logs, 180-day logs in India; incident runbook (CERT-In 6h, DPDP 72h); photo blur and EXIF strip; short GPS retention; Terms of Use and advisory framing; source labelling of official versus model alerts; SoI-conformant boundaries; self-certification note for geospatial data; UGC rules, grievance officer and report-abuse flow; DLT registration; IMD/CWC/SDMA data terms for commercial use; written MoU or letter for each pilot city; basic E&O and cyber insurance. |
| **Launch** | Full DPDP compliance in place before 13/14 May 2027, including notice, rights handling (90-day response), retention schedule, DPO or contact point, processor contracts; DPIA; annual third-party audit and VAPT by a CERT-In-empanelled auditor; WCAG 2.1 AA; WhatsApp utility templates and IVR A2P declaration under the amended TCCCPR; SACHET/CAP feed agreement; ISO 27001 progress; 112/108 data-sharing agreement; GeM listing; documented fairness audit; decision log kept for one year. |
| **Scale** | Assess SDF status and appoint an India-based DPO; independent audit and DPIA cycle; ISO 27001 certified; GIGW 3.0 for government-branded deliverables; STQC audit if needed; per-state ERSS and SDMA integrations; legal-hold and claims playbook; regular insurance review; Consent Manager integration if useful; public transparency report. |

## 10. Top risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | A user is harmed after following a route, leading to criminal or civil action (Bareilly precedent) | High | Section 3 controls, insurance, runbook |
| 2 | DPDP penalties for a location-data breach or non-compliant consent | High | Minimisation, on-device logic, security stack |
| 3 | IMD or CWC data licence breach (commercial use or redistribution) | High | Signed MoUs or paid licences |
| 4 | False or unofficial warnings cause panic (s.54 DMA) or conflict with official messages | Medium-High | Labelling, confidence, override |
| 5 | Retention rules (1-year logs) conflict with minimisation | Medium | Separate raw location from audit logs |
| 6 | Wrong boundary depiction on map | Medium | SoI standard overlay |
| 7 | Crowd-data manipulation | Medium | Corroboration and reputation |
| 8 | Procurement delay; ICCC funding uncertainty | Medium | Several partner routes, state-level sale |
| 9 | A2P/IVR and SMS non-compliance under the amended TCCCPR | Medium | Early DLT and A2P declaration |

## 11. Open questions

- Was the DPDP compliance window compressed, and what is the exact commencement date (13 or 14 Nov 2026 and May 2027)?
- Does Rule 8(3)'s one-year log retention reach raw location trails?
- Does a routine heavy-rain waterlogging event qualify as a "disaster" for s.7(h)?
- Can IMD or CWC licence data for a commercial routing product, and on what terms?
- Does NDMA or C-DOT grant third parties a SACHET CAP feed or API?
- Are crowd-report-driven "road closed" labels treated as warnings under the DMA?
- What is the commencement date for each part of the Sept 2026 TCCCPR amendment, and does it exempt safety alerts?
- Are ICCCs funded after Mar 2025, and by whom, in each target city?

## 12. What to ask a lawyer

1. Confirm the DPDP commencement dates, any 2026 amendment, and whether we are likely to be an SDF.
2. Advise on the consent architecture: baseline consent plus s.7(f) and s.7(h) reliance, background location, and photo handling including third-party faces and plates.
3. Draft the retention schedule reconciling Rule 6 and Rule 8(3) with minimisation.
4. Draft Terms of Use, the limitation of liability, and a duty-of-care analysis in light of the Bareilly FIR. Is "advisory" framing enough? Does the free-tier CPA exclusion hold?
5. Advise on s.54 DMA and BNS exposure for model-generated and crowd-sourced "road closed" statements, and the right labelling.
6. Review IMD, CWC, SDMA and SACHET data terms, plus redistribution of derived products. Draft a template MoU.
7. Map and boundary compliance: OSM self-hosting, SoI depiction, and the Indian-entity rule for fine-resolution data.
8. IVR and SMS: A2P declaration, DLT, and whether safety messages are exempt from DND under the amended TCCCPR.
9. Intermediary status: safe harbour, grievance officer, takedown workflow, and significant-intermediary thresholds.
10. Procurement structuring: processor/fiduciary roles, indemnity caps, data-localisation clauses, and a startup-relaxation checklist.
11. Insurance: scope of E&O, cyber and bodily-injury cover for advisory software.
12. Cross-border: any foreign cloud, analytics or ML vendors, and any Rule 15 order.

## Sources

Primary (opened in this session):
- S1 DPDP Rules 2025 (MeitY): https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf
- S2 DPDP Act 2023 (MeitY): https://www.meity.gov.in/static/uploads/2024/06/2bf1f0e9f04e6fb4f8fef35e82c42aa5.pdf
- S3 PIB explainer on DPDP Rules: https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- S4 DST Geospatial Guidelines 15 Feb 2021: https://dst.gov.in/sites/default/files/Final%20Approved%20Guidelines%20on%20Geospatial%20Data.pdf
- S5 CERT-In Directions 28 Apr 2022: https://www.cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf
- S6 TRAI press release, 18 Sep 2026 (TCCCPR Third Amendment): https://www.trai.gov.in/sites/default/files/2026-09/PR_No119of2026.pdf
- S7 IMD "warnings through APIs" note: https://mausam.imd.gov.in/Forecast/marquee_data/API_doc.pdf
- S8 SACHET portal: https://sachet.ndma.gov.in

Secondary (search results or fetched summaries; verify before relying):
- S9 IMD AWS/ARG lock-up: https://www.downtoearth.org.in/amp/story/climate-change/imd-locking-up-its-awsarg-data-portal-hampers-public-weather-alerts-experts ; IMD data supply procedure: https://mausam.imd.gov.in/patna/mcdata/Data_Supply_Procedure(ENGLISH).pdf
- S10 Kerala private forecasters: https://onmanorama.com/news/kerala/2020/06/23/kerala-ditches-imd-weather-data-sanctions-private-companies.html
- S11 MoES reply (snippet only): https://moes.gov.in/sites/default/files/PIB2147267.pdf
- S12 DMA ss.51, 52, 54: https://www.insightsonindia.com/disaster-management/national-disaster-management-act-2005/punishment-clause/ ; https://drishtiias.com/pdf/1738360756.pdf
- S14 Bareilly incident: https://keralakaumudi.com/en/news/news-amp.php?id=1431888 ; https://www.etvbharat.com/amp/en/!state/bareilly-bridge-accident-google-removes-route-from-map-enn24112705234
- S15 CWC-Google: https://un-spider.org/news-and-events/news/indias-government-teams-google-improve-flood-management
- S16 NDMA urban flooding guidelines: https://sdma.goa.gov.in/sites/default/files/2022-05/management_urban_flooding.pdf
- S17 CPA service definition and unfair contract: https://nyaaya.org/legal-explainer/what-are-services/ ; https://taxguru.in/corporate-law/power-declare-terms-contract-null-void-under-consumer-protection-act-2019.html
- S18 Smart Cities Mission closure: https://www.drishtiias.com/pdf/1739761283.pdf
- S19 BNS ss.106 and 353: https://devgan.in/bns/section/353/
- S21 DPDP timeline commentary: https://www.india-briefing.com/news/india-dpdp-compliance-timeline-enforcement-2026-27-44740.html/
- S22 SDF duties: https://sflc.in/dpdp-rules-2025-significant-data-fiduciaries-and-data-transfers/
- S23 SACHET agencies: https://msdma.mn.gov.in/cap_sachet
- S24 Cell Broadcast test: https://www.newsonair.gov.in/govt-begins-testing-new-mobile-alert-system-for-real-time-disaster-warnings
- S25 National Geospatial Policy 2022: https://www.nextias.com/ca/current-affairs/28-02-2025/national-geospatial-policy-2022-2
- S26 Geospatial Information Regulation Bill 2016: https://www.governancenow.com/news/regular-story/rs-100-crore-fine-jail-term-wrong-map-india
- S27 TCCCPR and traceability: https://www.storyboard18.com/how-it-works/trai-extends-deadline-for-commercial-message-traceability-to-december-10-49053.htm
- S28 WhatsApp India pricing and policy: https://support.myoperator.com/portal/en/kb/articles/whatsapp-has-shifted-to-per-message-pricing-effective-july-1-2025-based-on-message-categories-and-your-recipient-s-country-in-india-there-are-three-paid-categories
- S29 Telecom Act 2023: https://trilegal.com/knowledge_repository/trilegal-update-government-notifies-sections-of-the-telecommunications-act-2023/
- S30 CERT-In audit guidelines 2025: https://www.lawrbit.com/article/comprehensive-cyber-security-audit-policy-guidelines/
- S31 MeitY cloud empanelment: https://aws.amazon.com/blogs/publicsector/aws-achieves-full-empanelment-for-the-delivery-of-cloud-services-by-indias-ministry-of-electronics-and-information-technology/
- S32 GIGW 3.0: https://www.digit.in/features/general/what-is-gigw-3-0-indian-govts-design-guidelines-for-official-websites-and-apps.html
- S33 IT Rules amendments 2025: https://www.drishtiias.com/daily-updates/daily-news-analysis/information-technology-it-amendment-rules-2025/print_manually
- S34 Startup procurement: https://www.startupindia.gov.in/content/sih/en/public_procurement.html
- S35 Yes Bengaluru: https://www.deccanherald.com/india/karnataka/bengaluru/yes-bengaluru-challenge-to-make-city-future-ready-3623352 ; K-GIS: https://thesouthfirst.com/karnataka/in-a-city-under-stress-young-innovators-map-a-smarter-future-for-bengaluru-at-k-gis-exhibition/
- S36 112 ERSS: https://wayanad.keralapolice.gov.in/page/erss ; https://www.pressreader.com/india/hindustan-times-ranchi/20240416/281689734854076
- S37 GODL-India: https://cis-india.org/openness/public-consultation-for-the-first-draft-of-government-open-data-use-license-india-announced
