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
    └── test_occ_realism.py     unit: escalation, IATA metadata, EU261 comp

frontend/
├── package.json            (uses yarn; craco wraps Create React App)
├── craco.config.js
├── tailwind.config.js
├── public/index.html
└── src/
    ├── App.js              orchestrator: boot → roster → ops → debrief
    ├── api.js              axios client for every /api/sim/* call
    ├── index.css           control-room design tokens
    └── components/
        ├── BootScreen.jsx  scenario picker
        ├── HeaderBar.jsx   clock, transport controls, KPI tiles
        ├── Sidebar.jsx     left navigation
        ├── AssignModal.jsx crew-assignment dialog with legality pre-check
        └── views/
            ├── RosterBoard.jsx     Phase 1 crew board
            ├── FlightTimeline.jsx  Gantt of aircraft + crew duties
            ├── IncidentQueue.jsx   live disruptions
            ├── CrewPanel.jsx       crew list
            ├── CrewRoster.jsx      days-off calendar
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
| `GET /sim/{game_id}/crew_roster` | The days-off calendar view (per-crew duty history + planned days off). |
| `POST /sim/{game_id}/crew/{crew_id}/day_off` | Plan/unplan a rest day. Body: `{"day":N,"off":true｜false}`. |
| `POST /sim/{game_id}/check_assignment/{flight_id}` | Legality pre-check for a crew member. Body: `{"crew_id":"…"}`. Returns `{"warnings":[…],"has_critical":bool}`. |
| `POST /sim/{game_id}/assign/{flight_id}` | Assign crew. Body: `{"crew_id":"…","force":false}`. `force:true` overrides critical warnings (records a breach). |
| `POST /sim/{game_id}/unassign/{flight_id}/{crew_id}` | Remove a crew member from a flight. |
| `POST /sim/{game_id}/auto_roster` | Legally fill all open crew gaps. Only valid in the `ROSTER` phase (else HTTP 400). |
| `POST /sim/{game_id}/start_day` | Move `ROSTER → OPS`. |
| `POST /sim/{game_id}/tick` | Advance the clock. Body: `{"minutes":30}`. Returns new incidents, escalations, reactionary delays, curfew/compensation events, updated KPIs and clock. |
| `POST /sim/{game_id}/resolve/{incident_id}` | Apply a recovery action. Body: `{"action":"callout_standby"｜"cancel"｜…}`. |
| `POST /sim/{game_id}/restart_day` | Reset the current day to 04:00Z, keeping the roster. |
| `POST /sim/{game_id}/end_day` | Move `OPS → DEBRIEF` and compute the day's rating. |
| `POST /sim/{game_id}/next_day` | Roll a campaign into the next day. Only valid in `DEBRIEF` (else HTTP 400). |
| `POST /sim/{game_id}/advisor` | Ask the AI advisor. Body: `{"incident_id":"…"?,"question":"…"?}`. Falls back to a canned reply (HTTP 200, `ok:false`) if no API key. |

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

The full suite is currently **72 tests**. Integration tests exercise real
Mongo reads/writes, so they need MongoDB running too.

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
