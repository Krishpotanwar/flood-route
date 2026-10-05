# Design-partner term sheet (non-binding outline)

Draft v0.1, 2026-10-05. For a pilot with a control room or a fleet.

> **This is not legal advice and it is not an offer.** It is a non-binding outline for discussion. It binds nobody until counsel has drafted a proper agreement and the competent persons of both sides have signed it. **Every clause marked COUNSEL needs an Indian lawyer before it is shown to a partner.** Nothing here has been sent.

**Tags.** **[V url]** = I opened that official page this session. **[U]** = unverified (recalled, or only in research docs). **[EST]** = my proposal. **[PLACEHOLDER]** = a number or name the founder or counsel fills. URLs are written without `https://`.

**Variants.** **[CR]** = clause for a control room or authority. **[FLEET]** = clause for a delivery, cab or school-bus fleet. Unmarked clauses apply to both.

**Source of the positions.** PRD section 13 (offer partners override rights, no exclusivity on government data, open accuracy reporting, a clear processor and fiduciary split), PRD principles 1 to 4, PRD FR-C3, FR-C4, FR-RT8, FR-M4, TRD section 16 and research 05 section 7. Nothing is invented beyond those, except where marked [EST].

## A. Clauses

| # | Clause | Proposed position (non-binding) | Counsel |
|---|---|---|---|
| 1 | Parties and authority | [COMPANY LEGAL NAME] ("FloodRoute", CIN [PLACEHOLDER]) and [PARTNER LEGAL NAME]. [CR] The signatory is the competent authority under the department's rules; internal approvals are the partner's to obtain. Nothing binds until both sides sign. | COUNSEL |
| 2 | Purpose and scope | A pilot of a road-by-road rain advisory for [AREA, for example the agreed Bengaluru hotspot and underpass list] and [VEHICLE CLASSES]. Live advisory pilot April to June 2027. An optional observer period from [DATE] to March 2027 where FloodRoute produces predictions and logs them with no operational use. Out of scope: automatic dispatch, public closure orders, cell broadcast. | COUNSEL |
| 3 | Advisory-only mode | All outputs are advisory. Wording is "likely", "avoid if possible", "clear as of [time]", never "safe" (PRD principle 1). Each output is labelled Official, FloodRoute model or Crowd. Unknown and Not assessed are shown as such, never as clear. No automatic rerouting. [CR] A named dispatcher confirms every ambulance assignment (PRD FR-RT8). | COUNSEL |
| 4 | Data sharing both ways | See table B. Only the listed data moves. Each flow has a purpose, a format, a retention period and a named owner on each side. | COUNSEL |
| 5 | Roles under DPDP | See table C. Roles are fixed in writing before any personal data moves. A processor contract is in place before processing starts. | COUNSEL |
| 6 | Override rights | The partner's authorised operators may close, reopen or force Watch on any segment, with a reason and an expiry (default 2 hours); arterial roads need a second operator (PRD FR-C3). Partner overrides outrank the model. Every override is logged append-only and exportable (FR-C4). The partner may switch FloodRoute advisories off for its own users at any time. FloodRoute may freeze outputs to "advisory off" (TRD 16) and will tell the partner within [PLACEHOLDER] minutes. | COUNSEL |
| 7 | No exclusivity on government data | The partner owns its data and may share it with anyone, including other vendors. FloodRoute claims no ownership of government or public data and will not ask the partner to assign rights in it. Third-party feeds (IMD, SACHET, KSNDMC and others) stay under their own terms; neither party can grant rights it does not hold. The partner is free to use other tools. | COUNSEL |
| 8 | Accuracy reporting | After each significant storm: an event note covering what was predicted, what happened, misses, false alarms and overrides. Each season: POD, FAR, lead time, calibration slope, override rate and data freshness, by vehicle class and area (PRD FR-M4, section 9). Shared with the partner first. A summary may be published only with the partner's consent. PRD targets are goals, not guarantees: **no accuracy warranty.** | COUNSEL |
| 9 | Liability framing | The partner remains responsible for operational decisions and instructions to crews or riders. FloodRoute provides decision support and does not warrant fitness for emergency dispatch or any outcome. Each party answers for its own negligence to the extent the law allows. Limitation of liability, caps and indemnities [PLACEHOLDER: amounts and structure]. FloodRoute holds technology E&O and cyber cover with bodily-injury and "advice" exclusions checked (TRD 16) [PLACEHOLDER: policy]. Both sides note that liability for death caused by negligence is not something a contract can exclude (BNS s.106, research 05 [U secondary]), and that Indian courts have named platform executives in criminal complaints after a navigation death (Bareilly, research 05 [U secondary]). | COUNSEL |
| 10 | Safety and incident protocol | A shared hazard log. A defined incident: harm or near-miss after following an advisory. On an incident: preserve logs under legal hold, notify each other and insurers, flag or pull the advisory, issue a correction, joint review within [PLACEHOLDER] days. No public statement naming the other party without prior notice, except as law requires. Decision log (inputs, model version, advisories shown) kept one year (PRD FR-M1). | COUNSEL |
| 11 | Messaging and public statements | FloodRoute messages users only in its own name, from its own WhatsApp and SMS accounts. The partner's name or logo is used only with written consent. FloodRoute never claims official status and never originates cell-broadcast alerts (PRD FR-L4). **The partner does not send through FloodRoute's accounts**: WhatsApp's policy prohibits use of its Business Platform by law-enforcement agencies [V whatsappbusiness.com/policy]. | COUNSEL |
| 12 | Security and hosting | Data stored and processed in India; encryption in transit and at rest; access logs; 180-day ICT logs kept in India; incident reporting to CERT-In within 6 hours and DPDP breach duties [U: research 05 reports both as verified, not re-opened here; DPDP dates to confirm]; annual VAPT by an empanelled auditor; a named security contact each side; sub-processors listed and notified. | COUNSEL |
| 13 | Fees, procurement and integrity | Pilot at no charge unless a separate paid-pilot agreement is signed. [CR] No gifts, inducements or promise to purchase. Any later purchase follows GeM or tender rules; DPIIT relaxations apply only where the tender says so [V startupindia.gov.in/content/sih/en/public_procurement.html]. Conflict-of-interest declarations. [CR] RTI: documents may be disclosable, so each side marks confidential material [U]. | COUNSEL |
| 14 | Rider and driver welfare [FLEET] | The partner will not penalise a rider or driver for declining a flagged road, or for delay caused by following an advisory, and will not use an advisory to press anyone to enter floodwater. | COUNSEL (wording), founder |
| 15 | Term, reviews, exit | Pilot term to 30 June 2027 [EST], reviewed weekly (PLAN phase 2) and at 30 June. Either side may end it on [PLACEHOLDER] days' notice. Immediate suspension is allowed for safety or legal reasons. On exit: partner data is returned or deleted within [PLACEHOLDER] days; audit and processing logs are kept for the legal minimum (one year under DPDP Rules 6 and 8(3), research 05 [U, COUNSEL]); data export in open formats (GeoJSON, CSV, CAP). No lock-in. | COUNSEL |
| 16 | Confidentiality, IP, law | Mutual confidentiality. Each side keeps its own IP. Who owns model improvements trained on de-identified data: [PLACEHOLDER, a real negotiation point]. Governing law India; forum [PLACEHOLDER]. | COUNSEL |

