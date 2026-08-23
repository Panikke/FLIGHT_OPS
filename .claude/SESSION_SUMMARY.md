# Session Summary — FLIGHT_OPS (EGW//OCC)
Last checkpoint: 2026-07-26. 2 checkpoints so far.

## Resume point
Large amount of uncommitted work on branch `claude/aircraft-control-fixes` —
NOT yet committed, NOT yet PR'd. Working tree currently has:
`backend/server.py`, `backend/simulation.py`, `backend/tests/test_aircraft_control.py`,
`backend/tests/test_incident_recovery.py`, `backend/tests/test_occ_realism.py`,
`frontend/src/App.js`, `frontend/src/api.js`, `frontend/src/components/HeaderBar.jsx`,
`frontend/src/components/views/AircraftControl.jsx`,
`frontend/src/components/views/IncidentQueue.jsx` all modified, plus new
`backend/tests/test_ferry.py` and `docs/research/Aircraft-Fleet-Management-Research.md`.
All 117 backend tests pass (`REACT_APP_BACKEND_URL=http://localhost:8001 .venv/Scripts/python.exe -m pytest tests/ -q`
from `backend/`). Frontend compiles clean. Both dev servers were left running
in background (backend :8001, frontend :3000, started via Bash not
preview_start — restart manually if the session/harness resets, this has
happened once already this session and killed both silently).
**Next step**: Dan hasn't asked to commit/PR yet — don't commit until asked.
Natural next asks: crew type-rating hard-block on swaps, ferry cost (currently
free — no cost_usd charged for a positioning flight, arguably should be), or
the "reset to zero" cascading-incident mechanic (see backlog below).

## Standing facts
- **Project**: EGW//OCC — airline crew-control simulation game. Repo
  `Panikke/FLIGHT_OPS` (private), local path `C:\Users\Dan\FLIGHT_OPS`.
- **Stack**: FastAPI backend (`backend/server.py`) + pure-function rules
  engine (`backend/simulation.py`) + MongoDB (one `games` collection). React
  19 (CRA + craco) frontend, Tailwind "control-room" dark design system
  (`.interface-design/system.md` is source of truth for tokens/type/style).
- **Domain model**: pairings (sectors sharing `pairing_id`; short-haul =
  out-and-back, long-haul = single sector) — one crew set + one tail per
  pairing. `FLEET` = list of `{reg, type, spare?}`; 8 active tails + 3 spare
  (one per family: A320/A350/B777), spares start each day idle at hub (LHR).
  `state["fleet"]` is now `copy.deepcopy(FLEET)` per game (was a shared-mutable
  bug before this session — every game pointed at the same list).
- **Legality pattern**: `check_*` functions return `list[dict]` warnings
  `{code, severity, message, rule_ref}`; severity `critical` blocks unless
  crew assignment uses `force=True` (aircraft assignment has NO override —
  physical constraints are hard).
- **MEL/deferred-defect system** (new this session): `ac["mel_items"]` list
  of `{id, category(B/C), note, days_remaining, expired}`. `mel_defer`
  incident action now opens a real item (Cat B=3d, Cat C=10d limits) instead
  of being a no-op. `advance_to_next_day` rolls it (70% overnight-clear
  chance else -1 day, `expired=True` at 0). Expired items hard-block
  `check_aircraft_assignment` (`AC_MEL_EXPIRED`, no override).
- **Aircraft-decision pause mechanic** (new this session — Dan's explicit
  design direction, see preferences below): a major-severity TECH incident
  sets `requires_aircraft_decision=True` and `is_clock_paused(state)` freezes
  the WHOLE sim (`tick()` becomes a no-op, returns `{"paused": true}`) until
  resolved. Its incident-queue options collapse to Cancel-only — the real fix
  path is the Aircraft Control desk (`assign_aircraft` or `ferry_spare_aircraft`,
  both auto-resolve the incident + unpause on success). Every resolution gets
  graded (`_grade_aircraft_decision`/`_best_aircraft_decision`) against the
  best feasible alternative, measured in total network reactionary-delay
  minutes (`_simulate_pairing_impact`, scratch-copy what-if, cancel converted
  via `CANCEL_DELAY_EQUIVALENT_MIN_PER_PAX=240`).
