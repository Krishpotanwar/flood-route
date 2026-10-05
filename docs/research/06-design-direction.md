# FloodRoute: Design Direction Brief

Date: 2026-10-05. Method: read in full taste-skill v2 (`skills/taste-skill/SKILL.md`, plus README, CHANGELOG, stitch variant), impeccable (`SKILL.src.md`, `craft-floor`, `operate`, `shape`, `init`, `document`, `harden`, `adapt`, `typeset`, `colorize`, `animate`, `layout`, `optimize`, `clarify`, `critique`, repo PRODUCT.md/DESIGN.md, detector rule list), apple-design and its siblings emil-design-eng and mobile-native. Palette numbers below were computed (WCAG contrast plus Machado CVD simulation), not eyeballed.

Two findings shape everything:

1. **taste-skill v2 declares dashboards, dense product UI, multi-step flows and native mobile out of scope (its section 13).** It governs the landing site fully. For the citizen app and dispatcher console we apply only its locks, bans and checklist, and take structure from impeccable's Operate mode.
2. **Impeccable chooses mode per surface.** Landing is Persuade. Citizen app and console are Operate, where "the tool should disappear into the task", motion is 150 to 250 ms, and there are no page-load sequences.

---

## A. Design read and dials

| Surface | Design read (taste section 0.B) | VARIANCE | MOTION | DENSITY |
|---|---|---|---|---|
| Citizen PWA | Reading this as: map-first safety tool for a stressed, often one-handed rider or driver in rain, with a calm, plain, trust-first language, leaning toward own tokens on Radix primitives and a MapLibre map. | 2 | 3 | 4 |
| Dispatcher console | Reading this as: 24-hour operations cockpit for trained ICCC operators on large screens, with a quiet, exact, instrument-panel language, leaning toward own tokens on Radix primitives and dense tables. | 2 | 2 | 8 |
| Marketing site | Reading this as: public-sector-adjacent landing for citizens, city officials and procurement, with a sober editorial trust-first language, leaning toward Tailwind v4 utilities and one real product preview. | 5 | 4 | 3 |

Reasoning:
- **Citizen: 2/3/4.** Taste's own trust-first row is 3-4 / 2-3 / 4-5. Variance drops to 2 because the layout (map plus bottom sheet) is a learned pattern and Apple's familiarity principle says break it only if proven better. Motion 3 means feedback, sheet physics and one reroute highlight only. Density 4 keeps one decision per screen.
- **Console: 2/2/8.** Predictability is a feature at 3 a.m. Density above 7 triggers taste rules: no card containers, hairlines between rows, tabular numerals for all numbers.
- **Site: 5/4/3.** Asymmetric split hero (variance above 4 bans centered), but trust beats spectacle. Motion above 3 requires reduced-motion handling and "motion shown", so the single motion moment is a real reroute playing on a real map component.

---

## B. PRODUCT.md (drop into repo root)

