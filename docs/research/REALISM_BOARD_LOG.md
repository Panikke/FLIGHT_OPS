# Realism Board — suggestion log

Append-only record of what the board has proposed, so successive runs build on
each other instead of rediscovering the same gaps. Agents read this before
proposing; the main session appends after each run.

Status vocabulary: **proposed** (on the table) · **accepted** (agreed, not yet
built) · **built** (shipped — note the PR) · **rejected** (with the reason,
which is the most useful field in this file).

---

## Standing rejections — do not re-propose

| Idea | Why rejected |
|---|---|
| Generalise the clock pause to all incident types | Deliberate design: only aircraft-grounding decisions freeze the sim. Crew sick, weather and ATC must stay live so the player triages under time pressure. |
| Build a recovery optimiser / auto-solver | The game is the decision. An optimiser removes it. Grading against the best alternative already gives the learning benefit without taking the choice away. |
| Simplify the ruleset for approachability | Realism is the product. Make complexity *legible* instead. |

---

## Run history

## 2026-08-19 — Run 1 (baseline sweep, all four agents)

Focus: `ops-realism` on the crew/regulatory side, `rostering-systems` on
baseline vendor research, `occ-interface` on Aircraft Control + Incident
Queue, `gameplay-design` on lever trade-offs. 21 suggestions merged to 20.
All code citations spot-checked against the tree before logging.

### Independent convergences (two agents, separate routes — strongest signal)

- **Delay does not consume FDP.** `ops-realism` #1 and `rostering-systems` #1,
  both their top pick. `fdp_used_min` accrues scheduled `block_min` only
  (`simulation.py:2257`); `delay_min` appears nowhere in the FDP path and
  nothing re-runs `check_assignment` on a delayed flight. A pairing can slip
  4h with crew legality byte-identical.
- **Standby is free and undifferentiated.** `ops-realism` #6 and
  `rostering-systems` #3. No airport/home split, no callout notice, no duty
  accrual. `RegsHelp.jsx:26` *documents a rule the engine does not implement*.
- **Shipped-and-discarded payloads.** `gameplay-design` #2 (cascade edges from
  `propagate_reactionary_delays`, 0 frontend refs) and `occ-interface` #1
  (`fleet[].rotations`, `first_dep`, `last_arr`, `min_turnaround_min`, 0
  frontend refs). Same class of defect, different fields.

### Ranked merged set

**Tier 1 — structural**

1. **Delay consumes FDP; crew can time out.** New `check_crew_hours` /
   `crew_duty_clock`, `FDP_TIMEOUT` critical, `CREW_HOURS` incident raised
   from `tick()`. Wires the delay engine to the crew desk — today they are
   near-independent subsystems. `ops-realism` #1 + `rostering-systems` #1. M
2. **Price reactionary delay in the score.** `_recompute_kpis`
   (`simulation.py:2872-2876`) has four terms; delay reaches the player only
   via `max(0, (75-otp)*5)`, zero at OTP>=75. `pax_delay_min` written in 3
   places, read nowhere. Measured consequence: reset-to-zero 0/120
   score-positive (median -458); cancel 0/200 wins vs ferry. Also split
   `otp_pct` (operated flights) from `completion_factor_pct` — the current
   denominator (`len(flights)`) punishes cancelling twice. `gameplay-design`
   #1. M
3. **Cascade ledger.** `propagate_reactionary_delays` builds
   `{callsign, inbound_callsign, added_min}` edges, returned by `tick()`,
   `resolve_incident()` and the aircraft route; frontend refs: 0. Persist as
   `state["cascade_log"]`, render live strip + per-decision diff.
   `gameplay-design` #2. M

**Tier 2 — cheap, high value**

4. `--status-crit` is an undefined token, used only at
   `AircraftControl.jsx:152,161` — both on RESET TO ZERO. Invalid at
   computed-value time, so the destructive control's red framing does not
   render. `occ-interface` #5. XS
5. RTZ `reactionary_avoided_min` counts the cancelled flights' own delay —
   median 71.8% self-credit, 100% in 42% of cases. Rendered green as the only
   benefit against ~$292k. `gameplay-design` #3. S
