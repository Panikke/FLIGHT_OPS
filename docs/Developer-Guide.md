# Developer Guide

For contributors and anyone who wants to understand, modify, or deploy the game.
If you only want to *play*, you don't need this page — see the
[setup guides](Home.md) instead.

---

## Architecture at a glance

```
frontend/  React 19 SPA (Create React App + craco, Tailwind)
   │  axios calls to  ──►  /api/sim/*
backend/   FastAPI service
   ├─ server.py       thin HTTP layer: routes, load/save game state to Mongo
   └─ simulation.py   ALL the game logic — a pure, dependency-light rules engine
MongoDB    one collection, `games`, one document per game (keyed by `id`)
```

Key design points:

- **`simulation.py` is the heart of the project** and is almost entirely pure
  functions that take a `state` dict and mutate/return it. This is why most
  tests can run without a database or server.
- **`server.py` is deliberately thin** — each route loads the game state from
  Mongo, calls one `simulation` function, saves, and returns. Adding a mechanic
  usually means editing `simulation.py` and, at most, adding one route.
- **The frontend holds no game rules.** It renders whatever state the backend
  returns and posts player actions back. All legality, scoring, and disruption
  logic lives server-side.
- **No auth, no accounts.** The browser keeps the current game's `id` in
  `localStorage`; there is nothing user-specific server-side.

### The game lifecycle

```
new_game → (phase: ROSTER) → assign/auto_roster → start_day
        → (phase: OPS) → tick × N, resolve incidents → end_day
        → (phase: DEBRIEF) → next_day (campaign) ──┐
                                    ▲               │
                                    └───────────────┘
```

---

## Project layout

```
backend/
├── server.py               FastAPI routes (the /api/sim/* surface)
├── simulation.py           Domain model + rules engine (crew, flights,
│                           incidents, delays, curfew, EU261, days-off, scoring)
├── requirements.txt
├── .env.example            Template for the (gitignored) .env you create
└── tests/                  pytest suite
    ├── test_occ_backend.py     integration: core API happy-paths
    ├── test_pairings.py        integration: out-and-back pairing realism
    ├── test_campaign.py        integration: multi-day campaign roll-over
    ├── test_survive7.py        integration: Survive-7 + FDP/bunk rules
    ├── test_incident_recovery.py  integration: state-aware recovery options
    ├── test_reactionary.py     unit: knock-on delay propagation
    ├── test_days_off.py        unit: statutory days-off rules
    ├── test_curfew.py          unit: LHR night curfew
    ├── test_occ_realism.py     unit: escalation, IATA metadata, EU261 comp
    ├── test_aircraft_control.py unit: tail assignment, position, overlap
    ├── test_ferry.py           unit: positioning flights, curfew, crew, cost
    ├── test_reset_to_zero.py   unit: block cancellation and what it relieves
    ├── test_crew_hours.py      unit: delay-aware FDP, discretion, Art.9 care
    ├── test_tier3.py           unit: FDP tables, standby, deadhead, AOG
    └── test_disposition.py     unit: disposition desk, bulk planning, open time

frontend/
├── package.json            (uses yarn; craco wraps Create React App)
├── craco.config.js
├── tailwind.config.js
├── public/index.html
└── src/
    ├── App.js              orchestrator: boot → roster → ops → debrief
    ├── api.js              axios client for every /api/sim/* call
    ├── index.css           control-room design tokens
    ├── lib/
    │   ├── status.js       shared delay thresholds + severity tones
    │   ├── useModalDialog.js  Escape, focus trap, dialog semantics
    │   └── useHotkeys.js   global keyboard accelerators
    └── components/
        ├── BootScreen.jsx  scenario picker
        ├── HeaderBar.jsx   clock, transport controls, KPI tiles
        ├── Sidebar.jsx     left navigation
        ├── AssignModal.jsx crew-assignment dialog with legality pre-check
        ├── WarningBlock.jsx  the single legality-warning renderer
        ├── ProblemMonitor.jsx standing conditions strip
        ├── CascadeStrip.jsx  live knock-on attribution
        ├── OpenTime.jsx      uncovered flying, assignable
        └── views/
            ├── RosterBoard.jsx     Phase 1 crew board
            ├── FlightTimeline.jsx  Gantt of aircraft + crew duties
            ├── IncidentQueue.jsx   live disruptions
            ├── CrewPanel.jsx       crew list
            ├── CrewRoster.jsx      roster planner (duty lines, bulk planning)
            ├── CrewDisposition.jsx out-of-position crew and their options
            ├── AdvisorPanel.jsx    AI advisor chat
            ├── RegsHelp.jsx        FTL rules cheat-sheet
            └── Debrief.jsx         end-of-day report
```

The visual design language (colours, spacing, component patterns) is documented
in `.interface-design/system.md`.

---

## API reference

Base URL: `http://<host>:8001/api`. All responses are JSON. There is no
authentication. `{game_id}` is the `id` returned by `POST /sim/new` (e.g.
`GAME-1A2B3C`).

