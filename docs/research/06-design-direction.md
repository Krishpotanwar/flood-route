# FloodRoute: Design Direction Brief

Date: 2026-10-05. Read in full: taste-skill v2, impeccable (skill source plus 15 reference files and the detector rule list), apple-design, emil-design-eng, mobile-native. Palette numbers were computed (WCAG contrast, Machado CVD simulation).

Two findings shape everything:
1. **taste-skill v2 puts dashboards, dense product UI, multi-step flows and native mobile out of scope (its section 13).** It fully governs the landing site. For the app and console we apply its locks, bans and pre-flight only, and take structure from impeccable's Operate mode.
2. **Impeccable picks a mode per surface.** Landing is Persuade. Citizen app and console are Operate: the tool disappears into the task, transitions run 150 to 250 ms, no page-load sequences.

---

## A. Design read and dials

| Surface | Design read | VARIANCE | MOTION | DENSITY |
|---|---|---|---|---|
| Citizen PWA | Map-first safety tool for a stressed, often one-handed rider in rain, calm and plain, trust-first, own tokens on Radix primitives with MapLibre. | 2 | 3 | 4 |
| Dispatcher console | 24-hour ICCC operations cockpit for trained operators on large screens, quiet and exact, own tokens on Radix primitives with dense tables. | 2 | 2 | 8 |
| Marketing site | Sober trust-first landing for citizens, officials and procurement, Tailwind v4 with one real product preview. | 5 | 4 | 3 |

- **Citizen 2/3/4.** Taste's trust-first row is 3-4 / 2-3 / 4-5. Map plus bottom sheet is a learned pattern (apple: familiarity), so variance stays low. Motion covers feedback, sheet physics and one reroute highlight. One decision per screen.
- **Console 2/2/8.** Predictability matters at 3 a.m. Density above 7 triggers taste rules: no card containers, hairline rows, tabular numerals.
- **Site 5/4/3.** Asymmetric split hero (centered is banned above variance 4). Motion above 3 needs reduced-motion handling and "motion shown", so the one motion moment is a real reroute on a real map component.

---

## B. PRODUCT.md (drop into repo root)

```markdown
# Product

<!-- impeccable:product-schema 1 -->

## Platform
adaptive web: installable PWA (Android first), desktop console, marketing site.

## Users
- Citizens, mainly two-wheeler riders and car drivers in Indian cities in heavy rain: one hand free, wet screen, sun glare between showers, 2 to 3 GB RAM Android, patchy data, Hindi or a regional language first.
- Dispatchers and ICCC operators (ambulance, fire, police, drainage): trained, on shift for hours, multi-monitor, accountable for every closure and assignment.
- Administrators who review decisions afterwards.

## Product Purpose
Predict which roads become unusable in heavy rain, say so early and honestly, and keep rerouting citizens and emergency vehicles. Success: a citizen avoids a flooded underpass because they understood a message in 3 seconds; an ambulance is never routed into a road we already knew was closing; every closure is auditable.

## Positioning
A flood-specific layer, not general navigation. Honest about uncertainty and data age, light enough for weak phones, reachable by SMS and WhatsApp when the app is not.

## Operating Context
Rain at night, underpasses, wet fingers, power cuts, congested networks, alerts arriving mid-ride. Control rooms are dim and staffed around the clock. Feeds can be late or wrong, and the interface must say so.

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
```

---

## C. DESIGN.md

### C.1 Principles
1. **Operate, not Persuade.** Familiar patterns win. Delight is one calm moment: "Route updated. You are clear."
2. **Unknown is a state.** Five states, never four. No data never renders as safe.
3. **Redundant encoding.** Level = color + icon + label + line style. Adjacent levels differ in at least two non-color cues.
4. **Direct and interruptible** (apple): feedback on pointer-down, 1:1 drag, springs start from the live value.
5. **One system.** Same tokens on all surfaces. Console is a density mode, not a second system.

### C.2 Color
Neutrals are blue-slate tinted: no pure `#000`, no `#fff`, no neutral gray. One brand accent. Risk is a separate status system. Risk hues stay inside the IMD families people recognise, but green shifts to cyan-teal and impassable is near-black crimson so deuteranopia and protanopia do not collapse the scale.

