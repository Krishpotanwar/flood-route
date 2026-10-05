# packages/ui: changes, decisions and verification log

Date: 2026-10-05. Source of truth for values: `tokens.css`. Source of the numbers: `docs/research/06-design-direction.md` section C.
Run `pnpm check` (root) or `pnpm --filter ui check` to reproduce everything below. Open `preview.html` in a browser; `preview.html#dark`, `#hc`, `#hc-dark`, `#sunlight`, `#light` deep-link a theme.

## 1. Changes to values that report 06 names

None. No token the report specifies was altered. No WCAG threshold fails in any theme (text 4.5, risk text 7, graphics and focus 3), so there was nothing to fix on accessibility grounds. The one documented exception is unchanged from the report: `watch` is 1.43 to 1 as a bare line on the light canvas, so it is only ever drawn with its ink casing (casing on canvas is 16.06 to 1).

## 2. Figures in report 06 that were wrong or incomplete

Measured by `scripts/check-tokens.mjs` and cross-checked with independent code (section 5).

| Report claim | Measured | Verdict |
|---|---|---|
| High contrast solids "7.9 to 16.7:1" (C.2) | 7.90 to 16.69 on `#FFFFFF`. On the HC canvas used here (`#FBFCFD`): 7.69 to 16.24. On the standard canvas `#F3F6F8`: 7.28 to 15.37 | Wrong for any canvas the report allows. It only holds on pure white, which C.2 forbids ("no `#fff`"). Every solid still clears 7:1 |
| CVD minimum deltaE "safe-impassable 43, watch-risky 37, risky-impassable 57" | CIE76: 42.7, 36.6, 57.4. CIEDE2000: 31.7, 27.8, 29.6 | Right only as CIE76 and only for the light palette. The report never says which metric. CIEDE2000 is 9 to 27 lower |
| Same CVD check, implied for the whole palette | Dark, CIE76: safe-impassable 40.9, watch-risky 15.9, risky-impassable 19.0. CIEDE2000: 34.1, 11.2, 12.2 | Does not hold in dark. Dark watch-risky (deuteranopia, 15.9) sits inside the 8 to 16 range the report used to reject a red-green set |
| Accent "(HSL sat 73%)" for both themes | Light 73.5%. Dark `#8DB6FF`: 100%. OKLCH chroma 0.168 light, 0.114 dark | One figure given for two colours. Dark exceeds taste's 80% limit in HSL, though HSL overstates chroma at lightness 78% |
| Dark chips "9.3 to 10.6" | The report names no dark chip colours | Unverifiable as written. The values in `tokens.css` are derived (section 3) and measure 9.96 to 10.01 |
| "A conventional red-green set scored 8 to 16" | The set is not named | Unverified |
| Type scale "ratio about 1.2" (C.4) | Steps between 13, 14, 16, 18, 22, 28, 36 are 1.08, 1.14, 1.13, 1.22, 1.27, 1.29 | Loose, not wrong. Geometric mean is 1.19 |

Every other colour figure reproduces to within 0.05: ink 16.1 / 15.9, ink-2 7.8 / 9.3, accent 7.1 / 9.1, unknown 5.1 / 7.0, solids on canvas (safe 4.9 / 10.2, watch 1.4 / 12.4, risky 4.8 / 7.2, impassable 15.4 / 4.0), light chips 8.3 to 12.9, dark HC 8.2 to 15.3.

Method. Contrast: WCAG 2.x relative luminance. CVD: Machado, Oliveira, Fernandes 2009 matrices at severity 1.0 on linear sRGB, clipped to 0..1, then CIE Lab with D65 white. CIE76 is the Euclidean distance. CIEDE2000 is Sharma, Wu, Dalal 2005 with kL = kC = kH = 1.

## 3. Decisions where report 06 is silent or ambiguous

Each of these is a value or reading I chose. None overrides a number in the report.

