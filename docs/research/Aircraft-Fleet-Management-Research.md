# Research: How Real Airlines Manage Their Fleet — and What It Means for EGW//OCC

Compiled 2026-07-24 from five parallel research passes (MEL/maintenance, tail assignment &
swaps, spare-aircraft strategy, utilization/turnaround/curfews, and IROPS case studies).
All findings below are sourced; game-design implications are called out separately so the
two don't get blurred.

---

## 1. Maintenance status & the MEL/CDL system

**Findings**
- MEL deferral categories have real day-limits: **Category B = 3 days, C = 10 days, D = 120
  days** (Category A has no fixed interval, it's item-specific). The clock starts the day
  *after* discovery. [ctsys.com MEL guide](https://www.ctsys.com/minimum-equipment-list-mel-pilots-guide/),
  [Pilot Institute](https://pilotinstitute.com/what-is-mel/)
- The **CDL** (Configuration Deviation List) is a separate list for missing external parts
  (fairings, panels). Max 2 missing CDL items at once, max 1 per ATA chapter, and missing
  parts often carry a fuel-burn/speed penalty applied to the flight plan.
  [AviationHunt](https://www.aviationhunt.com/configuration-deviation-list/)
- An open MEL/CDL item can carry operational limitations (no dispatch into certain weather,
  reduced payload, no ETOPS) that exclude a tail from specific routes even though it's
  legally airworthy for others. [AviationHunt](https://www.aviationhunt.com/mmel-vs-mel-definitive-guide/)
- Once deferred, a defect becomes a logged **ADD (Acceptable Deferred Defect)** in the
  aircraft tech log and must be briefed to every subsequent crew — it travels with the tail
  number across sectors until cleared or the deferral limit expires.
  [SKYbrary](https://skybrary.aero/articles/defect-assessment)
- **C-checks** run ~18–24 months / ~3,000 flight hours apart and pull a tail out of service
  for 1–4 weeks; planning starts ~18 months ahead because parts lead times run 8–26 weeks.
  Poor pre-planning routinely turns a 10-day check into 14 days — heavy-check downtime is
  variable, not fixed. [oxmaint.com](https://oxmaint.com/industries/aviation-management/aircraft-heavy-maintenance-planning-a-check-d-check)
- Real AOG examples: **Qantas QF32** (Nov 2010) grounded Qantas's entire 6-aircraft A380
  fleet for 23 days after an uncontained engine failure; the damaged aircraft itself didn't
  return to service for ~2 years, ~A$139M cost.
  [Wikipedia](https://en.wikipedia.org/wiki/Qantas_Flight_32) — **2013 787 battery grounding**
  kept the entire worldwide 787 fleet down ~3 months while Boeing sent ~300 technicians to
  13 locations to retrofit fix kits in place.
  [Wikipedia](https://en.wikipedia.org/wiki/2013_Boeing_787_Dreamliner_grounding)
- Industry-cited AOG cost: **$10,000–$150,000/hour** once lost revenue, crew disruption, and
  delay compensation are counted. [Kinexon](https://kinexon.com/resources/blog/aog-delays-when-rotables-and-missing-assets-ground-your-aircraft)

**Implementation ideas**
- Add an `mel_items: list[dict]` field per tail (`{code, category, deferred_date, expiry_day,
  restriction}`), with a `check_mel_expiry()` warning function following the existing
  `check_*` → `{code, severity, message, rule_ref}` pattern. Category B/C items should raise
  a `warning`-severity flag as the deadline nears and a `critical` (no-override, per your
  "aircraft assignment has no force=True" rule) once expired — the tail simply can't be
  dispatched until cleared.
- Route restrictions from open MEL items are a natural fit for the existing
  `AC_WRONG_STATION`-style hard check you added in PR #25 — e.g. `AC_MEL_RESTRICTED` blocking
  assignment to routes needing ETOPS or specific weather minimums the tail can't currently
  meet.
- A scheduled C-check is really just a multi-day version of what spares already model:
  pull a tail from `FLEET` availability for a fixed day-range, known in advance. This gives
  you a lightweight "planned unavailability" layer distinct from the reactive AOG/MEL layer.
- An occasional random AOG event (rare, high-severity) that force-grounds a tail mid-rotation
  would be a strong "spare of last resort" pressure test — directly exercises your existing
  spare-tail mechanic under stress, the way QF32/787 did to Qantas/Boeing.

---

## 2. Tail assignment, rotations, and swaps

**Findings**
- Airlines separate **fleet assignment** (which aircraft *type* flies a route, locked
  4–6 months out) from **tail assignment** (which specific registration, locked ~24–48h
  before ops, once maintenance status/position are known).
  [Vueling tail-assignment case study](https://www.researchgate.net/publication/349076061_The_Tail_Assignment_Problem_A_Case_Study_at_Vueling_Airlines)
- Real tail-swap triggers: mechanical (route a tail with a deferred defect onto a sector
  where the restriction doesn't matter — e.g. broken wiper, no rain forecast), and
  demand/weather (upgauge a bigger jet onto a route to absorb stranded passengers).
- **Southwest Dec 2022**: the canonical tail/crew-matching collapse. Root cause per DOT was
  *not* the storm — it was a 20-year-old crew-scheduling tool (SkySolver) that couldn't
  re-solve crew-to-aircraft matching at volume once the network fell out of position. Result:
  ~16,700 cancellations, $140M DOT fine (largest ever), $1.3B committed to tech overhaul
  afterward. [Wikipedia](https://en.wikipedia.org/wiki/2022_Southwest_Airlines_scheduling_crisis)
- **Reactionary delay** (Europe) / **late-arriving aircraft** (US) is cited as the single
  biggest driver of network delay — an estimated **54% of total delay cost** comes from
  degraded rotation quality, not the originating delay itself.
  [arXiv](https://arxiv.org/pdf/1301.1136)
- Rotation-breaking (pulling a tail out of sequence) becomes the OCC's tool of choice once
  projected downstream delay would bust a **curfew window** — a hard, non-negotiable
  constraint at hubs like Sydney/Heathrow/Narita.
- Gauge-swap constraints: range/performance margin, runway length (FAA: manufacturer perf
  data required below 60% runway-length utilization), gate/jetbridge compatibility, and
  **crew type rating** — a swap outside the crew's type-rating family can't use the assigned
  crew at all. [FAA AC 150/5360-13](https://www.faa.gov/documentLibrary/media/advisory_circular/150-5360-13/150_5360_13_part2.pdf)

**Implementation ideas**
- Your `reset_reactionary_delays()` fix (PR #25) already models the core insight here —
  a tail swap should clear stale knock-on delay. Consider going further: model reactionary
  delay as *propagating* along a rotation (pairing_id chain) rather than a single flag, so
  the player sees delay cascade forward through the day if they don't intervene — this is
  the "54% of delay cost" mechanic made visible.
  incorporate the tail-swap eligibility rule already partially built (`AC_WRONG_STATION`,
  type/overlap/in-progress checks) — you have most of the plumbing already.
- A once-or-twice-per-game "your crew-scheduling tool falls behind" incident — a period
  where reassignment suggestions are deliberately withheld or delayed, forcing the player to
  manually match crew-to-tail like Southwest's dispatchers did — would be a strong, sourced
  set-piece incident (directly modeled on Dec 2022).
- Curfew-driven rotation breaks: since LHR is already your hub, a **hard curfew window**
  (no-override, like aircraft-assignment legality) that forces early rotation-break decisions
  late in the game day would create real tension without inventing a new subsystem — it's a
  time constraint on the existing pairing/rotation model.

---

## 3. Spare aircraft & reserve-crew strategy

**Findings**
- No fixed industry spare ratio for aircraft (unlike transit's mandated 20%). Real example:
  **US Airways (2012) kept 13 spares total across the whole fleet** — roughly one per
  subfleet — because aircraft are "phenomenally expensive to purchase, operate, and
  maintain." [Simple Flying](https://simpleflying.com/airlines-backup-planes-how-many/)
- Spares skew toward widebodies disproportionately to fleet share, because losing a
  widebody flight (stranded pax, long-haul crew/hotel costs) is much costlier than losing a
  narrowbody one.
- Spare availability is **seasonal, not fixed** — airlines run near-zero spares at summer/
  holiday peak and carry more slack in low season.
- Spares are staged at **hubs, not spokes** — most alternative routes to redeploy into, most
  connections at risk if not covered. Multi-hub airlines have more places to reset from;
  Southwest's point-to-point network (no hub concentration) was cited as a structural reason
  it couldn't easily reposition spare capacity or crews during Dec 2022.
- Ferrying a spare cross-network to the point of need is explicitly a **last-resort, high-cost**
  move in the recovery literature — spares are pre-positioned, not moved reactively.
- **JetBlue Valentine's Day 2007**: aircraft existed but the airline couldn't determine which
  crews still had legal duty-time remaining — 1,195 cancellations, $41M+ cost. A pure
  "crew-legality visibility" failure distinct from aircraft shortage.
  [coverage](https://www.thestreet.com/investing/stocks/candid-jetblue-learns-from-its-2007-mistakes-12218339)
- Reserve pilot ("ready reserve") staffing is the crew-side mirror of spare aircraft — sized
  probabilistically against predicted daily reserve demand, treated explicitly as "the last
  line of defense" after on-call reserve. One disclosed mainline figure: categories
  projected to need ≥20% reserve coverage get extra scheduled days off.
  [Journal of Scheduling](https://link.springer.com/article/10.1007/s10951-006-6778-8)
- Southwest 2022 and JetBlue 2007 both show that **aircraft-spare strategy and crew-reserve
  strategy are not independent** — a failure in crew-legibility/tracking collapses the value
  of physical spare aircraft even when they exist.

**Implementation ideas**
- Your current model (3 spares, one per family, idle at hub, start-of-day) is already close
  to the real US Airways ratio (~1 per subfleet) — good realism baseline. Consider a
  **seasonal/demand toggle**: a "peak day" scenario where 1 of the 3 spares is pre-committed
  to a schedule gap, forcing the player to manage with fewer effective spares — mirrors the
  real "near-zero spares at peak" finding.
- The JetBlue/Southwest insight — that a spare *tail* is useless without a legally available
  crew to put on it — argues for coupling your aircraft-control desk more tightly to crew
  legality: when a spare gets activated, immediately surface whether a legal crew is
  actually available for it, rather than treating aircraft and crew assignment as fully
  separate desks. That's a good hook for advisor-driven feedback ("spare N426AZ available,
  but no legal crew within range — consider reserve pilot X").
- Since spares are real-world "hub-staged, not moved reactively," a design rule worth
  adopting: don't let the player costlessly ferry a spare from one base to another mid-day;
  make it take time/consume duty hours, so ferrying reads as the expensive last resort it is
  in reality.

---

## 4. Utilization, turnarounds, and curfews

**Findings**
- Utilization benchmarks: Ryanair ~9.1 block-hrs/day per 737; legacy hub carriers (United/
  Delta) run lower (~8–10 hrs) than LCCs because hub "bank" scheduling forces idle
  connection windows. [Aerodata](https://aerodata.ai/aircraft-utilization-rate/)
- Turnaround times: narrowbody 30–45 min (Airbus quotes 35–45 for a full A320 turn);
  widebody 90 min–3 hrs, largely due to single-jetbridge deplaning bottlenecks on many
  widebody gates. [Simple Flying](https://simpleflying.com/narrowbody-turnaround-times-time-differences-guide/)
- OAG's framing: shaving 10 minutes off a turn 4x/day frees 40 min of extra revenue-flying
  time per tail per day — turnaround compression is directly monetizable.
  [OAG](https://www.oag.com/blog/science-aircraft-turnarounds)
- Hard curfews are real, geography-specific constraints: **Sydney** ~2300–0600 hard curfew;
  **Frankfurt** legally mandated 2300–0500 CET ban (upheld by Germany's Federal
  Administrative Court) — delayed flights landing after midnight must divert; **Heathrow**
  night restrictions cap available slots. These force certain tails to specific overnight
  bases purely by curfew geometry, independent of route economics.
- Type-swap friction: widebody-for-narrowbody substitution is rare and mostly a US-domestic
  phenomenon; LCCs avoid widebodies almost entirely (higher acquisition/fuel/crew cost per
  trip). Crew type-rating is the binding constraint on cross-type swaps during IROPS.
  [IEOM 2020 paper](http://www.ieomsociety.org/ieom2020/papers/79.pdf)
- Quantified OCC decision-speed cost: a 950-aircraft / 4,500-daily-departure airline with
  ~150 swaps/day — modeling 5-minute vs. 60-second swap decisions — showed thousands of
  controller-hours/year at stake, illustrating why fast swap tooling matters operationally.
  [analysis](https://stechair.substack.com/p/the-fatal-asymmetry-when-your-occ)

**Implementation ideas**
- You already have LHR night curfew (PR #19). Extending the same mechanic to a second hub
  with a *different* curfew window (if you ever add one) would let the player feel the
  "geometry forces overnight basing" constraint the research describes — right now with one
  hub it's a single hard cutoff, not yet a routing puzzle.
- A visible "utilization" stat per tail (block-hours flown today vs. idle time) would turn
  the abstract "idle time = money" finding into a legible score/pressure metric — could tie
  into a scoring/efficiency system if EGW//OCC ever wants one beyond legality/on-time
  metrics.
- Given crew type-rating is the real hard constraint on cross-type swaps, and your `FLEET`
  already tags `{reg, type, spare}` — make sure your tail-assignment legality check already
  blocks (not just discourages) assigning a tail to a pairing whose crew isn't rated for that
  type. If that check doesn't exist yet, it's a clean, well-sourced addition to the
  aircraft-control legality set.

---

## 5. IROPS recovery patterns (case-study synthesis)

**Findings**
- **Southwest Dec 2022** (detailed above) — root cause: crew-tracking tool failure, not
  weather. Recovery tactic used: a deliberate **"reset to zero"** on Dec 26 — preemptively
  cancelling large schedule blocks to re-sync crew/aircraft positions with reality, rather
  than digging out flight-by-flight. Initially still failed because the crew system kept
  assigning crews to already-cancelled flights.
- **Delta / CrowdStrike (Jul 2024)** — Delta's crew-tracking system was corrupted and
  "unable to effectively process the unprecedented number of changes" needed to reassign
  crews; recovery was slowed further because much of Delta's IT had to be manually rebooted
  server-by-server. Delta took days longer to recover than peers hit by the same outage —
  32–36% of schedule cancelled across the worst days, still 22% down the following Monday.
  [CIO Dive](https://www.ciodive.com/news/delta-air-lines-tech-woes-flight-cancelations-crowdstrike-microsoft/722056/)
- OCC triage logic, per industry/academic sources: protect long-haul/international (harder
  to reposition, fewer daily alternatives) over short-haul/regional (many daily
  alternatives); protect dense **hub connection banks** over standalone routes.
  [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0968090X21001480)
- Vendor tools (IBS iFlight, Lufthansa Systems NetLine/Ops++) describe tail-assignment
  optimizers whose **objective function itself shifts** during disruption — from
  cost-minimization in normal ops to "minimize schedule changes / maximize crew roster
  stability" during recovery. [IBS blog](https://blog.ibsplc.com/airline-operations/transforming-aircraft-tail-assignment-through-multi-objective-optimization)

**Implementation ideas**
- The "reset to zero" tactic is a genuinely interesting *player-facing decision*, not just
  flavor: model it as an explicit, costly action the player can choose during a bad
  incident cascade — pre-emptively cancel a block of pairings to resynchronize the fleet,
  trading guaranteed short-term pain (cancellations, EU261-style compensation you already
  model per PR #21) for stopping a worse cascade. This would be a strong, sourced signature
  mechanic distinct from anything you have now.
- The IBS "objective shifts during disruption" idea maps well onto an **advisor mode
  toggle**: in normal ops the advisor optimizes for on-time/utilization; once an incident
  opens (you already have incident-open hooks per the backlog item "advisor proactive
  one-liner on incident open"), the advisor's suggested aircraft assignments could
  explicitly reprioritize toward minimizing further reassignment churn rather than
  optimizing punctuality — a subtle but realistic behavior change the player would notice.
- The Delta/CrowdStrike case is a good template for a rare "your tooling itself degrades"
  incident type distinct from weather/mechanical — e.g. a period where the aircraft-control
  desk's assignment suggestions become unavailable or delayed, forcing manual assignment
  (mirrors both Southwest's and Delta's actual failure mode, and would be a nice thematic
  callback if you ever add a "systems outage" incident category).

---

## Summary: highest-value additions for the Aircraft Control desk

Ranked by (a) how directly sourced-and-real the mechanic is, and (b) how cheaply it builds on
what already exists (`FLEET`, `check_*` pattern, `force=True` override rule, pairing_id
rotations, spares, LHR curfew):

1. **MEL/deferred-defect tracking per tail** — new `check_mel_expiry()`, ties into the
   existing hard-check pattern for aircraft assignment (no override, matching your existing
   design rule).
2. **Crew type-rating hard-block on tail swaps** — cheap addition to existing legality
   checks if not already present; directly sourced as the real binding constraint on
   cross-type substitution.
3. **"Reset to zero" as a player action** — a genuinely novel, sourced, high-drama mechanic
   for cascading incidents, distinct from anything currently in the game.
4. **Scheduled C-check / planned unavailability** — lightweight reuse of the spare-tail
   availability model, just with a known multi-day window instead of reactive AOG.
5. **Spare-aircraft/crew-legality coupling** — surfacing "spare available but no legal crew"
   as advisor feedback, sourced directly from both Southwest and JetBlue's actual failure
   modes.

No current gameplay P1 is agreed yet per the session summary — this list is ranked to make
that conversation easier, not to preempt it.