| Token | Light | Dark | Role |
|---|---|---|---|
| canvas | `#F3F6F8` | `#0B141C` | base |
| surface | `#FBFCFD` | `#121E28` (elevated `#1A2935`) | sheets, panels |
| ink | `#0F1B26` | `#E8EEF2` | text, 16.1 / 15.9:1 |
| ink-2 | `#3E4F5E` | `#A9BAC7` | secondary, 7.8 / 9.3:1 |
| accent | `#1B4DB1` | `#8DB6FF` | actions, route line, 7.1 / 9.1:1 (HSL sat 73%) |
| safe | `#0E7490` | `#5CCFE6` | clear |
| watch | `#F5CB45` | `#F5D060` | water may rise |
| risky | `#C2410C` | `#FF7A3D` | likely flooded |
| impassable | `#3D0A1C` | `#D6336C` | closed or flooded now |
| unknown | `#5B6B79` | `#8FA1B0` | no recent data, 5.1 / 7.0:1 |

Solids on canvas (light / dark): safe 4.9 / 10.2, watch **1.4** / 12.4, risky 4.8 / 7.2, impassable 15.4 / 4.0. Watch fails 3:1 as a bare light-mode line, so every map line gets a 1.5 px casing (ink in light, white in dark) and watch never carries text.

**Chips** use tint plus hue-derived ink, never gray on color. Light (tint/ink): safe `#D9F0F5`/`#063E4D`, watch `#FBEBB8`/`#4A3300`, risky `#FCE3D6`/`#7A2306`, impassable `#F6DCE3`/`#3D0A1C`; 8.3 to 12.9:1. Dark chips: 9.3 to 10.6.

**CVD check** (minimum deltaE across normal, deuter, protan, tritan): safe-impassable 43, watch-risky 37, risky-impassable 57. A conventional red-green set scored 8 to 16 on the same pairs and was rejected.

**High contrast** (`prefers-contrast: more` or Sunlight mode): solids `#00596F`, `#5C4100` (text), `#8F2A00`, `#3D0A1C` (7.9 to 16.7:1), 2 px casings, no tints or translucency. Dark HC on `#05090D`: `#7FE3F5`, `#FFE066`, `#FF9466`, `#FF7AA5` (8.2 to 15.3). Under `forced-colors`, defer to system colors, keep icons and labels.

### C.3 Non-color encoding

| Level | Label (HI needs native review) | Phosphor icon | Map line | Polygon |
|---|---|---|---|---|
| safe | Clear / साफ़ | check-circle | solid 4 px | none |
| watch | Watch / सावधानी | drop | long dash 5 px | sparse dots |
| risky | Likely flooded / पानी भरने की आशंका | warning | short dash 6 px | diagonal hatch |
| impassable | Impassable / बंद | prohibit | solid 8 px, cross ticks | cross-hatch |
| unknown | No recent data / ताज़ा डेटा नहीं | question | dotted 3 px | none |

Observed = solid fill. Forecast = lower fill with labels prefixed "~". CAP certainty drives wording, not extra colors.

### C.4 Typography
- **Noto Sans for Latin and every Indic script**, one family. Justified override of taste's Inter discouragement: per-script Noto cuts share heights and stroke weights, so mixed Hindi/English lines sit evenly. JetBrains Mono for IDs, coordinates and timestamps only. Western digits by default, locale digits as a setting.
- **Payload:** Android ships Noto per script, so use `system-ui, "Noto Sans"` with `lang` set and `src: local()` first; load a subsetted woff2 (target 60 KB per script, unmeasured) only when local is missing. Verify on low-end OEM skins.
- **Scale** (fixed rem, ratio about 1.2): 13 / 14 / 16 / 18 / 22 / 28 / 36 px. Body 16 minimum; 13 for timestamps only. Indic body +6% via `:lang()`.
- **Leading** (apple: inverse to size, taller for tall scripts): Latin body 1.5, headings 1.2. Indic body 1.65, headings 1.4, chips 1.35 (research: clipping at 1.1, safe near 1.6). Console 1.4 Latin, 1.5 Indic.
- **Tracking:** Latin display -0.02em, body 0. **Indic: always 0**, never negative (breaks conjuncts and matras), no uppercase, no italics, emphasis by weight 600.
- Tabular numerals for ETA, depth, ages, table columns. Rem spacing so text-size settings scale layout.

### C.5 Spacing, radius, elevation
4 px base: 4, 8, 12, 16, 24, 32, 48. **Radius lock:** 8 px (controls, chips, inputs), 16 px (sheets, banners, route cards); console uses 8 only; circles only for map markers. **Elevation declared once:** tinted shadow with offset and blur, `0 8px 24px -8px rgb(15 27 38 / .28)`; dark mode uses tonal layers; console tables use hairlines.