1. **Dark risk chips** (tint / ink): safe `#00343E` / `#BCE5EF`, watch `#382C07` / `#E7DBBB`, risky `#452416` / `#F7D4C5`, impassable `#44212A` / `#F7D0D8`. Method: OKLCH at the hue of each dark solid, tint lightness 0.30, ink lightness solved for 10 to 1. Contrast 9.96 to 10.01, inside the report's "9.3 to 10.6".
2. **Unknown chip** (the report has no unknown chip): light `#E1E9EF` / `#2D363F` (10.00), dark `#252F37` / `#D2DEE9` (9.97). Same method, slate hue 244.
3. **Unknown solid in high contrast**: `#485765` on the light HC canvas (7.23). The default `#5B6B79` is 5.35 there, which would break "AAA for risk text" because HC chips have no tint and the solid is the text.
4. **High contrast canvas**: light `#FBFCFD` (the surface token), dark `#05090D` (the report's). Canvas, surface and elevated are the same value in HC.
5. **High contrast watch (reading of "`#5C4100` (text)")**: `#5C4100` is the watch text colour (`--fr-watch-ink`). The watch line stays `#F5CB45` with its 2 px casing, as in the light theme. The other reading, `#5C4100` as the line too, leaves `#5C4100` and `#8F2A00` indistinguishable under protanopia (CIE76 1.6, CIEDE2000 1.0). Every value the report lists is still present.
6. **Casing "white in dark"**: the dark `ink` token (`#E8EEF2`), because C.2 forbids pure white. Casing equals `--fr-ink` in every theme.
7. **Focus ring**: colour is `--fr-accent` (7.05 to 9.77 on canvas, surface and elevated in every theme). Width and offset 2 px. The report asks for focus at 3:1 but defines no focus token.
8. **Font stack**: `"Noto Sans", system-ui, sans-serif`. C.4 says one Noto Sans family for Latin and every Indic script, while its payload bullet lists `system-ui` first, which would render Latin in Roboto on Android and defeat the one-family reason. Whether Android ships a local "Noto Sans" Latin face is unverified (spike S6). Nothing here loads a webfont.
9. **Latin chip leading 1.2** (the report gives Indic chips only: 1.35). **Indic selector list**: hi, mr, kn, ta, te, ml, bn, gu, pa, or.
10. **Dash arrays** in px for SVG and CSS samples: watch `14 7`, risky `6 5`, unknown `0 6` with round caps. The report says "long dash", "short dash", "dotted". MapLibre `line-dasharray` uses line-width units, so divide by the width there.
11. **Motion**: `--fr-ease-out: cubic-bezier(0.16, 1, 0.3, 1)` for "ease-out". Under reduced motion: camera 0 ms, highlight 150 ms, press scale 1.
12. **Materials**: sheet edge is ink at 12% (light) or 14% (dark), not translucent white. Shadow is `none` in dark, HC and forced colors. Solid fallback under `prefers-reduced-transparency`.
13. **`--fr-edge-width`** (new token, 0 in default themes, 2 px in HC and forced colors): HC removes tints and shadows, so chips, banners and panels need a border there. Renamed from a chip-only name once the preview showed panels vanishing in HC.
14. **Runtime theme name** `--fr-theme` (`light`, `dark`, `hc`, `hc-dark`, `forced`) so JS, for example the map style, can read the resolved theme instead of repeating the media queries.
15. **Sunlight** is the light HC palette on solid materials (`data-theme="sunlight"` shares the `hc` block). The report says "`prefers-contrast: more` or Sunlight mode" for one palette.
16. **PRODUCT.md Platform**: report text `adaptive web: installable PWA ...` is not a valid value. impeccable 4.1.0 warned `not recognized; treating the project as web`. The first line is now the bare `web`; the surfaces clause stays on its own line below (verified: impeccable reads `web`). In impeccable `adaptive` means native iOS and Android, which a PWA is not.
17. **DESIGN.md**: report text re-homed verbatim under the DESIGN.md headings (every non-heading line of section C is present; checked by script). Frontmatter tokens added: `primary` is the accent (the official linter requires a `primary` colour), light colours plus `-dark` keys, a text scale, `mono`, radii, spacing, risk chips. No Creative North Star was set (the report has none). No Do's and Don'ts section (the report has none).

## 4. Open issues, not changed

- **Weak colour separation, reported by the check (not gated)**: dark watch-risky (CIE76 15.9, CIEDE2000 11.2, deuteranopia) and HC dark risky-impassable (10.2 and 5.0, tritanopia). They rely on icon, label and line style, which satisfies WCAG 1.4.1 but is below the report's own colour bar. Needs a design decision, for example a deeper dark `risky`.
- Unknown vs safe is the closest pair among the five under protanopia in light (CIE76 10.7, CIEDE2000 6.8) and HC (6.8, 4.4). Dotted line, question icon and label carry it.
- `unknown` on canvas is 5.06 to 1 in light (AA, not AAA). Unknown text must go through the chip (10.0 to 1) to meet "AAA for risk text".
- **Forced colors**: Chromium paints a Canvas backplate behind text, so Canvas-coloured text on a LinkText or CanvasText fill disappears. The preview hit this on the selected theme button and the primary button. Use ButtonFace with ButtonText plus a border for primary and selected controls. Noted in `tokens.css`.
- Elevation has no representation in HC beyond `--fr-edge-width`; components need `border: var(--fr-edge-width) solid var(--fr-ink)` on cards and panels.
- In dark, the near-white casing dominates 4 to 6 px lines (the colour reads as a thin core inside white). Faithful to C.2; revisit with the real map style.
- Hindi labels are the report's and still need native review.
- The preview draws chip icons at 16 px so 8 px of vertical padding keeps the risk badge at 32 px; the 24 px size applies to standalone icons. Decide this when the badge component is built.
- Orphan warnings from the official DESIGN.md linter (15) are colours no component references yet. They go away when components exist (December).

## 5. Verification log

- `pnpm check`, `pnpm --filter ui check`: exit 0 (26 pairs in 5 themes, CVD in 5 themes, structure checks).
- Mutation tests of the check (scratch, 13 runs): a clean baseline exits 0. Each of 12 mutations exits 1 with the expected message: low-contrast dark ink-2, drifted dark block, removed sunlight alias, hex leaked into the forced block, light risky moved next to watch (CVD claim), casing as pale as the canvas, token missing from the hc-dark block, pure white HC canvas, risky chip text below 7:1, dark elevated surface too light, and two DESIGN.md colours that differ from tokens.css.
- Independent cross-check (scratch): own regex parser plus `wcag-contrast-ratio` recomputed 104 contrast values, 0 mismatches. `colorspacious` (Machado 2009, severity 100) plus `scikit-image` CIEDE2000 reproduce every CVD figure to the displayed precision. 27 Sharma 2005 test pairs: max error 4e-5 (also a self-test inside the script).
- `npx @google/design.md lint DESIGN.md`: 0 errors, 15 warnings (orphaned tokens only), contrast of all 10 chip components passes.
- `npx impeccable context --target packages/ui` and `doctor` on the final PRODUCT.md and DESIGN.md: platform `web`, no warnings. Without `--target`, impeccable asks which workspace to use, because `pnpm-workspace.yaml` makes the repo a monorepo; `doctor` reports one expected mention (`workspace-context-inherited`: packages/ui inherits the root files).
- `npx impeccable detect packages/ui`: 0 findings, exit 0. First run found 13 cramped-padding chips (fixed: 8 px vertical padding, 16 px icon) and one undeclared font (fixed: `mono` added to DESIGN.md). Two advisory radius notes are waived inline in `preview.html` (every radius is a token equal to the DESIGN.md scale; the detector misparses `16px 16px 0 0`).
- Headless Chromium 141.0.7390.37 (Playwright 1.56, `/opt/pw-browsers/chromium`): all five themes plus OS-driven dark, `prefers-contrast: more`, both together, forced colors and reduced motion resolve to the expected `--fr-theme`; no console errors; no horizontal overflow at 390 px; the page's own measurement shows no failing pair. Defects found by looking and fixed: wrapped samples and misaligned tables, chips wrapping, map demo without an edge, panel boundaries missing in HC, invisible selected and primary button labels in forced colors.
- Not verified: rendering on a real low-end Android, a native Hindi review, real Noto availability on Android, CVD simulation against real users.
