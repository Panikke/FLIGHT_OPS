# EGW//OCC — Eaglewing Operations Control Simulation

## Original problem statement
> Browser-deployed, mixed-fleet, hardcore airline crew-control simulation that combines roster planning with a live disruption desk. Research foundation: EASA flight-time limitations, UK CAA framing, disruption recovery, standby, sickness, delayed reporting, positioning, discretion, rest, roster legality. Simulation model: mixed-fleet airline with crew ranks, qualifications, bases, duty periods, aircraft rotations, sectors, reserve/standby pools, sickness/late reports, weather diversions, technical delays, legality/fatigue/cost consequences. Gameplay loop: roster planning → day-of-ops disruption desk. Hardcore EASA/CAA-inspired rule checks. Polished React web app with operations-control dashboard, roster board, crew detail panels, flight timeline, incident queue, decision actions, scoring, scenario progression, help overlays. Label as simulation, not an official compliance tool.

## User choices (locked)
- Scope: Both modes connected (roster → ops)
- Airline: Mixed short/long-haul flag carrier (A320 + A350/B777, hub LHR)
- Persistence: No login, local session (localStorage `egw_occ_game_id` + MongoDB game state)
- AI Ops Advisor: Yes — Emergent LLM key, Claude Sonnet 4.5 via `emergentintegrations`
- Visual style: Agent's choice — "Control Room / Retro-Futurism" (Azeret Mono + Figtree + JetBrains Mono, 0-radius, dark, cyan/amber/red/green status)

## Architecture
- **Backend**: FastAPI + MongoDB (motor). All endpoints under `/api/sim/*`. Game state document stored under collection `games`, keyed by `id`.
- **Frontend**: React 19 single-page app. Three phases: ROSTER → OPS → DEBRIEF. Sidebar nav (Roster, Timeline, Incidents, Crew, Advisor, Regs).
- **LLM**: Anthropic Claude Sonnet 4.5 via `emergentintegrations` library + `EMERGENT_LLM_KEY`. Session id per game. Graceful fallback if outage.

## Domain model
- Fleet: 4×A320, 2×A350, 2×B777 (8 aircraft, all G-EAGx tails)
- Routes: 10 short-haul (LHR-CDG/AMS/FRA/MAD/BCN/FCO/DUB/ZRH/MXP/CPH), 5 long-haul (JFK/DXB/SIN/HKG/LAX) with type pref
- Crew: 114 (CP 14, FO 22, SC 18, CC 60). Type ratings, base, rest hours, FDP used, 28-day block, fatigue score (0-100), status (available/on_duty/standby/sick/off)
- Flights: ~26 / day with std/sta, block min, pax, required crew per type and block length, assigned_crew_ids[]
- Incidents: CREW_SICK, LATE_REPORT, WEATHER, TECH, ATC_FLOW with severity minor/major and recovery option sets

## EASA/UK CAA-inspired rule checks (simulation)
Implemented in `/app/backend/simulation.py::check_assignment`:
- TYPE_QUAL — type rating validity (FCL.740)
- OVERLAP — duty overlap on another assigned flight
- MIN_REST — 12h home rest (ORO.FTL.235)
- STATUS_SICK / STATUS_OFF — fitness to fly
- FDP_EXCEED — 13h short / 14h long FDP (ORO.FTL.205)
- BLOCK_28D — 100 block hr / 28 days (ORO.FTL.210)
- FATIGUE_HIGH — soft warning >70 (ORO.FTL.120)

OVERRIDE: critical breaches can be forced; each force increments `kpis.legality_breaches` and deducts score.