### C.6 Iconography
Phosphor only, regular weight, 24 px app, 20 px console, shipped as a sprite. No hand-drawn SVG, emoji or glyph icons. Icon-only buttons need accessible names.

### C.7 Map styling
- Low-chroma custom MapLibre style so risk dominates; water desaturated slate; labels in `ink` with a 2 px canvas halo for glare; labels in the user's script, glyph ranges lazy.
- Risk = casing + fill + dash + midpoint icon (zoom 14+). Route line is accent, 8 px. Fastest vs safest differ by line style (safest solid, fastest dashed) and labels.
- Segment details open on **tap**, never hover, as a pinned tooltip.
- Camera pads for the sheet so the route is never hidden. Vehicle markers are shapes with a text callsign.

### C.8 Motion
Allowed: press feedback (100 to 160 ms, `scale(.97)`), sheet physics, camera move to a new route (about 400 ms ease-out), a one-shot 600 ms highlight on a changed route, skeleton fades. Not allowed: loops or pulses, marquees, parallax, entrance choreography, bounce or elastic, animation on keyboard actions, hover movement.
- **Springs critically damped:** damping 1.0, response 0.3 to 0.4 s (`bounce: 0`). The sheet may use `bounce 0.1` on flick release only (resolves apple's 0.8 vs impeccable's bounce ban).
- Interruptible: animate from the live value, Pointer Events with `setPointerCapture`, ignore second touch mid-drag, handle `pointercancel`. Enter and exit along one path; exit faster than enter; compositor properties only.
- Reduced motion: 150 ms cross-fade, no slides, camera jump-cut. State changes stay visible.

### C.9 Materials
One translucent layer: the citizen bottom sheet over the map (`blur(16px) saturate(140%)`, surface at 88% alpha, 1 px top edge). Risk text and chips always sit on an opaque inner surface. Solid fallback under `prefers-reduced-transparency`, `prefers-contrast: more`, Sunlight mode and a frame-time guard on weak GPUs. Never stack translucent layers. Console has none.

### C.10 Components
- **Risk badge:** icon + label + tint, 32 px; vehicle chip beside it (bike, car, bus, ambulance) because passability depends on vehicle.
- **Route card (two: fastest, safest):** large tabular ETA, delta ("8 min longer, avoids 2 flooded roads"), worst-segment badge, data age. Selected = accent ring plus check.
- **Segment tooltip:** road, level badge, "Observed 4 min ago" or "Likely in 20 to 30 min", confidence Low/Medium/High.
- **Alert banner:** full tint, icon, one sentence, one action, undo on dismiss. No side stripe.
- **Bottom sheet:** snaps at peek 96 px, half 50%, full 90% `dvh`. Target from projection `pos + (v/1000)*d/(1-d)`, d = 0.998; velocity sign decides reverse vs commit; rubber-band at ends; expand/collapse button as the WCAG 2.5.7 alternative.
- **Report flow, language switcher** (always in header, each language in its own script), **incident table** (virtualized; severity icon, place, age, unit, state), **forecast scrubber** (0 to 6 h, 15 min steps, "Now" pinned, step buttons as drag alternative, future hours labelled "forecast").

### C.11 States
- **Stale data (critical).** Every risk surface shows a data-age chip in tabular numerals. Under 5 min: neutral. 5 to 15: watch-tinted with clock icon. Over 15: persistent banner "Road status may be out of date. Last update 18 min ago. Showing last known conditions." and Clear segments degrade to unknown. Thresholds are proposals; calibrate to real feed cadence. Console shows per-source feed health in its top strip.
- **Offline:** keep last route and snapshot with timestamp ("You are offline. Showing conditions from 14:20."), visible report queue, SMS offer.
- **Loading:** skeletons shaped like sheet and cards. **Empty:** "No flooding reported near you. Save your places to get alerts." **Error:** what failed, what still works, retry. **GPS denied:** place search.

### C.12 Content rules
- Grade 6 to 8, about 12 words a sentence, verb first, landmarks over compass directions. "Underpass" and "waterlogged" are fine; avoid "inundation", "ETA" (use "arrive by").
- **Honest uncertainty:** "Likely waterlogged in about 25 min", or "in 20 to 30 min". Ranges, not points. Confidence as Low/Medium/High, number only on tap. Observed uses past tense with age: "Flooded now, reported 4 min ago." Never say "safe"; say "Clear as of 14:20".
- No em-dashes or en-dash separators (taste 9.G), no emoji, no "Oops".
- One language at a time, choice persists; alerts show local language first, English second. Whole translatable sentences, ICU plurals, 40% expansion budget.
- SMS: one fact, one action, under 70 characters for Indic ("Rasta band: Sitabuldi underpass. Use Wardha Road.").

