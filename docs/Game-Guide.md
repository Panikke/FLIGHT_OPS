# Game Guide

> **New to setting the game up?** This page is about *playing*. To install and
> run it first, see [Setup on Windows](Setup-Windows.md),
> [macOS](Setup-macOS.md), or [Linux & Raspberry Pi](Setup-Linux-and-Raspberry-Pi.md).

---

## What is EGW//OCC?

Every airline has an **Operations Control Centre (OCC)** — a room full of
specialists who keep the airline running in real time. When a pilot calls in
sick, a plane breaks, a storm closes an airport, or air-traffic control slows
everything down, the OCC scrambles to keep the flights moving.

In EGW//OCC you play the **Crew Controller** for a fictional airline,
**Eaglewing International**, flying out of London Heathrow (LHR) with a mixed
fleet of aircraft. Your job has two phases each day:

1. **Plan the roster** — put the right crew on every flight, legally.
2. **Run the day** — react to disruptions as the clock ticks, keeping planes
   on time and passengers happy without breaking the rules.

You are scored on punctuality, cost, passenger disruption, and rule-breaches.
It's meant to be **hard** — a real duty controller's day rarely goes to plan.

---

## Choosing a scenario

When the game boots, you pick one of two modes:

| Scenario | What it's like |
| -------- | -------------- |
| **Free Play** | An open-ended campaign. Play day after day for as long as you like. Disruptions are random. Great for learning. |
| **Survive 7 Days** | A fixed 7-day challenge. Every game is the *same* (fixed random seed), so you can compare runs. Disruption escalates hard toward day 7, and you get a final grade at the end. |

Click **START DUTY** (Free Play) or **START CHALLENGE** (Survive 7) to begin.

---

## Phase 1 — Building the roster

You land on the **Roster Board**: a list of every flight for the day, showing
its route, aircraft, departure time, and — crucially — the **crew it needs**.

### How crew requirements work

Every flight needs a specific mix of crew, following normal airline practice:

- **1 Captain (CP)** and **1 First Officer (FO)** up front.
- On **long-haul** flights, extra **relief First Officers** are added so the
  flight deck can take rest breaks (1 relief for 9–12h flights, 2 beyond 12h).
- **1 Senior Cabin (SC)** crew member — the inflight manager — on short-haul; a
  **second** (a purser) is added on long-haul.
- **Cabin Crew (CC)**: one for every 50 seats on the aircraft (so a 180-seat
  jet needs 4, a 325-seat jet needs 7).

Each flight row shows, for example, `CP1 FO1 SC1 CC4` — that's what you must
fill.

### Assigning crew

You have two ways to fill the roster:

- **AUTO-ROSTER** (the ⚡ button) — the game legally fills every open seat with
  the freshest qualified crew it can find. This is the fast way, and it
  respects all the rules.
- **ASSIGN** (per flight) — open a flight and pick crew by hand. Before you
  confirm, the game runs a **legality pre-check** and warns you about problems
  (wrong aircraft type-rating, not enough rest, duty-hour limits, and so on).
  Critical problems block the assignment unless you deliberately **OVERRIDE**
  (which counts as a rule-breach and hurts your score).

> **Why can't I assign this person?** Common reasons: they're not rated on that
> aircraft type, they haven't had their minimum rest, they'd exceed their
> weekly duty hours, or they're already flying an overlapping trip. The pre-check
> tells you exactly which rule is in the way.

When every flight is crewed (or you accept some gaps), press **START DAY**.

---

## Phase 2 — Running the day

Now the clock starts. This is the heart of the game.

### The clock and controls (top bar)

- **▶ PLAY** runs the clock automatically. The **1× / 2× / 5× / 15×** buttons
  change how fast.
- **+15M / +30M / +60M** jump the clock forward by hand.
- The big numbers across the top are your live scoreboard: **OTP%** (on-time
  performance), **BREACHES** (rules broken), **FATIGUE**, **COST**, **PAX
  DISR.** (passengers disrupted), and your overall **SCORE**.

> **The clock does not stop for problems.** Just like a real OCC, the operation
> keeps moving while you work. Watch the **INCIDENTS** menu — the number badge
> tells you how many open problems are waiting.

### Incidents — the disruptions

As the day runs, problems appear in the **INCIDENTS** queue. Each one is raised
by a specific OCC desk and tagged with the real two-digit **IATA delay code** an
airline would file it under:

