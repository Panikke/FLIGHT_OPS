# Setup on macOS

This guide takes you from a **fresh Mac** to **playing the game**. It assumes no
prior command-line experience. Follow it top to bottom.

Expect **20–40 minutes** the first time, mostly downloads.

---

## Step 0 — Open the Terminal

The **Terminal** is a window where you type commands.

1. Press **Cmd+Space**, type `Terminal`, and press **Enter**.
2. A window opens with a prompt. Type or paste one command at a time and press
   **Enter**. (Paste with **Cmd+V**.)

Keep it open — you'll use it throughout.

---

## Step 1 — Install Homebrew

**Homebrew** is the standard tool for installing software on a Mac. Paste this:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Follow the prompts (it may ask for your Mac password — typing shows nothing,
that's normal). When it finishes, it may print two `export` lines to run — if
so, paste and run them, then continue.

Check it worked:

```bash
brew --version
```

---

## Step 2 — Install the tools

```bash
brew install git python@3.11 node yarn
brew install --cask docker
```

This installs **Git**, **Python**, **Node.js**, **Yarn**, and **Docker
Desktop**.

Check the essentials (each should print a version):

```bash
git --version
python3 --version
node --version
yarn --version
```

---

## Step 3 — Start the database (Docker)

1. Open **Docker Desktop** (from Applications, or Spotlight → "Docker"). Wait
   until the whale icon in the menu bar says "Docker Desktop is running." First
   launch takes a minute or two, and you may need to accept its terms.
2. Start MongoDB in the Terminal:

   ```bash
   docker run -d --name mongo -p 27017:27017 -v mongo-data:/data/db --restart unless-stopped mongo:7.0
   ```

3. Confirm it's running:

   ```bash
   docker ps
   ```

   You should see a `mongo:7.0` line.

> **Prefer no Docker?** You can `brew install mongodb-community@7.0` and
> `brew services start mongodb-community@7.0` instead — same port 27017,
> everything else below is identical.

---

## Step 4 — Download the game

```bash
cd ~
git clone https://github.com/Panikke/FLIGHT_OPS.git
cd FLIGHT_OPS
```

> **Asked for a password?** This repo is private — you'll need a GitHub personal
> access token. See
> [Troubleshooting](Troubleshooting.md#git-clone-asks-for-a-password).

---

## Step 5 — Create the backend config file

Paste this block to create `backend/.env`:

```bash
cat > backend/.env <<'EOF'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="http://localhost:3000"
ANTHROPIC_API_KEY=""
EOF
```

That's enough to play. (AI advisor optional — see
[Configuration Reference](Configuration-Reference.md#the-ops-advisor-ai-key).)

---

## Step 6 — Start the backend

In your current Terminal window:

```bash
cd ~/FLIGHT_OPS/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --port 8001
```

- The first three lines create and enter a private Python space and download the
  backend's libraries (first time only).
- The last line **starts the backend.** You'll see
  `Uvicorn running on http://127.0.0.1:8001`.

**Leave this window running.**

---

## Step 7 — Start the frontend

Open a **second** Terminal window (**Cmd+N**), then:

```bash
cd ~/FLIGHT_OPS/frontend
yarn install
yarn start
```

`yarn install` downloads the web libraries (first time only — several minutes).
`yarn start` launches the frontend and opens your browser at
<http://localhost:3000>.

**Leave this window running too.**

---

## Step 8 — Play!

The **EGW//OCC** boot screen appears. Pick **Free Play → START DUTY**.

👉 New to the game? Read the **[Game Guide](Game-Guide.md)**.

---

## Playing again later

1. Make sure **Docker Desktop** is running.
2. **Backend** (new Terminal): `cd ~/FLIGHT_OPS/backend && source .venv/bin/activate && uvicorn server:app --port 8001`
3. **Frontend** (another Terminal): `cd ~/FLIGHT_OPS/frontend && yarn start`
4. Open <http://localhost:3000>.

You skip the one-time `venv` / `pip install` / `yarn install` steps.

---

## Problems?

See **[Troubleshooting](Troubleshooting.md)**.
