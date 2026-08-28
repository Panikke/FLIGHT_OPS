# Session Summary — FLIGHT_OPS (EGW//OCC)
Last checkpoint: 2026-08-28. 3 checkpoints so far.

## Resume point
Repo is fully synced and healthy: local `main` fast-forwarded from 7 commits
behind to `origin/main` (04c5332). Working tree clean. Backend restarted
fresh, full suite passing **221/222 (1 skipped)**. Frontend `node_modules`
present, not rebuilt/tested this checkpoint.

The PREVIOUS checkpoint (2026-07-26) was badly stale by the time this one was
written — it described a large body of work as "uncommitted, not yet PR'd."
In reality all of it (MEL system, aircraft-decision pause+grading, ferry
mechanic) had already shipped via PR #25, AND a full second wave had landed
on top since: a 20-item realism-board audit (all 3 tiers built and merged —
FDP/duty-clock accuracy, delay economics, cascade attribution, crew
disposition desk, cross-type substitution, roster planner), none of which
the old summary mentioned at all. **Lesson: verify `git log`/`git status`
against the summary's claims before trusting "uncommitted work" framing —
don't assume the file is current just because it exists.**

From the original Aircraft-Fleet-Management-Research.md 5-item ranked list,
genuinely still open: **(4) scheduled C-check / planned multi-day
unavailability** and **(5) advisor surfacing "spare available but no legal
crew"** (partially subsumed by the ferry/deadhead crew-feasibility preview,
but not advisor-specific). Items 1-3 (MEL, crew type-rating hard-block,
reset-to-zero) are all done.

**Next step**: asked Dan which of these two (or something else) to build —
awaiting answer, nothing started yet this checkpoint.

## Standing facts
- **Project**: EGW//OCC — airline crew-control simulation game. Repo
  `Panikke/FLIGHT_OPS` (private), local path `C:\Users\Dan\FLIGHT_OPS`.
- **Stack**: FastAPI backend (`backend/server.py`) + pure-function rules
  engine (`backend/simulation.py`, ~4300 lines) + MongoDB (one `games`
  collection). React 19 (CRA + craco) frontend, Tailwind "control-room" dark
  design system (`.interface-design/system.md` = source of truth for
  tokens/type/style; `frontend/src/lib/status.js` is the single shared status
  → tone mapping, replaced 3 diverged copies).
- **Domain model**: pairings (sectors sharing `pairing_id`) — one crew set +
  one tail per pairing. `FLEET`: 8 active tails + 3 spare (one per family:
  A320/A350/B777), `state["fleet"]` is `copy.deepcopy(FLEET)` per game.
  `mel_items` per tail (Cat B=3d/C=10d limits, expired = hard block, no
  override).
- **Legality pattern**: `check_*` → `list[dict]` warnings
  `{code, severity, message, rule_ref}`. `critical` blocks unless forced;
  `_UNFORCEABLE_CODES` (e.g. `TYPE_QUAL`, `REF_NOT_FOUND`) can NEVER be
  forced even with `force=True`. Aircraft assignment has no override at all.