## B. Data flows

| Flow | From to | Data | Format and cadence | Purpose | Personal data? | Retention |
|---|---|---|---|---|---|---|
| D1 | Partner to FloodRoute | Hotspot and underpass lists; closure and diversion SOPs; historical closure and waterlogging logs (de-identified); closed and reopened labels with time | GeoJSON or CSV; one-off, then weekly labels | Calibrate and validate the model | Mostly no; confirm per field | Pilot plus [PLACEHOLDER] |
| D2 [FLEET] | Fleet to FloodRoute | De-identified stall and breakdown logs (vehicle-trial-plan Stage 1); probe speed buckets by segment and time with at least 5 contributors (PRD FR-E3) | CSV or API; daily or streamed | Calibrate; supply evidence | Unclear after aggregation [COUNSEL] | [PLACEHOLDER] |
| D3 [CR] | Control room to FloodRoute | Optional unit class and position for route checks. **Never patient data.** | API; live | Console shows flood-safe ETA (FR-C2) | Yes if tied to a person | Transient, [PLACEHOLDER] hours |
| D4 | FloodRoute to partner | Risk state per segment and vehicle class at 0, 30, 60 and 120 minutes, confidence, data age, source labels | Console, API, webhooks; each scoring cycle | Decision support | No | Per partner policy |
| D5 | FloodRoute to partner | Audit log, decision log, override history | Export on demand | Review and oversight | Yes (partner staff IDs) | One year |
| D6 | FloodRoute to partner | Event notes and seasonal accuracy reports | PDF and CSV | Transparency | No | Indefinite |
| D7 | FloodRoute to partner | Citizen reports: corroborated segment-level only; individual reports only with the user's separate "share with authorities" consent (PRD FR-M2) | API | Situation awareness | Only with consent | [PLACEHOLDER] |
| D8 | Official feeds | IMD, SACHET, KSNDMC and others | Under their own terms | Inputs | No | Per source terms |