```markdown
# Product

<!-- impeccable:product-schema 1 -->

## Platform
adaptive-web (installable PWA, Android first; desktop web console; marketing site)

## Stack
React 19 + Vite PWA (citizen, console), Astro or Next static (site), MapLibre GL, Tailwind v4, Radix primitives, Motion.

## Users
- Citizens, mainly two-wheeler riders and car drivers in Indian cities during heavy rain: one hand free, rain on screen, sun glare between showers, 2 to 3 GB RAM Android phones, patchy data, Hindi or a regional language first, English second.
- Pedestrians, delivery riders, bus and school-van drivers, and family members checking on someone's commute.
- Emergency dispatchers and ICCC operators (ambulance, fire, police, municipal drainage): trained, on shift for hours, multi-monitor, keyboard-capable, accountable for every closure and assignment.
- City administrators who review decisions afterwards.

## Product Purpose
Predict which roads will become unusable in heavy rain, say so early and honestly, and keep rerouting people and emergency vehicles as conditions change. Success: a citizen avoids a flooded underpass because of a message they understood in under 3 seconds; an ambulance never gets routed into a road we already knew was closing; every closure is auditable.

## Positioning
Not a general navigation app. A flood-specific layer that is honest about uncertainty and data age, works on weak phones and weak networks, and is usable through SMS and WhatsApp when the app is not.

## Operating Context
Rain at night, flooded underpasses, wet fingers, power cuts, congested networks. Alerts arrive while riding. Control rooms are dim and staffed around the clock. Forecasts and sensor feeds can be late or wrong, and the interface must say so.

## Capabilities and Constraints
- Risk levels: safe, watch, risky, impassable, plus unknown. Risk depends on vehicle class.
- Low-end Android budgets (section C.14). Offline last-known snapshot. SMS (70-character Unicode segments for Indic text, DLT-registered templates) and WhatsApp fallbacks.
- Never claim accuracy figures, partner cities, testimonials or response-time wins that have not been measured. Illustrative data is labelled "sample".
- Every closure override needs reason, expiry and an audit entry.

## Brand Commitments
Voice: calm, direct, local, specific. Tone shifts with stakes: plain and brief in danger, warmer in empty and success states, never jokey about risk. Personality in three words: steady, plain, accountable.
Avoid: disaster-movie red alarm styling, AI-purple gradients, glass everywhere, beige "craft" palettes, cutesy copy, fake-precise numbers.

## Evidence on Hand
Design research in docs/research. IMD four-level colour warnings (green, yellow, orange, red: no action, be aware, be prepared, take action) are the public's existing mental model. CAP severity (Extreme, Severe, Moderate, Minor) and certainty (Observed, Likely at 50% or more, Possible below 50%) are the interoperable alert vocabulary. No user-research or accuracy evidence yet; do not invent it.

## Product Principles
1. Honest over reassuring: unknown is never shown as safe; stale data is always visible.
2. Glance, then act: one fact, one action, readable in 3 seconds at arm's length in rain.
3. Safety is never colour alone: every level has icon, label, line style and position.
4. Works when everything else does not: weak phone, weak network, no app.
5. People stay in control: easy undo, no traps, advice not commands for citizens; auditable commands for operators.
6. Local first: language, landmarks, vehicle type, numerals people actually use.

## Accessibility & Inclusion
WCAG 2.2 AA minimum, AAA contrast for risk text. Targets 48 px (56 px for emergency actions). Dragging always has a non-drag alternative. Screen reader, voice guidance, reduced motion, reduced transparency, forced colours. Copy at grade 6 to 8 reading level, Hindi plus the launch city's language from day one.
```

---

## C. DESIGN.md

### C.1 Principles
1. **Operate, not Persuade.** Familiar patterns win in the app and console. Delight is saved for one moment: a calm "Route updated, you are clear" confirmation.
2. **Unknown is a state.** Five states, never four. Absence of data never renders as safe.
3. **Redundant encoding.** Level = color + icon shape + text label + line style. Any two adjacent levels differ in at least two non-color cues.
4. **Direct manipulation, interruptible motion** (apple-design): feedback on pointer-down, 1:1 drag tracking, springs that start from the live value.
5. **One system.** Same tokens across all three surfaces. Console is a density mode, not a second design system.

### C.2 Color (OKLCH-derived hex; one accent; risk is a separate status system)
Neutrals are blue-slate tinted. No pure `#000`, no `#fff`, no neutral gray (taste 8.B, impeccable). Risk hues sit inside the IMD family so people recognise them, but the green is shifted to cyan-teal and impassable is near-black crimson so deuteranopia and protanopia do not collapse the scale.

| Token | Light | Dark | Role |
|---|---|---|---|
| canvas | `#F3F6F8` | `#0B141C` | page and map-chrome base |
| surface | `#FBFCFD` | `#121E28` | sheets, panels (dark elevated `#1A2935`) |
| ink | `#0F1B26` | `#E8EEF2` | primary text (16.1:1 / 15.9:1 on canvas) |
| ink-2 | `#3E4F5E` | `#A9BAC7` | secondary (7.8:1 / 9.3:1) |
| accent | `#1B4DB1` | `#8DB6FF` | actions, selection, route line (7.1:1 / 9.1:1; HSL sat 73%) |
| safe | `#0E7490` | `#5CCFE6` | clear |
| watch | `#F5CB45` | `#F5D060` | water may rise |
| risky | `#C2410C` | `#FF7A3D` | likely flooded |
| impassable | `#3D0A1C` | `#D6336C` | closed or flooded now |
| unknown | `#5B6B79` | `#8FA1B0` | no recent data (5.1:1 / 7.0:1) |