6. `MIN_REST_AWAY_HR = 10` defined at `simulation.py:79`, referenced nowhere;
   rest never derived from the preceding duty (re-rolled randomly at
   rollover). ORO.FTL.235: >= preceding duty, or 12h home / 10h down-route.
   `ops-realism` #4. S
7. Duty of care on weather/ATC. Art. 9 is not defeated by extraordinary
   circumstances (*McDonagh v Ryanair* C-12/11); zero hits for hotel/meal/care
   in the codebase, so weather is economically free. `ops-realism` #3. S
8. Escalation fuse invisible. `ESCALATION_AFTER_MIN = 60` drives the pressure
   loop; UI shows raised-time and a post-hoc badge. Queue defaults to ALL
   (`IncidentQueue.jsx:12`), unsorted. `occ-interface` #2. S
9. Severity colour has three dialects across four views; the reassign
   compatibility block hard-codes red for every severity while the ferry block
   20 lines below branches correctly. `occ-interface` #3. S
10. Debrief shows one combined DELAY column; split PRIMARY / KNOCK-ON (IATA
    93), and carry `decision_grade` + delay-caused into the decisions log.
    `gameplay-design` #5. S
11. `CREW_WRONG_STATION` check — crew have `base` but no position, so an
    LHR standby can be rostered onto a JFK->LHR sector and teleport. Mirrors
    the existing `AC_WRONG_STATION`. Critical but overridable.
    `rostering-systems` #2. S
12. Commander's discretion (ORO.FTL.205(f)): +2h, +3h augmented, rest floor
    10h, CAA report within 28d if >1h. Replaces the blanket `force=True`
    cheat for FDP-only breaches. `ops-realism` #2. S/M

**Tier 3 — larger**

13. Candidate rows show station / free-from / turn margin; payload already
    carries it. `occ-interface` #1 (their top pick). M
14. Standby split APT/HSBY with callout notice and CS FTL.1.225 FDP erosion.
    `ops-realism` #6 + `rostering-systems` #3. M
15. Ferry offered as a choice not a fallback (`canFerryInstead` requires the
    plain path to be blocked first), priced in standby crew rather than only
    cash; consider staging one spare off-hub. `gameplay-design` #4. M
16. Problem Monitor — legality-driven irregularities strip + real vocabulary
    (open sectors, crewing officer, positioning not deadhead).
    `rostering-systems` #4. M
17. Deadhead is a stub: `flight["delay_min"] += 45` and nothing else
    (`simulation.py:2757`). Build `_deadhead_plan` / `check_deadhead` /
    `preview_deadhead` mirroring the ferry path. `rostering-systems` #5. M
18. Modal dialog semantics (Escape, focus trap, `role="dialog"`) + keyboard
    accelerators; PR #18's a11y work did not propagate to newer components.
    `occ-interface` #4. M
19. Timeline as a real tracking board: rows from `state.fleet` so spares are
    visible, ground-time segments against `min_turnaround_min`, delay drawn as
    displacement not a longer sector. `occ-interface` #6. M
20. FDP cap by report time / sector count / acclimatisation (ORO.FTL.205
    Tables 2 and 3) instead of a flat 13h. `ops-realism` #5. M

### Agent-flagged uncertainty (carried forward, do not treat as settled)

- Standby FDP-reduction threshold varies by operator scheme (4h/6h/8h) — pick
  one and cite it in the constant's comment.
- Augmented-crew FDP interaction with in-flight rest not worked through.
- Callout notice figures (easyJet 90min, BA 2h) are forum/Glassdoor anecdote.
- Two FAA human-factors PDFs cited by existence only, not text-extracted.

### Status

**Tier 1 (items 1-3): BUILT** 2026-08-19, not yet committed.

- Delay now consumes FDP. `_pairing_fdp_min` is the single source of the
  pairing-duty maths and carries the delay term; `crew_duty_clock` gives every
  crew a live slack figure and a latest-off-blocks time; `check_crew_hours`
  raises `FDP_TIMEOUT`; `tick()` opens a `CREW_HOURS` incident (desk CREW
  CONTROL, IATA 63) when a duty busts, one per pairing per day. Its options
  deliberately exclude "hold" — accepting more delay is what caused it.
  Resolving by crew swap stands the timed-out crew down into rest first.
