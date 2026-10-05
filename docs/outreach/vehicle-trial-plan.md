# Vehicle passability trial plan

Draft v0.1, 2026-10-05. How to learn real passable depths for Indian vehicles **without putting anyone at risk**, and how the result replaces the provisional table in PRD section 11.2. Nothing here has been proposed to anyone. Not legal advice. The safety lead, the test partner's safety officer and counsel must review before any Stage 2 contact.

**Tags.** **[V url]** = I opened that page or document this session. **[U]** = unverified (*secondary* = a news or vendor page I opened, *snippet* = search-result text only). **[EST]** = my estimate or starting proposal. URLs are written without `https://`.

## Non-negotiables

1. **We never ask, pay, reward or encourage anyone to drive, ride or walk into floodwater**, in any stage, for any reason.
2. **We never ask for new photos or video taken in or near floodwater.** Only records that already exist. We do not publish or promote videos of vehicles in water.
3. **No person is in or on a test vehicle in water in Stage 2.** Where weight matters, occupants are represented by weights; the UNSW tow-tank tests used sandbags [V unsw.edu.au WRL TR2017/07, see Sources].
4. No tests on public roads, in natural water bodies, or in flowing water.
5. A result is never shown as a "safe depth". It is "a stall was seen at X cm in test conditions". Product thresholds stay conservative (PRD principle 1: never "safe").
6. The test partner's safety officer has the final word on stopping. Where their rules are stricter than ours, theirs apply.

## 1. What we need to learn

PRD 11.2 holds provisional, mostly [U] thresholds for two-wheelers, autos, cars, SUVs, ambulances and buses. No Indian vehicle-depth guidance was found (research 04). The only controlled precedent read here is Australian: in tow-tank tests, traction "decreases rapidly with floodwater depths above the vehicle's floor pan level", a Toyota Yaris of about 1.0 tonne "completely floated in water 0.6 m deep" and a Nissan Patrol over 2.4 tonnes at 0.95 m [V unsw.edu.au/content/dam/pdfs/engineering/civil-environmental/water-research-laboratory/publications/WRL-TR2017-07-Vehicle-Stability-Testing-for-Flood-Flows.pdf]. Those vehicles are not Indian, and flotation is not the same failure as an engine stall. For small Indian vehicles the first failure is more likely water reaching the air intake, exhaust or electrics [U, general engineering].

Per vehicle class we want: depth at first fault, depth at stall, whether restart works, and what makes models differ. Velocity, debris, open manholes and electrical hazards stay outside any tank test, so the hidden-hazard flag in PRD 11.2 stays.

Pedestrians and children are never tested. Their rows stay as literature values.

## 2. Stage 1: retrospective logs (no one is exposed because of us)

Start now, alongside the P1 and P2 interviews. PLAN item 9 already asks fleet partners for stall data.

### Sources and what to ask

| Source | What they may hold | Ask | Handling |
|---|---|---|---|
| Delivery, cab and school-bus fleets | Breakdown and recovery logs, cancelled-trip reasons, incident reports, telematics stall flags | Existing records of rain-related stalls and recoveries, last [PLACEHOLDER: 3] seasons | De-identify at source before transfer |
| 108 ambulance operators | Delay reasons, breakdown logs, rain-related reroutes. In Karnataka the state launched its own 108 command and control centre on 25 May 2026, replacing the private operator GVK EMRI [U secondary: etvbharat.com/en/state/karnataka-government-on-sunday-launched-state-owned-108-arogya-kavacha-centralised-command-and-control-centre-enn26052503708]; elsewhere EMRI, BVG or ZHL [U] | Same, with no patient data at all | Written data-sharing agreement; no patient identifiers |
| Traffic police and towing | Recovery and tow logs; ASTraM waterlogging events [U snippet] | Aggregated events with place and time | Segment-level only |
| Workshops and service centres | Water-ingress repair job cards: model, fuel, damage, water mark height | Anonymised job-card extracts | No customer names, no plates |
| Motor insurers (later) | Flood-claim aggregates by class | Aggregates only | Pilot-stage conversation |

### Fields (one row per event)

