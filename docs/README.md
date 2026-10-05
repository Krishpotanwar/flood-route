# FloodRoute planning docs

Status: draft v0.1, 2026-10-05. Scope: India only. Branch: `claude/floodroute-project-plan-g5cntf`.

FloodRoute predicts which roads will become unusable during heavy rain and keeps rerouting dispatched fleets, emergency vehicles and citizens around them.

## Read in this order

| Doc | What it answers |
|---|---|
| [00-brainstorm.md](00-brainstorm.md) | Why this shape of product: options considered, the decision, assumptions I made in place of asking you. |
| [PRD.md](PRD.md) | What we build and for whom: users, requirements with acceptance criteria, metrics, release gates, business model. |
| [TRD.md](TRD.md) | How we build it: architecture, data model, scoring model, routing, APIs, security, infra, testing, decision records. |
| [PLAN.md](PLAN.md) | When and in what order: phases from Oct 2026 to Dec 2027, gates, workstreams, team, budget, decisions needed from you. |
| [research/](research/) | Six sourced research reports the docs above are built on. |

## Research reports

| # | Report | Headline |
|---|---|---|
| 01 | [Hazard data sources](research/01-hazard-data-sources.md) | No open source shows street-level flooding. SACHET is the one free live official feed. IMD and CWC data is chargeable for commercial use. |
| 02 | [Geospatial and routing stack](research/02-geospatial-routing-stack.md) | Self-host Valhalla on OSM. Commercial map APIs cannot take custom flood risk. Two legal traps: the 1 m / 3 m data threshold and boundary depiction. |
| 03 | [Market, users, launch cities](research/03-market-users-competition-launch.md) | Beachhead is dispatched fleets in Bengaluru. White space is predicted road-segment passability by vehicle class. Google's 20 km flash-flood forecast is the main strategic risk. |
| 04 | [Prediction, routing, architecture](research/04-prediction-routing-architecture.md) | Layered model: static prior, rainfall trigger, live evidence. Time-dependent, risk-aware routing with hysteresis. |
| 05 | [Legal and compliance](research/05-legal-regulatory-compliance.md) | DPDP duties start about 13/14 May 2027. Liability is the sleeper risk (Bareilly precedent). Do not scrape IMD. |
| 06 | [Design direction](research/06-design-direction.md) | Built with taste-skill, impeccable and apple-design. Five risk states including "unknown". Stale data is a critical state. |

## How the research was done

- Brainstorming skill (Superpowers): classified the work as **architectural**, so the output is a written spec and plan. It is not enabled in the cloud session, so its method was followed from the source on GitHub.
- Six research subagents ran in parallel and wrote the reports above. Claims are tagged verified (with a URL) or unverified. Estimates are labelled as estimates.
- Design skills applied: taste-skill, impeccable and apple-design (see report 06).
- Ponytail skill at level `ultra` is installed at `.claude/skills/ponytail/` and governs code and dependency choices. It does not shorten these documents.

## Reading the confidence tags

- **[V]** seen in a fetched source. Many are secondary or news reports.
- **[U]** unverified or recalled. Confirm before relying on it.
- **[EST]** an estimate or judgement call, not sourced.

Several load-bearing facts are still unverified: IMD API commercial terms, vehicle-depth thresholds for Indian vehicles, Google's flash-flood coverage of Indian cities, DPDP commencement dates, and any 112/ERSS integration API. Each is tracked as an open question in the PRD, TRD and PLAN.

## Not legal advice

The legal report is product-planning research. Items marked **[COUNSEL]** need an Indian lawyer before launch.
