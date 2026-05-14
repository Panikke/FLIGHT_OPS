# EGW//OCC — Airline Crew-Control Simulation

> A hardcore, mixed-fleet, browser-based airline operations-control simulation.
> Plan the roster, then survive a day of sickness, weather, tech and ATC flow as
> the duty Crew Controller. **This is a SIMULATION — not an official compliance
> tool.**

* **Frontend**: React 19 (CRA + craco) — control-room aesthetic, dark theme
* **Backend**: FastAPI (Python 3.11+) with MongoDB
* **AI Ops Advisor**: Claude Sonnet 4.5 via the `emergentintegrations` library
  using a single `EMERGENT_LLM_KEY` (one key, multi-provider)
* **No login** — sessions are kept locally per browser (`localStorage`)
* **Two scenarios**: open-ended **Free Play** campaign, or fixed-seed
  **Survive 7 Days** challenge with escalating disruption

---

## Table of contents

1. [What's in the box](#1-whats-in-the-box)
2. [Prerequisites](#2-prerequisites)
3. [Getting the code](#3-getting-the-code)
4. [Configuration — environment variables](#4-configuration--environment-variables)
5. [Database setup (MongoDB)](#5-database-setup-mongodb)
6. [LLM key (Ops Advisor)](#6-llm-key-ops-advisor)
7. [Install dependencies](#7-install-dependencies)
8. [Run in development mode](#8-run-in-development-mode)
9. [Run in production (single server)](#9-run-in-production-single-server)
10. [Run with `supervisor` (recommended for VMs)](#10-run-with-supervisor-recommended-for-vms)
11. [Run with `systemd` (alternative)](#11-run-with-systemd-alternative)
12. [Reverse-proxy with Nginx + HTTPS](#12-reverse-proxy-with-nginx--https)
13. [Run with Docker / Docker Compose](#13-run-with-docker--docker-compose)
14. [Smoke-test the install](#14-smoke-test-the-install)
15. [Updating / maintenance](#15-updating--maintenance)
16. [Troubleshooting](#16-troubleshooting)
17. [Project layout](#17-project-layout)

---

## 1. What's in the box

```
/app
├── backend/                 # FastAPI service
│   ├── server.py            # HTTP routes (/api/sim/*)
│   ├── simulation.py        # Domain model + EASA-inspired rule engine
│   ├── tests/               # pytest suite (30+ tests)
│   ├── requirements.txt
│   └── .env                 # NOT committed in production
├── frontend/                # React SPA
│   ├── src/                 # Components, views, API client
│   ├── package.json
│   └── .env                 # Points to backend URL
└── README.md                # ← you are here
```

---

## 2. Prerequisites

You will need a Linux/macOS/Windows machine with the following installed.
Versions shown are the minimum supported.

| Tool          | Version | Purpose                                |
| ------------- | ------- | -------------------------------------- |
| **Python**    | 3.11+   | Runs the FastAPI backend               |
| **Node.js**   | 20.x    | Builds and runs the React frontend     |
| **Yarn**      | 1.22+   | Frontend package manager (required — do not use npm; package.json declares `packageManager: yarn@1.22.22`) |
| **MongoDB**   | 6.0+    | Game state persistence                 |
| **git**       | any     | Get the code                           |

Optional (for production):

| Tool          | Purpose                              |
| ------------- | ------------------------------------ |
| **nginx**     | Reverse-proxy + HTTPS termination    |
| **supervisor** or **systemd** | Keep services running on boot |
| **certbot**   | Free Let's Encrypt TLS certificate   |
| **Docker** + **Docker Compose** | Containerised deploy   |

### Install commands by OS

**Debian / Ubuntu**

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip nodejs git curl
sudo npm install -g yarn
# MongoDB 7.0 (community edition)
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc \
  | sudo gpg --dearmor -o /usr/share/keyrings/mongo-7.0.gpg
echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/mongo-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
  | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt update
sudo apt install -y mongodb-org
sudo systemctl enable --now mongod
```

**macOS (Homebrew)**

```bash
brew install python@3.11 node yarn git
brew tap mongodb/brew
brew install mongodb-community@7.0
brew services start mongodb-community@7.0
```

**RHEL / Rocky / Alma**

```bash
sudo dnf install -y python3.11 nodejs git
sudo npm install -g yarn
# MongoDB: follow https://www.mongodb.com/docs/manual/tutorial/install-mongodb-on-red-hat/
```

---

## 3. Getting the code

```bash
# Option A: clone from your git host
git clone <your-repo-url> egw-occ
cd egw-occ

# Option B: copy/scp the /app directory onto the server
scp -r ./app youruser@yourserver:/opt/egw-occ
ssh youruser@yourserver
cd /opt/egw-occ
```

Choose a working directory, e.g. `/opt/egw-occ`. The rest of this README uses
that path.

---

## 4. Configuration — environment variables

There are exactly **two** `.env` files. **Do not commit them to git.**

### `/opt/egw-occ/backend/.env`

```dotenv
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="https://your-domain.example.com,http://localhost:3000"
EMERGENT_LLM_KEY="sk-emergent-xxxxxxxxxxxxxxxxxx"
```

| Variable           | Required | Notes                                                                    |
| ------------------ | -------- | ------------------------------------------------------------------------ |
| `MONGO_URL`        | **yes**  | MongoDB connection string (local: `mongodb://localhost:27017`; Atlas: full SRV URL) |
| `DB_NAME`          | **yes**  | Database name — backend writes to a single `games` collection            |
| `CORS_ORIGINS`     | **yes**  | Comma-separated list of allowed frontend origins. Use `*` ONLY for local dev. |
| `EMERGENT_LLM_KEY` | optional but **strongly recommended** | Without it, the Ops Advisor returns a hard-coded fallback message. See [§ 6](#6-llm-key-ops-advisor). |

### `/opt/egw-occ/frontend/.env`

```dotenv
REACT_APP_BACKEND_URL=https://your-domain.example.com
WDS_SOCKET_PORT=443
ENABLE_HEALTH_CHECK=false
```

| Variable                | Required | Notes                                                          |
| ----------------------- | -------- | -------------------------------------------------------------- |
| `REACT_APP_BACKEND_URL` | **yes**  | Public URL where the backend is reachable. The frontend prepends `/api` to every call (so set this to the **root** of your domain, not `/api`). |
| `WDS_SOCKET_PORT`       | dev only | Set to 443 if you proxy webpack-dev-server over TLS. Omit for local dev on port 3000. |

> ⚠ Anything prefixed with `REACT_APP_` is **baked into the static bundle at
> build time**. Changing it requires a rebuild (`yarn build`).

---

## 5. Database setup (MongoDB)

### Option A — local MongoDB

The default `MONGO_URL` works once `mongod` is running.
Verify:

```bash
mongosh --eval 'db.runCommand({ ping: 1 })'
# should print: { ok: 1 }
```

No schema setup is required — the app creates the `games` collection on first
write.

### Option B — MongoDB Atlas (managed)

1. Create a free cluster at https://cloud.mongodb.com
2. Network Access → add your server's public IP (or `0.0.0.0/0` for testing)
3. Database Access → create a user with `readWrite` on the database
4. Click *Connect* → *Drivers* → copy the SRV connection string
5. Put it in `backend/.env`:

   ```dotenv
   MONGO_URL="mongodb+srv://USER:PASS@cluster0.mongodb.net/?retryWrites=true&w=majority"
   DB_NAME="egw_occ"
   ```

### Option C — self-hosted MongoDB with auth

```bash
mongosh
> use admin
> db.createUser({ user: "occ", pwd: "<strongpass>", roles: ["readWriteAnyDatabase"] })
> exit
sudo sed -i 's/#security:/security:\n  authorization: enabled/' /etc/mongod.conf
sudo systemctl restart mongod
```

```dotenv
MONGO_URL="mongodb://occ:<strongpass>@localhost:27017/?authSource=admin"
```

---

## 6. LLM key (Ops Advisor)

The in-game **Ops Advisor** is powered by Anthropic Claude Sonnet 4.5 routed
through Emergent's `emergentintegrations` library. The library accepts a
**single universal key** (`EMERGENT_LLM_KEY`) and handles billing.

### Get a key

* Sign in at https://app.emergent.sh
* **Profile → Universal Key → Copy**
* Optionally enable auto top-up

Paste it into `backend/.env`:

```dotenv
EMERGENT_LLM_KEY="sk-emergent-xxxxxxxxxxxxxxxxxx"
```

### Use your own LLM provider instead

If you prefer to pay Anthropic, OpenAI or Google directly, edit
`/opt/egw-occ/backend/server.py` and change the `LlmChat` initialization
in the `/api/sim/{id}/advisor` route:

```python
chat = LlmChat(
    api_key=os.environ["YOUR_OWN_KEY"],
    session_id=f"advisor-{game_id}",
    system_message=...,
).with_model("anthropic", "claude-sonnet-4-5-20250929")   # or
# .with_model("openai", "gpt-5.2")
# .with_model("gemini", "gemini-2.5-pro")
```

Then set the corresponding key in `backend/.env`.

> If `EMERGENT_LLM_KEY` is missing or invalid, the app **still runs** — the
> Advisor falls back to a fixed message (status 200, `ok:false`). Nothing else
> in the game depends on the LLM.

---

## 7. Install dependencies

### Backend

```bash
cd /opt/egw-occ/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# If pip cannot find emergentintegrations on PyPI, use Emergent's index:
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
```

### Frontend

```bash
cd /opt/egw-occ/frontend
yarn install --frozen-lockfile
```

> Always use **yarn**, not npm. The `package.json` declares a specific yarn
> version and the lockfile is yarn-format.

---

## 8. Run in development mode

Open two terminals on the server.

**Terminal 1 — backend**

```bash
cd /opt/egw-occ/backend
source .venv/bin/activate
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 — frontend**

```bash
cd /opt/egw-occ/frontend
yarn start
```

* Frontend dev server: <http://localhost:3000>
* Backend API: <http://localhost:8001/api/>

Visit `http://<server-ip>:3000` from your browser. The boot screen will load,
showing the Free Play / Survive 7 Days scenario selector.

---

## 9. Run in production (single server)

In production you build the React app into static files and serve them with
nginx, while the backend runs as a long-lived uvicorn (or gunicorn) process.

### 9.1 Build the frontend

```bash
cd /opt/egw-occ/frontend
yarn build
# produces /opt/egw-occ/frontend/build/
```

The `build/` directory contains a static SPA that nginx can serve directly.

### 9.2 Run the backend

```bash
cd /opt/egw-occ/backend
source .venv/bin/activate
# uvicorn directly:
uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
# OR with gunicorn (production-grade):
pip install "gunicorn[gevent]"
gunicorn -w 2 -k uvicorn.workers.UvicornWorker server:app --bind 127.0.0.1:8001
```

Bind to `127.0.0.1` (not `0.0.0.0`) because nginx will proxy to it.

---

## 10. Run with `supervisor` (recommended for VMs)

```bash
sudo apt install -y supervisor
```

Create `/etc/supervisor/conf.d/egw-occ.conf`:

```ini
[program:egw-backend]
command=/opt/egw-occ/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
directory=/opt/egw-occ/backend
autostart=true
autorestart=true
stdout_logfile=/var/log/egw-occ/backend.out.log
stderr_logfile=/var/log/egw-occ/backend.err.log
environment=PATH="/opt/egw-occ/backend/.venv/bin"
user=www-data

# (optional) only needed if you DON'T put the frontend behind nginx.
# In production you should run nginx and serve frontend/build/ statically.
# [program:egw-frontend]
# command=/usr/bin/yarn start
# directory=/opt/egw-occ/frontend
# autostart=true
# autorestart=true
# stdout_logfile=/var/log/egw-occ/frontend.out.log
# stderr_logfile=/var/log/egw-occ/frontend.err.log
# user=www-data
```

```bash
sudo mkdir -p /var/log/egw-occ
sudo chown -R www-data:www-data /opt/egw-occ /var/log/egw-occ
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl status
```

---

## 11. Run with `systemd` (alternative)

If you prefer systemd, create `/etc/systemd/system/egw-occ-backend.service`:

```ini
[Unit]
Description=EGW OCC Backend (FastAPI)
After=network.target mongod.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/egw-occ/backend
EnvironmentFile=/opt/egw-occ/backend/.env
ExecStart=/opt/egw-occ/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8001 --workers 2
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now egw-occ-backend
sudo systemctl status egw-occ-backend
```

The frontend is static — no service needed; nginx serves it directly.

---

## 12. Reverse-proxy with Nginx + HTTPS

This setup serves the React build statically and proxies `/api/*` to the
backend.

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

Create `/etc/nginx/sites-available/egw-occ`:

```nginx
server {
    listen 80;
    server_name your-domain.example.com;

    # Static frontend
    root /opt/egw-occ/frontend/build;
    index index.html;

    # API → backend
    location /api/ {
        proxy_pass         http://127.0.0.1:8001/api/;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;        # advisor LLM can take ~20s
        proxy_send_timeout 90s;
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/egw-occ /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Enable HTTPS (Let's Encrypt)

```bash
sudo certbot --nginx -d your-domain.example.com --redirect --agree-tos -m you@example.com
```

After certbot finishes, the site is reachable on **https://your-domain.example.com**.

Now update `frontend/.env` to match and **rebuild**:

```dotenv
REACT_APP_BACKEND_URL=https://your-domain.example.com
```

```bash
cd /opt/egw-occ/frontend
yarn build
```

Don't forget to update the backend `CORS_ORIGINS`:

```dotenv
CORS_ORIGINS="https://your-domain.example.com"
```

…and restart the backend:

```bash
sudo supervisorctl restart egw-backend   # or: sudo systemctl restart egw-occ-backend
```

---

## 13. Run with Docker / Docker Compose

A drop-in `docker-compose.yml` (place at the repo root):

```yaml
version: "3.9"

services:
  mongo:
    image: mongo:7.0
    restart: unless-stopped
    volumes:
      - mongo-data:/data/db
    ports:
      - "127.0.0.1:27017:27017"

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - ./backend/.env
    environment:
      - MONGO_URL=mongodb://mongo:27017
    depends_on:
      - mongo
    ports:
      - "127.0.0.1:8001:8001"

  frontend:
    image: nginx:alpine
    restart: unless-stopped
    volumes:
      - ./frontend/build:/usr/share/nginx/html:ro
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"
    depends_on:
      - backend

volumes:
  mongo-data:
```

`backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir emergentintegrations \
        --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "2"]
```

`nginx.conf` (sits next to docker-compose.yml):

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;
    location /api/ {
        proxy_pass http://backend:8001/api/;
        proxy_read_timeout 90s;
    }
    location / { try_files $uri $uri/ /index.html; }
}
```

```bash
# 1) build the React app for production
cd frontend && yarn build && cd ..
# 2) build images + start the stack
docker compose up -d --build
```

Visit <http://your-server-ip/>.

---

## 14. Smoke-test the install

```bash
# Backend health
curl -s http://localhost:8001/api/ | jq
# → {"service":"OCC Sim","ok":true, ...}

# Create a fresh game
curl -s -X POST http://localhost:8001/api/sim/new \
     -H "Content-Type: application/json" \
     -d '{"scenario":"free_play"}' | jq '.id, .phase'
# → "GAME-XXXXXX"
# → "ROSTER"

# Run the full pytest suite
cd /opt/egw-occ/backend
source .venv/bin/activate
pytest tests/ -v
# → 30 passed
```

Then load the frontend in a browser and click *START DUTY*. The boot screen
should disappear and the Roster Board should populate with ~24 flights.

---

## 15. Updating / maintenance

```bash
cd /opt/egw-occ
git pull                                  # pull latest code

# Backend
cd backend
source .venv/bin/activate
pip install -r requirements.txt           # any new deps
sudo supervisorctl restart egw-backend    # or systemctl

# Frontend
cd ../frontend
yarn install --frozen-lockfile
yarn build                                # rebuild static assets

# nginx will pick up the new build immediately, no reload needed
```

### Backups

Game state lives in MongoDB. A simple nightly dump:

```bash
mongodump --uri="mongodb://localhost:27017" --db=egw_occ --out=/var/backups/egw-occ/$(date +%F)
# restore:
mongorestore --uri="mongodb://localhost:27017" /var/backups/egw-occ/2026-05-14/
```

### Resetting all games

```bash
mongosh
> use egw_occ
> db.games.drop()
> exit
```

---

## 16. Troubleshooting

| Symptom                                              | Cause / fix                                                              |
| ---------------------------------------------------- | ------------------------------------------------------------------------ |
| Browser shows the boot screen but `START DUTY` does nothing | `REACT_APP_BACKEND_URL` is wrong or CORS is blocking the call. Open DevTools → Network — look for a failing `POST /api/sim/new`. |
| Backend logs `KeyError: 'MONGO_URL'`                 | `.env` not loaded — check the file is at `backend/.env`, not committed with `.env.example` name. |
| `pip install emergentintegrations` fails             | Use the extra index: `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` |
| Advisor returns "Advisor offline"                    | `EMERGENT_LLM_KEY` missing, expired, or out of credit. Check at <https://app.emergent.sh>. |
| `502 Bad Gateway` from nginx                         | Backend not running on 127.0.0.1:8001, OR firewall blocks the loopback. Run `curl http://127.0.0.1:8001/api/`. |
| Frontend build is huge / slow                        | Normal — CRA bundles all routes. Build once on a beefy machine, then `scp` the `build/` directory to small VPS targets. |
| Static assets 404 after deploy                       | nginx `root` must point at `frontend/build`, AND `try_files $uri $uri/ /index.html;` must be present for SPA routing. |
| `Cannot find module …` on `yarn start`               | Run `yarn install` again — never `npm install`. The lockfile is yarn-format. |
| MongoDB error `Authentication failed`                | Wrong creds in `MONGO_URL`, or you forgot `?authSource=admin`.           |
| Sessions don't persist across browsers               | They aren't supposed to — saved game ids live in **browser** localStorage by design (no login). |

Backend log (supervisor):

```bash
tail -f /var/log/egw-occ/backend.err.log
```

Backend log (systemd):

```bash
journalctl -u egw-occ-backend -f
```

---

## 17. Project layout

```
backend/
├── server.py               # FastAPI routes
├── simulation.py           # Domain model + EASA-inspired rule engine
├── requirements.txt
├── .env                    # MONGO_URL, DB_NAME, CORS_ORIGINS, EMERGENT_LLM_KEY
└── tests/
    ├── test_occ_backend.py
    ├── test_pairings.py
    ├── test_campaign.py
    └── test_survive7.py

frontend/
├── package.json
├── craco.config.js
├── tailwind.config.js
├── public/
│   └── index.html
└── src/
    ├── App.js              # Orchestrator: boot → roster → ops → debrief
    ├── api.js              # axios client (all /api/sim/* calls)
    ├── index.js
    ├── index.css           # Control-room design tokens
    └── components/
        ├── BootScreen.jsx
        ├── HeaderBar.jsx
        ├── Sidebar.jsx
        ├── AssignModal.jsx
        └── views/
            ├── RosterBoard.jsx
            ├── FlightTimeline.jsx
            ├── IncidentQueue.jsx
            ├── CrewPanel.jsx
            ├── AdvisorPanel.jsx
            ├── RegsHelp.jsx
            └── Debrief.jsx
```

---

## Licence & disclaimer

This software is a **simulation for entertainment and training value only**.
It is **NOT** an EASA / UK CAA / FAA compliance tool, scheduling system, or
crew-management system. Do not use it for real flight operations or roster
legality decisions. EASA / CAA references in the game text are simplified for
gameplay and do not constitute regulatory advice.

EASA, the European Union Aviation Safety Agency, the UK Civil Aviation
Authority, AIMS, Sabre and any airline names mentioned are trademarks of their
respective owners.