- **Aircraft-decision pause** (Dan's explicit direction, see preferences):
  major TECH incidents set `requires_aircraft_decision=True`, freeze the
  whole clock (`tick()` no-ops) until resolved via Aircraft Control
  (`assign_aircraft`/`ferry_spare_aircraft`), graded against the best
  feasible alternative by total network reactionary-delay minutes.
- **Ferry/deadhead**: `ferry_spare_aircraft` = empty positioning flight,
  modeled as a real flight record; `_deadhead_plan`/`check_deadhead`/
  `preview_deadhead` = crew repositioning against a real inbound seat.
  Ferries are deliberately exempt from the crew-position check (would be
  unusable otherwise) — stated in code, not left silent.
- **FDP/duty accuracy** (realism-board tier 1): `_pairing_fdp_min` is the
  single source of pairing-duty maths, carries delay; `crew_duty_clock` gives
  live slack + latest-off-blocks per crew; `check_crew_hours` →
  `FDP_TIMEOUT`; busts open a `CREW_HOURS` incident (desk CREW CONTROL, IATA
  63) with no "hold" option. ORO.FTL.205 Tables 2/3 replace the old flat 13h
  cap (Table 2 only for non-augmented ops; augmented long-haul keeps 18h).
- **Delay economics**: reactionary minutes priced at `DELAY_COST_PER_MIN_USD
  = 110` (EUROCONTROL) → `kpis["delay_cost_usd"]`. `otp_pct` now measures
  operated flights only; `completion_factor_pct` is the separate
  cancellation metric (was double-punished through OTP before).
  `state["cascade_log"]` = causal edges stamped by trigger (`tick`, `ferry`,
  `reset_to_zero`, `aircraft_change`, `incident_<action>`) — not written from
  inside `propagate_reactionary_delays` since that also runs on scratch
  preview copies.
- **Crew disposition desk** (`CrewDisposition.jsx`): handles out-of-position
  crew. `CREW_WRONG_STATION` check. Standby splits APT/HSBY with callout
  notice + CS FTL.1.225 erosion (6h threshold chosen/cited, operator-scheme-
  dependent per research — flagged uncertain).
- **UI additions this pass**: `CascadeStrip` (OPS header), `ProblemMonitor`
  strip, `HOURS LEFT` duty-clock column in `CrewPanel`, KNOCK-ON + COMPL.
  FACTOR header tiles, incident queue defaults to OPEN + triage-sorted +
  shows escalation fuse, modals now have W3C dialog contract (Escape, focus
  trap, `role="dialog"`) + keyboard accelerators (`useHotkeys`,
  `useModalDialog` in `frontend/src/lib/`), timeline draws real fleet rows +
  ground time + delay-as-displacement.
- **AI Advisor**: was broken (bad model id), fixed to `claude-sonnet-5`.
  Still non-functional locally — `backend/.env`'s `ANTHROPIC_API_KEY` is
  empty on Windows; Dan needs to paste a real key + restart backend.
- **Dev workflow**: `gh` CLI not installed — PRs via raw GitHub REST API,
  token from `git-credential-manager.exe get`. Dan merges very fast — always
  `git fetch origin main` (or just `git pull` on `main`) before trusting
  local branch state.
- Backend: `cd backend && .venv/Scripts/python.exe -m uvicorn server:app --port 8001`.
  Tests need `REACT_APP_BACKEND_URL=http://localhost:8001` for the HTTP-
  integration files. 222 backend tests total (221 pass, 1 skip).
- `docs/research/REALISM_BOARD_LOG.md` = the running findings/status log for
  the `/realism-board` skill (4 parallel research agents: gameplay-design,
  occ-interface, ops-realism, rostering-systems). Its own "Status" sections
  can go stale the same way this file can — cross-check against git log,
  don't trust a "not yet committed" note at face value.

## Standing preferences & corrections
- **Aircraft-change decisions are never auto-resolved.** Player decides via
  Aircraft Control; sim clock pauses while undecided; choice graded after.
  Applies ONLY to aircraft-grounding incidents — don't generalize the pause
  to other incident types without asking.
- Dan cares about real operational realism to a high level of detail and
  will specify the exact regulatory mechanism unprompted (EASA FTL, curfew-
  as-hard-constraint, UK261 articles). Default to reusing existing legality
  engines rather than inventing simplified new ones.
- Research asks mean BROAD operational realism (desks, workflows, decisions,
  economics) transposed into gameplay generally — not narrowed to one stat.
- Dan tests by playing and reports short, real problem statements (e.g. "no
  control over the aircraft") — reproduce against his actual saved game
  state in Mongo before guessing; synthetic repros have missed real bugs
  twice already this project (grounded-tail-graded-as-best; AC_DEPARTED
  wrongly blocking partial-pairing reassignment; crew-position false-
  criticals from wrong pairing-exclusion + wrong departure-time reference).
- Don't add `.claude/skills/*` (generic third-party skill caches) to the
  repo. DO track `.interface-design/` and `docs/research/*` — project-
  relevant.
- BreakGlass continuity doc (separate, heavier mechanism):
  `C:\Users\Dan\Documents\FLIGHT_OPS_BreakGlass\00_Break-Glass_v1_2026-06-12.docx`.

## Open threads
- **Decide next feature** — top open candidates: (4) scheduled C-check /
  planned multi-day tail unavailability, (5) advisor flags "spare available
  but no legal crew." Asked Dan, awaiting answer.
- REVOKE exposed Anthropic key (prefix `sk-ant-api03-eVC5Ow…`, pasted
  2026-06-12) — still not confirmed revoked.
- Pi deployment (Tailscale 100.107.242.66) not re-confirmed running end-to-
  end since the recent merges.
- Agent-flagged research uncertainties (carried forward, not settled):
  standby FDP-reduction threshold is operator-scheme-dependent (6h chosen);
  augmented-crew FDP × in-flight-rest interaction not fully worked through;
  callout-notice figures (easyJet 90min/BA 2h) are anecdotal, not primary-
  sourced; 2 cited FAA human-factors PDFs never text-extracted.
- Idea backlog (assessed, not started): Survive-7 local best-scores, debrief
  decision review with counterfactuals.
- 3 unrelated local git worktrees exist under `.claude/worktrees/` (old
  karaoke-app extraction work, one dev-setup branch) — not FLIGHT_OPS-
  relevant, ignore unless asked to clean up.

## History (condensed)
- 2026-08-2x: realism-board pass — 20 findings across gameplay/interface/
  ops-realism/rostering agents, all 3 tiers built & merged: FDP/duty-clock
  accuracy fix, delay economics (EUROCONTROL cost/min, completion factor),
  cascade-log attribution, crew disposition desk, cross-type substitution
  (upgauge to bigger spare), roster planner (duty lines + open-time work
  list), reset-to-zero refinement, deadhead crew repositioning, W3C modal
  dialogs, real-fleet-row timeline. Type-rating now in `_UNFORCEABLE_CODES`.
  221/222 tests passing.
- PR #25: aircraft-control bug fixes — spares no longer scheduled day 2+,
  `AC_WRONG_STATION` hard-check, `reset_reactionary_delays()` for stale
  knock-on after a tail swap. Also this session: MEL/deferred-defect system,
  aircraft-decision pause+grading mechanic, ferry/positioning-flight
  mechanic with EASA-FTL crew legality + curfew scheduling, AI Advisor model-
  id fix, shared-mutable FLEET bug fix.
- PR #24: Windows setup docs — `Set-Content -Encoding utf8` BOM broke
  `python-dotenv`'s `MONGO_URL` read; switched to `-Encoding ascii`.
- PR #23: Aircraft Control desk — assign tails to rotations, 3 spare tails,
  hard legality checks (type/overlap/in-progress, no override).
- PR #22: novice-friendly README + full `docs/` wiki.
- PR #21: OCC-realism pass — no forced pause-on-incident, Poisson incident
  timing, IATA desk/code metadata, escalation, EU261/UK261 compensation.
- PR #20: realistic crew composition. PR #19: crew-availability + LHR
  curfew. PR #18: UI accessibility pass.
- Commit 8024f62: tracked `.interface-design/system.md`, local tool perms.