### C.13 Accessibility
WCAG 2.2 AA: 2.5.8 targets at least 24 px (we ship 48; 56 emergency; 8 px gaps), 2.4.11 focus never hidden by sheet or banner, 2.5.7 drag alternatives, 3.3.7 no re-entry, 3.3.8 no cognitive tests (no puzzles; reporting needs no login). Sheet is a labelled region; reroutes announce via live region, assertive only for impassable on the active route. Voice guidance with pre-recorded fallback for critical phrases, since regional TTS varies on cheap phones. **Rider mode** (suggested above walking speed, never forced): fewer controls, 56 px targets, voice first, no text entry. **Wet-hand rules:** no long-press, no hover, no swipe-only action, commit on release with a generous cancel zone.

### C.14 Performance budgets (citizen, Moto G-class, 2 to 3 GB, slow 4G)
Newzoo: about 92% of Indian Android users have 2 GB or more RAM, 73% have 3 GB or more. Russell: about 130 KB gzipped JS for a $200 phone on slow 3G.
- Shell at most 70 KB gzipped, showing a text risk summary and routes before the map. MapLibre loads on idle as its own chunk (measure at build; likely 200 KB class) with a text fallback.
- LCP 2.5 s, INP 200 ms, CLS 0.1, on a real low-end device. Risk payload at most 20 KB first load, 5 KB deltas. Sheet drag 60 fps, map 30 fps acceptable. No webfonts on Android. Service worker precaches shell, snapshot, glyphs.
- Mobile floor (mobile-native): `100dvh`, `touch-action: manipulation`, 16 px inputs, `overscroll-behavior: none`, `viewport-fit=cover` with safe-area insets, per-scheme `theme-color`, hover gated by `(hover:hover)`.

---

## D. Key screens and flows

**Citizen**
1. **Onboarding (2 screens).** Language (each in its own script, auto-detected), then location with a plain reason and "Search a place instead". Vehicle chips (two-wheeler default). No account. Push asked later, at the first alert-worthy moment.
2. **Home map.** Full-bleed map, status pill ("Heavy rain expected 17:00 to 20:00", data age), sheet at peek with "Where to?" and saved places. Tabs named for content: Map, Routes, Alerts, Report. Fixed 56 px Report button in the thumb zone.
3. **Route compare.** Sheet at half: Fastest and Safest cards with delta and worst-segment badge. Safest pre-selected when fastest has risky or impassable segments. Distinct line styles on the map. One 56 px Start button.
4. **Live reroute.** Push plus banner: "Road ahead may flood in about 20 min. Switch to Wardha Road? 4 min longer." Switch or Keep. Auto-switch only if enabled or the current segment turns impassable, then announce by voice. 10 s undo.
5. **Report flood (3 taps).** Report, then a depth tile (Wet road, Ankle-deep, Knee-deep, Vehicles stuck) drawn against a tyre silhouette with location pre-filled, then Send. Photo optional after. Offline queue with visible status. "Do not report while riding."
6. **Offline and SMS.** Offline banner with snapshot time. SMS and WhatsApp keyword returns status, best alternative and data age in the user's language.

**Dispatcher console** (dark default, light available; 1366x768 minimum)
1. **Situation board.** Top strip: feed health per source with ages, active warnings, shift clock. Left incident table, center map with scrubber, right detail drawer. Keys: J/K rows, A assign, C closure, Esc. Hairlines, no cards or hero metrics.
2. **Vehicle assignment.** Console proposes units by vehicle class and flood-safe ETA; assign by Enter or drag. The route to scene shows risk badges; if it degrades the row flags "Route changed" until acknowledged.
3. **Closure override.** Segment, action (close, reopen, force watch), required reason, required expiry (default 2 h), impact preview ("affects n active routes"). Reversible, so undo toast, not a modal. Arterials need a second operator.
4. **Audit log.** Append-only: time, operator, action, segment, reason, expiry, before and after, export, filters.

---

## E. Pre-flight QA and conflicts

