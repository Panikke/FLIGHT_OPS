# Configuration Reference

This page explains every setting the game uses. The setup guides tell you *when*
to create these files; this page is the *what and why*, so you can look things
up later.

---

## The two config files

The game reads settings from two small text files called **`.env`** files
("environment" files). Each is just a list of `NAME="value"` lines.

| File | Committed to Git? | You must create it? |
| ---- | ----------------- | ------------------- |
| `backend/.env` | **No** (it's private — it can hold your secret API key) | **Yes — by hand** |
| `frontend/.env` | Yes (already in the project) | No, unless you're going remote |

---

## `backend/.env` — the backend settings

This file does **not** exist after you download the game — you create it
yourself. A template is provided in **`backend/.env.example`**; the setup guides
show you the exact command to create the real file.

```dotenv
MONGO_URL="mongodb://localhost:27017"
DB_NAME="egw_occ"
CORS_ORIGINS="http://localhost:3000"
ANTHROPIC_API_KEY=""
```

| Setting | Required? | What it means |
| ------- | --------- | ------------- |
| `MONGO_URL` | **Yes** | Where the MongoDB database is. `mongodb://localhost:27017` means "on this computer, the standard port." For a cloud database (MongoDB Atlas) this is the long `mongodb+srv://…` string they give you. |
| `DB_NAME` | **Yes** | The name of the database. `egw_occ` is fine. The game creates it automatically on first save. |
| `CORS_ORIGINS` | **Yes** | A safety setting listing which web addresses may talk to the backend. For local play, `http://localhost:3000` is correct. Separate multiple addresses with commas. Use `*` (meaning "allow anything") only for quick local testing. |
| `ANTHROPIC_API_KEY` | Optional | Unlocks the AI **Ops Advisor**. Leave it as `""` (empty) and the game runs fine — the advisor just shows a canned "offline" message. See below. |

> **If the backend prints `KeyError: 'MONGO_URL'` when it starts,** it means it
> couldn't find `backend/.env`, or the file is missing that line. See
> [Troubleshooting](Troubleshooting.md).

---

## `frontend/.env` — the frontend settings

This file **already exists** in the project and normally needs **no changes**:

```dotenv
REACT_APP_BACKEND_URL=http://localhost:8001
```

- `REACT_APP_BACKEND_URL` tells the web page where to find the backend. The
  default (`http://localhost:8001`) is correct when you play on the **same
  computer** that runs the backend.
- **Only change this** if you want to play from a *different* device (e.g. run
  the game on a Raspberry Pi and play from your laptop). Then set it to the
  server's network address, e.g. `http://192.168.1.50:8001`, and **also** add
  that browser's address to `CORS_ORIGINS` in `backend/.env`.

> **⚠ Important:** anything starting with `REACT_APP_` is baked into the web page
> when it *starts*. If you change this file, you must **stop and restart**
> `yarn start` for it to take effect.

---

## The Ops Advisor (AI key)

The in-game **Ops Advisor** gives you tactical advice during disruptions. It's
powered by [Anthropic Claude](https://www.anthropic.com/). It is **completely
optional** — every other part of the game works without it.

### To enable it

1. Go to **<https://console.anthropic.com>** and sign in (you'll need to set up
   billing — the advisor uses tiny amounts of credit per question).
2. Open **API Keys → Create Key**, and **copy** the key (it's shown only once).
   It looks like `sk-ant-api03-…`.
3. Paste it into `backend/.env`:

   ```dotenv
   ANTHROPIC_API_KEY="sk-ant-api03-your-real-key-here"
   ```

4. Restart the backend.

> **Keep this key secret.** Anyone with it can spend your Anthropic credit.
> Never paste it into a chat, screenshot, or public place. Because `backend/.env`
> is not committed to Git, your key won't be uploaded when you push code — but
> it's still your responsibility to guard it.

### To change which AI model it uses

Edit `backend/server.py`, find the `/api/sim/{id}/advisor` route, and change the
`model=` line:

```python
response = await anthropic_client.messages.create(
    model="claude-sonnet-4-6",   # or "claude-opus-4-8", "claude-haiku-4-5"
    ...
)
```

Sonnet is the default — a good balance of quality, speed and cost for the short
advisor replies.

---

## Ports (which "channels" the programs use)

| Program | Port | Address you use |
| ------- | ---- | --------------- |
| Frontend (the web page) | 3000 | <http://localhost:3000> |
| Backend (the rules API) | 8001 | <http://localhost:8001/api/> |
| MongoDB (the database) | 27017 | (used internally; you don't open this in a browser) |

If a port is already in use on your machine, see
[Troubleshooting](Troubleshooting.md).