Contrast of solids against canvas (light / dark): safe 4.9 / 10.2, watch **1.4** / 12.4, risky 4.8 / 7.2, impassable 15.4 / 4.0 (white casing). Watch fails 3:1 as a bare line in light mode, so every map line carries a 1.5 px casing (ink in light, white in dark) and the watch fill never carries text.

**Chips** use a tint plus hue-derived ink, never gray on color: light safe `#D9F0F5`/`#063E4D` (9.8), watch `#FBEBB8`/`#4A3300` (10.0), risky `#FCE3D6`/`#7A2306` (8.3), impassable `#F6DCE3`/`#3D0A1C` (12.9). Dark chips measure 9.3 to 10.6.

**CVD check (min pairwise deltaE across normal, deuter, protan, tritan):** safe-impassable 43, watch-risky 37, risky-impassable 57. The earlier red-green set scored 8 to 16 on the same pairs, which is why it was dropped.

**High-contrast set** (`prefers-contrast: more` or "Sunlight" mode): ink on near-white, risk solids `#00596F`, `#5C4100` (text), `#8F2A00`, `#3D0A1C` (7.9 to 16.7:1 on white), 2 px casings, no tints, no translucency. Dark HC: `#7FE3F5`, `#FFE066`, `#FF9466`, `#FF7AA5` on `#05090D` (8.2 to 15.3). Under `forced-colors`, defer to system colors and keep icons and labels.

Bans honored: no purple-blue gradients, no beige-brass, no gradient text, no glow halos, no side-stripe borders on alerts.

### C.3 Non-color encoding of risk

| Level | EN label | HI label (needs native review) | Icon (Phosphor, one weight) | Map line | Polygon fill |
|---|---|---|---|---|---|
| safe | Clear | साफ़ | check-circle | solid, 4 px | none |
| watch | Watch | सावधानी | drop | long dash, 5 px | sparse dots |
| risky | Likely flooded | पानी भरने की आशंका | warning (triangle) | short dash, 6 px | diagonal hatch |
| impassable | Impassable | बंद | prohibit (no-entry) | solid 8 px with cross ticks | dense cross-hatch |
| unknown | No recent data | ताज़ा डेटा नहीं | question | dotted 3 px, desaturated | none |

Forecast vs observed: observed = solid fill, forecast = same hue at lower fill with the label prefixed "~". CAP certainty drives copy (Observed, Likely, Possible), not extra colors.

### C.4 Typography
- **Family: Noto Sans** (Latin and every Indic script), one family for all UI. This is a justified override of taste's Inter discouragement: per-script Noto cuts share heights and stroke weights, so mixed Hindi/English lines look even. Mono (IDs, coordinates, timestamps only): JetBrains Mono. Use Western digits by default, locale digits as a setting.
- **Citizen payload:** on Android, `font-family: system-ui, "Noto Sans", sans-serif` with `lang` set; Android ships Noto per script, so Indic costs 0 KB. Add `@font-face` with `src: local(...)` first, then a subsetted woff2 (target at most 60 KB per script, to be measured) only when local is missing. Verify on low-end OEM skins.
- **Scale (fixed rem, ratio about 1.2, impeccable Operate):** 13 / 14 / 16 / 18 / 22 / 28 / 36 px. Body 16 px minimum, 13 px floor for timestamps only. Indic body gets `:lang(hi,mr,bn,ta,te,kn) { font-size: 1.0625rem }`.
- **Leading (apple: size-inverse, tall scripts more):** Latin body 1.5, headings 1.2. Indic body 1.65, Indic headings 1.4, chips 1.35. Research shows clipping at 1.1 and a safe floor near 1.6 for body Indic text. Console Latin 1.4, Indic 1.5.
- **Tracking:** Latin display -0.02em, Latin body 0, small caps-free. **Indic scripts: letter-spacing 0 always,** no negative tracking (breaks conjuncts and matras), no uppercase, no italics, emphasise with weight 600.
- Tabular numerals (`font-variant-numeric: tabular-nums`) for ETA, depth, ages, table columns. Respect user text size; spacing in rem.