| Field | Notes |
|---|---|
| event_id, source_id | Pseudonymous |
| date, time_bucket | Day, and 15-minute bucket [EST] |
| location | Road segment ID or a 100 m grid cell [EST], never a GPS point or a track |
| vehicle_class | PRD 11.2 classes |
| make, model, year, fuel, transmission | Optional, fleet level |
| engine_state | running, idling, off, unknown |
| depth_cm and depth_method | **A** measured gauge or fixed marker; **B** high-water mark measured on the vehicle or a wall by a technician after recovery; **C** an existing photo with a known reference object; **D** driver's estimate by body landmark; **E** unknown. Only A and B count toward threshold changes |
| water_movement | still, flowing, unknown |
| speed_band | stopped, walking pace, faster, unknown |
| outcome | passed, stalled, turned back, stuck, floated or swept, damaged, towed |
| recovery_minutes | If known |
| consequence | none, delay, damage, injury (no medical detail) |
| notes | Free text, scrubbed of names and numbers |

**Never collected:** names, phone numbers, registration plates, patient or rider identities, exact GPS tracks, photos showing people or plates.

**Method B** (a technician measures the water line on a recovered vehicle) needs no new exposure and is the best retrospective depth source [U: idea to validate with one workshop]. **Landmark card:** on dry ground, measure each fleet model's hub centre, door sill, floor, air-intake inlet and exhaust tip once, so driver estimates (method D) convert to centimetres and Stage 2 can generalise by geometry [EST].

### Limits to state in every report

- Logs over-represent failures. "Passed" events are rarely recorded, so Stage 1 can give the **lowest depths at which a class was seen to stall**, and failure modes. It cannot prove a depth is passable.
- Depth in self-reports is noisy. Say so, and weight by method.
- Minimum evidence before a class row changes: [PLACEHOLDER: 30] events with method A or B from at least two independent sources [EST].

### Legal handling [COUNSEL]

Each source remains the fiduciary for its own records and signs a data-sharing agreement. We receive de-identified extracts only, stored in India. Whether location rounded to a segment is still personal data is for counsel. DPDP core duties begin about 13/14 May 2027 (research 05, [U] to confirm), so build the habits now.

## 3. Stage 2: supervised tests at an automotive test partner

### Partner screening

Must have: a controlled water tank, wading track or tow tank with adjustable depth; trained staff and an independent safety officer; a written safety case and insurance; the ability to run **unoccupied** tests; depth sensors with calibration records; clear data-ownership terms; willingness to let aggregated results be published; HV-qualified staff if electric vehicles are included.

Candidates to approach, **none contacted, none verified as willing or equipped**:
- ICAT, Manesar. A 2019 news report says its new site has a water wading track to test underbody seepage and battery security in an EV [U secondary: autocarindia.com/car-news-amp/icat-sets-up-new-test-track-at-manesar-414846].
- ARAI, Pune; GARC, Chennai. Both are named NATRiP centres [U snippet]. Wading capability unknown.
- NATRAX, Pithampur. Its site lists 14 tracks and 5 labs and no wading or flood facility [V natrax.in].
- An OEM proving ground. A search result says the Mahindra SUV Proving Track has water wading and rain simulation [U snippet].
- A university hydraulics lab with a tow tank or flume, as in the UNSW precedent [PLACEHOLDER: name].

Contact routes are not verified. The founder asks each for its testing-enquiry route before writing.

### Method options, safest first (the partner chooses; we do not ask for the last)

1. **Unoccupied, held or slowly winched through stepped depths, engine idling.** UNSW's team winched full-size vehicles in a tow tank, with occupants as sandbags, filling the basin in under two minutes to limit ingress [V WRL TR2017/07]. Default for Stage 2.
2. **Remote-driven or robot-driven at walking speed** under the partner's accredited setup [U].
3. **A professional test driver under the partner's own accredited wading procedure.** Only if the partner's written safety case covers it and our counsel and insurer have signed off [COUNSEL]. FloodRoute does not request this.

Tank water is still, clean and level. Real floods are not. Results can only lower our thresholds or support the current ones, not certify roads.

### Test matrix [EST]

Classes from PRD 11.2, two to three representative models each: scooter and commuter motorcycle (including one above 150 cc), auto-rickshaw (CNG and electric where available), hatchback, sedan, SUV, van-based ambulance, and bus or truck if budget allows. Electric and hybrid vehicles only with OEM consent and HV-qualified staff. A manufacturer's declared wading depth, where published, is a plausibility check and never a safe depth [U].

### Static measurements per model (dry ground)

Ground clearance, floor-pan height, air-intake inlet height, exhaust-tip height, ECU and fuse-box location, tyre size, kerb weight, any snorkel or modification, with photos.