- Reactionary minutes are priced at `DELAY_COST_PER_MIN_USD = 110`
  (EUROCONTROL) as `kpis["delay_cost_usd"]`, with its own score term. `otp_pct`
  now measures operated flights only; cancelling shows up in the new
  `completion_factor_pct` instead of being punished twice through OTP.
- `state["cascade_log"]` persists the causal edges, stamped with the trigger
  that produced them (`tick`, `ferry`, `reset_to_zero`, `aircraft_change`,
  `incident_<action>`). Deliberately not written from inside
  `propagate_reactionary_delays`, which also runs on preview scratch copies.

UI: KNOCK-ON and COMPL. FACTOR tiles in `HeaderBar`, an `HOURS LEFT` duty-clock
column in `CrewPanel`, and a new `CascadeStrip` under the header during OPS.
`duty_clocks` is computed fresh on `GET /sim/{id}` rather than persisted.

Bug found and fixed during implementation: the first cut of `crew_duty_clock`
double-counted sectors already flown (`fdp_used_min` accrues per landed sector,
while `_pairing_fdp_min` spans the whole pairing), reporting legal crews as
550min out of hours. Regression tests added.

**Tier 2 (items 4-12) and Tier 3 (items 13-20): BUILT** 2026-08-20/21, not yet
committed. 177 backend tests passing, frontend building clean, verified
end-to-end against a live game.

Tier 2 highlights: the undefined `--status-crit` token (the destructive
control's red framing never rendered); reset-to-zero now measures third-party
relief only, plus `sectors_relieved`; cancelling owes UK261 Art. 7; Art. 9 care
is charged regardless of cause, so weather is no longer economically free;
ORO.FTL.235 rest is the longer of the preceding duty and the 12h/10h floor;
`CREW_WRONG_STATION`; commander's discretion replaces the blanket override for
FDP-only breaches; the incident queue defaults to OPEN, triage-sorts, and shows
the escalation fuse; one `WarningBlock` and one `lib/status.js` replace three
diverged copies; the debrief splits PRIMARY from KNOCK-ON.

Tier 3 highlights: ORO.FTL.205 Tables 2 and 3 replace the flat FDP cap; standby
splits APT/HSBY with a callout notice and CS FTL.1.225 erosion; positioning is a
real movement against a real inbound (`_deadhead_plan` / `check_deadhead` /
`preview_deadhead`) instead of `delay_min += 45`; `crew_irregularities` plus a
`ProblemMonitor` strip; the ferry is offered as a choice and priced in standby
crew; candidate rows show station, free-from and turn margin; the timeline draws
fleet rows, ground time and delay-as-displacement; modals get the W3C dialog
contract and the app gets keyboard accelerators.

Bugs found during implementation, all now pinned by tests:

- **Item 20's FDP column mapping was off by one** — 6 sectors read the
  7-sector cap. Caught by asserting the published gap between columns rather
  than merely "less than".
- **Item 11 shipped two bugs only a live game exposed**, both about what counts
  as a crew's position. Excluding the crew's own pairing (right for a tail
  swap, wrong for crew) made every out-and-back return read as out of position:
  36 false criticals. Measuring against the scheduled rather than the effective
  departure then turned every knock-on into a fake breach: 13 more. The unit
  tests missed both because the fixtures used two pairing ids and no delay.

Deviations from what the board proposed, and why:

- **Ferries are exempt from the crew position check.** A ferry departing MXP
  cannot be crewed by LHR pilots — true to life, but it would have made the
  lever unusable before item 17 existed. Stated in the code with a pointer to
  the deadhead mechanic rather than left silent.
- **Item 20 applies Table 2 only to operations without in-flight rest.**
  Augmented long-haul keeps its 18h cap: ORO.FTL.205(b) is the basic table and
  augmented crew fall under the in-flight rest provisions.
- **`test_day7_more_incidents_than_day1` was measuring the wrong thing.** It
  ticked 20 times without resolving anything, so on day 7 (tech_mult 2.5) the
  aircraft-decision pause froze the clock at tick 3 and the busiest day looked
  like the quietest. It now stands in for a controller who keeps up.

Carried forward, unresolved: the agent-flagged uncertainties above still stand —
the standby FDP-reduction threshold is operator-scheme-dependent (6h chosen and
cited in the constant), and the callout notice figures remain anecdote.