### C.5 Spacing, radius, elevation
- 4 px base: 4, 8, 12, 16, 24, 32, 48. Tight inside groups, generous between; more space above headings than below.
- **Radius lock:** 8 px (controls, chips, inputs), 16 px (sheets, banners, route cards). Console uses 8 only. Circle only for map markers.
- **Elevation declared once:** shadow, not border, with offset and blur, tinted to canvas: `0 8px 24px -8px rgb(15 27 38 / .28)`. Dark mode uses tonal layers (`surface`, `elevated`), no shadow. Console tables use hairlines, no shadows.

### C.6 Iconography
Phosphor only (taste allowed list), regular weight, 2 px optical stroke, 24 px in app, 20 px in console. No hand-rolled SVG, emoji or glyph icons. Risk icons ship in a sprite of about 10 glyphs. Icon-only buttons need accessible names.

### C.7 Map styling
- Custom MapLibre style: low-chroma base so risk dominates; water desaturated blue-slate; labels `ink` with 2 px canvas halo for glare.
- Risk drawn as casing plus fill plus dash plus midpoint icon (zoom 14 and up). Route line is accent, 8 px, white or ink casing. Fastest and safest alternatives differ by line style (safest solid, fastest dashed) and by label, not by color alone.
- Segment details open on **tap** (never hover), as a pinned tooltip anchored to the segment.
- Map pads for the sheet so the active route is never hidden under it. Base labels in the user's script; glyph ranges load lazily. Offline: PMTiles for the city extent.
- Markers: vehicles are shapes with heading and a text callsign, never color-only.

### C.8 Motion
Allowed in an emergency tool: press feedback (100 to 160 ms, `scale(.97)`), sheet physics, map camera moves to the new route (about 400 ms, ease-out), a one-shot 600 ms highlight when a route changes, skeleton fades. Not allowed: looping or pulsing indicators, marquees, parallax, entrance choreography, bounce or elastic curves, animation on keyboard actions (console), hover movement.
- **Springs, critically damped by default:** damping 1.0, response 0.3 to 0.4 s (Motion `bounce: 0`). Apple's sheet value (0.8) is capped at `bounce 0.1` on flick release only, which resolves apple-design vs impeccable's bounce ban.
- Interruptible: animate from the live value, Pointer Events plus `setPointerCapture`, ignore second touch mid-drag, handle `pointercancel` and `lostpointercapture`. Enter and exit along one path.
- Reduced motion: cross-fade 150 ms, no slides, no camera easing (jump cut with 150 ms fade). State changes stay visible.
- Compositor only (`transform`, `opacity`); exit faster than enter.

### C.9 Materials
One translucent layer only: the citizen bottom sheet over the map (`backdrop-filter: blur(16px) saturate(140%)`, surface at 88% alpha, 1 px top edge). Risk text and chips always sit on an opaque inner surface. `prefers-reduced-transparency`, `prefers-contrast: more`, Sunlight mode and low-end devices (no `backdrop-filter` support check or frame-time guard) fall back to solid `surface`. Never stack translucent layers. Console: no translucency.

### C.10 Components
- **Risk badge:** icon plus label plus chip tint, 32 px high, never icon-only on a card; vehicle-class chip beside it (bike, car, bus, ambulance) because passability depends on vehicle.
- **Route card (2 cards, fastest and safest):** ETA large (tabular), delta vs other ("8 min longer, avoids 2 flooded roads"), worst-segment badge, data age. Selected state = accent ring plus check, not color alone.
- **Segment tooltip:** road name, level badge, "Observed 4 min ago" or "Likely in 20 to 30 min", confidence band (Low, Medium, High), source.
- **Alert banner:** full tint, icon, one sentence, one action, dismiss with undo. No side stripe.
- **Bottom sheet:** snap points peek 96 px, half 50%, full 90% of `dvh`. Release target from momentum projection `pos + (v/1000)*d/(1-d)`, d = 0.998; velocity sign decides reverse vs commit; rubber-band beyond ends; explicit expand/collapse button as the dragging alternative (WCAG 2.5.7).
- **Report-flood flow, language switcher** (always visible in header and in onboarding, shows each language in its own script), **dispatcher incident table** (virtualized, sortable, tabular numerals, row = severity icon, location, age, assigned unit, state), **forecast scrubber** (0 to 6 h in 15 min steps, "Now" pinned, buttons for step back and forward as alternative to drag, forecast hours labelled "forecast").