**Checklist** (taste section 14, impeccable craft-floor and critique, apple-design)
- [ ] Design read, dials and mode declared per surface.
- [ ] Zero em-dashes or en-dash separators in any source string.
- [ ] One accent, one radius system (8, 16), one theme per view, one icon family; no pure black or white, AI-purple or beige-brass.
- [ ] Risk: five states, icon + label + line style everywhere; CVD simulation passes; unknown never reads as safe.
- [ ] Contrast measured: text 4.5:1 (risk text AAA), graphics and focus 3:1, in light, dark, HC and Sunlight.
- [ ] Data-age chip on every risk surface; stale and offline banners tested by cutting the feed.
- [ ] Targets 48 px (56 emergency); no hover-only, long-press-only or swipe-only action; drag alternatives exist.
- [ ] Press feedback on pointer-down; drags 1:1; second finger, `pointercancel` and blur tested on a real phone.
- [ ] Reduced motion, reduced transparency, `prefers-contrast`, forced colors tested; all states built (loading, empty, error, offline, stale).
- [ ] Indic: leading, zero tracking, no clipping, 40% expansion, 200% zoom, checked on a low-end phone.
- [ ] Copy self-audit: ranges not points, no fake-precise numbers, no invented stats or testimonials.
- [ ] No nested cards, hero-metric template, three-equal-card rows, decorative dots, side stripes or eyebrows.
- [ ] Budgets met on the target device; `impeccable detect` clean or waived with a reason.

**Conflicts and resolutions**

| Conflict | Resolution |
|---|---|
| taste: dashboards out of scope | Console uses taste locks, bans and pre-flight only; structure from impeccable Operate. |
| taste: one accent, saturation under 80% vs four risk hues | Risk is a status system, not an accent. One brand accent. |
| taste: Inter and serif discouraged | Noto Sans for script coverage (override allowed for accessibility-first briefs). |
| taste: no decorative dots; impeccable: no pulsing dot | Risk uses icons. "Live" is a static labelled indicator. |
| taste: cards only for hierarchy | Two route cards are selectable options. Never nested, never three equal. |
| taste: no default glass; apple: translucent materials | One glass layer (sheet), opaque inner surfaces, solid fallbacks. |
| apple: sheet damping 0.8; impeccable: no bounce | Damping 1.0 default; `bounce 0.1` on sheet flick only. |
| impeccable: no side-stripe alerts | Full tint, icon, label. |
| taste: CTAs never wrap | Holds for English and site; app buttons use min-height and may wrap in Indic. |
| apple: negative display tracking | Latin only; Indic tracking 0. |
| taste: perpetual motion above dial 5 | Never here. Unacknowledged console alerts use a persistent badge plus audio. |
| apple: confirm only irreversible | Closures get undo, expiry and audit; second operator only for arterials. |
| taste: real imagery, no fake screenshots | Live MapLibre preview with sample data labelled, licensed photography, no invented customers. |

---

## F. Recommended UI tech (one system)

- **Citizen and console: React 19 + Vite PWA**, not Next: no SSR need, smaller shell, simpler offline service worker. A shared monorepo package holds tokens, risk components and the copy catalog. Marketing site: Astro or Next static on the same tokens.
- **Map:** MapLibre GL JS, self-hosted vector tiles, PMTiles offline, custom style. deck.gl on console only if segment counts demand it.
- **Styling:** Tailwind v4 on semantic CSS variables (light, dark, HC via `data-theme` and media queries); console via `data-density`.
- **Components:** Radix Primitives with our own styling, not shadcn defaults or Radix Themes (taste: one system, never default state). Sheet logic written in-house on Pointer Events and Motion springs, to own snap and projection behavior and the shell budget.
- **Motion:** `motion/react`, `useMotionValue` for drags, CSS for fixed transitions. **Icons:** Phosphor sprite. **i18n:** FormatJS (ICU), lazy per-language bundles, `Intl`.
- **Tooling:** `impeccable detect`, axe and Lighthouse CI budgets in CI; a real low-end Android in the loop.

**Verify before build:** Hindi and regional strings, real MapLibre and font sizes, stale thresholds against feed cadence, regional TTS quality.

Sources: [IMD](https://www.deccanherald.com/india/what-do-imds-colour-coded-weather-warnings-mean-1235951.html), [CAP](https://etrp.wmo.int/mod/book/tool/print/index.php?id=11045), [WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/), [Indic type](https://docs.thottingal.in/web-typography), [budgets](https://redmonk.com/blog/2025/11/24/alex-russell/), [Newzoo](https://gamedevreports.substack.com/p/newzoo-only-53-of-indian-players), [CVD](https://www.audioeye.com/post/colorblind-friendly-palettes/), [Mappls](https://apps.mgov.gov.in/details?appid=1796), [Waze](https://www.waze.com/discuss/t/flood-closures/280070).
