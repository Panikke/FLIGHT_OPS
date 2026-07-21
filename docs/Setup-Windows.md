# Setup on Windows

This guide takes you from a **fresh Windows PC** to **playing the game**. It
assumes you have never used a command line before. Follow it top to bottom and
don't skip steps.

Expect it to take **20–40 minutes** the first time, mostly waiting for
downloads.

---

## What you'll install

The game is made of a few pieces. You'll install the tools that run them:

1. **Git** — downloads the game's code.
2. **Python** — runs the backend (the rules engine).
3. **Node.js + Yarn** — run the frontend (the web page).
4. **Docker Desktop** — runs the MongoDB database (the easiest way on Windows).

---

## Step 0 — Open a terminal

A **terminal** (also called PowerShell) is a window where you type commands.

1. Press the **Windows key**, type `PowerShell`, and click **Windows
   PowerShell**.
2. A dark window opens with a blinking cursor. This is where the commands below
   go. **Type or paste one line at a time and press Enter.**

> **To paste** into PowerShell: right-click, or press **Ctrl+V**.

Keep this window open — you'll use it throughout.

---

## Step 1 — Install the tools

The easiest way to install everything is with **winget**, Windows' built-in
installer (included on Windows 10 and 11). Paste these one at a time:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Docker.DockerDesktop -e
```

> **If `winget` is "not recognized":** install "App Installer" from the Microsoft
> Store (it provides winget), or download each tool manually:
> [Git](https://git-scm.com/download/win),
> [Python](https://www.python.org/downloads/windows/) (**tick "Add python.exe to
> PATH"** in the installer!),
> [Node.js LTS](https://nodejs.org/),
> [Docker Desktop](https://www.docker.com/products/docker-desktop/).

After installing, **close and reopen PowerShell** so it picks up the new tools.

Now install **Yarn** (the frontend's package manager):

```powershell
npm install -g yarn
```

### Check everything installed

Paste this to confirm — each should print a version number:

```powershell
git --version
python --version
node --version
yarn --version
```

If any says "not recognized," that tool didn't install or PowerShell needs
reopening. Re-run its installer and reopen PowerShell.

---

## Step 2 — Start the database (Docker)

1. **Launch Docker Desktop** from the Start menu. Wait until its whale icon in
   the system tray stops animating and says "Docker Desktop is running." The
   first launch can take a couple of minutes.
2. In PowerShell, start MongoDB:

   ```powershell
   docker run -d --name mongo -p 27017:27017 -v mongo-data:/data/db --restart unless-stopped mongo:7.0
   ```

   This downloads MongoDB (first time only) and runs it in the background. It
   will auto-start with Docker from now on.

3. Confirm it's up:

   ```powershell
   docker ps
   ```

   You should see a line mentioning `mongo:7.0`.

> **Prefer not to use Docker?** You can install
> [MongoDB Community Server](https://www.mongodb.com/try/download/community) as a
> Windows service instead — it runs on the same port 27017 and everything else
> below is identical. Docker is just simpler to clean up later.

---

## Step 3 — Download the game

Choose a folder for the game and download it. Your home folder is a fine place:

```powershell
cd $HOME
git clone https://github.com/Panikke/FLIGHT_OPS.git
cd FLIGHT_OPS
```

You're now inside the game's folder. Everything below happens from here.

> **`git clone` asks for a password?** This repository is private. You'll need a
> GitHub **personal access token** with read access, used as the password. See
> [Troubleshooting](Troubleshooting.md#git-clone-asks-for-a-password).

---

## Step 4 — Create the backend config file

The backend needs a small settings file. Paste this whole block — it creates
`backend\.env` with sensible local defaults:

```powershell
@'
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="http://localhost:3000"
ANTHROPIC_API_KEY=""
'@ | Set-Content -Encoding utf8 backend\.env
```

That's all you need to play. (Want the AI advisor? Add your key later — see
[Configuration Reference](Configuration-Reference.md#the-ops-advisor-ai-key).)

---

## Step 5 — Start the backend

The backend runs in its own PowerShell window. In your current window:

```powershell
cd $HOME\FLIGHT_OPS\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server:app --port 8001
```

Line by line:
- `python -m venv .venv` creates a private space for the backend's Python
  libraries (so it doesn't touch the rest of your system).
- `.venv\Scripts\Activate.ps1` switches into that space. Your prompt now shows
  `(.venv)` at the start.
- `pip install -r requirements.txt` downloads the backend's libraries (first
  time only — takes a minute or two).
- `uvicorn server:app --port 8001` **starts the backend.**

You'll know it worked when you see:

```
Uvicorn running on http://127.0.0.1:8001
```

**Leave this window running.** Closing it stops the backend.

> **"Activate.ps1 cannot be loaded because running scripts is disabled"?** Run
> this once, then retry the activate line:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## Step 6 — Start the frontend

Open a **second** PowerShell window (Start menu → PowerShell again), then:

```powershell
cd $HOME\FLIGHT_OPS\frontend
yarn install
yarn start
```

- `yarn install` downloads the web page's libraries (first time only — this one
  takes several minutes, be patient).
- `yarn start` **starts the frontend** and should automatically open your
  browser at <http://localhost:3000>.

If your browser doesn't open on its own, open it and go to
**<http://localhost:3000>** yourself.

**Leave this window running too.** You now have two windows open: one for the
backend, one for the frontend.

---

## Step 7 — Play!

You should see the **EGW//OCC** boot screen. Pick **Free Play**, click **START
DUTY**, and you're in.

👉 New to the game itself? Read the **[Game Guide](Game-Guide.md)**.

---

## Playing again later

Once installed, starting the game again is quick:

1. Make sure **Docker Desktop** is running (it restarts MongoDB automatically).
2. **Backend** — new PowerShell window:
   ```powershell
   cd $HOME\FLIGHT_OPS\backend
   .venv\Scripts\Activate.ps1
   uvicorn server:app --port 8001
   ```
3. **Frontend** — another PowerShell window:
   ```powershell
   cd $HOME\FLIGHT_OPS\frontend
   yarn start
   ```
4. Open <http://localhost:3000>.

(You don't repeat the `venv`, `pip install`, or `yarn install` steps — those
were one-time.)

---

## Something not working?

See **[Troubleshooting](Troubleshooting.md)** — it lists the common Windows
problems (ports in use, script-execution policy, private-repo password) and
their fixes.