### C.11 States (all required, per impeccable Operate)
- **Stale data (critical).** Every risk surface shows a data-age chip in tabular numerals. Under 5 min: neutral. 5 to 15 min: watch-tinted chip with clock icon. Over 15 min: persistent banner "Road status may be out of date. Last update 18 min ago. Showing last known conditions." and "Clear" segments degrade to unknown. Thresholds are proposals; calibrate to real feed cadence. Console shows per-source feed health in the top strip.
- **Offline:** last route and snapshot kept with its timestamp, "You are offline. Showing conditions from 14:20." Report queue visible. SMS fallback offered.
- **Loading:** skeletons shaped like the sheet and route cards, never a centered spinner.
- **Empty:** "No flooding reported near you. Check again after the next rain alert." plus save-places action.
- **Error:** what failed, what still works, retry.
- **GPS denied or weak:** manual place search, landmark entry.

### C.12 Content rules
- Plain language, grade 6 to 8, sentences about 12 words, verb first, local landmarks over compass directions. Say "underpass", "waterlogged"; avoid "inundation", "ingress", "ETA" (use "arrive by").
- **Honest uncertainty:** "Likely waterlogged in about 25 min" or "in 20 to 30 min". Ranges, not points. Confidence as Low/Medium/High, number only on tap. Observed uses past tense with age ("Flooded now, reported 4 min ago"). Never "safe", say "Clear as of 14:20".
- No em-dashes or en-dash separators anywhere (taste 9.G), hyphen only. No emoji, no filler verbs, no "Oops".
- Bilingual pattern: one language at a time, user's choice persists. In alerts, local language first, English second line. Whole sentences are translatable units, no concatenation, ICU plurals. Budget 40% expansion for Indic labels.
- Voice and SMS: under 70 characters per SMS segment for Indic text, one fact plus one action ("Rasta band: Sitabuldi underpass. Use Wardha Road.").

### C.13 Accessibility
WCAG 2.2 AA minimum: 2.5.8 target at least 24 px (we ship 48; 56 for emergency actions, 8 px gaps), 2.4.11 focus not hidden by sheets or banners, 2.5.7 dragging alternatives, 3.3.7 no re-entry (location carries between steps), 3.3.8 no cognitive tests (no CAPTCHA puzzles; report needs no login). Screen reader: sheet is a labelled region with live-region announcements for reroutes (assertive only for impassable on active route). Voice guidance with pre-recorded fallback for critical phrases because TTS in regional languages varies on cheap phones. Rider mode (auto-suggested above walking speed, never forced): fewer controls, 56 px targets, voice first, no lists, no text entry. Wet-hand rules: no long-press, no hover, no swipe-only action, tap commits on release, generous cancel zone.

### C.14 Performance budgets (citizen, Moto G-class 2 to 3 GB RAM, slow 4G)
Benchmarks: Newzoo reports about 92% of Indian Android users have 2 GB or more and 73% have 3 GB or more; Alex Russell's guidance is about 130 KB gzipped JS for a $200 phone on slow 3G.
- Shell (HTML, CSS, JS) at most 70 KB gzipped, showing text risk summary and routes before the map. MapLibre loads on idle as a separate chunk (check actual size at build; likely 200 KB class) with a text and static fallback.
- LCP at most 2.5 s, INP at most 200 ms, CLS at most 0.1, measured on a real low-end device.
- Risk payload first load at most 20 KB, deltas at most 5 KB. Sheet drag at 60 fps, map interactions 30 fps acceptable. No webfonts on Android. Service worker precache of shell, snapshot, glyphs.
- Console: 1,000+ virtualized rows, WebSocket deltas, no animation on repeated keyboard actions.
- Mobile platform floor (emil mobile-native): `100dvh`, `touch-action: manipulation`, 16 px inputs, `overscroll-behavior: none` on root, `viewport-fit=cover` plus safe-area insets, per-scheme `theme-color`, `(hover:hover)` gating.

---

## D. Key screens and flows

