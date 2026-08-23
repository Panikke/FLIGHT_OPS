# EGW//OCC Realism Board — shared brief

Every agent in `.claude/agents/` reads this file FIRST, every time. It is the
common ground so four specialists don't re-derive the same context, don't
propose things that already exist, and produce reports that can be read
side by side.

## What the product is

EGW//OCC is an airline **crew-control / operations-control simulation game**.
The player works an OCC desk: a day of flying degrades (tech faults, crew
sickness, weather, ATC), and they recover it under real-world constraints.
It is a *game*, but its entire appeal is that the constraints are genuine —
EASA-style flight-time limitations, curfews, MEL deferrals, aircraft type
compatibility. Realism IS the gameplay. Treat "this isn't how a real OCC
works" as a P1 bug, not a nitpick.

## Architecture you must know before suggesting anything

| Concern | Where |
|---|---|
| Rules engine — pure functions, no I/O | `backend/simulation.py` |
| HTTP API | `backend/server.py` |
| Tests (pure-engine + HTTP integration) | `backend/tests/` |
| React UI | `frontend/src/components/views/` |
| Design system — **source of truth for all UI** | `.interface-design/system.md` |
| Prior research + ranked backlog | `docs/research/` |
| Session state / current work | `.claude/SESSION_SUMMARY.md` |

Key conventions — proposals that violate these will be rejected:

- **`check_*` functions return `list[dict]`** warnings shaped
  `{code, severity, message, rule_ref}`. `severity: "critical"` blocks.
- **Crew constraints are overridable** with `force=True` (a controller can
  make a commercial call). **Aircraft/physical constraints are not** — no
  override, ever.
- **`preview_*` functions** are read-only what-ifs that price a lever before
  the player pulls it (`preview_reset_to_zero`, `preview_ferry`). Any new
  costly lever needs one.
- Everything that changes the world flows through the reactionary-delay
  engine (`propagate_reactionary_delays`) rather than inventing new maths.
- Pairings, not flights, are the unit of crewing: sectors sharing a
  `pairing_id` get one crew set and one tail.

## Already implemented — do NOT propose these

Flight-time limitations (rest, FDP, 7d/28d, consecutive duty days), augmented
crew and bunk FDP extensions, realistic crew composition by aircraft size,
pairings, LHR night curfew (as a hard scheduling constraint, not a fine),
EU261/UK261-style compensation, Poisson-timed incidents, IATA delay codes and
desk metadata, escalation of ignored incidents, aircraft assignment with hard
type/station/overlap checks, a spare-tail fleet, MEL deferred defects with
Cat B/C limits and overnight rectification, an aircraft-decision pause that
freezes the sim clock until the player resolves a grounding, decision grading
against the best feasible alternative, ferry/positioning flights with real
flight-deck crew legality, curfew-adjusted departure and full costing, and
"reset to zero" block cancellation with a priced preview.

Check `docs/research/` and `.claude/SESSION_SUMMARY.md` before every run —
this list goes stale.

## Research sources — the standing remit

Prefer primary sources. Cite a URL for every factual claim.

- **Regulators**: UK CAA (caa.co.uk — CAP 371, ORS, UK Reg (EU) 965/2012
  Subpart FTL), EASA (Air OPS, ORO.FTL), ICAO (Annex 6, Doc 9966 fatigue
  management), IATA (Standard Schedules Information Manual, delay codes,
  Airport Handling Manual).
- **Rostering / ops systems** — how real crews and controllers actually work:
  AIMS (aimsurl), Sabre AirCentre / CrewTrac, Lufthansa Systems NetLine/Crew
  and NetLine/Ops, Jeppesen Crew Rostering, Hitit Crew, IBS iFlight.
- **Crew-facing apps** — what the crew see, which is where realism detail
  hides: eCrew, RosterBuster, CrewLink, Crew Mobile.
- **Airlines to study**: British Airways, easyJet, Ryanair, Virgin Atlantic,
  Jet2, TUI, Wizz Air, Lufthansa, KLM, Air France, Aer Lingus, SAS.
  Their OCC structure, desk layout, published disruption procedures, and any
  public IROPS post-mortems.

## Output contract — every agent, every run

Return **at least 3 suggestions**. More is fine; fewer is a failed run.
Rank them best-first. Each suggestion uses exactly this shape:

```
### N. <short imperative title>

**Gap today** — what the sim does now, with a `file.py:line` citation proving
you actually looked. If you could not find the code, say so explicitly rather
than assuming.

**Real world** — how it actually works, with a source URL. Name the airline,
regulation, or system.

**Proposal** — concrete enough to implement: which function or component,
what the new state/fields look like, which existing engine it reuses.

**Why it matters** — the gameplay or realism payoff, in one or two sentences.

**Effort** — S (a few hours) / M (a session) / L (multi-session).
```

Close with a one-line **Top pick** naming your single highest-value item.

## House rules

1. **Read the code before you claim a gap.** A suggestion without a
   `file:line` citation is worthless and will be discarded.
2. **No generic advice.** "Add more polish" or "consider accessibility" is
   noise. Name the component, the token, the rule.
3. **Reuse beats invention.** If an existing engine can carry the feature,
   say which one. Proposing a parallel legality system is a rejection.
4. **Small and real beats big and vague.** One S-effort suggestion that
   lands is worth more than an L-effort platform rewrite.
5. **Say when you're unsure.** Flag speculation as speculation. Do not
   present a plausible-sounding regulation you did not verify.
