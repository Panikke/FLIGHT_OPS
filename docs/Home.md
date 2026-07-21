# EGW//OCC Wiki

Welcome! This wiki explains **everything** about setting up, running, and
playing EGW//OCC — the airline crew-control simulation. It is written for
complete beginners: if a step involves a command, the command is here, ready to
copy and paste, with an explanation of what it does.

---

## 🎮 Just want to understand the game?

- **[Game Guide](Game-Guide.md)** — what EGW//OCC is, what you actually *do*,
  and a full walkthrough of a day in the operations centre.

## 💻 Want to install and run it?

Pick the guide that matches your computer and follow it top to bottom. Each one
is self-contained — you won't need to jump around.

- **[Setup on Windows](Setup-Windows.md)**
- **[Setup on macOS](Setup-macOS.md)**
- **[Setup on Linux & Raspberry Pi](Setup-Linux-and-Raspberry-Pi.md)**

## 🔧 Reference material

- **[Configuration Reference](Configuration-Reference.md)** — every setting and
  config file explained (the `.env` files, ports, the AI key, and more).
- **[Troubleshooting](Troubleshooting.md)** — "it's not working" → find your
  symptom and the fix.
- **[Developer Guide](Developer-Guide.md)** — how the code is organised, the
  full API reference, how to run the automated tests, and how to contribute.

---

## The 30-second overview

EGW//OCC has two halves that talk to each other over your local network:

```
   Your web browser                Two programs running on your computer
  ┌────────────────┐   http://    ┌───────────────┐      ┌──────────────┐
  │   The game UI  │ ───────────► │   Frontend    │      │              │
  │ localhost:3000 │              │  (yarn start) │      │              │
  └────────────────┘              └───────┬───────┘      │              │
                                          │  /api calls   │              │
                                          ▼               │              │
                                  ┌───────────────┐       │   MongoDB    │
                                  │    Backend    │ ────► │  (database)  │
                                  │  port 8001    │       │  port 27017  │
                                  │  (the rules)  │       │              │
                                  └───────────────┘       └──────────────┘
```

To play, you start **three** things:

1. **MongoDB** — the database that remembers your game (usually via Docker).
2. **The backend** — the Python program that runs the rules (`uvicorn`).
3. **The frontend** — the web page you actually click on (`yarn start`).

Then you open **<http://localhost:3000>** in your browser. That's it — the setup
guides walk you through each piece.

---

> **A note on "localhost"**: `localhost` just means "this same computer." When
> the guides tell you to open `http://localhost:3000`, they mean open your web
> browser and type that into the address bar, on the same machine where you
> started the programs.
