---
name: FloodRoute
description: Predicts which roads become unusable in heavy rain and keeps rerouting citizens and emergency vehicles. Steady, plain, accountable.
colors:
  # primary is the single brand accent (--fr-accent in packages/ui/tokens.css). Light values; "-dark" keys are the dark theme.
  primary: "#1B4DB1"
  canvas: "#F3F6F8"
  surface: "#FBFCFD"
  surface-elevated: "#FBFCFD"
  ink: "#0F1B26"
  ink-2: "#3E4F5E"
  safe: "#0E7490"
  watch: "#F5CB45"
  risky: "#C2410C"
  impassable: "#3D0A1C"
  unknown: "#5B6B79"
  safe-tint: "#D9F0F5"
  safe-ink: "#063E4D"
  watch-tint: "#FBEBB8"
  watch-ink: "#4A3300"
  risky-tint: "#FCE3D6"
  risky-ink: "#7A2306"
  impassable-tint: "#F6DCE3"
  impassable-ink: "#3D0A1C"
  unknown-tint: "#E1E9EF"
  unknown-ink: "#2D363F"
  primary-dark: "#8DB6FF"
  canvas-dark: "#0B141C"
  surface-dark: "#121E28"
  surface-elevated-dark: "#1A2935"
  ink-dark: "#E8EEF2"
  ink-2-dark: "#A9BAC7"
  safe-dark: "#5CCFE6"
  watch-dark: "#F5D060"
  risky-dark: "#FF7A3D"
  impassable-dark: "#D6336C"
  unknown-dark: "#8FA1B0"
  safe-tint-dark: "#00343E"
  safe-ink-dark: "#BCE5EF"
  watch-tint-dark: "#382C07"
  watch-ink-dark: "#E7DBBB"
  risky-tint-dark: "#452416"
  risky-ink-dark: "#F7D4C5"
  impassable-tint-dark: "#44212A"
  impassable-ink-dark: "#F7D0D8"
  unknown-tint-dark: "#252F37"
  unknown-ink-dark: "#D2DEE9"
typography:
  # Report 06 fixes the scale (13 to 36 px), body 1.5, headings 1.2 and Latin display tracking -0.02em. Heading leading is applied from 22px up (the report does not name the boundary).
  # Indic text overrides leading (body 1.65, headings 1.4, chips 1.35), body size +6% and tracking 0 through :lang() in tokens.css.
  text-13:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 0.8125rem
    lineHeight: 1.5
  text-14:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 0.875rem
    lineHeight: 1.5
  text-16:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 1rem
    lineHeight: 1.5
  text-18:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 1.125rem
    lineHeight: 1.5
  text-22:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 1.375rem
    lineHeight: 1.2
  text-28:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 1.75rem
    lineHeight: 1.2
  text-36:
    fontFamily: Noto Sans, system-ui, sans-serif
    fontSize: 2.25rem
    lineHeight: 1.2
    letterSpacing: -0.02em
  # JetBrains Mono for IDs, coordinates and timestamps only (report 06 C.4). Not loaded as a webfont on Android.
  mono:
    fontFamily: JetBrains Mono, ui-monospace, monospace
rounded:
  control: 8px
  sheet: 16px
spacing:
  "1": 4px
  "2": 8px
  "3": 12px
  "4": 16px
  "6": 24px
  "8": 32px
  "12": 48px
components:
  risk-chip-safe:
    backgroundColor: "{colors.safe-tint}"
    textColor: "{colors.safe-ink}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-safe-dark:
    backgroundColor: "{colors.safe-tint-dark}"
    textColor: "{colors.safe-ink-dark}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-watch:
    backgroundColor: "{colors.watch-tint}"
    textColor: "{colors.watch-ink}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-watch-dark:
    backgroundColor: "{colors.watch-tint-dark}"
    textColor: "{colors.watch-ink-dark}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-risky:
    backgroundColor: "{colors.risky-tint}"
    textColor: "{colors.risky-ink}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-risky-dark:
    backgroundColor: "{colors.risky-tint-dark}"
    textColor: "{colors.risky-ink-dark}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-impassable:
    backgroundColor: "{colors.impassable-tint}"
    textColor: "{colors.impassable-ink}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-impassable-dark:
    backgroundColor: "{colors.impassable-tint-dark}"
    textColor: "{colors.impassable-ink-dark}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-unknown:
    backgroundColor: "{colors.unknown-tint}"
    textColor: "{colors.unknown-ink}"
    rounded: "{rounded.control}"
    height: 32px
  risk-chip-unknown-dark:
    backgroundColor: "{colors.unknown-tint-dark}"
    textColor: "{colors.unknown-ink-dark}"
    rounded: "{rounded.control}"
    height: 32px
---

