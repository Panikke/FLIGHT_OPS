# EGW//OCC Design System

Control-room aesthetic for an airline operations-control simulation. The player
is a duty crew controller working a disrupted day: the interface should feel
like certified ops equipment — dense, legible at a glance, never decorative.
Source of truth for tokens: `frontend/src/index.css`.

## Direction & feel

- Dark, instrument-panel calm: near-black surfaces (`#050505` page, `#0a0a0c`
  raised), information glows out of the dark in status colors.
- Everything is signal. Color is never decoration — it is always status.
- Dense but quiet: small mono type, generous tracking on labels, whisper
  borders. Craft check: squint — hierarchy survives, nothing shouts.

## Tokens (defined in index.css)

- Status: `--status-info` (cyan — identity/interactive), `--status-nominal`
  (green — OK/legal), `--status-warning` (amber — degraded/attention),
  `--status-critical` (red — breach/blocked).
- Text hierarchy via classes: default, `t-sec`, `t-muted` (+ status tones
  `t-info` / `t-nominal` / `t-warn` / `t-crit`).
- Type: `font-azeret` (Azeret Mono) for display/headlines; `font-mono-jb`
  (JetBrains Mono) for data, tables, terminal text; `label-key` and
  `uppercase-wide` for tracked uppercase labels.

## Depth strategy: borders only

No shadows. Separation is `border-white/10` (standard), `border-white/[0.04]`
(table rows), `border-white/20` (emphasis, e.g. segmented controls). Overlays
use backdrop blur + `bg-black/80`. Do not introduce shadows or new surface hues.

## Spacing

Tailwind scale, base unit 4px. Cell padding `px-3 py-2`; panel/section padding
`px-4`–`px-5`, `py-2`–`py-3`. Gaps `gap-2`–`gap-4`.

## Component patterns

- **KPI tile** (`HeaderBar.jsx` `Kpi`): `label-key` caption, `kpi-num text-2xl`
  value in a status tone, `uppercase-wide t-muted` sub-caption, `border-r`
  separation, `min-w-[120px]`.
- **Header rule:** the top bar and its transport-controls container are
  `flex-wrap` — the PLAY/pause/speed controls must NEVER be clipped off-screen;
  they wrap to a second row on narrow viewports. Don't remove the wrap.
- **Data tables:** `text-xs font-mono-jb`, sticky `thead` on the page color,
  `zebra` body, row borders `border-white/[0.04]`, hover `bg-white/[0.03]`.
- **Status text convention:** entity ids in `t-info`; qualifications green when
  matching / red when not; fatigue thresholds 45/70 (nominal/warn/crit).
- **Inline truth badges:** when engine state contradicts a surface label (e.g.
  crew shows AVAILABLE but is rostered on an overlapping flight), surface the
  engine's knowledge inline in `t-warn` 10px mono (`ROSTERED · EGW142`) rather
  than relying on a rejection message after the action.
- **Warning blocks** (`AssignModal` legality pre-check): `border-l-2` in the
  severity color, `[SEVERITY] CODE` line in mono caps, message, then
  `REF: <rule>` in `uppercase-wide t-muted`.
- **Buttons:** `.btn` base; `btn-primary` (cyan) main action, `btn-ok` (green)
  go/confirm, `btn-warn` (amber) destructive-ish/timeline, `btn-danger` (red)
  remove/override. Critical legality failures disable the primary action and
  reveal an explicit red OVERRIDE — never silently allow.

## Signature

The interface speaks in ops-control language everywhere: terminal prefixes
(`[OK]`, `[WAIT]`, `>> SYS_MSG`), Zulu clock, rule references (ORO.FTL.205),
duty codes. New components should adopt this voice, not generic SaaS copy.

## Planned (not yet built)

- Crew roster calendar (AerOPS-style): rows = crew, columns = days, duty codes
  FLT / SBY / OFF / REST as colored cells — the natural home for the future
  days-off feature.