**Citizen**
1. **Onboarding (2 screens max).** Language (each in own script, auto-detected, one tap), then location permission with a plain reason and "Search a place instead". Vehicle type chip row (two-wheeler default). No account. Push permission asked later, at the first alert-worthy moment.
2. **Home map.** Full-bleed map, status pill top ("Heavy rain expected 17:00 to 20:00", data age), sheet at peek: "Where to?" plus saved Home and Work. Tabs named for content: Map, Routes, Alerts, Report. Report button fixed, 56 px, thumb zone.
3. **Route compare.** Sheet at half: two route cards, Fastest and Safest, with delta line and worst-segment badge. Safest is pre-selected when fastest contains risky or impassable. Both drawn on the map with distinct line styles. Start is one 56 px button.
4. **Live reroute notification.** Push and in-app banner: "Road ahead may flood in about 20 min. Switch to Wardha Road? 4 min longer." Actions: Switch, Keep. Auto-switch only if the user enabled it, or the current segment becomes impassable, in which case it switches and announces by voice. Undo for 10 s.
5. **Report flood (3 taps).** Tap 1: Report. Tap 2: depth tile (Wet road, Ankle-deep, Knee-deep, Vehicles stuck), drawn against a tyre silhouette; location pre-filled and adjustable. Tap 3: Send. Photo optional afterwards. Offline queue with visible status. Safety line: "Do not report while riding."
6. **Offline and SMS.** Offline banner with snapshot time. SMS and WhatsApp: short code "FLOOD <place>" returns status, best alternative and data age in the user's language.

**Dispatcher console** (dark default, light available; 1366x768 minimum, multi-monitor aware)
1. **Situation board.** Top strip: feed health per source with ages, active warnings, shift clock. Left: virtualized incident table. Center: map with risk, units and forecast scrubber at bottom. Right: detail drawer. Keyboard: J/K rows, A assign, C closure, Esc close. No cards or hero metrics, hairlines only.
2. **Vehicle assignment.** Select incident, console proposes units by vehicle class and flood-safe ETA; assign with Enter or drag (both). The route to scene is drawn with its risk badges; if the best route degrades later, the row flags "Route changed" until acknowledged.
3. **Closure override.** Pick segment, choose close, reopen or force-watch, reason (required), expiry (required, default 2 h), impact preview ("affects n active routes"). Reversible, so undo toast, not a modal. Arterial roads add a second-operator confirm.
4. **Audit log.** Append-only table: time, operator, action, segment, reason, expiry, before and after state, export. Filter by operator and road.

---

## E. Pre-flight QA checklist and conflicts

**Checklist (merged from taste section 14, impeccable craft-floor and critique, apple-design)**
- [ ] Design read, dials and mode (Persuade or Operate) declared per surface.
- [ ] Zero em-dashes or en-dash separators in any string, all languages' English source included.
- [ ] One accent, one radius system (8 and 16), one theme per view, one icon family; no pure black or white, no AI-purple, no beige-brass.
- [ ] Risk: five states, icon plus label plus line style on every instance; CVD simulation passed; unknown never renders as safe.
- [ ] Contrast measured: text 4.5:1 (AAA for risk text), graphics and focus 3:1, in light, dark, HC and Sunlight.
- [ ] Data-age chip on every risk surface; stale and offline banners tested by cutting the feed.
- [ ] Targets 48 px (56 emergency), 8 px gaps; no hover-only, long-press-only or swipe-only action; dragging alternatives present.
- [ ] Press feedback on pointer-down; drags 1:1; springs interruptible; second finger, `pointercancel`, window blur tested on a real phone.
- [ ] Reduced motion, reduced transparency, `prefers-contrast`, forced colors each tested.
- [ ] Indic: leading, no tracking, no clipping, 40% expansion, longest language checked at 200% zoom, on a real low-end phone.
- [ ] Every state exists: default, hover (pointer only), focus, active, disabled, loading, empty, error, offline, stale.
- [ ] Copy self-audit: grade 6 to 8, ranges not points, no fake-precise numbers, no invented stats or testimonials.
- [ ] No nested cards, no hero-metric template, no three-equal-card rows, no decorative dots, no side-stripe borders, no eyebrows.
- [ ] Budgets met on target device; Lighthouse plus real-device trace; `impeccable detect` clean or waived with reason.

**Conflicts and resolutions**