### Procedure outline (partner writes the detail)

Raise water in steps (suggest 2 cm for two-wheelers and autos, 5 cm for cars [EST]); hold [PLACEHOLDER: 60 s] per step; record the first misfire, warning lamp, stall or cabin ingress; **stop at the first of these**; no restart attempts in water; inspect for ingress before any restart.

### Fields (one row per test)

| Group | Fields |
|---|---|
| Test | test_id, date, facility, test director, safety officer, method (1, 2 or 3), speed, engine state |
| Vehicle | class, make, model, year, fuel, mileage, condition, modifications |
| Geometry | the static measurements above |
| Water | depth resolution, sensor type and calibration date, water type, temperature |
| Events | time, depth at each event: misfire, warning lamp (which), stall, restart result, cabin ingress, ABS or ESC fault, HV isolation fault |
| Outcome | maximum depth reached, reason for stopping, damage found afterwards |
| Admin | video reference (facility's own, not for release), notes |

## 4. Stop rules and ethics

**Minimum stop rules** (the partner may add stricter ones; engineering details are [U] and the partner's safety officer decides):
1. Depth reaches the ceiling set by the partner's safety officer for that class.
2. First stall, misfire pattern, electrical or ECU warning, or HV isolation fault. The vehicle's test ends.
3. Any spark, smoke, burning smell, fuel or oil sheen, unexpected movement, rigging or winch fault, loss of communications, or lightning.
4. Any person asks to stop. Any staff member is unwell or unfit.
5. After an EV test, quarantine and inspect per the partner's procedure.
6. Incident: stop all testing, report to the partner and to our counsel within [PLACEHOLDER: hours], review before resuming.

**Governance.** Test director and an independent safety officer with stop authority; FloodRoute attends as observer. Insurance confirmed by both sides. Staff consent. Written agreement on data ownership, credit and aggregated publication [DECISION]. Counsel reviews liability for commissioning tests, the insurance position and the wording of any published result [COUNSEL].

## 5. How results update PRD section 11.2

1. **Evidence note per class**: n, methods, sources, limits, dates. Location [PLACEHOLDER: set by the main session; docs/research or docs/outreach/results].
2. **Rule** [EST, starting proposal]. *Unusable* = the lower of (a) the 10th percentile of reliable field stall depths (methods A and B) and (b) the lowest stall depth among tested models in the class, minus a safety margin. Starting margin: the larger of 5 cm or 25% [EST]; the safety lead and counsel set the real margin. *Caution* = 50% to 75% of Unusable [EST], which matches the spread in today's table.
3. **Asymmetry.** One credible source may lower a threshold. Raising one needs two independent sources, the safety lead's sign-off, and a counsel read of the advisory wording.
4. **Edit.** The PRD owner replaces Caution and Unusable and changes the Basis cell from [U] to a reference such as `[V trial T-03, n=…, date]` or `[FIELD n=…]`, adds a changelog line, and keeps the section titled "provisional" until every row has a trial basis. Tenant profile configuration (FR-R7) is updated, replay tests are re-run, and a release note goes to partners. **I cannot edit the PRD; the main session applies this.**
5. **Re-validate** after any model or class change, each year, and when new vehicle types such as electric two-wheelers appear in pilot fleets.

## 6. Order, decisions, counsel

| When | Step |
|---|---|
| Oct to Nov 2026 | Ask for Stage 1 records in P1 and P2 interviews; sign data-sharing terms; start the landmark card with one fleet |
| Dec 2026 | First Stage 1 review; shortlist test partners; ask for quotes [PLACEHOLDER: Rs] |
| Jan to Mar 2027 | Stage 2 if budget and partner exist [EST]; update PRD 11.2 before G1 |

**Founder decides:** which sources to approach first; partner shortlist and budget; who is the safety lead; whether to publish aggregated results. **Counsel:** liability and insurance for commissioned tests; DPDP treatment of the logs; wording of any published result.

## Sources

- UNSW Water Research Laboratory, Vehicle Stability Testing for Flood Flows, WRL TR2017/07, May 2017 [V unsw.edu.au/content/dam/pdfs/engineering/civil-environmental/water-research-laboratory/publications/WRL-TR2017-07-Vehicle-Stability-Testing-for-Flood-Flows.pdf]. Its authors repeat the advice "Never drive, ride or walk through floodwater".
- NATRAX [V natrax.in]. ICAT news report [U secondary, URL above].
