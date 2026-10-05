# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

Installable PWA (Android first), desktop console, marketing site.

## Users
- Citizens, mainly two-wheeler riders and car drivers in Indian cities in heavy rain: one hand free, wet screen, sun glare between showers, 2 to 3 GB RAM Android, patchy data, Hindi or a regional language first.
- Dispatchers and ICCC operators (ambulance, fire, police, drainage): trained, on shift for hours, multi-monitor, accountable for every closure and assignment.
- Administrators who review decisions afterwards.

## Product Purpose
Predict which roads become unusable in heavy rain, say so early and honestly, and keep rerouting citizens and emergency vehicles. Success: a citizen avoids a flooded underpass because they understood a message in 3 seconds; an ambulance is never routed into a road we already knew was closing; every closure is auditable.

## Positioning
A flood-specific layer, not general navigation. Honest about uncertainty and data age, light enough for weak phones, reachable by SMS and WhatsApp when the app is not.

## Operating Context
Rain at night, underpasses, wet fingers, power cuts, congested networks, alerts mid-ride. Dim control rooms staffed around the clock. Feeds can be late or wrong, and the interface must say so.

## Capabilities and Constraints
- Risk levels: safe, watch, risky, impassable, plus unknown. Passability depends on vehicle class.
- Offline last-known snapshot. SMS (70-character Unicode segments for Indic, DLT-registered templates) and WhatsApp fallbacks.
- Never claim accuracy figures, partner cities, testimonials or response-time wins that are unmeasured. Illustrative data is labelled "sample".
- Every closure override has a reason, an expiry and an audit entry.

## Brand Commitments
Voice: calm, direct, local, specific. Tone follows stakes: plain and brief in danger, warmer in empty and success states, never jokey about risk. Three words: steady, plain, accountable.
Avoid: disaster-movie red styling, AI-purple gradients, glass everywhere, beige craft palettes, cute copy, fake-precise numbers.

## Evidence on Hand
Research in docs/research. IMD's four colour warnings (green no action, yellow be aware, orange be prepared, red take action) are the public's mental model. CAP severity (Extreme, Severe, Moderate, Minor) and certainty (Observed, Likely at 50% or more, Possible below 50%) are the interoperable vocabulary. No user-research or accuracy evidence exists yet; do not invent any.

## Product Principles
1. Honest over reassuring: unknown is never shown as safe; data age is always visible.
2. Glance, then act: one fact and one action, readable in 3 seconds in rain.
3. Never color alone: icon, label, line style and position carry every level.
4. Works when everything else does not: weak phone, weak network, no app.
5. People stay in control: undo, no traps; advice for citizens, auditable commands for operators.
6. Local first: language, landmarks, vehicle type, familiar numerals.

## Accessibility & Inclusion
WCAG 2.2 AA minimum, AAA for risk text. Targets 48 px (56 px emergency actions). Drag always has a non-drag alternative. Screen reader, voice guidance, reduced motion, reduced transparency, forced colors. Grade 6 to 8 reading level. Hindi plus the launch city's language from day one.