<!-- Text from docs/research/06-design-direction.md section C, re-homed under the DESIGN.md headings. Tokens: packages/ui/tokens.css is the source of truth. Measured corrections to the report's colour figures: packages/ui/CHANGES.md. -->

# Design System: FloodRoute

## Overview

### Principles

1. **Operate, not Persuade.** Familiar patterns win. Delight is one calm moment: "Route updated. You are clear."
2. **Unknown is a state.** Five states; no data never renders as safe.
3. **Redundant encoding.** Level = color + icon + label + line style; adjacent levels differ in two non-color cues.
4. **Direct and interruptible** (apple): feedback on pointer-down, 1:1 drag, springs start from the live value.
5. **One system.** Same tokens everywhere; console is a density mode.

## Colors

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

### Non-color encoding

| Level | Label (HI needs native review) | Phosphor icon | Map line | Polygon |
|---|---|---|---|---|
| safe | Clear / साफ़ | check-circle | solid 4 px | none |
| watch | Watch / सावधानी | drop | long dash 5 px | sparse dots |
| risky | Likely flooded / पानी भरने की आशंका | warning | short dash 6 px | diagonal hatch |
| impassable | Impassable / बंद | prohibit | solid 8 px, cross ticks | cross-hatch |
| unknown | No recent data / ताज़ा डेटा नहीं | question | dotted 3 px | none |

Observed = solid fill. Forecast = lower fill with labels prefixed "~". CAP certainty drives wording, not extra colors.

## Typography

- **Noto Sans for Latin and every Indic script**, one family. Justified override of taste's Inter discouragement: per-script Noto cuts share heights and stroke weights, so mixed Hindi/English lines sit evenly. JetBrains Mono for IDs, coordinates and timestamps only. Western digits by default, locale digits as a setting.
- **Payload:** Android ships Noto per script, so use `system-ui, "Noto Sans"` with `lang` set and `src: local()` first; load a subsetted woff2 (target 60 KB per script, unmeasured) only when local is missing. Verify on low-end OEM skins.
- **Scale** (fixed rem, ratio about 1.2): 13 / 14 / 16 / 18 / 22 / 28 / 36 px. Body 16 minimum; 13 for timestamps only. Indic body +6% via `:lang()`.
- **Leading** (apple: inverse to size, taller for tall scripts): Latin body 1.5, headings 1.2. Indic body 1.65, headings 1.4, chips 1.35 (research: clipping at 1.1, safe near 1.6). Console 1.4 Latin, 1.5 Indic.
- **Tracking:** Latin display -0.02em, body 0. **Indic: always 0**, never negative (breaks conjuncts and matras), no uppercase, no italics, emphasis by weight 600.
- Tabular numerals for ETA, depth, ages, table columns. Rem spacing so text-size settings scale layout.

## Layout

4 px base: 4, 8, 12, 16, 24, 32, 48.

## Elevation & Depth

**Elevation declared once:** tinted shadow with offset and blur, `0 8px 24px -8px rgb(15 27 38 / .28)`; dark mode uses tonal layers; console tables use hairlines.

### Materials

One translucent layer: the citizen bottom sheet over the map (`blur(16px) saturate(140%)`, surface at 88% alpha, 1 px top edge). Risk text and chips always sit on an opaque inner surface. Solid fallback under `prefers-reduced-transparency`, `prefers-contrast: more`, Sunlight mode and a frame-time guard on weak GPUs. Never stack translucent layers. Console has none.

## Shapes

**Radius lock:** 8 px (controls, chips, inputs), 16 px (sheets, banners, route cards); console uses 8 only; circles only for map markers.

## Components

- **Risk badge:** icon + label + tint, 32 px; vehicle chip beside it (bike, car, bus, ambulance) because passability depends on vehicle.
- **Route card (two: fastest, safest):** large tabular ETA, delta ("8 min longer, avoids 2 flooded roads"), worst-segment badge, data age. Selected = accent ring plus check.
- **Segment tooltip:** road, level badge, "Observed 4 min ago" or "Likely in 20 to 30 min", confidence Low/Medium/High.
- **Alert banner:** full tint, icon, one sentence, one action, undo on dismiss. No side stripe.
- **Bottom sheet:** snaps at peek 96 px, half 50%, full 90% `dvh`. Target from projection `pos + (v/1000)*d/(1-d)`, d = 0.998; velocity sign decides reverse vs commit; rubber-band at ends; expand/collapse button as the WCAG 2.5.7 alternative.
- **Report flow, language switcher** (always in header, each language in its own script), **incident table** (virtualized; severity icon, place, age, unit, state), **forecast scrubber** (0 to 6 h, 15 min steps, "Now" pinned, step buttons as drag alternative, future hours labelled "forecast").

### Iconography

