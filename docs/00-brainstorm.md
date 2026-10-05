# Brainstorm: what shape should FloodRoute take?

Method: Superpowers brainstorming skill, followed from its public source. Classification: **architectural** (new system, new structure), so the output is a written spec (PRD, TRD) and a plan. No implementation starts before you approve the decisions in section 5.

## 1. The ask, restated

Predict which roads will become unusable during heavy rain, and keep rerouting people and emergency vehicles. India only at first. Deliverables: plan, PRD, TRD, built from sourced research and the three design skills.

## 2. What the research changed

The original one-line pitch hides four hard facts.

1. **Nobody observes street-level flooding.** Everything open is rainfall, river stage or coarse alerts (report 01). The product has to build road risk itself and earn its own ground truth.
2. **Google already forecasts urban flash floods**, at a 20 km grid with no road-level output, launched 12 Mar 2026 (reports 03, 04). The gap is road-segment passability by vehicle class, with routing attached. That gap will narrow, so speed and local data deals matter.
3. **Wrong advice can kill, and Indian courts have named a maps executive in an FIR** after the Bareilly bridge deaths (report 05). Liability shapes the product, not only the terms of use.
4. **Government is slow and the free consumer market has no revenue.** Delivery and cab platforms already pay for rain surges and have the cleanest buying path (report 03).

## 3. Options considered

| Option | What it is | For | Against | Verdict |
|---|---|---|---|---|
| A. Citizen app first | "Waze for floods": map, crowd reports, rerouting for everyone | Big reach, brand | Competes head-on with Google Maps defaults. No revenue. Cold-start crowd data. Highest liability per user. | No |
| B. Dispatch and fleet first | Console and API for ambulance operators, traffic control rooms and delivery or cab fleets, plus a WhatsApp channel for citizens | Paying buyers exist. Fleets give probe data. Control rooms give labels and credibility. Human in the loop limits harm. | Smaller top-of-funnel. Needs partnerships. Seasonal revenue. | **Recommended** |
| C. Data and API layer for map platforms | Sell a risk layer to Mappls, Ola Maps and others | Light product, strong distribution | Ola and Google terms bar ML and custom edges. Few buyers, long cycles. Hard to prove value alone. | Later channel |
| D. Government command-centre first | Sell to ICCCs and state disaster agencies | Mission fit, strong credibility | 9 to 18 month cycles. Smart Cities Mission closed 31 Mar 2025, so budgets are unclear. Low ARPU. | Anchor partners, not revenue source |

**Decision: B, with C and D as channels and citizens served through WhatsApp and a light PWA.** Reasoning: it gets revenue in 3 to 6 months, field validation with real routes, and a defensible safety story before any public rollout.

## 4. Recommended shape in one paragraph

A segment-level flood risk engine for Indian cities, starting in **Bengaluru**, that scores each chronic hotspot and underpass for the next 0 to 120 minutes per vehicle class. It feeds a dispatcher console, a fleet API and a WhatsApp bot, and reroutes with hysteresis so routes do not flap. It runs in **advisory mode only in 2027**, labels every output as official, model or crowd, and shows unknown and stale data honestly. Chennai runs in shadow mode through the Oct to Dec 2026 north-east monsoon to collect labels. Mumbai and Gurugram follow in the 2027 south-west monsoon.

## 5. Decisions I need from you

Each has a default I used, so work can continue. Please confirm or change.

| # | Decision | Default used | Why it matters |
|---|---|---|---|
| D1 | Beachhead city | Bengaluru (ties Mumbai on score, wins on B2B density, KSNDMC data, less incumbent competition) | Drives data deals, partners, hotspot library |
| D2 | First paying customer type | Delivery or cab platform via API, with one 108 or traffic-control-room design partner | Shapes MVP scope and pricing |
| D3 | Advisory mode only in 2027 | Yes. No automatic ambulance rerouting without human confirmation | Liability and safety case |
| D4 | Legal entity | Indian-owned and controlled entity | Needed for fine-resolution geospatial data rules, DPIIT recognition, DLT registration |
| D5 | Team and runway | 4 to 6 people for 9 months (see PLAN) | Sets scope and sequencing |
| D6 | Stack language | Python backend, TypeScript clients | One backend language, matches the data work |
| D7 | Cloud | AWS Mumbai primary, Hyderabad backup region | Government customers want India residency |
| D8 | Citizen product weight | WhatsApp bot plus light PWA, no native Android until fleets need it | Keeps the shell small and the team focused |
| D9 | Name and domain | FloodRoute as a working name | Trademark and domain check not done |
| D10 | Open source posture | Closed core, upstream OSM contributions (`flood_prone=yes`) | ODbL share-alike boundary needs counsel |

## 6. Questions I would have asked, and the assumption I made

The skill asks one question at a time. To avoid stalling a first pass I answered these myself.

- Who is building and what is the budget? Assumed a small founding team and seed-stage budget (see PLAN).
- Is there a design-partner relationship already? Assumed none. PLAN schedules 8 to 10 discovery interviews first.
- Is the goal revenue, public good, or both? Assumed both, with revenue from fleets funding public WhatsApp access.
- Is the founding entity Indian-owned? Assumed yes.
- Are you open to scope cuts that reduce coverage? Yes: the MVP covers about 100 to 300 chronic hotspot segments and all underpasses in one city, not the whole road graph.

## 7. What is deliberately not in the first release

Native iOS app, voice assistant, automatic ambulance rerouting, public closure statements that contradict an official closure, city-wide hydrodynamic modelling, hill-road landslide routing, and a marketing site beyond one static page.

## 8. Next step

Approve or edit section 5. Then [PRD.md](PRD.md) and [TRD.md](TRD.md) become the baseline and PLAN phase 0 starts.
