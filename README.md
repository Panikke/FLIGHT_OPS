# EGW//OCC — Airline Crew-Control Simulation

**You are the duty Crew Controller at a busy airline.** Build the day's crew
roster, then keep the airline flying through sickness, weather, technical
faults, air-traffic delays and knock-on chaos — all under real-world-inspired
flight-time and rest rules. It runs in your web browser.

> This is a **game / simulation for entertainment and training value only**. It
> is **not** an official aviation compliance or scheduling tool.

<p align="center">
  <em>Free Play — an open-ended campaign &nbsp;•&nbsp; Survive 7 Days — a fixed
  challenge with escalating disruption</em>
</p>

---

## 🚀 New here? Start with the guides

If you have never run a project like this before, **don't use the quick start
below** — follow the friendly, step-by-step guide for your computer instead.
Each one assumes zero prior experience and explains every command:

| Your computer | Start here |
| ------------- | ---------- |
| 🪟 **Windows** | **[Setup on Windows](docs/Setup-Windows.md)** |
| 🍎 **macOS** | **[Setup on macOS](docs/Setup-macOS.md)** |
| 🐧 **Linux / Raspberry Pi** | **[Setup on Linux & Raspberry Pi](docs/Setup-Linux-and-Raspberry-Pi.md)** |

Just want to know what the game *is* and how to play it? Read the
**[Game Guide](docs/Game-Guide.md)**.

📚 **[Browse the full wiki →](docs/Home.md)**

---

## ⚡ Quick start (for people who've done this before)

You need **Python 3.11+**, **Node 20+**, **Yarn**, **Git**, and a **MongoDB**
database. The fastest way to get MongoDB is Docker:

```bash
# 0. A MongoDB database (Docker is the easy cross-platform way)
docker run -d --name mongo -p 27017:27017 -v mongo-data:/data/db --restart unless-stopped mongo:7.0

# 1. Get the code
git clone https://github.com/Panikke/FLIGHT_OPS.git
cd FLIGHT_OPS

# 2. Create the backend config file (see docs/Configuration-Reference.md)
cat > backend/.env <<'EOF'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="http://localhost:3000"
ANTHROPIC_API_KEY=""
EOF

# 3. Start the backend (terminal 1)
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn server:app --port 8001

# 4. Start the frontend (terminal 2)
cd frontend
yarn install
yarn start
```

Then open **<http://localhost:3000>** and click **START DUTY**.

> The in-game **Ops Advisor** (an AI assistant) needs an
> [Anthropic API key](docs/Configuration-Reference.md#the-ops-advisor-ai-key).
> Leaving `ANTHROPIC_API_KEY` empty is fine — everything else in the game works
> without it.

---

## What's inside

| Part | Technology | What it does |
| ---- | ---------- | ------------ |
| **Frontend** | React 19 (Create React App + craco) | The control-room screen you play in |
| **Backend** | FastAPI (Python) | The rules engine and game logic |
| **Database** | MongoDB | Saves your game so you can come back to it |
| **Ops Advisor** | Anthropic Claude (optional) | An AI you can ask for tactical advice |

There is **no login** — your current game is remembered by your own browser.

---

## Documentation

Everything lives in the **[`docs/` wiki](docs/Home.md)**:

- **[Home](docs/Home.md)** — the wiki index
- **[Game Guide](docs/Game-Guide.md)** — what the game is and how to play it
- **[Setup on Windows](docs/Setup-Windows.md)** · **[macOS](docs/Setup-macOS.md)** · **[Linux & Raspberry Pi](docs/Setup-Linux-and-Raspberry-Pi.md)**
- **[Configuration Reference](docs/Configuration-Reference.md)** — every setting explained
- **[Troubleshooting](docs/Troubleshooting.md)** — fixes for common problems
- **[Developer Guide](docs/Developer-Guide.md)** — architecture, API reference, running the tests

---

## Licence & disclaimer

This software is a **simulation for entertainment and training value only**. It
is **not** an EASA / UK CAA / FAA compliance tool, scheduling system, or
crew-management system. Do not use it for real flight operations or roster
legality decisions. The regulatory references in the game text are simplified
for gameplay and do not constitute regulatory advice.

Any airline, aircraft-manufacturer, regulator, or software names mentioned are
trademarks of their respective owners and are used here for realism only.