| Conflict | Resolution |
|---|---|
| taste: dashboards out of scope | Apply only locks, bans and checklist to console; structure from impeccable Operate. |
| taste: max 1 accent, saturation under 80% vs 4 risk hues | Risk is a semantic status system, not an accent. One brand accent remains. |
| taste: Inter discouraged, serif discouraged | Noto Sans for script coverage and harmony; override allowed for accessibility-first briefs. |
| taste: zero decorative dots; impeccable: no pulsing dot | Risk uses icons, not dots. Live state is a static labelled indicator, no pulse. |
| taste: cards only for hierarchy; no identical grids | Two route cards are selectable options, hence hierarchy. Never nested; never three equal. |
| taste: no glass by default; apple: translucent materials | One glass layer (sheet), opaque inner surfaces, solid fallbacks. |
| apple: bounce 0.8 on sheets; impeccable: no bounce | Damping 1.0 default; at most `bounce 0.1` on flick release of the sheet. |
| impeccable: no side-stripe alert borders vs common alert idiom | Full tint plus icon plus label. |
| impeccable: no gray-on-color; CAP/IMD red-orange-yellow-green | Hue-derived ink; IMD families kept but green shifted to teal for CVD. |
| taste: CTA labels must not wrap | Holds for English and site. App buttons use min-height and may wrap for Indic labels. |
| taste: apple negative tracking on display | Latin only; Indic tracking is 0. |
| taste: animated loops allowed when motion above 5 | Never in these surfaces; unacknowledged console alerts use a persistent badge plus audio, not a loop. |
| apple: confirm only irreversible; ops safety | Undo plus expiry plus audit for closures; second-operator confirm only for arterials. |
| taste: real imagery required on landing; no fake screenshots | Use a live MapLibre preview with labelled sample data and licensed monsoon photography; no invented customers or accuracy claims. |

---

## F. Recommended UI tech (one system)

- **Citizen and console: React 19 + Vite PWA** (not Next). No SSR need, smaller shell, simpler service worker for offline. Shared monorepo package for tokens, risk components and copy catalog. Marketing site: Astro or Next static, same tokens package.
- **Map:** MapLibre GL JS, self-hosted vector tiles (PMTiles for offline), custom style; deck.gl only on console if segment counts demand it.
- **Styling:** Tailwind v4 with semantic CSS variables from the tokens above (light, dark, HC via `data-theme` plus media queries). Console density via a `data-density` attribute.
- **Components:** Radix Primitives with our own styling (not shadcn defaults, not Radix Themes), honoring taste "one system" and "never default state". Vaul-style sheet logic written in-house on Pointer Events plus Motion springs, to own the snap and projection behavior and to meet the shell budget.
- **Motion:** Motion (`motion/react`), `useMotionValue` for drags (no `useState` for continuous values), CSS for predetermined transitions.
- **Icons:** Phosphor sprite. **i18n:** ICU message format (FormatJS), per-language bundles lazy-loaded, `Intl` for dates and numbers.
- **Tooling:** `impeccable detect` in CI, axe, Lighthouse CI with budgets, one low-end Android in the test loop, CVD simulation in Storybook.

**Open items to verify:** Hindi and regional translations (native review), exact MapLibre and per-script font sizes at build, stale-data thresholds against real feed cadence, voice TTS quality per language on target phones, whether launch city has a preferred state design language to align with.

Sources: [IMD colour warnings](https://www.deccanherald.com/india/what-do-imds-colour-coded-weather-warnings-mean-1235951.html), [CAP severity, urgency, certainty](https://etrp.wmo.int/mod/book/tool/print/index.php?id=11045), [WCAG 2.2 what is new](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/), [Indic web typography](https://docs.thottingal.in/web-typography), [Alex Russell budgets](https://redmonk.com/blog/2025/11/24/alex-russell/), [Newzoo RAM India](https://gamedevreports.substack.com/p/newzoo-only-53-of-indian-players), [Okabe-Ito and ColorBrewer CVD notes](https://www.audioeye.com/post/colorblind-friendly-palettes/), [Mappls safety alerts](https://apps.mgov.gov.in/details?appid=1796), [Waze flood reporting](https://www.waze.com/discuss/t/flood-closures/280070).
