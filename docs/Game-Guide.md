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

> **Two things OVERRIDE cannot do.** A **type rating** is valid only for the
> aircraft it was issued on, so an A320-rated pilot can never be put in a B777
> — no override, no score penalty, the flight simply does not go with that
> crew. And an **FDP overrun** has a better answer than overriding: see
> commander's discretion below.

### Commander's discretion

If a crew would bust their Flight Duty Period by a modest amount, you may have
a third option next to ASSIGN and OVERRIDE: **COMMANDER'S DISCRETION**.

Under the real rule (ORO.FTL.205(f)) a captain may extend the maximum FDP by up
to **2 hours** (3 with an augmented crew) when something unforeseen happens
after report. Used this way the duty is **legal** — no breach is recorded —
but it is not free:

- the following rest may be reduced, never below **10 hours**;
- the crew take a fatigue hit;
- if the extension exceeds **1 hour** the airline must file a report with the
  regulator, which shows on your debrief.

Discretion only ever covers an FDP overrun. It will refuse to cover a missing
type rating, a sick crew member, or a crew in the wrong place.

> **Why can't I assign this person?** Common reasons: they're not rated on that
> aircraft type, they haven't had their minimum rest, they'd exceed their
> weekly duty hours, or they're already flying an overlapping trip. The pre-check
> tells you exactly which rule is in the way.

### Standby — your insurance policy

Some crew are held in reserve rather than rostered on a flight, and there are
**two kinds**, which behave very differently when you need them:

| Type | Reports in | The catch |
| ---- | ---------- | --------- |
| **Airport standby** (`SBY-A`) | 30 minutes | Their duty clock is already running — airport standby counts in full as duty. |
| **Home standby** (`SBY-H`) | 90 minutes | Fresh, but standby beyond 6 hours eats into the FDP they can then fly (CS FTL.1.225). |

So a bank of airport standbys recovers fast but burns hours all day; home
standbys are cheap to hold but cost you an hour and a half exactly when you
haven't got it. You choose the mix yourself in the **Roster Planner**.

When every flight is crewed (or you accept some gaps), press **START DAY**.

---

## Phase 2 — Running the day

Now the clock starts. This is the heart of the game.

### The clock and controls (top bar)

- **▶ PLAY** runs the clock automatically. The **1× / 2× / 5× / 15×** buttons
  change how fast.
- **+15M / +30M / +60M** jump the clock forward by hand.
- The big numbers across the top are your live scoreboard:

| Tile | Means |
| ---- | ----- |
| **OTP%** | On-time performance, measured on flights you actually **operated** — the way airlines report it. Cancelling does not flatter it. |
| **COMPL. FACTOR** | The share of the schedule you actually flew. This is where cancelling shows up. |
| **BREACHES** | Rules broken. |
| **FATIGUE** | Fleet-average crew fatigue. |
| **COST** | Everything you have spent. |
| **PAX DISR.** | Passengers disrupted. |
| **SCORE** | The overall number. |

> **Delay costs money.** Every minute of knock-on delay across the network is
> charged at a per-minute rate — the same way EUROCONTROL prices it in real
> economic analyses. It is the currency all your recovery levers trade in, so
> a decision that saves cash but floods the network with delay is not a saving.

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
| Crew out of hours | Crew Control | 63 |
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

### When an aircraft breaks — the clock stops

A **major technical fault grounds the aeroplane** (AOG — "aircraft on ground").
This is the one disruption that behaves differently from everything else:

- The tail is marked **unserviceable** and maintenance gives an estimate. It
  cannot be assigned to anything — including the rotation it was already on —
  until it is fixed. Rectification runs 4–10 hours, and anything still open at
  the end of the day is cleared by the overnight shift.
- **The whole simulation clock freezes** until you decide what to do with the
  rotation. Everything else — sickness, weather, ATC — keeps running while you
  work, but a grounded aircraft stops the world.
- The incident card itself only offers **cancel**. The real fix lives on the
  **Aircraft Control** desk.

An unattended *minor* tech defect that escalates becomes a major one and
grounds the tail the same way, so leaving them alone is expensive.

### Aircraft Control — the tail desk

Press `2` or click **AIRCRAFT**. This is where you fix a broken rotation, and
you have four levers:

| Lever | What it does | What it costs |
| ----- | ------------ | ------------- |
| **Reassign** | Put a different same-type tail on the rotation. | Free if the tail is already in the right place. |
| **Ferry** | Fly a spare **empty** to where it is needed, then operate. | A dispatch fee plus fuel — and it burns a Captain and an FO out of your standby bank, checked against the same FTL rules as any other duty. LHR's night curfew can push the departure. |
| **Substitute** | Cover the rotation with a **bigger** aircraft (upgauge). | Setup fee plus the block-cost difference — and the whole rostered crew stands down, because a type rating is type-specific. A B777 needs a purser and 7 cabin crew you may not have. |
| **Cancel** | Stop flying it. | Cancellation costs, UK261 compensation, and Art. 9 care for every passenger. |

Each candidate tail shows **where it is**, **when it is next free**, and its
**turnaround margin**, so you can see why a swap is or isn't possible before
you pick it. Sub-fleet (off-type) options sit in their own collapsed section
with either their price or the reason they are impossible — range, stand size,
or no crew rated on the type.

> **Aircraft constraints are hard.** Unlike crew rules, there is no override:
> an aeroplane cannot be the wrong type for its stands, out of range, in two
> places at once, or broken.

### Your decision gets graded

Every time you resolve a grounding, the game works out the **best available
alternative** — every legal tail, every ferry, and cancelling — and grades what
you actually chose against it: **OPTIMAL**, **GOOD**, or **SUBOPTIMAL**, with
the gap shown in cost. It is the game teaching you the shape of the decision
after the fact, not a punishment.

### Reset to zero

When a day has fallen far enough apart, real airlines sometimes stop trying to
recover flight by flight and **pre-emptively cancel a block** to resynchronise
the fleet. The **RESET TO ZERO** control on the aircraft desk does exactly that:
pick a set of rotations and it prices the whole thing before you commit —
cancellation cost, compensation, care, and how many *other* rotations it
actually relieves.

Watch that last number. If it says nothing else is relieved, the reset is
buying you nothing.

### Knock-on delays (the domino effect)

Aircraft fly several flights a day. If one flight runs late, the *same aircraft's*
next flight can't leave on time either — this is called a **reactionary** or
**knock-on** delay (IATA code 93), and in the real world it's the single
biggest cause of delay. The game models it: a late inbound cascades down that
aircraft's whole day, shown with a **KNOCK-ON** badge and a `·R` marker on the
timeline. Recovering early stops the dominoes.

### Crew can run out of hours

A Flight Duty Period runs from report to the final on-blocks, so **ground delay
is duty burned**. Let a pairing slip far enough and its crew will time out
before they can finish it — the game raises a **CREW OUT OF HOURS** incident
when that happens, and its options deliberately do *not* include "hold": more
delay is what caused it.

Every crew carries a live clock, so you can see it coming: the **CREW** desk
shows hours left, and the problem monitor flags a duty heading for the wall
before it hits.

### Two costly rules to watch

- **LHR night curfew** — departures or arrivals at Heathrow between **23:00 and
  06:00 Zulu** draw a regulatory fine. Delays that push a flight into the night
  cost you.
- **EU261 / UK261 passenger compensation** — if a flight *arrives* 3+ hours
  late, you owe every passenger compensation (more for long-haul). **Exception:**
  if the delay was caused by weather or ATC ("extraordinary circumstances"), no
  compensation is due — exactly as in the real regulation. This is what makes
  "accept a big delay vs. cancel" a genuine money decision.
- **Article 9 duty of care** — meals once a delay passes its threshold, and a
  hotel once it is long enough that passengers are staying the night. Unlike
  compensation, care is **never** excused by weather or ATC (*McDonagh v
  Ryanair*). A weather day still bleeds cash.
- **Cancelling does not dodge either.** A cancellation owes compensation and
  care just as a long delay does.
- **Crew accommodation (HOTAC)** — any crew who end the day away from base need
  a hotel, transport and a per diem, whether or not you chose to leave them
  there.

---

## The other screens (left menu)