- **Ferry (positioning-flight) mechanic** (new this session): `ferry_spare_aircraft`
  dispatches a same-type, fully-free tail EMPTY to reposition it, modeled as
  a REAL flight record (so the existing reactionary-delay engine handles the
  wait-for-it-to-land math for free). Requires real min flight-deck crew (1
  CP+1 FO) found via `_legal_candidates`/`check_assignment` — the SAME EASA-
  FTL-inspired legality engine every other duty uses (rest/FDP/7d/28d/
  consecutive-days). LHR curfew (23:00-06:00Z) pushes departure via
  `_ferry_schedule_avoiding_curfew` — adjusts the schedule, doesn't just fine.
  `check_ferry`/`ferry_spare_aircraft`/`_ferry_plan` in `simulation.py`;
  frontend: AircraftControl's ReassignModal shows a live "FERRY OPTION" panel
  (crew+curfew feasibility) whenever the plain reassign is blocked.
- **`check_aircraft_assignment`/`assign_aircraft` fix** (this session): a
  partially-flown pairing (outbound landed, return still open) used to be
  wrongly treated as fully blocked (`AC_DEPARTED`) and the REASSIGN button
  disabled — real bug that caused Dan's "no control over the aircraft"
  report. Now only blocks when NO sector is left active; reassignment only
  ever touches still-active sectors, completed ones keep their real tail.
- **AI Advisor**: was fully broken — hardcoded model id `claude-sonnet-4-6`
  doesn't exist (fixed → `claude-sonnet-5`). Still non-functional because
  `backend/.env`'s `ANTHROPIC_API_KEY` is empty on Windows — Dan needs to
  paste a real key in and restart the backend; not something Claude can do.
- **Dev workflow**: `gh` CLI not installed — PRs opened via raw GitHub REST
  API using a token from `git-credential-manager.exe get` (Python urllib).
  Dan merges PRs very fast; always `git fetch origin main` before branching.
- Backend run: `cd backend && .venv/Scripts/python.exe -m uvicorn server:app --port 8001`
  (restart via netstat→Stop-Process→relaunch if it dies). Tests need
  `REACT_APP_BACKEND_URL=http://localhost:8001` for the HTTP-integration
  test files.

## Standing preferences & corrections
- **Major direction-setting correction (2026-07-26)**: Dan does NOT want
  aircraft-change decisions auto-resolved by a one-click option. When an
  aircraft needs to change, that's left entirely to the player via Aircraft
  Control — full cascading consequences, the whole sim clock pauses while
  it's undecided, and the choice gets graded against the best possible
  solution afterward. This reverses part of PR #21's "don't force-pause on
  every incident" philosophy, but ONLY for aircraft-grounding incidents
  specifically — everything else (crew sick, weather, ATC) still doesn't
  pause. Don't generalize the pause to other incident types without asking.
- Dan cares about real operational realism to a high level of detail —
  when he flagged the ferry gap, he specified EASA FTL crew legality and
  curfew-as-hard-constraint unprompted. Default to reusing existing legality
  engines (`check_assignment`) rather than inventing simplified new ones —
  it was already comprehensive enough (rest/FDP/duty limits) to cover this.
- When asked to research real airlines/OCCs, Dan means BROAD operational
  realism (desks, workflows, decision-making, economics) transposed into
  gameplay generally — NOT narrowed to one statistic (e.g. delay causes).
- Dan tests by playing and reports findings as short problem statements
  (e.g. "no control over anything to do with the aircraft") — these are
  real bug reports, not vague complaints. Reproduce directly against his
  actual saved game state in Mongo (`db.games.find_one({"id": ...})`) before
  guessing; this found 2 genuine bugs this session that a synthetic repro
  would have missed (grounded-tail-graded-as-best-option; AC_DEPARTED
  wrongly blocking partial-pairing reassignment).