| Method & path | Purpose |
| ------------- | ------- |
| `GET /` | Health check → `{"service":"OCC Sim","ok":true,"time":…}` |
| `POST /sim/new` | Create a game. Body: `{"scenario":"free_play"｜"survive_7"}` (optional, defaults to free play). Returns the full game state. |
| `GET /sim/{game_id}` | Fetch the full current game state. |
| `GET /sim/{game_id}/roster_status` | Roster completeness summary. |
| `GET /sim/{game_id}/crew_roster` | The roster-planner view: per-crew duty history, planned duties, and today's duty as a full line (report, off-duty, sectors, route, FDP vs cap). |
| `POST /sim/{game_id}/crew/{crew_id}/day_off` | Plan/unplan a single rest day. Body: `{"day":N,"off":true｜false}`. |
| `POST /sim/{game_id}/plan_duty` | **Bulk** duty planning across crew × days. Body: `{"crew_ids":[…],"days":[N,…],"code":"OFF"｜"SBY_APT"｜"SBY_HOME"｜"CLEAR"}`. Returns what applied and what was skipped, with reasons. |
| `GET /sim/{game_id}/open_time` | Uncovered flying, with the legal candidates for each open rank. |
| `GET /sim/{game_id}/irregularities` | The problem monitor: conditions that are wrong right now by the rules (open sectors, duties about to bust, crew out of position, reserve running dry). |
| `GET /sim/{game_id}/crew_disposition` | Crew who need a positioning decision, each with priced, feasibility-checked options. |
| `POST /sim/{game_id}/crew/{crew_id}/preview_dispose` | Price one disposition action without committing. Body: `{"action":"…"}`. |
| `POST /sim/{game_id}/crew/{crew_id}/dispose` | Act on a stranded crew. Body: `{"action":"position_home"｜"hold_downroute"｜"recrew_local"｜"night_stop"}`. |
| `GET /sim/{game_id}/aircraft_control` | The tail desk: fleet with rotations, positions, MEL/AOG state, and `min_turnaround_min`. |
| `POST /sim/{game_id}/check_aircraft/{pairing_id}` | Legality of putting a tail on a rotation. Body: `{"reg":"…"}`. |
| `POST /sim/{game_id}/assign_aircraft/{pairing_id}` | Reassign a rotation to another same-type tail. |
| `POST /sim/{game_id}/check_ferry/{pairing_id}` | Price and gate a positioning flight — returns warnings, the planned leg, its cost, and the flight-deck crew it would consume. |
| `POST /sim/{game_id}/ferry_aircraft/{pairing_id}` | Dispatch a spare empty to reposition it. |
| `POST /sim/{game_id}/check_substitution/{pairing_id}` | Price and gate an **upgauge** onto an off-type tail: cost, seats, and the crew impact. |
| `POST /sim/{game_id}/substitute_aircraft/{pairing_id}` | Cover a rotation with a bigger aircraft. Recomputes `required_crew` and stands down anyone not type-rated. |
| `POST /sim/{game_id}/preview_reset_to_zero` | Price a block cancellation: cost, compensation, care, and how many *other* rotations it relieves. Body: `{"pairing_ids":[…]}`. |
| `POST /sim/{game_id}/reset_to_zero` | Commit the block cancellation. |
| `POST /sim/{game_id}/check_assignment/{flight_id}` | Legality pre-check for a crew member. Body: `{"crew_id":"…"}`. Returns `{"warnings":[…],"has_critical":bool,"discretion":{…}}`. |
| `POST /sim/{game_id}/assign/{flight_id}` | Assign crew. Body: `{"crew_id":"…","force":false,"discretion":false}`. `force:true` overrides critical warnings and records a breach — except `TYPE_QUAL`, which no override reaches. `discretion:true` applies commander's discretion to an FDP overrun, which is **legal** rather than a breach. |
| `POST /sim/{game_id}/unassign/{flight_id}/{crew_id}` | Remove a crew member from a flight. |
| `POST /sim/{game_id}/auto_roster` | Legally fill all open crew gaps. Only valid in the `ROSTER` phase (else HTTP 400). |
| `POST /sim/{game_id}/start_day` | Move `ROSTER → OPS`. |
| `POST /sim/{game_id}/tick` | Advance the clock. Body: `{"minutes":30}`. Returns new incidents, escalations, reactionary delays, curfew/compensation events, updated KPIs and clock. |
| `POST /sim/{game_id}/resolve/{incident_id}` | Apply a recovery action. Body: `{"action":"callout_standby"｜"cancel"｜…}`. |
| `POST /sim/{game_id}/restart_day` | Reset the current day to 04:00Z, keeping the roster. |
| `POST /sim/{game_id}/end_day` | Move `OPS → DEBRIEF` and compute the day's rating. |
| `POST /sim/{game_id}/next_day` | Roll a campaign into the next day. Only valid in `DEBRIEF` (else HTTP 400). |
| `POST /sim/{game_id}/advisor` | Ask the AI advisor. Body: `{"incident_id":"…"?,"question":"…"?}`. Falls back to a canned reply (HTTP 200, `ok:false`) if no API key. |

