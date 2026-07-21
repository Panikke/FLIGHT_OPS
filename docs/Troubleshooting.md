# Troubleshooting

Find your symptom below. If you're stuck, the two most useful things to check
are: **(1) is the backend window still running without errors?** and **(2) does
the browser's developer console (F12 → Console/Network) show a failed request?**

---

## Setup & install

### `git clone` asks for a password

This repository is **private**, so GitHub needs to know who you are.

1. On GitHub: **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. Give it access to the **FLIGHT_OPS** repository with **Contents: Read**
   permission.
3. Copy the token (shown once).
4. When `git clone` asks:
   - **Username:** your GitHub username.
   - **Password:** paste the **token** (not your GitHub password).

Or embed it in the URL:
`git clone https://<YOUR_TOKEN>@github.com/Panikke/FLIGHT_OPS.git`

> Tokens can't be recovered after creation — if you lose it, generate a new one.

### `winget` / `brew` / a tool is "not recognized" or "command not found"

The tool didn't install, or your terminal was open **before** it was installed.
**Close and reopen the terminal**, then re-check with `--version`. If it still
fails, re-run that tool's installer (and on Windows Python, make sure you ticked
**"Add python.exe to PATH"**).

### Windows: "Activate.ps1 cannot be loaded because running scripts is disabled"

PowerShell blocks scripts by default. Allow them for your user, then retry:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux/Pi: frontend fails with `error:0308010C … digital envelope routines::unsupported`

Your Node.js is newer than the frontend's old build tooling expects. Start the
frontend with the compatibility flag:

```bash
NODE_OPTIONS=--openssl-legacy-provider yarn start
```

### Linux/Pi: `apt update` errors about a MongoDB repository / bad signature

You (or a previous guide) added MongoDB's apt repo, which doesn't work on newer
Debian/Pi releases. Remove it and update again — it's a "deb822" file, so match
on the URL, not the distro name:

```bash
grep -rl 'repo.mongodb.org' /etc/apt/sources.list.d/ | xargs sudo rm -f
sudo apt update
```

Then use **Docker** for MongoDB (see
[the Linux guide, Step 3](Setup-Linux-and-Raspberry-Pi.md#step-3--start-mongodb-use-docker)).

---

## The backend won't start

### `KeyError: 'MONGO_URL'`

The backend can't find its config. Check that **`backend/.env` exists** and
contains the `MONGO_URL` line. Re-create it using the block in your setup guide.
On Linux/Pi, verify it has the right number of lines: `wc -l backend/.env`
(should be 4).

### `ServerSelectionTimeoutError` / can't connect to MongoDB

The database isn't reachable.
- **Docker users:** is it running? `docker ps` should list `mongo:7.0`. If not,
  start it: `docker start mongo` (or re-run the `docker run …` command).
- Docker itself must be running first (Docker Desktop on Windows/Mac).
- Just started the container? Mongo takes a few seconds to accept connections —
  wait and retry.

### `Address already in use` / port 8001 is taken

Another program (often a backend you started earlier) is using the port.
- **Windows:** `Get-Process -Id (Get-NetTCPConnection -LocalPort 8001).OwningProcess`
  to see what it is, then close that window/process.
- **Mac/Linux:** `lsof -i :8001` to see it, then stop it.
- Or just run the new backend on a different port
  (`uvicorn server:app --port 8002`) — but then also update
  `REACT_APP_BACKEND_URL` in `frontend/.env` to match and restart the frontend.

---

## The frontend / browser

### The page loads but `START DUTY` does nothing

The web page can't reach the backend. Check, in order:
1. **Is the backend running?** Look at its terminal — it should say
   `Uvicorn running …` with no red errors. Test it directly by opening
   <http://localhost:8001/api/> — you should see a small JSON message.
2. **`REACT_APP_BACKEND_URL`** in `frontend/.env` must point at the backend
   (`http://localhost:8001` for same-computer play). If you changed it, restart
   `yarn start`.
3. **CORS:** if you're playing from another device, that browser's address must
   be listed in `CORS_ORIGINS` in `backend/.env`. Open the browser's dev tools
   (F12) → Network tab and look for a failed `POST /api/sim/new` — a CORS error
   confirms this.

### `yarn start` errors with `Cannot find module …`

The frontend's libraries didn't fully install. In `frontend/`, run
`yarn install` again. **Always use `yarn`, never `npm`** for this project.

### The browser opened but shows "This site can't be reached"

The frontend isn't running (or isn't ready yet). Check the frontend terminal —
`yarn start` prints "Compiled successfully!" when the page is ready. First
compile can take a minute.

---

## In-game

### The Ops Advisor says "Advisor offline"

That's expected if you haven't added an AI key — the rest of the game is
unaffected. To enable real advice, add an `ANTHROPIC_API_KEY` (see
[Configuration Reference](Configuration-Reference.md#the-ops-advisor-ai-key)).
If you *did* add a key and still see this, it may be invalid or out of credit —
check at <https://console.anthropic.com>.

### My saved game disappeared / didn't follow me to another browser

That's by design — there's **no login**. Your current game is remembered by the
**specific browser** you played it in (via its local storage). A different
browser, a different device, or clearing your browser data starts fresh.

### Auto-roster leaves a few flights unfilled

A small number of gaps can happen on a busy day when a particular aircraft-type
rating is scarce. You can fill the rest by hand (**ASSIGN**), or start the day
with the gaps and manage the shortfall as an incident — the game lets you.

---

## Still stuck?

- Re-read your setup guide's steps — a skipped step is the usual cause.
- Check the **backend terminal** for the actual error message; it's almost
  always the real clue.
- For deeper issues, the **[Developer Guide](Developer-Guide.md)** explains how
  the pieces connect and how to run the built-in health check and tests.