| Incident | Raised by | Delay code |
| -------- | --------- | ---------- |
| Crew sickness | Crew Control | 64 |
| Crew running late | Crew Control | 63 |
| Technical fault / MEL | Maintenance Control | 41 |
| Weather at destination | Dispatch | 72 |
| ATC flow restriction | Network / ATC | 81 |

For each incident you can:

- **DECIDE** — choose a recovery action. The options are calculated live from
  the current situation, each showing its **cost** and whether it's even
  possible right now (e.g. "call out standby crew" is greyed out if no legal
  standby of the right rank is available). Actions include calling out standby
  crew, swapping crew or aircraft, accepting a delay, or cancelling.
- **ASK ADVISOR** — get a tactical recommendation from the AI Ops Advisor
  (needs an API key — see [Configuration](Configuration-Reference.md#the-ops-advisor-ai-key)).

> **⚠ Ignoring an incident makes it worse.** Leave an open incident unattended
> for an hour of game-time and it **escalates**: severity jumps to major, the
> flight takes extra delay, and some cheaper recovery options close off. This is
> the pressure that replaces the old "pause on every incident" behaviour — you
> must triage.

### Knock-on delays (the domino effect)

Aircraft fly several flights a day. If one flight runs late, the *same aircraft's*
next flight can't leave on time either — this is called a **reactionary** or
**knock-on** delay (IATA code 93), and in the real world it's the single
biggest cause of delay. The game models it: a late inbound cascades down that
aircraft's whole day, shown with a **KNOCK-ON** badge and a `·R` marker on the
timeline. Recovering early stops the dominoes.

### Two costly rules to watch

- **LHR night curfew** — departures or arrivals at Heathrow between **23:00 and
  06:00 Zulu** draw a regulatory fine. Delays that push a flight into the night
  cost you.
- **EU261 / UK261 passenger compensation** — if a flight *arrives* 3+ hours
  late, you owe every passenger compensation (more for long-haul). **Exception:**
  if the delay was caused by weather or ATC ("extraordinary circumstances"), no
  compensation is due — exactly as in the real regulation. This is what makes
  "accept a big delay vs. cancel" a genuine money decision.

---

## The other screens (left menu)

| Menu item | What it shows |
| --------- | ------------- |
| **ROSTER** | The flight-by-flight crew board (Phase 1). |
| **TIMELINE** | A visual Gantt chart of every aircraft's day and every crew member's duty, with delays drawn in. |
| **INCIDENTS** | The live disruption queue (Phase 2). |
| **CREW** | The full crew list with status, fatigue, rest, and qualifications. |
| **DAYS OFF** | A calendar for planning crew rest days (see below). |
| **OPS ADVISOR** | The AI advisor chat log. |
| **FTL REGS** | A cheat-sheet of the flight-time-limit rules the game enforces. |

### Days Off

Crew can't work forever — after too many consecutive duty days they legally
**must** have a day off. The **DAYS OFF** calendar shows each crew member's
recent roster and lets you plan future rest days by clicking a cell. The game
also auto-plans a day off for anyone about to hit the legal limit, so you're
never forced to micro-manage all 170+ crew — but you can override.

---

## Ending the day

Press **END DAY** to close the day and see your **Debrief**: a rating (GOLD /
GREEN / AMBER / RED), your day's stats (OTP, breaches, curfew fines, EU261
compensation, cost, cancellations), and a log of every decision you made.

- In **Free Play**, press **▶ DAY N+1** to roll into the next day (fatigue,
  rest, and days-off all carry over — it's a real campaign).
- In **Survive 7 Days**, after day 7 you get a **final grade** for the whole
  run.

You can also **RESTART DAY** at any time during ops to replay the current day
from 04:00Z with the same roster — handy when a day goes sideways.

---

## Tips for a good score

- **Auto-roster first, then fine-tune.** It's legal and fast; fix the few gaps
  by hand.
- **Triage incidents by cost and time.** An unattended incident escalates —
  deal with the expensive, time-critical ones first.
- **Stop the dominoes early.** A small delay recovered now beats a cascade later.
- **Weigh the money.** Cancelling avoids EU261 compensation but disrupts every
  passenger; a big delay keeps them moving but may owe compensation *unless*
  weather/ATC caused it.
- **Mind the night curfew.** Don't let delays push Heathrow movements past 23:00Z.
- **Rest your crew.** Fatigue and days-off aren't optional — plan ahead or the
  legal wall hits you mid-campaign.