## Implemented (May 2026)
- 2026-05-13: Full backend simulation engine (114-crew flag carrier, EASA-inspired rule checks, incident generator, recovery actions, debrief scoring)
- 2026-05-13: Claude Sonnet 4.5 Ops Advisor (LLM advisor referencing live state JSON) with graceful fallback
- 2026-05-13: React frontend with control-room aesthetic — Boot screen, header KPI strip, sidebar, Roster Board, Flight Timeline Gantt, Incident Queue, Crew Pool, Advisor Panel (telex), FTL Regs cheat sheet, End-of-Day Debrief
- 2026-05-13: Assign Modal with crew search, rank filter, live legality pre-check, ASSIGN + OVERRIDE buttons
- 2026-05-13: localStorage session persistence
- 2026-05-13: **Time speed control** — PLAY/PAUSE + 4 speed levels (1×/2×/5×/15×). Auto-pauses on new incident or any open incident.
- 2026-05-14: **Realism — crew pairings**. Short-haul out-and-back operated by the same crew set (single `pairing_id`, single FDP, assign/unassign propagates across siblings). Long-haul is single-sector per day with crew night-stop. AssignModal shows pairing notice. RosterBoard PAIRING column shows sector sequence.
- 2026-05-14: Bug fixes — IncidentQueue default filter ALL (resolved cards stay visible), Advisor send button no longer occluded by Emergent badge, tick() auto-pauses on backend error.
- 2026-05-14: Backend pytest 13/13 (10 legacy + 3 new pairing tests). Frontend full E2E walked through: boot → roster → assign with pairing notice → start-day → play (clock advanced) → tick → resolve incident → advisor with real Claude response → end-day → debrief.

## Backend endpoints
- `GET /api/` – health
- `POST /api/sim/new` – new game
- `GET /api/sim/{id}` – state
- `GET /api/sim/{id}/roster_status` – roster completeness
- `POST /api/sim/{id}/check_assignment/{flight_id}` – legality pre-check
- `POST /api/sim/{id}/assign/{flight_id}` – assign crew (with optional force)
- `POST /api/sim/{id}/unassign/{flight_id}/{crew_id}` – remove
- `POST /api/sim/{id}/start_day` – ROSTER → OPS
- `POST /api/sim/{id}/tick` – advance clock, spawn incidents
- `POST /api/sim/{id}/resolve/{incident_id}` – apply recovery action
- `POST /api/sim/{id}/end_day` – DEBRIEF
- `POST /api/sim/{id}/advisor` – Claude Sonnet 4.5 advisory

## Testing
- Backend: 10/10 pytest tests passed (`/app/backend/tests/test_occ_backend.py`, JUnit XML at `/app/test_reports/pytest/pytest_results.xml`)
- Frontend: Boot → Roster → Assign Modal → Start Day → OPS time-control header verified via Playwright selectors. Full UI E2E (resolve → advisor → debrief) wired but not yet retested after `data-testid` rename + time-control addition.

## Prioritized backlog
- **P0**: Final UI E2E retest after time-speed feature (tick → resolve → advisor → debrief)
- **P1**: Drag-and-drop crew onto flights in the roster board
- **P1**: AI Advisor "one-click apply" recommendations
- **P2**: Multi-day campaign with crew fatigue + 28-day block carry-over
- **P2**: Scripted set-piece scenarios ("Storm Brunhilde over LHR", "B777 AOG at JFK")
- **P2**: Shareable end-of-day debrief card / leaderboard
- **P2**: Multiple bases (LHR + MAN + EDI), positioning legs

## Files
- `/app/backend/server.py` — FastAPI routes
- `/app/backend/simulation.py` — Domain + rules + incident engine
- `/app/backend/.env` — `MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `EMERGENT_LLM_KEY`
- `/app/frontend/src/App.js` — Orchestrator, play/pause loop
- `/app/frontend/src/api.js` — Axios client
- `/app/frontend/src/components/BootScreen.jsx`
- `/app/frontend/src/components/HeaderBar.jsx` — KPIs + time controls
- `/app/frontend/src/components/Sidebar.jsx`
- `/app/frontend/src/components/AssignModal.jsx`
- `/app/frontend/src/components/views/RosterBoard.jsx`
- `/app/frontend/src/components/views/FlightTimeline.jsx`
- `/app/frontend/src/components/views/IncidentQueue.jsx`
- `/app/frontend/src/components/views/CrewPanel.jsx`
- `/app/frontend/src/components/views/AdvisorPanel.jsx`
- `/app/frontend/src/components/views/RegsHelp.jsx`
- `/app/frontend/src/components/views/Debrief.jsx`
