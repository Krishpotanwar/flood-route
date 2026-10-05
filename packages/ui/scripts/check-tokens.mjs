#!/usr/bin/env node
// Checks packages/ui/tokens.css against the numbers claimed in docs/research/06-design-direction.md. Plain Node, no dependencies.
//   Contrast: WCAG 2.x relative-luminance ratio.
//   CVD: Machado, Oliveira, Fernandes 2009 matrices, severity 1.0 (dichromacy), applied to linear sRGB, clipped to 0..1.
//   Distance: CIE Lab with D65 white, from the simulated colours.
//     CIE76     = Euclidean distance. Report 06's CVD figures reproduce under this one.
//     CIEDE2000 = Sharma, Wu, Dalal 2005, kL = kC = kH = 1. The perceptual measure; always lower than CIE76 for large differences.
// Exit 1 on: a failed contrast threshold, a CVD minimum below the report's claim, or token-file drift (see "Structure").
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));

// ---------- colour maths ----------
const rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const luminance = (h) => { const [r, g, b] = rgb(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

const MACHADO = {
  normal: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  deuteranopia: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  protanopia: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  tritanopia: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
};
const D65 = [0.95047, 1, 1.08883];
const labf = (t) => (t > 216 / 24389 ? Math.cbrt(t) : ((24389 / 27) * t + 16) / 116);
function labOf(hex, kind) {
  const v = rgb(hex).map(lin);
  const [r, g, b] = MACHADO[kind].map((row) => Math.min(1, Math.max(0, row[0] * v[0] + row[1] * v[1] + row[2] * v[2])));
  const xyz = [0.4124564 * r + 0.3575761 * g + 0.1804375 * b, 0.2126729 * r + 0.7151522 * g + 0.0721750 * b, 0.0193339 * r + 0.1191920 * g + 0.9503041 * b];
  const [fx, fy, fz] = xyz.map((t, i) => labf(t / D65[i]));
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
const dE76 = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
function dE00([L1, a1, b1], [L2, a2, b2]) {
  const rad = Math.PI / 180, deg = 180 / Math.PI, p7 = 25 ** 7;
  const Cb = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2;
  const G = 0.5 * (1 - Math.sqrt(Cb ** 7 / (Cb ** 7 + p7)));
  const a1p = (1 + G) * a1, a2p = (1 + G) * a2;
  const C1 = Math.hypot(a1p, b1), C2 = Math.hypot(a2p, b2);
  const h1 = C1 === 0 ? 0 : (Math.atan2(b1, a1p) * deg + 360) % 360;
  const h2 = C2 === 0 ? 0 : (Math.atan2(b2, a2p) * deg + 360) % 360;
  let dh = 0;
  if (C1 * C2 !== 0) { dh = h2 - h1; if (dh > 180) dh -= 360; else if (dh < -180) dh += 360; }
  const dL = L2 - L1, dC = C2 - C1, dH = 2 * Math.sqrt(C1 * C2) * Math.sin((dh * rad) / 2);
  const Lb = (L1 + L2) / 2, Cm = (C1 + C2) / 2;
  let hb = h1 + h2;
  if (C1 * C2 !== 0) hb = Math.abs(h1 - h2) <= 180 ? hb / 2 : hb < 360 ? (hb + 360) / 2 : (hb - 360) / 2;
  const T = 1 - 0.17 * Math.cos((hb - 30) * rad) + 0.24 * Math.cos(2 * hb * rad) + 0.32 * Math.cos((3 * hb + 6) * rad) - 0.2 * Math.cos((4 * hb - 63) * rad);
  const Sl = 1 + (0.015 * (Lb - 50) ** 2) / Math.sqrt(20 + (Lb - 50) ** 2), Sc = 1 + 0.045 * Cm, Sh = 1 + 0.015 * Cm * T;
  const Rt = -Math.sin(2 * 30 * Math.exp(-(((hb - 275) / 25) ** 2)) * rad) * 2 * Math.sqrt(Cm ** 7 / (Cm ** 7 + p7));
  return Math.sqrt((dL / Sl) ** 2 + (dC / Sc) ** 2 + (dH / Sh) ** 2 + Rt * (dC / Sc) * (dH / Sh));
}

// Cheap guard so a broken formula cannot silently pass the tokens: known values from WCAG, Sharma 2005 and the Machado rows.
function selfTest() {
  const near = (name, got, want, tol) => { if (!(Math.abs(got - want) <= tol)) throw new Error(`self-test ${name}: got ${got}, want ${want}`); };
  near('black on white', contrast('#000000', '#FFFFFF'), 21, 1e-9);
  near('dE00 Sharma 1', dE00([50, 2.6772, -79.7751], [50, 0, -82.7485]), 2.0425, 1e-4);
  near('dE00 Sharma 2', dE00([50, 2.5, 0], [73, 25, -18]), 27.1492, 1e-4);
  near('dE00 Sharma 3', dE00([60.2574, -34.0099, 36.2677], [60.4626, -34.1751, 39.4387]), 1.2644, 1e-4);
  near('white stays white (protan)', labOf('#FFFFFF', 'protanopia')[0], 100, 1e-3);
  near('dE76 of a unit step', dE76([50, 0, 0], [51, 0, 0]), 1, 1e-12);
}
selfTest();

// ---------- tokens.css parser (comments out, brace-matched, @media tracked) ----------
function parseCss(text) {
  const src = text.replace(/\/\*[\s\S]*?\*\//g, '');
  const rules = [];
  let i = 0;
  (function walk(media) {
    let head = '';
    while (i < src.length) {
      const c = src[i++];
      if (c === '}') return;
      if (c !== '{') { head += c; continue; }
      const sel = head.trim(); head = '';
      if (sel.startsWith('@media')) { walk(sel.slice(6).trim()); continue; }
      const end = src.indexOf('}', i);
      const decls = {};
      for (const d of src.slice(i, end).split(';')) { const k = d.indexOf(':'); if (k > 0) decls[d.slice(0, k).trim()] = d.slice(k + 1).trim(); }
      rules.push({ media, selector: sel.replace(/\s+/g, ' '), decls });
      i = end + 1;
    }
  })(null);
  return rules;
}

const rules = parseCss(readFileSync(here('../tokens.css'), 'utf8'));
const byTheme = {};
for (const r of rules) if (r.decls['--fr-theme']) (byTheme[r.decls['--fr-theme']] ||= []).push(r);
const THEMES = ['light', 'dark', 'hc', 'hc-dark', 'sunlight'];
const fails = [];
const fail = (msg) => fails.push(msg);

// sunlight is an alias: it must share the hc block through its selector.
const aliasOk = byTheme.hc?.some((r) => r.selector.includes('[data-theme="sunlight"]'));
if (!aliasOk) fail('Structure: data-theme="sunlight" is not in the selector of the hc block');
const tokensOf = (theme) => byTheme[theme === 'sunlight' ? 'hc' : theme]?.[0].decls ?? {};

function value(theme, name, depth = 0) {
  const v = tokensOf(theme)[`--fr-${name}`];
  const ref = v?.match(/^var\(--fr-([\w-]+)\)$/);
  if (ref && depth < 5) return value(theme, ref[1], depth + 1);
  return v;
}
function hex(theme, name) {
  const v = value(theme, name);
  if (!/^#[0-9A-Fa-f]{6}$/.test(v ?? '')) throw new Error(`${theme}: --fr-${name} is "${v}", expected an opaque #RRGGBB`);
  return v.toUpperCase();
}

// ---------- claims from report 06 ----------
const NEED = { text: 4.5, risk: 7, graphic: 3, focus: 3 }; // risk = risk text, AAA
const CLAIM = {
  'ink on canvas': { light: 16.1, dark: 15.9 },
  'ink-2 on canvas': { light: 7.8, dark: 9.3 },
  'accent on canvas': { light: 7.1, dark: 9.1 },
  'unknown on canvas': { light: 5.1, dark: 7.0 },
  'safe on canvas': { light: 4.9, dark: 10.2 },
  'watch on canvas': { light: 1.4, dark: 12.4 },
  'risky on canvas': { light: 4.8, dark: 7.2 },
  'impassable on canvas': { light: 15.4, dark: 4.0 },
};
const SOLIDS = ['safe', 'watch', 'risky', 'impassable'];
const LEVELS = [...SOLIDS, 'unknown'];
const BGS = ['canvas', 'surface', 'surface-elevated'];
const PAIRS = [];
const add = (id, role, fg, bg) => PAIRS.push({ id, role, fg, bg });
for (const fg of ['ink', 'ink-2', 'accent', 'unknown']) for (const bg of BGS) add(`${fg} on ${bg}`, 'text', fg, bg);
for (const fg of SOLIDS) add(`${fg} on canvas`, 'graphic', fg, 'canvas');
add('casing on canvas', 'graphic', 'casing', 'canvas');
add('watch-ink on canvas', 'risk', 'watch-ink', 'canvas');
for (const bg of BGS) add(`focus on ${bg}`, 'focus', 'focus', bg);
for (const l of LEVELS) add(`${l} chip text`, 'risk', `${l}-ink`, `${l}-tint`);
const chip = (l) => `${l} chip text`;
const RANGES = [ // report gives min and max across the four levels, not per pair
  { theme: 'light', label: 'chip text, 4 risk chips', ids: SOLIDS.map(chip), claim: [8.3, 12.9] },
  { theme: 'dark', label: 'chip text, 4 risk chips', ids: SOLIDS.map(chip), claim: [9.3, 10.6], derived: true }, // report names no dark chip colours
  { theme: 'hc', label: 'HC solids on canvas', ids: ['safe on canvas', 'watch-ink on canvas', 'risky on canvas', 'impassable on canvas'], claim: [7.9, 16.7], alt: '#FFFFFF' }, // alt: the background the report's figures actually reproduce on
  { theme: 'hc-dark', label: 'HC dark solids on canvas', ids: ['safe on canvas', 'watch-ink on canvas', 'risky on canvas', 'impassable on canvas'], claim: [8.2, 15.3] },
];
const CVD_CLAIM = { light: { 'safe-impassable': 43, 'watch-risky': 37, 'risky-impassable': 57 } }; // minimum across normal, deuter, protan, tritan
const WEAK_CIE76 = 16; // report 06 rejected a red-green set that scored 8 to 16; at or below this we flag the pair

// ---------- WCAG table ----------
const ratio = {}; // ratio[theme][id]
for (const t of THEMES) { ratio[t] = {}; for (const p of PAIRS) ratio[t][p.id] = contrast(hex(t, p.fg), hex(t, p.bg)); }
const status = {}; // 'ok' | 'FAIL' | 'exc'
const differs = [];
for (const t of THEMES) for (const p of PAIRS) {
  const m = ratio[t][p.id], need = NEED[p.role];
  let s = m + 1e-9 >= need ? 'ok' : 'FAIL';
  // Report 06 C.2: watch is never a bare line on canvas; the 1.5px (2px in HC) ink casing carries it. Accept only if the casing itself passes.
  if (s === 'FAIL' && p.id === 'watch on canvas' && ratio[t]['casing on canvas'] >= NEED.graphic) s = 'exc';
  status[`${t}/${p.id}`] = s;
  if (s === 'FAIL' && t !== 'sunlight') fail(`Contrast: ${t}: ${p.id} is ${m.toFixed(2)}:1, needs ${need}:1 (${p.role})`);
  const c = CLAIM[p.id]?.[t];
  if (c !== undefined && Math.abs(m - c) > 0.2) differs.push(`${t.padEnd(8)} ${p.id.padEnd(22)} claimed ${c}:1, measured ${m.toFixed(2)}:1 (delta ${(m - c).toFixed(2)})`);
}
for (const r of RANGES) {
  const v = r.ids.map((id) => ratio[r.theme][id]), lo = Math.min(...v), hi = Math.max(...v);
  if (r.derived) {
    if (lo < r.claim[0] || hi > r.claim[1]) differs.push(`${r.theme.padEnd(8)} ${r.label.padEnd(22)} claimed ${r.claim[0]} to ${r.claim[1]}:1, measured ${lo.toFixed(2)} to ${hi.toFixed(2)}:1 (outside the range; colours are derived, report names none)`);
  } else if (Math.abs(lo - r.claim[0]) > 0.2 || Math.abs(hi - r.claim[1]) > 0.2) {
    const alt = r.alt && r.ids.map((id) => contrast(hex(r.theme, PAIRS.find((p) => p.id === id).fg), r.alt));
    differs.push(`${r.theme.padEnd(8)} ${r.label.padEnd(22)} claimed ${r.claim[0]} to ${r.claim[1]}:1, measured ${lo.toFixed(2)} to ${hi.toFixed(2)}:1${alt ? `; on ${r.alt} it is ${Math.min(...alt).toFixed(2)} to ${Math.max(...alt).toFixed(2)}, so the report used pure white, which its own C.2 rule forbids` : ''}`);
  }
}

const cell = (t, p) => {
  const m = ratio[t][p.id], s = status[`${t}/${p.id}`], c = CLAIM[p.id]?.[t];
  const mark = s === 'FAIL' ? '!' : s === 'exc' ? '~' : c !== undefined && Math.abs(m - c) > 0.2 ? '*' : ' ';
  return `${m.toFixed(2)}${c !== undefined ? ` [${c}]` : ''}${mark}`.padEnd(15);
};
console.log('WCAG 2.x contrast, measured [report claim]. ! fails threshold, ~ documented exception (casing carries it), * differs from claim by > 0.2');
console.log(`${'pair'.padEnd(29)}${'need'.padEnd(6)}${THEMES.map((t) => t.padEnd(15)).join('')}`);
for (const p of PAIRS) console.log(`${p.id.padEnd(29)}${String(NEED[p.role]).padEnd(6)}${THEMES.map((t) => cell(t, p)).join('')}`);
console.log('Ranges claimed by the report (min to max across the four levels):');
for (const r of RANGES) { const v = r.ids.map((id) => ratio[r.theme][id]); console.log(`  ${r.theme.padEnd(8)} ${r.label.padEnd(26)} claimed ${r.claim[0]} to ${r.claim[1]}, measured ${Math.min(...v).toFixed(2)} to ${Math.max(...v).toFixed(2)}${r.derived ? ' (derived colours)' : ''}`); }

// ---------- CVD table ----------
const KINDS = Object.keys(MACHADO);
const cvdPairs = [];
for (let i = 0; i < SOLIDS.length; i++) for (let j = i + 1; j < SOLIDS.length; j++) cvdPairs.push([SOLIDS[i], SOLIDS[j]]);
for (const s of SOLIDS) cvdPairs.push([s, 'unknown']); // information only: unknown must never read as safe
const cvd = {};
for (const t of THEMES) {
  cvd[t] = {};
  for (const [a, b] of cvdPairs) {
    const per = KINDS.map((k) => { const x = labOf(hex(t, a), k), y = labOf(hex(t, b), k); return { k, d76: dE76(x, y), d00: dE00(x, y) }; });
    const w76 = per.reduce((m, e) => (e.d76 < m.d76 ? e : m)), w00 = per.reduce((m, e) => (e.d00 < m.d00 ? e : m));
    cvd[t][`${a}-${b}`] = { d76: w76.d76, k76: w76.k, d00: w00.d00, k00: w00.k };
  }
}
const weak = [];
console.log('\nColour-vision separation of the risk solids: minimum over normal, deuteranopia, protanopia, tritanopia. Watch uses --fr-watch (the line colour).');
for (const [metric, key, title] of [['d00', 'k00', 'CIEDE2000'], ['d76', 'k76', 'CIE76 [report claim]; ~ differs from claim by > 2']]) {
  console.log(`${title}. w = at or below ${WEAK_CIE76} CIE76 (the ceiling of the set report 06 rejected)`);
  console.log(`${'pair'.padEnd(27)}${THEMES.map((t) => t.padEnd(15)).join('')}`);
  for (const [a, b] of cvdPairs) {
    const id = `${a}-${b}`;
    const row = THEMES.map((t) => {
      const e = cvd[t][id], c = metric === 'd76' ? CVD_CLAIM[t]?.[id] : undefined;
      const isWeak = e.d76 <= WEAK_CIE76;
      if (metric === 'd76' && isWeak && b !== 'unknown' && t !== 'sunlight') weak.push(`${t.padEnd(8)} ${id.padEnd(18)} ${e[metric].toFixed(1)} CIE76, ${cvd[t][id].d00.toFixed(1)} CIEDE2000 (${e[key].replace('anopia', '')})`);
      const mark = isWeak ? 'w' : c !== undefined && Math.abs(e[metric] - c) > 2 ? '~' : ' ';
      return `${e[metric].toFixed(1)}${c !== undefined ? ` [${c}]` : ''}${mark}`.padEnd(15);
    });
    console.log(`${(id + (b === 'unknown' ? ' (info)' : '')).padEnd(27)}${row.join('')}`);
  }
}
for (const [id, c] of Object.entries(CVD_CLAIM.light)) {
  const e = cvd.light[id];
  if (e.d76 < c - 2) fail(`CVD: light ${id}: CIE76 ${e.d76.toFixed(1)}, report claims at least ${c}`);
  if (Math.abs(e.d76 - c) > 2 || Math.abs(e.d00 - c) > 2) differs.push(`light    ${id.padEnd(22)} claimed ${c}, measured ${e.d76.toFixed(1)} CIE76 (delta ${(e.d76 - c).toFixed(1)}), ${e.d00.toFixed(1)} CIEDE2000 (delta ${(e.d00 - c).toFixed(1)}); the report's figures are CIE76`);
}

// ---------- structure: the single source of truth must not drift ----------
const keysOf = (r) => Object.keys(r.decls).filter((k) => k.startsWith('--fr-')).sort().join(' ');
const lightKeys = keysOf(byTheme.light[0]);
for (const [name, rs] of Object.entries(byTheme)) {
  for (const r of rs) if (keysOf(r) !== lightKeys) fail(`Structure: a "${name}" block (${r.media ?? 'base'}: ${r.selector}) does not define the same tokens as light`);
  const norm = (r) => JSON.stringify(Object.entries(r.decls).sort());
  for (const r of rs.slice(1)) if (norm(r) !== norm(rs[0])) fail(`Structure: two blocks for theme "${name}" differ (${rs[0].media ?? 'base'} vs ${r.media ?? 'base'}: ${r.selector})`);
}
for (const t of ['light', 'dark', 'hc', 'hc-dark']) if (!byTheme[t]) fail(`Structure: no block for theme "${t}"`);
const SYSTEM = /^(Canvas|CanvasText|LinkText|VisitedText|ActiveText|ButtonFace|ButtonText|ButtonBorder|Field|FieldText|Highlight|HighlightText|SelectedItem|SelectedItemText|Mark|MarkText|GrayText|AccentColor|AccentColorText)$/;
for (const k of ['canvas', 'surface', 'surface-elevated', 'ink', 'ink-2', 'accent', ...LEVELS, ...LEVELS.flatMap((l) => [`${l}-tint`, `${l}-ink`]), 'casing', 'focus']) {
  const v = byTheme.forced?.[0].decls[`--fr-${k}`];
  if (!SYSTEM.test(v ?? '')) fail(`Structure: forced-colors block must map --fr-${k} to a system colour, found "${v}"`);
}
for (const t of ['light', 'dark', 'hc', 'hc-dark']) for (const k of ['canvas', 'surface', 'surface-elevated', 'ink', 'ink-2', 'unknown']) {
  const h = hex(t, k), [r, g, b] = rgb(h);
  if (h === '#000000' || h === '#FFFFFF' || (r === g && g === b)) fail(`Structure: ${t}: --fr-${k} ${h} is pure black, pure white or neutral grey (report 06 C.2)`);
}
const dmPath = here('../../../DESIGN.md');
if (existsSync(dmPath)) { // DESIGN.md frontmatter repeats the colours for impeccable; keep it equal to tokens.css (light, and "-dark" for dark)
  const block = readFileSync(dmPath, 'utf8').match(/^---\n([\s\S]*?)\n---/)?.[1].match(/^colors:\n((?:[ \t]+.*\n?)*)/m)?.[1] ?? '';
  let n = 0;
  for (const line of block.split('\n')) {
    const m = line.match(/^\s+([\w-]+):\s*"(#[0-9A-Fa-f]{6})"/);
    if (!m) continue;
    n++;
    const dark = m[1].endsWith('-dark'), base = dark ? m[1].slice(0, -5) : m[1], name = base === 'primary' ? 'accent' : base; // DESIGN.md calls the accent "primary"
    if (hex(dark ? 'dark' : 'light', name) !== m[2].toUpperCase()) fail(`Structure: DESIGN.md colors.${m[1]} is ${m[2]}, tokens.css says ${hex(dark ? 'dark' : 'light', name)}`);
  }
  if (n === 0) fail('Structure: DESIGN.md has no colors in its frontmatter');
}

// ---------- report ----------
const sat = (h) => { const [r, g, b] = rgb(h), mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; return mx === mn ? 0 : ((mx - mn) / (1 - Math.abs(2 * l - 1))) * 100; };
console.log(`\nAccent HSL saturation: light ${sat(hex('light', 'accent')).toFixed(1)}% (report: 73%), dark ${sat(hex('dark', 'accent')).toFixed(1)}% (report states one figure for both)`);
if (weak.length) console.log(`\nWeak colour separation (not gated; these pairs rely on icon, label and line style):\n  ${weak.join('\n  ')}`);
console.log(`\nDiffers from report 06 by more than 0.2 ratio or 2 deltaE (${differs.length}):\n  ${differs.join('\n  ') || 'none'}`);
console.log(fails.length ? `\nFAIL (${fails.length}):\n  ${fails.join('\n  ')}` : '\nOK: every threshold holds, tokens.css is consistent.');
process.exit(fails.length ? 1 : 0);