Phosphor only, regular weight, 24 px app, 20 px console, shipped as a sprite. No hand-drawn SVG, emoji or glyph icons. Icon-only buttons need accessible names.

## Map Styling

- Low-chroma custom MapLibre style so risk dominates; water desaturated slate; labels in `ink` with a 2 px canvas halo for glare; labels in the user's script, glyph ranges lazy.
- Risk = casing + fill + dash + midpoint icon (zoom 14+). Route line is accent, 8 px. Fastest vs safest differ by line style (safest solid, fastest dashed) and labels.
- Segment details open on **tap**, never hover, as a pinned tooltip.
- Camera pads for the sheet so the route is never hidden. Vehicle markers are shapes with a text callsign.

## Motion

Allowed: press feedback (100 to 160 ms, `scale(.97)`), sheet physics, camera move to a new route (about 400 ms ease-out), a one-shot 600 ms highlight on a changed route, skeleton fades. Not allowed: loops or pulses, marquees, parallax, entrance choreography, bounce or elastic, animation on keyboard actions, hover movement.
- **Springs critically damped:** damping 1.0, response 0.3 to 0.4 s (`bounce: 0`). The sheet may use `bounce 0.1` on flick release only (resolves apple's 0.8 vs impeccable's bounce ban).
- Interruptible: animate from the live value, Pointer Events with `setPointerCapture`, ignore second touch mid-drag, handle `pointercancel`. Enter and exit along one path; exit faster than enter; compositor properties only.
- Reduced motion: 150 ms cross-fade, no slides, camera jump-cut. State changes stay visible.

## States

- **Stale data (critical).** Every risk surface shows a data-age chip in tabular numerals. Under 5 min: neutral. 5 to 15: watch-tinted with clock icon. Over 15: persistent banner "Road status may be out of date. Last update 18 min ago. Showing last known conditions." and Clear segments degrade to unknown. Thresholds are proposals; calibrate to real feed cadence. Console shows per-source feed health in its top strip.
- **Offline:** keep last route and snapshot with timestamp ("You are offline. Showing conditions from 14:20."), visible report queue, SMS offer.
- **Loading:** skeletons shaped like sheet and cards. **Empty:** "No flooding reported near you. Save your places to get alerts." **Error:** what failed, what still works, retry. **GPS denied:** place search.

## Content Rules

- Grade 6 to 8, about 12 words a sentence, verb first, landmarks over compass directions. "Underpass" and "waterlogged" are fine; avoid "inundation", "ETA" (use "arrive by").
- **Honest uncertainty:** "Likely waterlogged in about 25 min", or "in 20 to 30 min". Ranges, not points. Confidence as Low/Medium/High, number only on tap. Observed uses past tense with age: "Flooded now, reported 4 min ago." Never say "safe"; say "Clear as of 14:20".
- No em-dashes or en-dash separators (taste 9.G), no emoji, no "Oops".
- One language at a time, choice persists; alerts show local language first, English second. Whole translatable sentences, ICU plurals, 40% expansion budget.
- SMS: one fact, one action, under 70 characters for Indic ("Rasta band: Sitabuldi underpass. Use Wardha Road.").

## Accessibility

WCAG 2.2 AA: 2.5.8 targets at least 24 px (we ship 48; 56 emergency; 8 px gaps), 2.4.11 focus never hidden by sheet or banner, 2.5.7 drag alternatives, 3.3.7 no re-entry, 3.3.8 no cognitive tests (no puzzles; reporting needs no login). Sheet is a labelled region; reroutes announce via live region, assertive only for impassable on the active route. Voice guidance with pre-recorded fallback for critical phrases, since regional TTS varies on cheap phones. **Rider mode** (suggested above walking speed, never forced): fewer controls, 56 px targets, voice first, no text entry. **Wet-hand rules:** no long-press, no hover, no swipe-only action, commit on release with a generous cancel zone.

## Performance Budgets (citizen, Moto G-class, 2 to 3 GB, slow 4G)

Newzoo: about 92% of Indian Android users have 2 GB or more RAM, 73% have 3 GB or more. Russell: about 130 KB gzipped JS for a $200 phone on slow 3G.
- Shell at most 70 KB gzipped, showing a text risk summary and routes before the map. MapLibre loads on idle as its own chunk (measure at build; likely 200 KB class) with a text fallback.
- LCP 2.5 s, INP 200 ms, CLS 0.1, on a real low-end device. Risk payload at most 20 KB first load, 5 KB deltas. Sheet drag 60 fps, map 30 fps acceptable. No webfonts on Android. Service worker precaches shell, snapshot, glyphs.
- Mobile floor (mobile-native): `100dvh`, `touch-action: manipulation`, 16 px inputs, `overscroll-behavior: none`, `viewport-fit=cover` with safe-area insets, per-scheme `theme-color`, hover gated by `(hover:hover)`.

---