## C. Processor and fiduciary split [COUNSEL for every row]

| Data | Decides purpose and means | FloodRoute is | Partner is | Note |
|---|---|---|---|---|
| Partner's operational records (D1, D3) | Partner | Data Processor, on written instructions, under a contract; fiduciary stays responsible (DPDP s.8, research 05 [U: Act not re-opened]) | Data Fiduciary | No own use beyond agreed de-identified learnings |
| FloodRoute's citizen users (WhatsApp, PWA, reports, photos) | FloodRoute | Data Fiduciary | Recipient of aggregates, or of individual data only with consent | Consent is the baseline; s.7(f) and s.7(h) only as a supplement for declared events and SOS (PRD NFR, research 05 [COUNSEL]) |
| Fleet probe data (D2) | Fleet for the raw data | Processor for any aggregation it performs; or independent fiduciary if it receives only aggregates | Fiduciary for raw riders' data | Whether k-anonymous buckets are personal data is a counsel question |
| Operator audit logs (D5) | Partner | Processor | Fiduciary (its own staff) | |
| [CR] government partner | The authority | Processor | Fiduciary; its processing may rest on a legitimate-use ground or a state-instrumentality notification (s.7 and s.17(2), research 05 [U]) | Counsel decides which applies to this authority |

DPDP core duties begin about 13/14 May 2027 and land mid-pilot (PLAN, research 05 [U] to confirm). The agreement should be written to the stricter reading from the start.

## D. What the founder decides before talking to any partner

1. Observer period or live advisory only, and the start date.
2. Whether the pilot is free for both variants, and what a paid conversion would look like (PRD section 12 numbers are [EST]).
3. Which clauses are negotiable and which are not. Suggested non-negotiable: 3 (advisory only), 6 (overrides outrank the model, with audit), 7 (no exclusivity), 8 (open accuracy reporting, no warranty), 11 (no use of our messaging accounts as theirs), 14.
4. Insurance in place before the live window (G1).
5. Who at FloodRoute is the named safety lead.

## E. Questions for counsel, in order

1. Is "advisory, not directive" enough protection given the Bareilly precedent and BNS s.106? Does the free-tier Consumer Protection Act exclusion matter for a B2B pilot?
2. Clause 9: caps, indemnities, and what is enforceable in India for a safety-critical advisory.
3. Table C: roles for each flow, and whether k-anonymous probe buckets are personal data.
4. Clause 6: duties created by a kill switch; who bears the risk when advisories are paused during a storm.
5. Clause 11: WhatsApp's government and law-enforcement rule, and whether relaying official alerts is allowed.
6. Clause 13: RTI, integrity pact and procurement rules for a free pilot with a government body.
7. Clause 15: log retention of one year against minimisation.
8. A short plain-language version for a control room that cannot sign a long contract: a letter of support plus an MoU.