### Engine conventions

Three patterns run through `simulation.py`, and new code is expected to follow
them rather than invent alternatives:

- **`check_*` returns a list of warnings**, each `{code, severity, message,
  rule_ref}`. `severity: "critical"` blocks. This is the only legality shape.
- **`preview_*` prices a lever without committing.** Anything that costs money
  has one, so the UI can show the bill before the player clicks. Previews run
  against scratch copies and must never write to real state — notably not to
  `state["cascade_log"]`.
- **Crew constraints are overridable, physical ones are not.** Rest, duty
  limits and days off are commercial calls a controller may take and pay for.
  Aircraft type, range, stand size, position and serviceability are not, and
  neither is a crew type rating.

Everything that changes the world routes through
`propagate_reactionary_delays`, so knock-on delay stays consistent no matter
which lever caused it.

### Quick smoke test

With the backend running:

```bash
# Health
curl -s http://localhost:8001/api/

# Create a game and read its id + phase
curl -s -X POST http://localhost:8001/api/sim/new \
     -H "Content-Type: application/json" -d '{"scenario":"free_play"}'
```

---

## Running the tests

The suite has two kinds of tests:

- **Pure-unit tests** (`test_reactionary.py`, `test_days_off.py`,
  `test_curfew.py`, `test_occ_realism.py`) — run `simulation.py` directly, need
  **no server and no database**. Fast.
- **Integration tests** (the rest) — hit a **running backend** over HTTP, so
  they need the backend up and a `REACT_APP_BACKEND_URL` (or `frontend/.env`)
  pointing at it.

```bash
cd backend
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# Just the fast unit tests (no server needed):
pytest tests/test_reactionary.py tests/test_days_off.py \
       tests/test_curfew.py tests/test_occ_realism.py -q

# The full suite (start the backend first, in another terminal):
#   uvicorn server:app --port 8001
REACT_APP_BACKEND_URL=http://localhost:8001 pytest tests -q
```

The full suite is currently **222 tests**. Integration tests exercise real
Mongo reads/writes, so they need MongoDB running too.

Most of the suite is pure-unit and runs in well under a second against
`simulation.py` directly; the minute-plus runtime is almost entirely the
HTTP-integration files.

---

## Maintenance

### Update to the latest code

```bash
cd FLIGHT_OPS
git pull
# backend deps (if requirements.txt changed):
cd backend && source .venv/bin/activate && pip install -r requirements.txt
# frontend deps (if package.json changed):
cd ../frontend && yarn install
```

### Back up / reset saved games

Game state lives in MongoDB's `games` collection.

```bash
# Back up
mongodump --uri="mongodb://localhost:27017" --db=egw_occ --out=./backup-$(date +%F)

# Wipe all saved games (start fresh)
mongosh --eval 'db.getSiblingDB("egw_occ").games.drop()'
```

(With Docker, prefix `mongosh`/`mongodump` calls with
`docker exec mongo …`, or install the Mongo shell locally.)

---

## Running as a permanent service

For casual play you just run `uvicorn` and `yarn start` in two terminals. To
keep the game running unattended (e.g. on a home server or Pi), run the backend
under a process manager and serve a **production build** of the frontend.

### 1. Build the frontend once

```bash
cd frontend
yarn build            # outputs frontend/build/ (static files)
```

### 2. Keep the backend alive with systemd (Linux)

Create `/etc/systemd/system/egw-occ-backend.service`:

```ini
[Unit]
Description=EGW OCC Backend
After=network.target docker.service

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/FLIGHT_OPS/backend
EnvironmentFile=/home/youruser/FLIGHT_OPS/backend/.env
ExecStart=/home/youruser/FLIGHT_OPS/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now egw-occ-backend
```

### 3. Serve everything behind nginx (optional)

Serve the static `frontend/build/` directory and proxy `/api/` to the backend:

```nginx
server {
    listen 80;
    server_name your-domain.example.com;

    root /home/youruser/FLIGHT_OPS/frontend/build;
    index index.html;

    location /api/ {
        proxy_pass         http://127.0.0.1:8001/api/;
        proxy_read_timeout 90s;   # the advisor call can take ~20s
    }
    location / { try_files $uri $uri/ /index.html; }
}
```

When served this way, set `REACT_APP_BACKEND_URL` to the public site root and
**rebuild** (`yarn build`), and add that origin to `CORS_ORIGINS`. Add HTTPS
with [certbot](https://certbot.eff.org/) (`sudo certbot --nginx -d
your-domain.example.com`).

---

## Contributing

- The engine is the source of truth — prefer adding logic in `simulation.py`
  with unit tests over spreading rules into `server.py` or the frontend.
- Add a focused test for any new mechanic. Pure-unit style (no server) is
  preferred where possible — see `test_curfew.py` or `test_occ_realism.py` for
  the pattern.
- Run the full suite green before opening a pull request.
- Keep UI changes within the existing design system
  (`.interface-design/system.md`).
