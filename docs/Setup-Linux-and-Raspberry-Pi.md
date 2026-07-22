# Setup on Linux & Raspberry Pi

This guide covers **Debian/Ubuntu Linux** and the **Raspberry Pi** (including
DietPi). It assumes you're comfortable pasting commands into a terminal, but it
explains the tricky parts that commonly trip people up on these systems.

> **Which Pi works?** MongoDB 7 needs a **64-bit ARMv8.2 CPU** — that's a
> **Raspberry Pi 5** (or a Pi 4 with the workaround of using MongoDB Atlas
> cloud, see the end). A Pi 3 or earlier can't run modern MongoDB locally.

---

## Step 1 — Install the base tools

On Debian/Ubuntu/DietPi:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

Most current distributions already ship a suitable **Python 3.11+**. Check:

```bash
python3 --version
```

---

## Step 2 — Install Node.js and Yarn

The version of Node in the default apt repositories is often too old. Install a
current one from **NodeSource**:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g yarn
```

Check:

```bash
node --version    # should be 20 or higher
yarn --version
```

> **Note for very new Node (v25+):** Create React App's older build can fail
> with `error:0308010C … digital envelope routines::unsupported`. If you hit
> that when starting the frontend, prefix the start command with a compatibility
> flag (shown in Step 6).

---

## Step 3 — Start MongoDB (use Docker)

**On Debian "trixie"/13 and current Raspberry Pi OS, do not use MongoDB's apt
repository** — it targets older releases and its signing key is rejected by the
newer package tools. **Run MongoDB in Docker instead** — it's reliable and
identical across systems.

Install Docker (if you don't have it):

```bash
curl -fsSL https://get.docker.com | sudo sh
```

Run MongoDB:

```bash
sudo docker run -d --name mongo -p 27017:27017 -v mongo-data:/data/db --restart unless-stopped mongo:7.0
```

Give it a few seconds, then confirm it answers:

```bash
sudo docker exec mongo mongosh --quiet --eval 'db.runCommand({ ping: 1 })'
# should print: { ok: 1 }
```

> **If you already tried the apt method and `apt update` now errors** about a
> MongoDB repository or a bad signature, remove the broken repo file and update
> again. The file is in the modern "deb822" format, so a plain search for the
> distro name misses it — match on the URL instead:
> ```bash
> grep -rl 'repo.mongodb.org' /etc/apt/sources.list.d/ | xargs sudo rm -f
> sudo apt update
> ```

---

## Step 4 — Download the game

```bash
cd ~
git clone https://github.com/Panikke/FLIGHT_OPS.git
cd FLIGHT_OPS
```

> **Private repo — needs a token.** Cloning will ask for a username and password;
> the "password" is a GitHub **personal access token** (fine-grained, with
> *Contents: Read* on this repo). You can also embed it in the URL:
> `git clone https://<YOUR_TOKEN>@github.com/Panikke/FLIGHT_OPS.git`. See
> [Troubleshooting](Troubleshooting.md#git-clone-asks-for-a-password).

Throughout the rest of this guide, use **absolute paths** (`~/FLIGHT_OPS/backend`
and `~/FLIGHT_OPS/frontend`). Jumping between relative folders is a common source
of "file not found" mistakes.

---

## Step 5 — Create the backend config file

```bash
cat > ~/FLIGHT_OPS/backend/.env <<'EOF'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="http://localhost:3000"
ANTHROPIC_API_KEY=""
EOF
```

Verify it wrote exactly four lines (a common paste mistake swallows a line):

```bash
wc -l ~/FLIGHT_OPS/backend/.env    # should print 4
```

See [Configuration Reference](Configuration-Reference.md) for what each line
means and how to add the optional AI advisor key.

---

## Step 6 — Start the backend

```bash
cd ~/FLIGHT_OPS/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001
```

The `--host 0.0.0.0` part lets you play from **another device** on your network
(useful for a headless Pi). You'll see
`Uvicorn running on http://0.0.0.0:8001`. **Leave this running.**

---

## Step 7 — Start the frontend

In a second terminal (or `ssh` session):

```bash
cd ~/FLIGHT_OPS/frontend
yarn install
yarn start
```

**If you hit the Node "digital envelope" error** (common on Node 25+), start it
with the compatibility flag instead:

```bash
NODE_OPTIONS=--openssl-legacy-provider yarn start
```

**Leave this running too.**

> **On a low-memory Pi**, avoid `yarn build` (it can run out of memory). The
> development server (`yarn start`) is the recommended way to play.

---

## Step 8 — Open the game

- **Playing on the Pi/PC itself:** open <http://localhost:3000>.
- **Playing from another device** (e.g. the Pi runs the game, you play from a
  laptop): open `http://<the-server-ip>:3000` from the laptop's browser, and
  make two adjustments so the browser can reach the backend:

  1. In `~/FLIGHT_OPS/frontend/.env`, set the backend to the server's address:
     ```dotenv
     REACT_APP_BACKEND_URL=http://<the-server-ip>:8001
     ```
     Then **stop and restart** `yarn start` (the frontend reads this only at
     startup).
  2. In `~/FLIGHT_OPS/backend/.env`, allow that browser origin:
     ```dotenv
     CORS_ORIGINS="http://<the-server-ip>:3000"
     ```
     Then restart the backend.

  Replace `<the-server-ip>` with the machine's LAN IP (`hostname -I` shows it),
  or its [Tailscale](https://tailscale.com/) address if you use one.

👉 New to the game? Read the **[Game Guide](Game-Guide.md)**.

---

## Playing again later

MongoDB (Docker) auto-restarts on boot. You just restart the two programs:

```bash
# Backend
cd ~/FLIGHT_OPS/backend && source .venv/bin/activate && uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend (second terminal)
cd ~/FLIGHT_OPS/frontend && yarn start   # add NODE_OPTIONS=--openssl-legacy-provider if needed
```

---

## Raspberry Pi 4 or older? Use cloud MongoDB

If your Pi's CPU can't run MongoDB 7 locally, use a **free MongoDB Atlas** cloud
database instead:

1. Create a free cluster at <https://cloud.mongodb.com>.
2. Add your network to its access list, and create a database user.
3. Copy the connection string and put it in `backend/.env`:
   ```dotenv
   MONGO_URL="mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
   DB_NAME="egw_occ"
   ```

Everything else in this guide is the same — just skip the Docker/MongoDB step.

---

## Problems?

See **[Troubleshooting](Troubleshooting.md)** — it covers the Node OpenSSL
error, the MongoDB repo trap, ports in use, and remote-access CORS issues.

For running the game as a permanent background service (systemd / nginx /
HTTPS), see the **[Developer Guide](Developer-Guide.md#running-as-a-permanent-service)**.