- Don't add `.claude/skills/*` (generic third-party skill caches) to the
  game repo — local tooling, not project-relevant. `.interface-design/`
  design-system doc IS worth tracking (project-relevant, added in commit
  8024f62). `docs/research/` (fleet-management research doc, this session)
  is also project-relevant and worth tracking.
- BreakGlass continuity doc exists separately:
  `C:\Users\Dan\Documents\FLIGHT_OPS_BreakGlass\00_Break-Glass_v1_2026-06-12.docx`
  (increment version on update, never overwrite) — a heavier/older mechanism,
  this SESSION_SUMMARY.md is the lighter faster-to-read complement.

## Open threads
- Uncommitted work (this whole session) needs a commit + PR — waiting on
  Dan to ask.
- Ferry flights currently cost $0 (`cost_usd` untouched) — inconsistent with
  every other recovery lever having a real cost. Likely wants fixing but
  wasn't asked for.
- Research-report backlog (from `docs/research/Aircraft-Fleet-Management-Research.md`,
  ranked): (1) MEL tracking — DONE this session. (2) crew type-rating
  hard-block on cross-type tail swaps — NOT done. (3) "reset to zero"
  player-triggered cascading-incident action — NOT done, flagged as the
  most novel/dramatic remaining idea. (4) scheduled C-check as planned
  multi-day unavailability — NOT done. (5) advisor surfacing "spare
  available but no legal crew" — partially subsumed by the ferry feature's
  live crew-feasibility preview, but not the advisor specifically.
- REVOKE exposed Anthropic key (prefix `sk-ant-api03-eVC5Ow…`, pasted
  2026-06-12) — not confirmed revoked. Windows `backend/.env` key is empty;
  live copy likely on the Pi's `backend/.env`.
- Pi deployment (Tailscale 100.107.242.66) not re-confirmed running
  end-to-end since the recent merges.
- Idea backlog (assessed, not started): Survive-7 local best-scores, advisor
  proactive one-liner on incident open, debrief decision review with
  counterfactuals.

## History (condensed)
- 2026-07-26 session: fixed AI Advisor (bad model id), added MEL/deferred-
  defect tracking (+overnight rectification), fixed shared-mutable FLEET
  bug, built the aircraft-decision pause+grading mechanic (major TECH
  incidents freeze the clock until resolved via Aircraft Control, graded
  against best alternative), fixed a real AC_DEPARTED bug blocking partial-
  pairing reassignment, built the full ferry/positioning-flight mechanic
  with EASA-FTL crew legality + LHR curfew scheduling. 117/117 tests
  passing. Not yet committed.
- PR #25: fixed 3 aircraft-control bugs — spares no longer scheduled from
  day 2+, added station/position hard-check (`AC_WRONG_STATION`), added
  `reset_reactionary_delays()` so a tail swap clears stale knock-on delay
  instead of leaving it stuck. 88/88 tests passing.
- PR #24: Windows setup docs — fixed `Set-Content -Encoding utf8` writing a
  BOM that broke `python-dotenv`'s `MONGO_URL` read; switched to `-Encoding
  ascii`, documented why in Setup-Windows.md + Troubleshooting.md.
- PR #23: new Aircraft Control desk — assign tails to rotations, 3 spare
  tails added to fleet, hard legality checks (type/overlap/in-progress, no
  override), full browser-verified reassign flow.
- PR #22: novice-friendly README rewrite + full `docs/` wiki (setup guides
  per OS, game guide, config reference, troubleshooting, dev guide).
- PR #21: OCC-realism pass — removed forced pause-on-incident, Poisson
  incident timing, IATA desk/code metadata, escalation after 60min idle,
  EU261/UK261-style compensation.
- PR #20: realistic crew composition (CP1/FO+relief/SC1-2+purser/CC per 50
  seats) replacing generic composition.
- PR #19: crew-availability fix (demand-sized pool) + LHR night curfew.
- PR #18: UI accessibility pass (focus rings, contrast, reduced motion).
- Committed 8024f62: tracked `.interface-design/system.md` design doc,
  updated local Claude Code tool permissions.