| Key | Menu item | What it shows |
| --- | --------- | ------------- |
| `1` | **ROSTER** | The flight-by-flight crew board (Phase 1). |
| `2` | **AIRCRAFT** | Aircraft Control — the tail desk. Reassign, ferry, substitute, or reset to zero. |
| `3` | **TIMELINE** | A tracking board of every tail's day, including idle spares and ground time, with delay drawn as displacement. |
| `4` | **INCIDENTS** | The live disruption queue (Phase 2). |
| `5` | **CREW** | The full crew list with status, fatigue, rest, qualifications and hours left. |
| `6` | **ROSTER PLANNER** | Plan duties and days off across the whole base, with the open-time work list (see below). |
| `7` | **OPS ADVISOR** | The AI advisor chat log. |
| `8` | **FTL REGS** | A cheat-sheet of the flight-time-limit rules the game enforces. |
| `9` | **DISPOSITION** | Crew who are out of position and need a decision (see below). |

### Keyboard

The desk is keyboard-driven, like the real thing. `1`–`9` switch desks,
**space** plays and pauses the clock, `[` and `]` push the clock forward 15 and
30 minutes, and **Escape** closes any dialog. The bindings are printed on the
controls themselves.

### Two strips above the work area

- **PROBLEM MONITOR** — what is wrong *right now* by the rules rather than by
  chance: uncovered sectors, duties about to bust, crew out of position, a
  reserve bank running dry. Grouped by type, collapsible, and it remembers.
- **CASCADE** — live attribution for knock-on delay: `EGW118 +40m ← EGW104
  LATE`. When an edge was caused by something *you* did, it says so.

### Roster Planner

Crew can't work forever — after too many consecutive duty days they legally
**must** have a day off. The planner is where you shape the base's week.

**Duty cells are roster lines.** Each shows the route, report and off-duty
times, sector count and the FDP the duty consumes against the cap that applies
to that crew — `LHR-FCO-LHR 09:33/17:33 2 SECTORS FDP 8h00/13h00`. An 05:00
four-sector day and a 14:00 single-sector day are very different animals, and
now they look it.

**Planning is bulk, on two axes.** Tick the crew you want on the left (or use
the select-all box), then click the **day columns** you want to change in the
header. The bar at the top tracks both and applies to the whole grid at once:

| Action | What it plans |
| ------ | ------------- |
| **DAY OFF** | A rest day, free of duty. |
| **AIRPORT STANDBY** | Reserve at the field — 30 min to report, duty clock running. |
| **HOME STANDBY** | Reserve at home — 90 min to report, fresh. |
| **CLEAR** | Remove whatever was planned. |

Choosing your standby mix is a real planning decision: it decides whether
tomorrow's sickness is survivable and how much it costs you when it happens.

> A day off the crew is **owed** always beats a planned standby. Rest is not
> something you can roster away by putting someone on reserve instead. The game
> also auto-plans a day off for anyone about to hit the legal limit, so you are
> never forced to micro-manage all 170+ crew.

**OPEN TIME** runs down the right-hand side: every sector with nobody on it,
what ranks it is short, and the legal candidates for each — click one to assign
straight from the list.

### Crew Disposition

Disruption strands people. When a crew ends up somewhere they cannot operate
their next duty from — or somewhere with nothing rostered at all — they appear
on the **DISPOSITION** desk with four options:

| Option | What it does | What it costs |
| ------ | ------------ | ------------- |
| **Position home** | Fly them back as passengers on a real inbound. | A seat and handling — and it counts as duty and FDP, so it costs you tomorrow too. |
| **Hold down-route** | Leave them to operate the return. | A hotel, and they are locked out of everything else until then. |
| **Re-crew locally** | Use somebody already at that station. | Usually impossible for a single-base airline — the desk says so rather than hiding the option. |
| **Night-stop** | Book the hotel, stand them down. | Hotel, transport and per diem; they are off tomorrow's roster. |

Only crew who genuinely need a **decision** appear here. A crew night-stopping
at Hong Kong with the return already rostered is ordinary long-haul, not a
problem, and the desk leaves them alone. Rows you have dealt with drop off the
list, with a count of how many you have handled.

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
- **Watch the duty clocks, not just the delays.** A four-hour delay does not
  only cost OTP — it can put the crew out of hours and turn one late flight
  into a cancellation.
- **Plan your standby mix deliberately.** Airport standby answers in 30
  minutes but burns duty all day; home standby is cheap to hold and costs you
  90 minutes when it matters. Both beat having none.
- **Read the grade after a grounding.** It tells you what the best available
  answer was and what your choice cost against it — the cheapest lesson in the
  game.
- **Deal with stranded crew the same day.** Doing nothing is a decision: they
  night-stop, you pay the hotel, and they are off tomorrow's roster.
