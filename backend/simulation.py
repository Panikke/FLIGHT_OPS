"""
Airline Crew-Control Simulation Engine
=======================================
Domain model + EASA/UK CAA-inspired (simplified) rule checks.
NOTE: This is a SIMULATION for entertainment / training value only.
It is NOT an official compliance tool.
"""

from __future__ import annotations
import copy
import math
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

# ------------------- Reference data ------------------- #

AIRLINE = {
    "icao": "EGW",
    "name": "Eaglewing International",
    "hub": "LHR",
    "country": "UK",
}

AIRCRAFT_TYPES = {
    # crew_rest_class: "none" | "class_3" (seat) | "class_2" (recliner) | "class_1" (bunk)
    # Class 1 bunks + augmented crew allow extended FDP (per CS-FTL.1.205(d))
    "A320": {"seats": 180, "haul": "short", "max_block_hr": 6, "crew_rest_class": "none"},
    "A350": {"seats": 325, "haul": "long", "max_block_hr": 14, "crew_rest_class": "class_1"},
    "B777": {"seats": 350, "haul": "long", "max_block_hr": 15, "crew_rest_class": "class_1"},
}

# Fleet: tail registrations. Tails flagged `spare` start the day on the ground
# with no scheduled flying — they are the fleet controller's reserve, available
# to swap onto a rotation (via the Aircraft Control desk) or to cover a tech
# aircraft. Non-spare tails each fly a generated set of rotations.
FLEET = [
    {"reg": "G-EAGA", "type": "A320"},
    {"reg": "G-EAGB", "type": "A320"},
    {"reg": "G-EAGC", "type": "A320"},
    {"reg": "G-EAGD", "type": "A320"},
    {"reg": "G-EAGL", "type": "A350"},
    {"reg": "G-EAGM", "type": "A350"},
    {"reg": "G-EAGN", "type": "B777"},
    {"reg": "G-EAGO", "type": "B777"},
    # Reserve aircraft (one per family) — on stand, ready to be assigned.
    {"reg": "G-EAGE", "type": "A320", "spare": True},
    {"reg": "G-EAGP", "type": "A350", "spare": True},
    {"reg": "G-EAGQ", "type": "B777", "spare": True},
]

# Routes: (origin, destination, block_minutes, type_pref)
ROUTES_SHORT = [
    ("LHR", "CDG", 75), ("LHR", "AMS", 75), ("LHR", "FRA", 95),
    ("LHR", "MAD", 145), ("LHR", "BCN", 130), ("LHR", "FCO", 165),
    ("LHR", "DUB", 80), ("LHR", "ZRH", 110), ("LHR", "MXP", 125),
    ("LHR", "CPH", 115),
]
ROUTES_LONG = [
    ("LHR", "JFK", 430, "A350"),
    ("LHR", "DXB", 410, "B777"),
    ("LHR", "SIN", 770, "B777"),
    ("LHR", "HKG", 720, "A350"),
    ("LHR", "LAX", 670, "B777"),
]

CREW_NAMES = [
    "Adeyemi","Bashir","Chen","Davies","Espinoza","Falconer","Gupta","Hadid",
    "Ibrahim","Johansson","Kowalski","Larsen","Mendoza","Nakamura","O'Connor",
    "Park","Quintero","Rasmussen","Sokolov","Tanaka","Ulloa","Vasquez","Wójcik",
    "Xu","Yamada","Zaragoza","Petrov","Olsen","Karim","Singh","Romero","Hassan",
    "Schmidt","Müller","Costa","Reyes","Khan","Brown","Smith","Jones","Wilson",
    "Patel","Ahmed","Garcia","Martinez","Lee","Kim","Wang","Liu","Tanaka",
]

# ------------------- Rules constants ------------------- #
MIN_REST_HOME_HR = 12
MIN_REST_AWAY_HR = 10
# --- Commander's discretion (ORO.FTL.205(f)) --------------------------------
# In unforeseen circumstances arising AFTER report, the commander may extend
# max FDP by up to 2h (3h with an augmented crew). The following rest may be
# reduced but never below 10h, and where the extension exceeds 1h the operator
# must report it — with its own comments — to the competent authority within
# 28 days. Its use must be non-punitive. This is a licensed judgement, not a
# cheat: it is the difference between a captain making a call and the roster
# being broken.
# https://www.easa.europa.eu/en/faq/47599
DISCRETION_MAX_MIN = 120
DISCRETION_MAX_MIN_AUGMENTED = 180
DISCRETION_REPORT_THRESHOLD_MIN = 60
DISCRETION_MIN_REST_AFTER_HR = 10
# --- Standby, ORO.FTL.225 / CS FTL.1.225 -----------------------------------
# Airport standby counts IN FULL as duty; other (home) standby counts at 25%.
# Where home standby runs past 6 hours, the maximum FDP is reduced by the
# excess. That is what makes the standby bank a real planning decision: the
# airport standby answers fast but is already burning duty, the home standby
# is fresh but costs you an hour and a half you may not have.
# https://regulatorylibrary.caa.co.uk/965-2012/Content/AMC%20GM%201/CS%20FTL%201%20225%20Standby.htm
STANDBY_AIRPORT = "APT"
STANDBY_HOME = "HSBY"
# Time from the call to reporting at the aircraft. Contractual rather than
# regulatory — these are typical UK short-haul figures, not a published rule.
STANDBY_RESPONSE_MIN = {STANDBY_AIRPORT: 30, STANDBY_HOME: 90}
STANDBY_DUTY_FRACTION = {STANDBY_AIRPORT: 1.0, STANDBY_HOME: 0.25}
# Home standby beyond this erodes the FDP that follows it.
STANDBY_FDP_FREE_HR = 6
# --- Basic maximum daily FDP, ORO.FTL.205(b) -------------------------------
# Table 2 (acclimatised crew): the cap falls with a later report and with every
# extra sector, which is what makes an early multi-sector short-haul day
# genuinely tighter than a late single-sector one. Bands are the start of the
# FDP (report time) in local time at the reporting point; values in minutes.
# https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32014R0083
_FDP_SECTOR_STEPS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
FDP_TABLE_ACCLIMATISED = {
    #  band start (inclusive) -> caps by sector count 1-2, 3, 4, 5, 6, 7, 8, 9, 10+
    ("05:00", "05:14"): (780, 750, 720, 690, 660, 630, 600, 570, 540),
    ("05:15", "05:29"): (795, 765, 735, 705, 675, 645, 615, 570, 540),
    ("05:30", "05:44"): (810, 780, 750, 720, 690, 660, 630, 570, 540),
    ("05:45", "05:59"): (825, 795, 765, 735, 705, 675, 645, 570, 540),
    ("06:00", "13:29"): (780 + 0, 750, 720, 690, 660, 630, 600, 570, 540),
    ("13:30", "13:59"): (765, 735, 705, 675, 645, 615, 585, 555, 540),
    ("14:00", "14:29"): (750, 720, 690, 660, 630, 600, 570, 540, 540),
    ("14:30", "14:59"): (735, 705, 675, 645, 615, 585, 555, 540, 540),
    ("15:00", "15:29"): (720, 690, 660, 630, 600, 570, 540, 540, 540),
    ("15:30", "15:59"): (705, 675, 645, 615, 585, 555, 540, 540, 540),
    ("16:00", "16:29"): (690, 660, 630, 600, 570, 540, 540, 540, 540),
    ("16:30", "16:59"): (675, 645, 615, 585, 555, 540, 540, 540, 540),
    ("17:00", "04:59"): (660, 630, 600, 570, 540, 540, 540, 540, 540),
}
# Table 3 — crew in an UNKNOWN state of acclimatisation, which is every crew
# returning from one of our long-haul outstations (all >=4h off UTC). No
# start-time banding: the whole point is that their body clock is unknown.
FDP_TABLE_UNKNOWN = (660, 630, 600, 570, 540, 540, 540, 540, 540)
# Stations far enough off UTC that a night-stop leaves the crew unacclimatised.
LONG_HAUL_STATIONS = frozenset(dest for _o, dest, _b, _t in ROUTES_LONG)

MAX_FDP_MIN_2SECTOR = 13 * 60         # short-haul, unaugmented
MAX_FDP_MIN_LONGHAUL_BASE = 14 * 60   # long-haul unaugmented
MAX_FDP_MIN_LONGHAUL_BUNK = 18 * 60   # long-haul, augmented crew + Class 1 bunks
MAX_BLOCK_28D_HR = 100
MAX_DUTY_7D_HR = 60
MAX_DUTY_7D_MIN = MAX_DUTY_7D_HR * 60
MIN_TURNAROUND_MIN = 45          # minimum ground time before the same tail departs again
DIVERSION_RECOVERY_MIN = 120     # extra positioning time after a diversion before next sector
# LHR night curfew (simplified, inspired by real EGLL noise-abatement rules):
# movements at the hub between 23:00Z and 06:00Z draw a regulatory fine.
CURFEW_AIRPORT = "LHR"
CURFEW_START_HOUR = 23
CURFEW_END_HOUR = 6
# Ferry (positioning) flights burn fuel and crew time for zero revenue — a
# genuine but expensive last-resort lever, not a free one. Dispatch fee plus
# a per-minute rate that scales with the type's fuel burn (wide-bodies cost
# noticeably more per minute to reposition empty than a narrow-body).
# Covers the slot, ground handling, crew callout AND positioning the two
# flight-deck crew to wherever the tail is stranded.
FERRY_DISPATCH_FEE_USD = 2500
FERRY_COST_PER_MIN_USD = {"A320": 10, "A350": 24, "B777": 27}
# What a minute of delay actually costs the network. EUROCONTROL's Standard
# Inputs put all-cause at-gate tactical delay at ~EUR166/min INCLUDING the
# reactionary knock-on, and network-average ATFM delay at EUR100/min. We price
# the reactionary minute alone at the lower figure — the primary delay that
# caused it is already paid for through the incident's own cost.
# https://ansperformance.eu/economics/cba/standard-inputs/latest/chapters/cost_of_delay.html
DELAY_COST_PER_MIN_USD = 110
# Real carriers run a completion factor in the high nineties; below that the
# schedule stops being a schedule.
TARGET_COMPLETION_FACTOR_PCT = 98
CURFEW_FINE_BASE_USD = 6000
CURFEW_FINE_PER_PAX_USD = 8
# Recurrent days free of duty: crew may not operate beyond this many consecutive
# duty days without a day off; a warning is raised the day before the limit.
MAX_CONSECUTIVE_DUTY_DAYS = 6
DAYS_OFF_WARN_AT = MAX_CONSECUTIVE_DUTY_DAYS - 1
# Duty codes recorded per crew per day (roster line / calendar cells)
DUTY_FREE_CODES = ("OFF", "REST", "SICK")   # a day that resets the consecutive-duty count


def _pairing_fdp_min(state: dict, flight: dict) -> tuple[int, int, int, int]:
    """FDP the pairing containing `flight` will consume, as
    (total_min, scheduled_min, delay_min, sector_count).

    A Flight Duty Period runs from report to the final on-blocks, so ground
    delay is FDP burned — a pairing that slips two hours costs its crew two
    hours of duty they will never get back. The scheduled baseline is report
    (60) + block + turnarounds (60 per sector change) + post-flight (30);
    the delay term is the last sector's accumulated delay, which is where
    the pairing actually ends. Earlier sectors' delays reach it through
    `propagate_reactionary_delays`, since a pairing shares one tail."""
    pairing_id = flight.get("pairing_id")
    pairing_flights = [f for f in state["flights"] if pairing_id and f.get("pairing_id") == pairing_id]
    if not pairing_flights:
        pairing_flights = [flight]
    pairing_flights.sort(key=lambda f: f["std"])
    sectors = len(pairing_flights)
    block = sum(pf["block_min"] for pf in pairing_flights)
    scheduled = block + 60 + 30 + (sectors - 1) * 60
    delay = pairing_flights[-1].get("delay_min", 0)
    return scheduled + delay, scheduled, delay, sectors


def _sector_column(sectors: int) -> int:
    """Table column index for a sector count. Column 0 covers 1-2 sectors, then
    one column per sector (3, 4, 5 ...), with 10+ sharing the last."""
    sectors = sectors or 1
    idx = 0 if sectors <= 2 else sectors - 2
    return max(0, min(len(FDP_TABLE_UNKNOWN) - 1, idx))


def _fdp_band_for(report_hhmm: str) -> tuple[str, str] | None:
    for band in FDP_TABLE_ACCLIMATISED:
        start, end = band
        if start <= end:
            if start <= report_hhmm <= end:
                return band
        else:                       # band wraps midnight (17:00-04:59)
            if report_hhmm >= start or report_hhmm <= end:
                return band
    return None


def _seed_standby_duty(crew: dict, index: int) -> None:
    """Put a standby crew on a real standby duty. Roughly one in three is held
    at the airport — they answer in half an hour but their duty clock is
    already running, which is exactly why airlines hold few of them."""
    airport = index % 3 == 0
    crew["standby_type"] = STANDBY_AIRPORT if airport else STANDBY_HOME
    # Standby started somewhere in the first part of the day; how long they
    # have been sitting is what erodes the FDP they can then operate.
    crew["standby_elapsed_hr"] = round(random.uniform(0.5, 8.0), 1)


def _standby_fdp_reduction_min(crew: dict) -> int:
    """CS FTL.1.225: home standby past 6h cuts the FDP that follows it by the
    excess. Airport standby does not reduce the cap — it counts as duty in
    full instead, which the duty accounting handles."""
    if crew.get("status") != "standby" or crew.get("standby_type") != STANDBY_HOME:
        return 0
    excess_hr = (crew.get("standby_elapsed_hr", 0) or 0) - STANDBY_FDP_FREE_HR
    return int(max(0, excess_hr) * 60)


def standby_response_min(crew: dict) -> int:
    """How long from the call until this crew can report."""
    return STANDBY_RESPONSE_MIN.get(crew.get("standby_type", STANDBY_HOME), 90)


def _fdp_cap_for_flight(flight: dict, sectors: int | None = None,
                        acclimatised: bool = True) -> tuple[int, str]:
    """Return (max_fdp_min, basis_str) for a flight.

    Augmented crew with in-flight rest are handled by the separate in-flight
    rest provisions rather than the basic table — ORO.FTL.205(b) Table 2 is
    the cap for operations WITHOUT in-flight rest. Everything else reads the
    real table: later report and more sectors both cut the cap, and a crew in
    an unknown state of acclimatisation reads Table 3 instead."""
    ac_type = flight["aircraft_type"]
    block = flight["block_min"]
    rest_class = AIRCRAFT_TYPES.get(ac_type, {}).get("crew_rest_class", "none")
    req = flight.get("required_crew", {})
    # Augmentation is carried entirely by relief First Officers now (a single
    # Captain operates every sector — see _required_crew_for) — so "augmented"
    # means a relief pilot is rostered, i.e. FO count above the base of 1.
    augmented = req.get("FO", 1) >= 2
    if block > 360 and augmented and rest_class == "class_1":
        return MAX_FDP_MIN_LONGHAUL_BUNK, f"long-haul augmented crew + Class 1 bunks ({ac_type})"

    if sectors is None:
        sectors = 1 if block > 360 else 2
    col = _sector_column(sectors)
    sector_label = "1-2 sectors" if sectors <= 2 else f"{sectors} sectors"

    if not acclimatised:
        return FDP_TABLE_UNKNOWN[col], (
            f"unknown acclimatisation state, {sector_label} "
            f"(ORO.FTL.205 Table 3)"
        )

    report = datetime.fromisoformat(flight["std"]) - timedelta(minutes=60)
    hhmm = report.strftime("%H:%M")
    band = _fdp_band_for(hhmm)
    if band is None:                                     # defensive
        return MAX_FDP_MIN_2SECTOR, "acclimatised, 2-sector (fallback)"
    cap = FDP_TABLE_ACCLIMATISED[band][col]
    if block > 360 and not augmented:
        # An unaugmented long-haul sector still reads the basic table, but we
        # keep the old floor so a single ultra-long sector is not made
        # impossible by a late report alone.
        cap = max(cap, MAX_FDP_MIN_LONGHAUL_BASE) if sectors <= 2 else cap
        return cap, f"long-haul ({ac_type}) without in-flight rest, report {hhmm}"
    return cap, f"acclimatised, {sector_label}, report {hhmm} (Table 2)"


def _crew_acclimatised(state: dict, crew: dict, flight: dict) -> bool:
    """A crew who night-stopped at one of our long-haul outstations is in an
    unknown state of acclimatisation — every long-haul destination we serve is
    at least four hours off UTC."""
    dep = datetime.fromisoformat(flight["std"])
    at = _crew_position_before(state, crew["id"], dep)
    return at not in LONG_HAUL_STATIONS

# ------------------- Helpers ------------------- #

def _hash_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Fallback block time for a city pair not in ROUTES_SHORT/ROUTES_LONG (there
# shouldn't be one, since the network only ever schedules real flights
# between airports that appear in these tables — this only guards against an
# unmodelled pair ever reaching a ferry calculation).
FERRY_FALLBACK_BLOCK_MIN = 180


def _route_block_min(origin: str, dest: str) -> int:
    """Typical block time between two airports, in either direction, reusing
    the same route data the day's schedule is generated from — a positioning
    (ferry) flight isn't a new kind of trip, just an empty one."""
    for o, d, blk in ROUTES_SHORT:
        if {o, d} == {origin, dest}:
            return blk
    for o, d, blk, _t in ROUTES_LONG:
        if {o, d} == {origin, dest}:
            return blk
    return FERRY_FALLBACK_BLOCK_MIN


# ------------------- Crew generation ------------------- #

def _seed_duty_history(days_since_off: int, length: int = 6) -> list[str]:
    """Synthesise a plausible recent roster line so the calendar is populated on
    day 1. The trailing run of duty codes equals `days_since_off` (kept consistent
    with the authoritative counter); a day off sits just before that streak."""
    duty_pool = ["FLT", "AVL", "FLT", "SBY"]
    hist: list[str] = []
    earlier = length - days_since_off
    for _ in range(max(0, earlier)):
        hist.append(random.choice(["FLT", "AVL", "OFF", "SBY", "FLT", "AVL"]))
    if earlier >= 1:
        hist[-1] = "OFF"   # the day-off that ended the previous streak
    for _ in range(min(days_since_off, length)):
        hist.append(random.choice(duty_pool))
    return hist[-length:]


RANK_TITLES = {"CP": "Captain", "FO": "First Officer", "SC": "Senior Cabin", "CC": "Cabin Crew"}
AIRCRAFT_TYPES_LIST = ["A320", "A350", "B777"]
# Headroom over expected daily slot demand: real crew bases run well beyond
# one day's minimum flying requirement to absorb standby, sickness, days-off
# and training — this is what keeps "start the day fully rostered" achievable
# without making disruption during ops toothless.
CREW_SUPPLY_BUFFER = 1.3


def _expected_daily_crew_demand() -> dict[tuple[str, str], float]:
    """Expected crew-slot demand per (rank, type), derived from the fleet and
    route-generation rules via _required_crew_for (single source of truth for
    crew composition — no duplicated headcount logic to drift out of sync).
    Not sampled from one game's random flights, so it stays stable across
    every day of a campaign. A320 rotation count and long-haul route choice
    are both randomised per aircraft per day — this averages over those
    distributions rather than assuming worst case, which would wildly
    over-provision the crew pool."""
    demand: dict[tuple[str, str], float] = {}

    def add(rank: str, t: str, n: float) -> None:
        demand[(rank, t)] = demand.get((rank, t), 0.0) + n

    # Spare tails don't fly a scheduled programme, so they generate no crew
    # demand — count only the active (non-spare) fleet.
    a320_count = sum(1 for ac in FLEET if ac["type"] == "A320" and not ac.get("spare"))
    if a320_count:
        avg_rotations = sum(range(2, 4)) / len(range(2, 4))  # random.choice([2, 3])
        req = _required_crew_for("A320", 0)  # block length doesn't affect A320 composition
        for rank in ("CP", "FO", "SC", "CC"):
            add(rank, "A320", a320_count * avg_rotations * req[rank])

    for t in ("A350", "B777"):
        fleet_count = sum(1 for ac in FLEET if ac["type"] == t and not ac.get("spare"))
        choices = [r for r in ROUTES_LONG if r[3] == t]
        if not fleet_count or not choices:
            continue
        for rank in ("CP", "FO", "SC", "CC"):
            avg_req = sum(_required_crew_for(t, r[2])[rank] for r in choices) / len(choices)
            add(rank, t, fleet_count * avg_req)

    return demand


def _make_crew(rank: str, quals: list[str], cid: int, used_names: set[str]) -> dict:
    for _try in range(50):
        surname = random.choice(CREW_NAMES)
        initial = random.choice("ABCDEFGHJKLMNPRSTW")
        disp = f"{initial}. {surname}"
        if disp not in used_names:
            used_names.add(disp)
            break
    dso = random.randint(0, 5)
    return {
        "id": f"EGW{cid}",
        "name": disp,
        "rank": rank,
        "rank_title": RANK_TITLES[rank],
        "base": "LHR",
        "qualifications": quals,
        # Operating state
        "fdp_used_min": 0,
        "block_28d_hr": round(random.uniform(20, 70), 1),
        "duty_7d_hr": round(random.uniform(10, 35), 1),
        "rest_hr_since_duty": round(random.uniform(11, 30), 1),
        "last_duty_min": 0,          # length of the duty most recently completed
        "station": None,             # where they are now; None = at base
        "status": "available",        # available | on_duty | rest | standby | sick | off
        "assigned_flight_id": None,
        "fatigue_score": random.randint(15, 45),  # 0-100 lower better
        "sickness_risk": round(random.uniform(0.01, 0.08), 3),
        # ---- Days-off / roster-line tracking ----
        # consecutive duty days since the crew's last day free of duty
        "days_since_off": dso,
        # per-completed-day duty codes (oldest->newest), grows each day
        "duty_history": _seed_duty_history(dso),
        # absolute future day_numbers the controller has pre-marked OFF
        "days_off_planned": [],
    }


def _generate_crew() -> list[dict]:
    crew: list[dict] = []
    used_names: set[str] = set()
    cid = 1000

    def spawn(rank: str, quals: list[str]) -> None:
        nonlocal cid
        crew.append(_make_crew(rank, quals, cid, used_names))
        cid += 1

    # 1. Guaranteed floor: single-type-qualified crew sized off expected daily
    # demand per (rank, type), with buffer — guarantees the fleet's actual
    # workload is coverable by rank AND by type-rating, not just in aggregate.
    for (rank, t), qty in _expected_daily_crew_demand().items():
        for _ in range(math.ceil(qty * CREW_SUPPLY_BUFFER)):
            spawn(rank, [t])

    # 2. Extra variety pool: dual/tri-rated crew for flavour and additional
    # standby depth beyond the guaranteed floor. Flight deck are rarely
    # multi-rated in reality; cabin crew commonly are.
    extras = {"CP": 3, "FO": 5, "SC": 4, "CC": 8}
    for rank, n in extras.items():
        for _ in range(n):
            primary = random.choice(AIRCRAFT_TYPES_LIST)
            quals = [primary]
            dual_chance = 0.15 if rank in ("CP", "FO") else 0.5
            if random.random() < dual_chance:
                quals.append(random.choice([t for t in AIRCRAFT_TYPES_LIST if t != primary]))
            spawn(rank, quals)

    return crew


# ------------------- Flight generation ------------------- #

def _add_minutes_to_clock(base_iso: str, minutes: int) -> str:
    base = datetime.fromisoformat(base_iso)
    return (base + timedelta(minutes=minutes)).isoformat()


def _generate_day_flights(day_start_iso: str) -> list[dict]:
    """Generate flights for the operational day.
    Short-haul: aircraft does multiple out-and-back rotations from LHR.
      Each (outbound + return) pair shares a `pairing_id` — the same crew set
      operates both sectors (realistic short-haul operation).
    Long-haul: aircraft does ONE outbound today; the return is a next-day
      operation (crew night-stops downroute). Pairing_id is unique to that
      single sector for the day.
    """
    flights = []
    day_start = datetime.fromisoformat(day_start_iso)
    fnum = 100
    for ac in FLEET:
        if ac.get("spare"):
            continue  # reserve tail — starts the day idle on stand
        depart_min = random.randint(0, 180)
        if ac["type"] == "A320":
            # 2 to 3 out-and-back rotations in the day, each = 1 pairing
            rotations = random.choice([2, 3])
            for _ in range(rotations):
                origin, dest, block = random.choice(ROUTES_SHORT)
                pairing_id = _hash_id("PAIR")
                std = (day_start + timedelta(minutes=depart_min)).isoformat()
                sta = _add_minutes_to_clock(std, block)
                out = _make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id)
                flights.append(out)
                fnum += 2
                turn = 60
                depart_min += block + turn
                std2 = (day_start + timedelta(minutes=depart_min)).isoformat()
                sta2 = _add_minutes_to_clock(std2, block)
                back = _make_flight(fnum, dest, origin, std2, sta2, block, ac, pairing_id)
                flights.append(back)
                fnum += 2
                depart_min += block + turn
        else:
            # Long-haul: ONE sector today (outbound), crew night-stops.
            # No same-day return — that's tomorrow's problem.
            choices = [r for r in ROUTES_LONG if r[3] == ac["type"]]
            if not choices:
                continue
            origin, dest, block, _type_pref = random.choice(choices)
            std = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta = _add_minutes_to_clock(std, block)
            pairing_id = _hash_id("PAIR")
            flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
            fnum += 2
    flights.sort(key=lambda f: f["std"])
    return flights


def _make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id):
    return {
        "id": _hash_id("FLT"),
        "callsign": f"EGW{fnum}",
        "origin": origin,
        "destination": dest,
        "std": std,
        "sta": sta,
        "block_min": block,
        "aircraft_reg": ac["reg"],
        "aircraft_type": ac["type"],
        "status": "scheduled",
        "delay_min": 0,
        "pax_count": random.randint(
            int(AIRCRAFT_TYPES[ac["type"]]["seats"] * 0.65),
            AIRCRAFT_TYPES[ac["type"]]["seats"],
        ),
        "assigned_crew_ids": [],
        "required_crew": _required_crew_for(ac["type"], block),
        "pairing_id": pairing_id,
        "note": "",
    }


def _relief_pilots_for(block_min: int) -> int:
    """Extra flight-deck pilots for cruise relief on long sectors, modelled as
    additional First Officers rather than a separate rank — one relief pilot
    covers rest breaks up to ~12h, two beyond that. A single Captain operates
    every sector regardless of length; only the FO count scales."""
    if block_min <= 540:      # <= 9h: standard 2-pilot crew, no relief needed
        return 0
    if block_min < 720:       # 9-12h: one relief pilot (3-pilot flight deck)
        return 1
    return 2                  # 12h+: two relief pilots (4-pilot flight deck)


def _required_crew_for(ac_type: str, block_min: int) -> dict:
    """Standard airline crew composition: 1 Captain + 1 First Officer (plus
    relief pilots on long sectors), 1 inflight/cabin manager (plus 1 purser
    on long-haul), and 1 cabin crew member per 50 certified seats."""
    seats = AIRCRAFT_TYPES[ac_type]["seats"]
    cc = math.ceil(seats / 50)
    if ac_type == "A320":
        return {"CP": 1, "FO": 1, "SC": 1, "CC": cc, "type_qual": ac_type}
    return {
        "CP": 1,
        "FO": 1 + _relief_pilots_for(block_min),
        "SC": 2,  # inflight manager + purser
        "CC": cc,
        "type_qual": ac_type,
    }


# ------------------- Game state factory ------------------- #

def new_game(scenario: str = "free_play") -> dict:
    """Create a fresh game state.
    scenario: 'free_play' (open-ended) or 'survive_7' (7-day fixed-seed challenge)
    """
    is_challenge = scenario == "survive_7"
    if is_challenge:
        # Fixed seed makes the challenge reproducible (and leaderboard-able)
        random.seed(20260514)
    else:
        random.seed()
    # Day clock anchored at 04:00 UTC today
    today = datetime.now(timezone.utc).replace(hour=4, minute=0, second=0, microsecond=0)
    day_start_iso = today.isoformat()
    crew = _generate_crew()
    flights = _generate_day_flights(day_start_iso)

    # Mark some crew as standby pool, some on rest
    random.shuffle(crew)
    standby_count = 0
    for c in crew:
        if c["rank"] in ("CP", "FO") and standby_count < 4:
            c["status"] = "standby"
            _seed_standby_duty(c, standby_count)
            standby_count += 1
        elif c["rank"] in ("SC", "CC") and standby_count < 14:
            c["status"] = "standby"
            _seed_standby_duty(c, standby_count)
            standby_count += 1

    state = {
        "id": _hash_id("GAME"),
        "scenario": scenario,
        "created_at": now_utc_iso(),
        "airline": AIRLINE,
        "fleet": copy.deepcopy(FLEET),
        "crew": crew,
        "flights": flights,
        "incidents": [],
        "decisions_log": [],
        "cascade_log": [],
        "kpis": {
            "otp_pct": 100.0,
            "legality_breaches": 0,
            "curfew_violations": 0,
            "compensation_usd": 0,
            "fatigue_index": 25,
            "cost_usd": 0,
            "pax_delay_min": 0,
            "pax_disrupted": 0,
            "reactionary_min": 0,
            "duty_of_care_usd": 0,
            "hotac_usd": 0,
            "discretion_used_count": 0,
            "discretion_reports": 0,
            "delay_cost_usd": 0,
            "completion_factor_pct": 100.0,
            "score": 1000,
        },
        "day_start": day_start_iso,
        "clock": day_start_iso,                # rolling sim clock
        "phase": "ROSTER",                     # ROSTER | OPS | DEBRIEF
        "tick_count": 0,
        "advisor_history": [],
        # ---- Multi-day campaign tracking ----
        "day_number": 1,
        "campaign_kpis": {
            "days_completed": 0,
            "total_score": 0,
            "total_breaches": 0,
            "total_cost_usd": 0,
            "total_pax_disrupted": 0,
            "avg_otp_pct": 0.0,
            "per_day": [],   # list of {day, score, otp, breaches, cost}
        },
        # Crew downroute (waiting for tomorrow's return)
        "outstation_crew": [],   # list of {crew_id, station, flight_id_to_return}
        # Scenario / challenge mode
        "is_challenge": is_challenge,
        "total_days": 7 if is_challenge else None,
        "campaign_complete": False,
        "final_grade": None,
    }
    return state


# ------------------- Multi-day campaign ------------------- #

def _final_grade(ck: dict) -> dict:
    """Compute final challenge grade based on campaign KPIs."""
    score = ck.get("total_score", 0)
    breaches = ck.get("total_breaches", 0)
    avg_otp = ck.get("avg_otp_pct", 0)
    days = ck.get("days_completed", 0)
    if breaches >= 10 or score <= 0:
        label, tone, note = "FAILED", "t-crit", "Authority audit triggered. Operating certificate at risk."
    elif breaches >= 5 or avg_otp < 60:
        label, tone, note = "MARGINAL", "t-warn", "You survived, but the regulator wrote you up."
    elif score >= 5500 and breaches == 0 and avg_otp >= 85:
        label, tone, note = "DISTINGUISHED", "t-nominal", "Textbook campaign. Promoted to Head of Crew Control."
    elif score >= 4000 and avg_otp >= 75:
        label, tone, note = "PASS", "t-nominal", "A clean, professional week. The CEO sends congratulations."
    else:
        label, tone, note = "WEAK PASS", "t-warn", "You got through it. Just."
    return {
        "label": label, "tone": tone, "note": note,
        "total_score": score, "total_breaches": breaches,
        "avg_otp_pct": avg_otp, "days_completed": days,
    }


def advance_to_next_day(state: dict) -> dict:
    """Roll the simulation to the next operational day.
    If is_challenge and current day == total_days: finalize the campaign instead
    (no further day generated; set campaign_complete and final_grade).
    """
    # Capture today
    day_kpis = dict(state["kpis"])
    ck = state.setdefault("campaign_kpis", {
        "days_completed": 0, "total_score": 0, "total_breaches": 0,
        "total_cost_usd": 0, "total_pax_disrupted": 0, "avg_otp_pct": 0.0, "per_day": []
    })
    ck["days_completed"] += 1
    ck["total_score"] += day_kpis["score"]
    ck["total_breaches"] += day_kpis["legality_breaches"]
    ck["total_cost_usd"] += day_kpis["cost_usd"]
    ck["total_pax_disrupted"] += day_kpis["pax_disrupted"]
    ck["per_day"].append({
        "day": state.get("day_number", 1),
        "score": day_kpis["score"],
        "otp": day_kpis["otp_pct"],
        "breaches": day_kpis["legality_breaches"],
        "cost": day_kpis["cost_usd"],
    })
    if ck["per_day"]:
        ck["avg_otp_pct"] = round(
            sum(d["otp"] for d in ck["per_day"]) / len(ck["per_day"]), 1
        )

    # Challenge mode: campaign complete after total_days
    if state.get("is_challenge") and state.get("day_number", 1) >= state.get("total_days", 7):
        state["campaign_complete"] = True
        state["final_grade"] = _final_grade(ck)
        # Keep phase at DEBRIEF (player can review and start new campaign)
        return {
            "day_number": state["day_number"],
            "pre_rostered_returns": 0,
            "campaign_kpis": ck,
            "campaign_complete": True,
            "final_grade": state["final_grade"],
        }

    # Per-crew block flown today
    today_block_by_crew: dict[str, float] = {}
    long_haul_assignments: dict[str, dict] = {}  # crew_id -> {station, route_back, ...}
    hotac_bill = 0                                # crew accommodation away from base
    for f in state["flights"]:
        if f["status"] == "cancelled":
            continue
        block_hr = f["block_min"] / 60.0
        for cid in f["assigned_crew_ids"]:
            today_block_by_crew[cid] = today_block_by_crew.get(cid, 0) + block_hr
        # Long-haul outbound — crew is now downroute and must operate the return tomorrow
        if f["aircraft_type"] in ("A350", "B777") and f["status"] != "cancelled":
            for cid in f["assigned_crew_ids"]:
                long_haul_assignments[cid] = {
                    "station": f["destination"],
                    "origin": f["destination"],
                    "destination": f["origin"],
                    "block_min": f["block_min"],
                    "aircraft_reg": f["aircraft_reg"],
                    "aircraft_type": f["aircraft_type"],
                }

    # Update crew
    incoming_day = state.get("day_number", 1) + 1
    for c in state["crew"]:
        flown = today_block_by_crew.get(c["id"], 0)
        # Record the duty code for the day just completed (status still reflects
        # how the day was spent, before we reset it for tomorrow).
        if flown > 0:
            day_code = "FLT"
        elif c["status"] == "off":
            day_code = "OFF"
        elif c["status"] == "sick":
            day_code = "SICK"
        elif c["status"] == "standby":
            day_code = "SBY"
        else:
            day_code = "AVL"   # available reserve — still a duty day, not a day off
        c.setdefault("duty_history", []).append(day_code)
        if len(c["duty_history"]) > 28:
            c["duty_history"] = c["duty_history"][-28:]
        # Consecutive-duty counter: a day free of duty resets it, anything else adds
        if day_code in DUTY_FREE_CODES:
            c["days_since_off"] = 0
        else:
            c["days_since_off"] = c.get("days_since_off", 0) + 1
            # Auto-plan tomorrow off once the consecutive-duty cap is reached.
            # Real crew-rostering software bakes legal rest days into the
            # baseline roster line rather than leaving compliance to be
            # remembered manually — the controller can still override via
            # the Days-Off calendar (set_day_off) if operational need demands
            # it, same as commander's/rostering discretion in practice.
            if c["days_since_off"] >= MAX_CONSECUTIVE_DUTY_DAYS:
                planned = c.setdefault("days_off_planned", [])
                if incoming_day not in planned:
                    planned.append(incoming_day)

        # Where this crew physically ended the day. Derived BEFORE the flight
        # list is replaced, and persisted, because tomorrow's position cannot
        # be read off tomorrow's empty schedule.
        c["station"] = (
            long_haul_assignments[c["id"]]["station"]
            if c["id"] in long_haul_assignments
            else _crew_end_of_day_station(state, c)
        )
        if c["station"] != c.get("base", AIRLINE["hub"]):
            # ORO.FTL.105: away from base, accommodating the crew is the
            # operator's responsibility. Charged whether or not the player
            # made the call deliberately.
            hotac_bill += CREW_HOTEL_USD + CREW_TRANSPORT_USD + CREW_PERDIEM_USD
            c["hotac_nights"] = c.get("hotac_nights", 0) + 1
        c.pop("disposition", None)
        c.pop("discretion_used", None)
        c.pop("rest_floor_next_hr", None)
        # Positioning legs carry absolute timestamps from today; left in place
        # they read as a permanently-satisfied move tomorrow.
        c.pop("positioning", None)
        c.setdefault("block_history", [])
        c["block_history"].append(flown)
        # keep sliding window of last 28 days
        if len(c["block_history"]) > 28:
            c["block_history"] = c["block_history"][-28:]
        c["block_28d_hr"] = round(sum(c["block_history"]), 1)
        # duty_7d_hr must be a ROLLING 7-day sum, not a running total — it's
        # incremented intraday in tick() as flights land (so same-day legality
        # checks see hours flown so far today), but nothing was ever rolling
        # the oldest day back out. Left unfixed, every active crew member
        # marches past the 60h/7-day cap by day 3-4 and never returns,
        # collapsing roster feasibility for the rest of the campaign.
        c["duty_7d_hr"] = round(sum(c["block_history"][-7:]), 2)
        c["fdp_used_min"] = 0
        # Fatigue update — a day off recovers more than an idle reserve day
        if flown > 0:
            c["fatigue_score"] = min(100, c["fatigue_score"] + random.randint(8, 18))
        elif day_code == "OFF":
            c["fatigue_score"] = max(5, c["fatigue_score"] - random.randint(12, 22))
        else:
            c["fatigue_score"] = max(5, c["fatigue_score"] - random.randint(6, 12))
        # Rest
        if flown == 0:
            c["rest_hr_since_duty"] = round(random.uniform(11, 30), 1)
        else:
            # Overnight rest is what is left of the 24h day after the duty the
            # crew actually worked — a long day genuinely eats into it, which
            # is the whole reason the ORO.FTL.235 "at least as long as the
            # preceding duty" floor exists.
            duty_hr = c.get("last_duty_min", 0) / 60
            c["rest_hr_since_duty"] = round(max(8.0, 24.0 - duty_hr + random.uniform(-1.0, 2.0)), 1)
        # Recover most sick crew
        if c["status"] == "sick":
            if random.random() < 0.7:
                c["status"] = "available"
        else:
            # Clear assignment for tomorrow (will be re-rostered)
            c["assigned_flight_id"] = None
            c["status"] = "available"
        # Sickness risk drift
        if c["fatigue_score"] > 70 and random.random() < 0.05:
            c["status"] = "sick"
        # Honour a pre-planned day off for the incoming day (wins over the reset
        # above, and keeps the crew out of the standby pool re-draw below).
        planned_code = c.get("duty_plan", {}).get(str(incoming_day))
        if planned_code in ("SBY_APT", "SBY_HOME"):
            # The controller chose this crew as reserve cover for today.
            c["status"] = "standby"
            c["assigned_flight_id"] = None
            c["standby_type"] = STANDBY_AIRPORT if planned_code == "SBY_APT" else STANDBY_HOME
            c["standby_elapsed_hr"] = 0.0
        if incoming_day in c.get("days_off_planned", []):
            c["status"] = "off"
            c["assigned_flight_id"] = None
            c["days_off_planned"] = [d for d in c["days_off_planned"] if d != incoming_day]
        # Consumed only once it has been acted on.
        c.get("duty_plan", {}).pop(str(incoming_day), None)

    # Re-establish standby pool (~10% of pool from those still available)
    available = [c for c in state["crew"] if c["status"] == "available"]
    random.shuffle(available)
    # Crew the controller planned onto standby already count toward the bank —
    # otherwise planning reserve cover silently doubled it.
    standby_count = sum(
        1 for c in state["crew"]
        if c["status"] == "standby" and c["rank"] in ("CP", "FO"))
    for c in available:
        if c["rank"] in ("CP", "FO") and standby_count < 4:
            c["status"] = "standby"
            _seed_standby_duty(c, standby_count)
            standby_count += 1
        elif c["rank"] in ("SC", "CC") and standby_count < 14:
            c["status"] = "standby"
            _seed_standby_duty(c, standby_count)
            standby_count += 1

    # Overnight engineering: most open MEL deferrals get rectified before the
    # next day's ops; anything left standing counts down another day, and a
    # defect that runs out its category's deferral window grounds the tail
    # (see AC_MEL_EXPIRED in check_aircraft_assignment) until cleared.
    for ac in state.get("fleet", []):
        # The overnight shift finishes any rectification still open. A tail
        # that broke at 16:00 is not still broken at tomorrow's first wave.
        ac.pop("aog", None)
        items = ac.get("mel_items")
        if not items:
            continue
        kept = []
        for m in items:
            if random.random() < MEL_OVERNIGHT_CLEAR_PROB:
                continue  # engineering cleared it overnight
            m["days_remaining"] -= 1
            if m["days_remaining"] <= 0:
                m["expired"] = True
            kept.append(m)
        ac["mel_items"] = kept

    # Advance the day clock
    today_dt = datetime.fromisoformat(state["day_start"])
    next_day_dt = today_dt + timedelta(days=1)
    next_day_iso = next_day_dt.isoformat()

    # Generate tomorrow's flights
    new_flights = _generate_next_day_flights(next_day_iso, long_haul_assignments, state["crew"])

    # Pre-roster long-haul returns with yesterday's crew
    pre_rostered = 0
    for f in new_flights:
        if f.get("prerostered_crew_ids"):
            f["assigned_crew_ids"] = list(f["prerostered_crew_ids"])
            # Mark those crew on duty
            for cid in f["assigned_crew_ids"]:
                cmem = next((c for c in state["crew"] if c["id"] == cid), None)
                if cmem:
                    cmem["status"] = "on_duty"
                    cmem["assigned_flight_id"] = f["id"]
            pre_rostered += 1
        f.pop("prerostered_crew_ids", None)

    # Roll state
    state["day_number"] = state.get("day_number", 1) + 1
    state["day_start"] = next_day_iso
    state["clock"] = next_day_iso
    state["flights"] = new_flights
    state["incidents"] = []
    state["decisions_log"] = []
    state["cascade_log"] = []
    state["tick_count"] = 0
    state["phase"] = "ROSTER"
    state["kpis"] = {
        "otp_pct": 100.0,
        "legality_breaches": 0,
        "curfew_violations": 0,
        "compensation_usd": 0,
        "fatigue_index": int(sum(c["fatigue_score"] for c in state["crew"]) / max(1, len(state["crew"]))),
        "cost_usd": 0,
        "pax_delay_min": 0,
        "pax_disrupted": 0,
        "reactionary_min": 0,
        "duty_of_care_usd": 0,
        "hotac_usd": 0,
        "discretion_used_count": 0,
        "discretion_reports": 0,
        "delay_cost_usd": 0,
        "completion_factor_pct": 100.0,
        "hotac_usd": hotac_bill,
        "score": 1000,
    }
    state["kpis"]["cost_usd"] += hotac_bill
    _recompute_kpis(state)
    return {
        "day_number": state["day_number"],
        "hotac_usd": hotac_bill,
        "pre_rostered_returns": pre_rostered,
        "campaign_kpis": ck,
    }


def _generate_next_day_flights(day_start_iso: str, long_haul_returns: dict, crew_list: list[dict]) -> list[dict]:
    """Generate tomorrow's flights.
    `long_haul_returns` maps crew_id -> {station, origin, destination, block_min, aircraft_reg, aircraft_type}
    Returns list of flight dicts; long-haul returns have `prerostered_crew_ids` set so they're auto-assigned.
    """
    flights: list[dict] = []
    day_start = datetime.fromisoformat(day_start_iso)
    fnum = 200

    # Group long-haul returns by aircraft (the same aircraft brings the crew back)
    returns_by_reg: dict[str, dict] = {}
    crew_by_reg: dict[str, list[str]] = {}
    for cid, info in long_haul_returns.items():
        reg = info["aircraft_reg"]
        returns_by_reg[reg] = info
        crew_by_reg.setdefault(reg, []).append(cid)

    # Long-haul returns — depart from outstation early in the day (1-4h after day start)
    long_haul_regs_used: set[str] = set()
    for reg, info in returns_by_reg.items():
        depart_min = random.randint(60, 240)
        std = (day_start + timedelta(minutes=depart_min)).isoformat()
        sta = _add_minutes_to_clock(std, info["block_min"])
        pairing_id = _hash_id("PAIR")
        ac = {"reg": reg, "type": info["aircraft_type"]}
        f = _make_flight(fnum, info["origin"], info["destination"], std, sta, info["block_min"], ac, pairing_id)
        f["prerostered_crew_ids"] = crew_by_reg.get(reg, [])
        f["note"] = "RETURN FROM NIGHT-STOP · crew pre-rostered"
        flights.append(f)
        long_haul_regs_used.add(reg)
        fnum += 2

    # Short-haul: every A320 does new out-and-backs from LHR
    for ac in FLEET:
        if ac.get("spare"):
            continue  # reserve tail — stays idle unless the controller assigns it
        if ac["type"] != "A320":
            continue
        depart_min = random.randint(0, 180)
        rotations = random.choice([2, 3])
        for _ in range(rotations):
            origin, dest, block = random.choice(ROUTES_SHORT)
            pairing_id = _hash_id("PAIR")
            std = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta = _add_minutes_to_clock(std, block)
            flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
            fnum += 2
            depart_min += block + 60
            std2 = (day_start + timedelta(minutes=depart_min)).isoformat()
            sta2 = _add_minutes_to_clock(std2, block)
            flights.append(_make_flight(fnum, dest, origin, std2, sta2, block, ac, pairing_id))
            fnum += 2
            depart_min += block + 60

    # Long-haul NEW outbounds: any LH aircraft NOT used for a return (i.e. it's at LHR)
    for ac in FLEET:
        if ac.get("spare"):
            continue  # reserve tail — stays idle unless the controller assigns it
        if ac["type"] == "A320":
            continue
        if ac["reg"] in long_haul_regs_used:
            continue  # this aircraft is downroute returning, no new outbound today
        choices = [r for r in ROUTES_LONG if r[3] == ac["type"]]
        if not choices:
            continue
        origin, dest, block, _type_pref = random.choice(choices)
        depart_min = random.randint(0, 180)
        std = (day_start + timedelta(minutes=depart_min)).isoformat()
        sta = _add_minutes_to_clock(std, block)
        pairing_id = _hash_id("PAIR")
        flights.append(_make_flight(fnum, origin, dest, std, sta, block, ac, pairing_id))
        fnum += 2

    flights.sort(key=lambda f: f["std"])
    return flights


# ------------------- Legality / rule checks ------------------- #

def check_assignment(state: dict, flight_id: str, crew_id: str) -> list[dict]:
    """Return list of legality warnings for assigning this crew to this flight.
    Each warning: {code, severity, message, rule_ref}
    """
    warnings: list[dict] = []
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        warnings.append({
            "code": "REF_NOT_FOUND",
            "severity": "critical",
            "message": "Flight or crew reference not found.",
            "rule_ref": "INTERNAL",
        })
        return warnings

    # Qualification
    type_q = flight["required_crew"]["type_qual"]
    if type_q not in crew["qualifications"]:
        warnings.append({
            "code": "TYPE_QUAL",
            "severity": "critical",
            "message": f"Crew {crew['id']} ({crew['name']}) is not type-rated on {type_q}. Cannot operate this sector.",
            "rule_ref": "EASA FCL.740 (Type Rating Validity)",
        })

    # Already assigned to another flight overlapping in time
    fstd = datetime.fromisoformat(flight["std"])
    fsta = datetime.fromisoformat(flight["sta"])
    for of in state["flights"]:
        if of["id"] == flight_id:
            continue
        if crew_id in of["assigned_crew_ids"]:
            ostd = datetime.fromisoformat(of["std"])
            osta = datetime.fromisoformat(of["sta"])
            if not (fsta <= ostd or osta <= fstd):
                warnings.append({
                    "code": "OVERLAP",
                    "severity": "critical",
                    "message": (
                        f"Crew {crew['id']} already assigned to {of['callsign']} "
                        f"({of['origin']}->{of['destination']}) which overlaps this duty."
                    ),
                    "rule_ref": "ORO.FTL.205 (FDP Limits)",
                })

    # Rest
    # Physical position. A crew based at LHR cannot operate a JFK departure
    # without getting to JFK first — the same rule already enforced hard for
    # tails (AC_WRONG_STATION). Overridable, because positioning them IS a
    # real option; teleporting them is not.
    # Positioning flights are exempt: getting the flight-deck crew to the
    # stranded tail is part of what the ferry dispatch fee buys. Modelling that
    # leg properly is the job of a real deadhead mechanic (see
    # docs/research/REALISM_BOARD_LOG.md item 17) — until that exists, an
    # exemption stated out loud beats a silent teleport.
    dep = datetime.fromisoformat(flight["std"]) + timedelta(minutes=flight.get("delay_min", 0))
    crew_at = _crew_position_before(state, crew_id, dep)
    if not flight.get("is_ferry") and crew_at != flight["origin"]:
        warnings.append({
            "code": "CREW_WRONG_STATION",
            "severity": "critical",
            "message": (
                f"Crew {crew['id']} ({crew['name']}) is at {crew_at}; "
                f"{flight['callsign']} departs {flight['origin']}. They must be "
                f"positioned there before they can operate it."
            ),
            "rule_ref": "Operational — crew positioning",
        })

    # ORO.FTL.235(a)/(b): minimum rest is "at least as long as the preceding
    # duty period, or 12h at home base / 10h away, whichever is GREATER". A
    # crew coming off a 14h duty may not report again after 12h just because
    # 12 is the headline number.
    away = flight["origin"] != crew.get("base", AIRLINE["hub"])
    floor_hr = MIN_REST_AWAY_HR if away else MIN_REST_HOME_HR
    prev_duty_hr = round(crew.get("last_duty_min", 0) / 60, 1)
    required_rest_hr = max(floor_hr, prev_duty_hr)
    # A crew who used commander's discretion may have their following rest
    # reduced — ORO.FTL.205(f) — but never below the 10h hard floor.
    if crew.get("rest_floor_next_hr"):
        required_rest_hr = max(crew["rest_floor_next_hr"], DISCRETION_MIN_REST_AFTER_HR)
    if crew["rest_hr_since_duty"] < required_rest_hr:
        basis = (
            f"the {prev_duty_hr:.1f}h duty just completed"
            if prev_duty_hr > floor_hr
            else f"the {floor_hr}h minimum {'down-route' if away else 'at home base'}"
        )
        warnings.append({
            "code": "MIN_REST",
            "severity": "critical",
            "message": (
                f"Insufficient rest. Crew {crew['id']} has had {crew['rest_hr_since_duty']:.1f}h rest; "
                f"{required_rest_hr:.1f}h required before report — set by {basis}."
            ),
            "rule_ref": "ORO.FTL.235 (Rest Periods)",
        })

    # Status
    if crew["status"] == "sick":
        warnings.append({
            "code": "STATUS_SICK",
            "severity": "critical",
            "message": f"Crew {crew['id']} is currently flagged SICK and unfit to operate.",
            "rule_ref": "MED.A.020 (Fitness to Fly)",
        })
    elif crew["status"] == "off":
        warnings.append({
            "code": "STATUS_OFF",
            "severity": "warning",
            "message": f"Crew {crew['id']} is on a scheduled day off. Assigning will incur callout cost.",
            "rule_ref": "Industrial Agreement Art. 14",
        })

    # FDP — short-haul out-and-back pairing is ONE Flight Duty Period
    pairing_id = flight.get("pairing_id")
    pairing_flights = [f for f in state["flights"] if pairing_id and f.get("pairing_id") == pairing_id]
    if not pairing_flights:
        pairing_flights = [flight]
    pairing_block = sum(pf["block_min"] for pf in pairing_flights)
    fdp_total, _sched, fdp_delay, pairing_sectors = _pairing_fdp_min(state, flight)
    projected_fdp = crew["fdp_used_min"] + fdp_total
    fdp_max, basis = _fdp_cap_for_flight(
        flight, sectors=pairing_sectors,
        acclimatised=_crew_acclimatised(state, crew, flight))
    standby_cut = _standby_fdp_reduction_min(crew)
    if standby_cut:
        fdp_max -= standby_cut
        basis += (
            f", less {standby_cut}min for home standby beyond "
            f"{STANDBY_FDP_FREE_HR}h (CS FTL.1.225)"
        )
    if projected_fdp > fdp_max:
        warnings.append({
            "code": "FDP_EXCEED",
            "severity": "critical",
            "message": (
                f"Flight Duty Period for this pairing ({pairing_sectors} sector{'s' if pairing_sectors>1 else ''}, "
                f"{pairing_block//60}h{pairing_block%60:02d}m block) would reach "
                f"{projected_fdp//60}h{projected_fdp%60:02d}m, exceeding the maximum "
                f"{fdp_max//60}h FDP applicable ({basis})."
                + (f" {fdp_delay}min of that is accumulated delay." if fdp_delay else "")
            ),
            "rule_ref": "ORO.FTL.205 / CS FTL.1.205",
        })

    # 7-day duty hours
    pairing_duty_hr = fdp_total / 60
    projected_7d = crew.get("duty_7d_hr", 0) + pairing_duty_hr
    if projected_7d > MAX_DUTY_7D_HR:
        warnings.append({
            "code": "DUTY_7D",
            "severity": "critical",
            "message": (
                f"Projected 7-day duty = {projected_7d:.1f}h, exceeds the {MAX_DUTY_7D_HR}h weekly limit. "
                f"Current accumulation: {crew.get('duty_7d_hr', 0):.1f}h."
            ),
            "rule_ref": "ORO.FTL.210(a) — 60h duty in 7 consecutive days",
        })

    # 28-day block hours (consider whole pairing)
    projected_28d = crew["block_28d_hr"] + (pairing_block / 60)
    if projected_28d > MAX_BLOCK_28D_HR:
        warnings.append({
            "code": "BLOCK_28D",
            "severity": "critical",
            "message": (
                f"Projected 28-day block hours = {projected_28d:.1f}h, exceeds {MAX_BLOCK_28D_HR}h limit."
            ),
            "rule_ref": "ORO.FTL.210(b)",
        })

    # Recurrent days free of duty — operating today adds another consecutive
    # duty day. Beyond the limit the crew is owed a statutory day off first.
    dso = crew.get("days_since_off", 0)
    if dso >= MAX_CONSECUTIVE_DUTY_DAYS:
        warnings.append({
            "code": "DAYS_OFF_REQUIRED",
            "severity": "critical",
            "message": (
                f"Crew {crew['id']} has worked {dso} consecutive duty days. A day free of "
                f"duty is required before further rostering (max {MAX_CONSECUTIVE_DUTY_DAYS})."
            ),
            "rule_ref": "ORO.FTL.235(d) — Recurrent days free of duty",
        })
    elif dso >= DAYS_OFF_WARN_AT:
        warnings.append({
            "code": "DAYS_OFF_DUE",
            "severity": "warning",
            "message": (
                f"Crew {crew['id']} is on consecutive duty day {dso}. Roster a day off within "
                f"{MAX_CONSECUTIVE_DUTY_DAYS - dso} day(s) to stay legal."
            ),
            "rule_ref": "ORO.FTL.235(d) — Recurrent days free of duty",
        })

    # Fatigue
    if crew["fatigue_score"] > 70:
        warnings.append({
            "code": "FATIGUE_HIGH",
            "severity": "warning",
            "message": (
                f"Crew fatigue score is {crew['fatigue_score']}/100. Consider FRM mitigation or alternative."
            ),
            "rule_ref": "ORO.FTL.120 (Fatigue Management)",
        })

    return warnings


# Criticals that no override reaches.
#
# A type rating is valid only for the type it was issued on (EASA FCL.740).
# There is no controller judgement that puts an A320-rated pilot in a B777 and
# no score penalty that makes it acceptable — so unlike rest, duty limits and
# days off, this is not a commercial call the player may take and pay for.
# `force` used to clear it along with everything else, which let the wrong
# type be flown for an 80-point breach. discretion_available already refused
# to cover it; force now agrees.
_UNFORCEABLE_CODES = {"TYPE_QUAL", "REF_NOT_FOUND"}


def discretion_available(state: dict, flight_id: str, crew_id: str) -> dict:
    """Whether commander's discretion can legally cover this assignment, and
    at what price. Returns `{available, cap_min, overrun_min, reportable,
    augmented, reason}`.

    Discretion covers FDP overruns and nothing else. A crew who is not type
    rated, is sick, or is in the wrong place cannot be discretion-ed into
    legality — those are not unforeseen circumstances, they are the roster
    being wrong."""
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        return {"available": False, "reason": "Flight or crew reference not found."}

    warnings = check_assignment(state, flight_id, crew_id)
    critical = [w for w in warnings if w["severity"] == "critical"]
    other = [w for w in critical if w["code"] not in ("FDP_EXCEED", "FDP_TIMEOUT")]
    if other:
        return {
            "available": False,
            "reason": (
                "Discretion covers an FDP overrun only — "
                + ", ".join(w["code"] for w in other) + " must be resolved."
            ),
        }
    if not critical:
        return {"available": False, "reason": "No FDP overrun to extend."}

    req = flight.get("required_crew", {})
    augmented = req.get("FO", 1) >= 2
    cap = DISCRETION_MAX_MIN_AUGMENTED if augmented else DISCRETION_MAX_MIN
    total, _sched, _delay, sectors = _pairing_fdp_min(state, flight)
    fdp_max, _basis = _fdp_cap_for_flight(
        flight, sectors=sectors, acclimatised=_crew_acclimatised(state, crew, flight))
    # CS FTL.1.225: home standby beyond six hours cuts the FDP that follows it.
    # check_assignment applies this; discretion must measure the overrun
    # against the same reduced cap or it licenses a duty nobody may fly.
    fdp_max -= _standby_fdp_reduction_min(crew)
    overrun = (crew.get("fdp_used_min", 0) + total) - fdp_max
    if overrun <= 0:
        return {"available": False, "cap_min": cap, "overrun_min": overrun,
                "augmented": augmented,
                "reason": "No FDP overrun to extend once the real cap is applied."}
    if overrun > cap:
        return {
            "available": False, "cap_min": cap, "overrun_min": overrun, "augmented": augmented,
            "reason": (
                f"Overrun is {overrun}min; commander's discretion is capped at "
                f"{cap}min{' (augmented crew)' if augmented else ''}."
            ),
        }
    return {
        "available": True, "cap_min": cap, "overrun_min": overrun, "augmented": augmented,
        "reportable": overrun > DISCRETION_REPORT_THRESHOLD_MIN,
        "reason": None,
    }


def assign_crew(state: dict, flight_id: str, crew_id: str, force: bool = False,
                discretion: bool = False) -> dict:
    """Assign a crew member to a flight. Returns {ok, warnings, breaches}.
    Short-haul out-and-back pairings: if this flight has siblings sharing
    `pairing_id`, the same crew is automatically rostered on the whole pairing
    (this is how real short-haul operates — crew operate out & back).
    """
    warnings = check_assignment(state, flight_id, crew_id)
    critical = [w for w in warnings if w["severity"] == "critical"]

    unforceable = [w for w in critical if w["code"] in _UNFORCEABLE_CODES]
    if unforceable:
        return {"ok": False, "warnings": warnings, "applied": False,
                "reason": unforceable[0]["message"]}

    # Commander's discretion makes an FDP overrun LEGAL rather than a breach —
    # within its cap, and at the price of a report and a shortened rest.
    disc = discretion_available(state, flight_id, crew_id) if discretion else {"available": False}
    if discretion and not disc["available"]:
        return {"ok": False, "warnings": warnings, "applied": False,
                "discretion": disc, "reason": disc.get("reason")}
    if disc["available"]:
        critical = []

    if critical and not force:
        return {"ok": False, "warnings": warnings, "applied": False}

    flight = next(f for f in state["flights"] if f["id"] == flight_id)
    crew = next(c for c in state["crew"] if c["id"] == crew_id)

    # All sectors in the same pairing — assign the crew to every sector
    pairing_id = flight.get("pairing_id")
    pairing_flights = [
        f for f in state["flights"]
        if pairing_id and f.get("pairing_id") == pairing_id
    ] or [flight]

    for pf in pairing_flights:
        if crew_id not in pf["assigned_crew_ids"]:
            pf["assigned_crew_ids"].append(crew_id)
    crew["assigned_flight_id"] = flight_id
    if crew["status"] not in ("standby", "off", "sick"):
        crew["status"] = "on_duty"

    if critical and force:
        state["kpis"]["legality_breaches"] += len(critical)
        state["kpis"]["score"] -= 80 * len(critical)

    if disc["available"]:
        # Legal, but it leaves a trail and it costs the crew tomorrow.
        crew["discretion_used"] = {
            "minutes": disc["overrun_min"], "flight_id": flight_id,
            "reportable": disc["reportable"], "at": state.get("clock"),
        }
        crew["fatigue_score"] = min(100, crew.get("fatigue_score", 0) + 12)
        # Following rest may be reduced, but never below 10h.
        crew["rest_floor_next_hr"] = DISCRETION_MIN_REST_AFTER_HR
        if disc["reportable"]:
            state["kpis"]["discretion_reports"] = state["kpis"].get("discretion_reports", 0) + 1
        state["kpis"]["discretion_used_count"] = state["kpis"].get("discretion_used_count", 0) + 1

    return {
        "ok": True,
        "warnings": warnings,
        "applied": True,
        "pairing_sectors": len(pairing_flights),
        "discretion": disc if disc["available"] else None,
    }


def unassign_crew(state: dict, flight_id: str, crew_id: str) -> dict:
    """Unassign a crew from a flight AND from any sibling sectors in the same
    pairing (short-haul out-and-back is a single duty)."""
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not flight or not crew:
        return {"ok": False}
    pairing_id = flight.get("pairing_id")
    pairing_flights = [
        f for f in state["flights"]
        if pairing_id and f.get("pairing_id") == pairing_id
    ] or [flight]
    for pf in pairing_flights:
        if crew_id in pf["assigned_crew_ids"]:
            pf["assigned_crew_ids"].remove(crew_id)
    if crew["assigned_flight_id"] in [pf["id"] for pf in pairing_flights]:
        crew["assigned_flight_id"] = None
        if crew["status"] == "on_duty":
            crew["status"] = "available"
    return {"ok": True, "pairing_sectors": len(pairing_flights)}


def roster_completeness(state: dict) -> dict:
    """How many flights have complete required crew."""
    total = len(state["flights"])
    complete = 0
    missing: list[dict] = []
    for f in state["flights"]:
        req = f["required_crew"]
        need = req["CP"] + req["FO"] + req["SC"] + req["CC"]
        have = len(f["assigned_crew_ids"])
        # Cheap counter by rank
        rank_counts = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
        for cid in f["assigned_crew_ids"]:
            c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
            if c:
                rank_counts[c["rank"]] = rank_counts.get(c["rank"], 0) + 1
        ok = all(rank_counts[r] >= req[r] for r in ("CP", "FO", "SC", "CC"))
        if ok:
            complete += 1
        else:
            missing.append({
                "flight_id": f["id"],
                "callsign": f["callsign"],
                "need": {r: max(0, req[r] - rank_counts[r]) for r in ("CP","FO","SC","CC")},
                "have": rank_counts,
                "total_have": have,
                "total_need": need,
            })
    return {"total": total, "complete": complete, "missing": missing}


# ------------------- Crew roster line / days off ------------------- #

def _today_duty_code(state: dict, crew: dict) -> str:
    """Live duty code for the current operational day (calendar 'today' cell)."""
    if crew.get("status") == "sick":
        return "SICK"
    cid = crew["id"]
    if any(cid in f["assigned_crew_ids"] for f in state["flights"]):
        return "FLT"
    st = crew.get("status")
    if st == "off":
        return "OFF"
    if st == "standby":
        return "SBY-A" if crew.get("standby_type") == STANDBY_AIRPORT else "SBY-H"
    return "AVL"   # available reserve / open


def _duty_line_for(state: dict, crew: dict) -> dict:
    """Today's duty as a roster LINE — report, off-duty, sectors, route, and
    the FDP it consumes against the cap.

    A cell that says only "FLT" tells the player nothing about the shape of the
    duty: an 05:00 four-sector day and a 14:00 single-sector day looked
    identical, even though every fatigue rule in this engine distinguishes
    them."""
    sectors = sorted(
        (f for f in state["flights"]
         if crew["id"] in f.get("assigned_crew_ids", []) and f["status"] != "cancelled"),
        key=lambda f: f["std"],
    )
    if not sectors:
        return {}
    first, last = sectors[0], sectors[-1]
    report = datetime.fromisoformat(first["std"]) - timedelta(minutes=60)
    off_duty = (datetime.fromisoformat(last["sta"])
                + timedelta(minutes=last.get("delay_min", 0) + 30))
    total, _sched, delay, count = _pairing_fdp_min(state, first)
    cap, _basis = _fdp_cap_for_flight(
        first, sectors=count, acclimatised=_crew_acclimatised(state, crew, first))
    cap -= _standby_fdp_reduction_min(crew)
    stations = [sectors[0]["origin"]] + [s["destination"] for s in sectors]
    return {
        "pairing_id": first.get("pairing_id"),
        "report_z": report.strftime("%H:%M"),
        "off_duty_z": off_duty.strftime("%H:%M"),
        "sectors": len(sectors),
        "route": "-".join(stations),
        "callsigns": [s["callsign"] for s in sectors],
        "fdp_min": total,
        "fdp_cap_min": cap,
        "fdp_delay_min": delay,
        "over_cap": total > cap,
    }


def open_time(state: dict) -> list[dict]:
    """Flying with nobody on it — the real desk's first question of the day.

    `roster_completeness` has always computed this; it was consumed only as an
    OPEN_SECTOR warning string and never as a work list you could assign from.
    Real systems call it OPEN TIME."""
    rows = []
    for m in roster_completeness(state)["missing"]:
        f = next((x for x in state["flights"] if x["id"] == m["flight_id"]), None)
        if not f or f["status"] == "cancelled":
            continue
        gaps = {r: n for r, n in m["need"].items() if n}
        if not gaps:
            continue
        rows.append({
            "flight_id": f["id"], "callsign": f["callsign"],
            "pairing_id": f.get("pairing_id"),
            "origin": f["origin"], "destination": f["destination"],
            "std": f["std"], "block_min": f["block_min"],
            "aircraft_type": f["aircraft_type"],
            "needs": gaps,
            "short_by": sum(gaps.values()),
            # Who could legally take it right now, per open rank.
            "candidates": {
                rank: [
                    {"crew_id": c["id"], "name": c["name"], "fatigue": c["fatigue_score"]}
                    for c in _legal_candidates(state, f, rank, ("available", "standby"))[:5]
                ]
                for rank in gaps
            },
        })
    rows.sort(key=lambda r: r["std"])
    return rows


def crew_roster(state: dict, past_days: int = 5, future_days: int = 4) -> dict:
    """Build the AerOPS-style crew calendar: one row per crew, one cell per day.
    Past cells come from the recorded duty_history, today is live, future cells
    show planned days off (anything else is open)."""
    day_number = state.get("day_number", 1)
    days = list(range(day_number - past_days, day_number + future_days + 1))
    base_date = datetime.fromisoformat(state["day_start"]).date()
    columns = [{
        "day": d,
        "date": (base_date + timedelta(days=d - day_number)).isoformat(),
        "is_today": d == day_number,
        "is_future": d > day_number,
        "is_past": d < day_number,
    } for d in days]
    rows = []
    for c in state["crew"]:
        hist = c.get("duty_history", [])
        planned = set(c.get("days_off_planned", []))
        dso = c.get("days_since_off", 0)
        cells = []
        for d in days:
            if d < day_number:
                offset = day_number - d            # 1 == yesterday
                code = hist[-offset] if offset <= len(hist) else None
                cells.append({"day": d, "code": code, "rel": "past"})
            elif d == day_number:
                cells.append({
                    "day": d, "code": _today_duty_code(state, c), "rel": "today",
                    **_duty_line_for(state, c),
                })
            else:
                planned_code = c.get("duty_plan", {}).get(str(d))
                cells.append({
                    "day": d,
                    "code": ("OFF" if d in planned
                             else {"SBY_APT": "SBY-A", "SBY_HOME": "SBY-H"}.get(planned_code)),
                    "rel": "future",
                    "planned_off": d in planned,
                    "planned_duty": planned_code,
                })
        rows.append({
            "crew_id": c["id"],
            "name": c["name"],
            "rank": c["rank"],
            "rank_title": c.get("rank_title", ""),
            "base": c.get("base", "LHR"),
            "qualifications": c.get("qualifications", []),
            "status": c.get("status"),
            "days_since_off": dso,
            "fatigue_score": c.get("fatigue_score", 0),
            "due_off": dso >= DAYS_OFF_WARN_AT,
            "at_limit": dso >= MAX_CONSECUTIVE_DUTY_DAYS,
            "cells": cells,
        })
    return {
        "day_number": day_number,
        "days": days,
        "columns": columns,
        "past_days": past_days,
        "future_days": future_days,
        "max_consecutive_duty_days": MAX_CONSECUTIVE_DUTY_DAYS,
        "warn_at": DAYS_OFF_WARN_AT,
        "crew": rows,
    }


# Duty a controller can PLAN onto a future day. Days off were the only thing
# the planner could write, which left the standby bank — the thing that decides
# whether tomorrow's sickness is survivable — entirely to a random draw.
PLANNABLE_DUTIES = {
    "OFF": "Day off (free of duty)",
    "SBY_APT": "Airport standby — 30min to report, but the duty clock is running",
    "SBY_HOME": "Home standby — 90min to report, fresh, erodes FDP past 6h",
    "CLEAR": "Clear any plan; the day is open again",
}


def plan_duty(state: dict, crew_ids: list[str], days: list[int], code: str) -> dict:
    """Write a planned duty onto one or more crew across one or more days.

    Bulk by design: rostering a base means moving groups of people, and doing
    it one cell at a time is not planning, it is data entry."""
    if code not in PLANNABLE_DUTIES:
        return {"ok": False, "error": "unknown_duty", "allowed": sorted(PLANNABLE_DUTIES)}
    day_number = state.get("day_number", 1)
    applied, skipped = [], []

    for crew_id in crew_ids:
        crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
        if not crew:
            skipped.append({"crew_id": crew_id, "reason": "crew_not_found"})
            continue
        plan = crew.setdefault("duty_plan", {})
        planned_off = crew.setdefault("days_off_planned", [])
        for day in days:
            if day < day_number:
                skipped.append({"crew_id": crew_id, "day": day, "reason": "cannot_change_past"})
                continue
            if day == day_number and state.get("phase") != "ROSTER":
                skipped.append({"crew_id": crew_id, "day": day, "reason": "day_in_progress"})
                continue

            if code == "CLEAR":
                plan.pop(str(day), None)
                if day in planned_off:
                    planned_off.remove(day)
                if day == day_number and crew["status"] in ("off", "standby"):
                    crew["status"] = "available"
            else:
                plan[str(day)] = code
                # days_off_planned stays the authoritative OFF list: the day
                # rollover, the consecutive-duty counter and roster_completeness
                # all read it, and they should not have to learn a second shape.
                if code == "OFF" and day not in planned_off:
                    planned_off.append(day)
                elif code != "OFF" and day in planned_off:
                    planned_off.remove(day)
                if day == day_number:
                    _apply_planned_duty_now(state, crew, code)
            applied.append({"crew_id": crew_id, "day": day, "code": code})

    return {"ok": True, "applied": applied, "skipped": skipped,
            "crew_count": len({a["crew_id"] for a in applied}),
            "day_count": len({a["day"] for a in applied})}


def _apply_planned_duty_now(state: dict, crew: dict, code: str) -> None:
    """Put a planned duty into effect for the current day (ROSTER phase only)."""
    if code == "OFF":
        for f in state["flights"]:
            if crew["id"] in f["assigned_crew_ids"]:
                f["assigned_crew_ids"].remove(crew["id"])
        crew["assigned_flight_id"] = None
        crew["status"] = "off"
    elif code in ("SBY_APT", "SBY_HOME"):
        for f in state["flights"]:
            if crew["id"] in f["assigned_crew_ids"]:
                f["assigned_crew_ids"].remove(crew["id"])
        crew["assigned_flight_id"] = None
        crew["status"] = "standby"
        crew["standby_type"] = STANDBY_AIRPORT if code == "SBY_APT" else STANDBY_HOME
        crew["standby_elapsed_hr"] = 0.0


def set_day_off(state: dict, crew_id: str, day: int, off: bool = True) -> dict:
    """Toggle a day off for a crew member. Future days are queued in
    days_off_planned (honoured when the sim rolls into that day). The current day
    can only be changed during the ROSTER phase (before the day starts)."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not crew:
        return {"ok": False, "error": "crew_not_found"}
    day_number = state.get("day_number", 1)
    if day < day_number:
        return {"ok": False, "error": "cannot_change_past"}
    planned = crew.setdefault("days_off_planned", [])

    if day == day_number:
        if state.get("phase") != "ROSTER":
            return {"ok": False, "error": "day_in_progress"}
        if off:
            for f in state["flights"]:
                if crew_id in f["assigned_crew_ids"]:
                    f["assigned_crew_ids"].remove(crew_id)
            crew["assigned_flight_id"] = None
            crew["status"] = "off"
        elif crew["status"] == "off":
            crew["status"] = "available"
        return {
            "ok": True, "crew_id": crew_id, "day": day, "off": off,
            "status": crew["status"], "days_off_planned": planned,
        }

    # Future day
    if off and day not in planned:
        planned.append(day)
        planned.sort()
    elif not off and day in planned:
        planned.remove(day)
    return {
        "ok": True, "crew_id": crew_id, "day": day, "off": off,
        "days_off_planned": planned,
    }


# ------------------- Auto-roster ------------------- #

def auto_roster(state: dict) -> dict:
    """Greedy auto-assignment: fill all crew gaps without legality violations.
    Processes each flight, each rank gap, picking the lowest-fatigue qualified
    available/standby crew that passes a full legality check.
    Returns counts of assigned slots, skipped slots, and which flights changed.
    """
    assigned_total = 0
    skipped_total = 0
    flights_touched: list[str] = []

    # Collect pairing ids already processed so we don't double-count sibling sectors
    processed_pairings: set[str] = set()

    for flight in state["flights"]:
        pid = flight.get("pairing_id")
        if pid and pid in processed_pairings:
            continue

        req = flight["required_crew"]
        type_q = req["type_qual"]

        # Aggregate assigned ranks across all pairing sectors
        pairing_flights = (
            [f for f in state["flights"] if f.get("pairing_id") == pid]
            if pid else [flight]
        )
        rank_counts: dict[str, int] = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
        all_assigned_ids: set[str] = set()
        for pf in pairing_flights:
            for cid in pf["assigned_crew_ids"]:
                all_assigned_ids.add(cid)
        for cid in all_assigned_ids:
            c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
            if c and c["rank"] in rank_counts:
                rank_counts[c["rank"]] += 1

        flight_changed = False
        for rank in ("CP", "FO", "SC", "CC"):
            gap = req[rank] - rank_counts[rank]
            for _ in range(gap):
                candidates = [
                    c for c in state["crew"]
                    if c["rank"] == rank
                    and type_q in c["qualifications"]
                    and c["status"] in ("available", "standby")
                    and c["id"] not in all_assigned_ids
                ]
                # Prefer lowest fatigue, then most rested
                candidates.sort(key=lambda c: (c["fatigue_score"], -c["rest_hr_since_duty"]))

                placed = False
                for candidate in candidates:
                    warnings = check_assignment(state, flight["id"], candidate["id"])
                    if not any(w["severity"] == "critical" for w in warnings):
                        # Assign across all pairing sectors
                        for pf in pairing_flights:
                            if candidate["id"] not in pf["assigned_crew_ids"]:
                                pf["assigned_crew_ids"].append(candidate["id"])
                        candidate["assigned_flight_id"] = flight["id"]
                        if candidate["status"] not in ("off", "sick"):
                            candidate["status"] = "on_duty"
                        all_assigned_ids.add(candidate["id"])
                        rank_counts[rank] += 1
                        assigned_total += 1
                        flight_changed = True
                        placed = True
                        break
                if not placed:
                    skipped_total += 1

        if flight_changed and flight["callsign"] not in flights_touched:
            flights_touched.append(flight["callsign"])
        if pid:
            processed_pairings.add(pid)

    return {
        "assigned": assigned_total,
        "skipped": skipped_total,
        "flights_touched": flights_touched,
    }


# ------------------- Aircraft (fleet) control ------------------- #
# The real-world "Aircraft Movement Control" desk: which tail flies which
# rotation. A rotation is a pairing (all sectors sharing a pairing_id — an
# out-and-back for short-haul, a single sector for long-haul). Every sector of
# a pairing is always operated by the SAME tail, so assignment happens at the
# pairing level, mirroring how crew are rostered per pairing.

_AC_ACTIVE_STATUSES = ("scheduled", "delayed", "boarding")


def _pairing_sectors(state: dict, pairing_id: str) -> list[dict]:
    """All sector flights of a pairing, in schedule order."""
    return sorted(
        (f for f in state["flights"] if f.get("pairing_id") == pairing_id),
        key=lambda f: f["std"],
    )


def _pairing_window(sectors: list[dict]) -> tuple[datetime, datetime]:
    """(earliest effective departure, latest effective arrival) for a pairing,
    including any delay already applied — the ground-to-ground span the tail is
    committed for."""
    first = min(datetime.fromisoformat(s["std"]) + timedelta(minutes=s.get("delay_min", 0))
                for s in sectors)
    last = max(datetime.fromisoformat(s["sta"]) + timedelta(minutes=s.get("delay_min", 0))
               for s in sectors)
    return first, last


def _pairing_route_label(sectors: list[dict]) -> str:
    """Human route summary, e.g. 'LHR-BCN-LHR' or 'LHR-SIN'."""
    stops = [sectors[0]["origin"]] + [s["destination"] for s in sectors]
    return "-".join(stops)


def _aircraft_position_before(state: dict, reg: str, before_dt: datetime, exclude_pairing_id: str | None = None) -> str:
    """Airport where tail `reg` is expected to be immediately before `before_dt`,
    based on its OTHER scheduled flights today. A tail with no earlier flight
    (a fresh spare, or this being its first sector of the day) is assumed to
    start the day at the hub — matching how every generated rotation departs
    from the hub, and how spares start the day parked there on stand."""
    flights_for_reg = sorted(
        (f for f in state["flights"]
         if f.get("aircraft_reg") == reg and f["status"] != "cancelled"
         and f.get("pairing_id") != exclude_pairing_id),
        key=lambda f: f["std"],
    )
    if not flights_for_reg:
        return AIRLINE["hub"]
    completed = [
        f for f in flights_for_reg
        if datetime.fromisoformat(f["sta"]) + timedelta(minutes=f.get("delay_min", 0)) <= before_dt
    ]
    if completed:
        completed.sort(key=lambda f: datetime.fromisoformat(f["sta"]) + timedelta(minutes=f.get("delay_min", 0)))
        return completed[-1]["destination"]
    return flights_for_reg[0]["origin"]


def _crew_end_of_day_station(state: dict, crew: dict) -> str:
    """Where a crew member is standing when the day ends — the destination of
    the last thing that moved them, else wherever they already were."""
    moves = []
    for f in state["flights"]:
        # Anything that has departed will end up at its destination, whether or
        # not it has landed by the time the day rolls over — a 13-hour sector
        # that is still airborne at midnight still leaves its crew in Singapore.
        if crew["id"] in f.get("assigned_crew_ids", []) and f["status"] in (
            "landed", "airborne", "diverted",
        ):
            moves.append((f["sta"], f["destination"]))
    for pos in crew.get("positioning", []):
        moves.append((pos["arrives"], pos["to"]))
    if not moves:
        return crew.get("station") or crew.get("base", AIRLINE["hub"])
    moves.sort()
    return moves[-1][1]


def _crew_position_before(state: dict, crew_id: str, before_dt: datetime,
                          exclude_pairing_id: str | None = None) -> str:
    """Airport where `crew_id` is expected to be immediately before
    `before_dt`, from their OTHER flying today. Mirrors
    `_aircraft_position_before` — crew are as physically located as aircraft
    are, and from day 2 the schedule has real outstation departures for them
    to be stranded away from."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    # Start from where they actually are, which after an overnight is not
    # necessarily home base.
    base = (crew.get("station") or crew.get("base", AIRLINE["hub"])) if crew else AIRLINE["hub"]
    sectors = sorted(
        (f for f in state["flights"]
         if crew_id in f.get("assigned_crew_ids", []) and f["status"] != "cancelled"
         and f.get("pairing_id") != exclude_pairing_id),
        key=lambda f: f["std"],
    )
    moves = [
        (datetime.fromisoformat(f["sta"]) + timedelta(minutes=f.get("delay_min", 0)),
         f["destination"])
        for f in sectors
    ]
    # Positioning legs move the crew just as operated ones do — they are flown
    # as passengers, but they still end up somewhere else.
    if crew:
        for pos in crew.get("positioning", []):
            moves.append((datetime.fromisoformat(pos["arrives"]), pos["to"]))
    completed = [m for m in moves if m[0] <= before_dt]
    if completed:
        completed.sort(key=lambda m: m[0])
        return completed[-1][1]
    return base


# --- Positioning (deadhead), ORO.FTL.215 ------------------------------------
# Crew flown as passengers to where they are needed. Sits ABOVE standby callout
# in the real cost-efficient recovery hierarchy: cheaper than holding reserve,
# dearer than swapping someone already on shift. Positioning after report but
# before operating counts as FDP but NOT as a sector.
# https://understandingeasa2016ftl.wordpress.com/easa-ftl/oro-ftl/oro-ftl-215-positioning/
DEADHEAD_SEAT_USD = 450          # a seat on our own metal, revenue foregone
DEADHEAD_HANDLING_USD = 900      # rebooking, ground transport, admin
DEADHEAD_REPORT_BUFFER_MIN = 60  # must land this long before the duty reports

# --- Crew accommodation (HOTAC) --------------------------------------------
# ORO.FTL.105 defines home base as the place where the operator is NOT
# responsible for accommodating the crew — so away from base, it is. Suitable
# accommodation means a separate quiet room per crew member with a bed,
# controllable temperature and light, and access to food and drink. The
# industry calls the whole package HOTAC: hotel plus ground transport.
# https://regulatorylibrary.caa.co.uk/965-2012/Content/Document%20Structure/03%20ORO/2%20Regs/05040_ORO.FTL.105_Definitions.htm
CREW_HOTEL_USD = 180             # room, per crew member per night
CREW_TRANSPORT_USD = 45          # airport-hotel-airport ground transport
CREW_PERDIEM_USD = 65            # subsistence allowance away from base

# --- Cross-type (sub-fleet) substitution -----------------------------------
# Putting an off-type tail on a rotation is routine IROPS recovery, not a
# forbidden act — the binding constraints are physical (range, stand size) and
# human (type ratings), never the paperwork. UPGAUGE ONLY here: a bigger
# aircraft covering a smaller rotation. Downgauging would mean offloading
# passengers into UK261 Art. 4 denied-boarding territory, and in this route
# network it cannot arise anyway — the A320's 6h max block cannot reach any
# long-haul destination (shortest is LHR-DXB at 6h50).
#
# ICAO Annex 14 aerodrome reference code: C is <36m wingspan (A320), E is
# <65m (A350, B777). Operating a higher code letter at a lower-code aerodrome
# needs prior approval — it is not a same-day OCC decision.
# https://skybrary.aero/articles/icao-aerodrome-reference-code
AERODROME_CODE = {"A320": "C", "A350": "E", "B777": "E"}
# Stations that can take a code-E aircraft on a stand at short notice: the hub
# and the long-haul outstations, plus the largest European fields. Judgement
# from what each station realistically handles, not a verified stand inventory.
CODE_E_STATIONS = frozenset({"LHR", "JFK", "DXB", "SIN", "HKG", "LAX",
                             "CDG", "FRA", "AMS", "MAD", "FCO"})
# Stand re-plan, re-catering, loading and weight-and-balance redo, cabin crew
# recall. Judgement figure in the same family as FERRY_DISPATCH_FEE_USD.
SUBSTITUTION_SETUP_USD = 4000

# --- AOG: aircraft on ground ----------------------------------------------
# A major technical defect physically stops the aeroplane. It is not a
# scheduling inconvenience that can be reassigned around by pointing the
# rotation back at the same tail — the tail is broken. Rectification takes
# hours, and if it is not finished by the end of the day the overnight shift
# gets it (the same shape as MEL rectification).
AOG_REPAIR_MIN_LOW = 240         # a defect line maintenance can clear
AOG_REPAIR_MIN_HIGH = 600        # one that needs a part flown in


def _positioning_leg(state: dict, crew_id: str, to_station: str,
                     arrive_by: datetime | None = None,
                     exclude_flight_id: str | None = None) -> dict | None:
    """The earliest sector that could carry `crew_id` to `to_station`, or None.

    The general form of `_deadhead_plan`: that one asks "can I get them to a
    flight in time to operate it", this one asks "can I get them to a station
    at all" — which is the question the disposition desk asks when sending a
    stranded crew home rather than onto a specific duty."""
    now = datetime.fromisoformat(state["clock"])
    origin = _crew_position_before(state, crew_id, now)
    if origin == to_station:
        return None                       # already there

    best = None
    for f in state["flights"]:
        if f["id"] == exclude_flight_id or f["status"] in ("cancelled", "landed"):
            continue
        if f["origin"] != origin or f["destination"] != to_station:
            continue
        f_dep = datetime.fromisoformat(f["std"]) + timedelta(minutes=f.get("delay_min", 0))
        f_arr = datetime.fromisoformat(f["sta"]) + timedelta(minutes=f.get("delay_min", 0))
        if f_dep < now:
            continue
        if arrive_by is not None and f_arr > arrive_by:
            continue
        if best is None or f_arr < best["arrives"]:
            best = {
                "carrier_flight_id": f["id"], "carrier_callsign": f["callsign"],
                "from": origin, "to": to_station,
                "departs": f_dep.isoformat(), "arrives": f_arr,
                "block_min": f["block_min"],
            }
    if best:
        best["arrives"] = best["arrives"].isoformat()
    return best


def _deadhead_plan(state: dict, flight: dict, crew_id: str) -> dict | None:
    """The sector that could carry `crew_id` to `flight`'s departure station in
    time to operate it, or None if nothing connects.

    Read-only. This is what turns "can I get a crew to MAD by 16:40" from a
    button into a question with an answer."""
    dep = datetime.fromisoformat(flight["std"]) + timedelta(minutes=flight.get("delay_min", 0))
    latest_arrival = dep - timedelta(minutes=DEADHEAD_REPORT_BUFFER_MIN)
    origin = _crew_position_before(state, crew_id, dep)
    if origin == flight["origin"]:
        return None                       # already there; nothing to position

    now = datetime.fromisoformat(state["clock"])
    best = None
    for f in state["flights"]:
        if f["id"] == flight["id"] or f["status"] in ("cancelled", "landed"):
            continue
        if f["origin"] != origin or f["destination"] != flight["origin"]:
            continue
        f_dep = datetime.fromisoformat(f["std"]) + timedelta(minutes=f.get("delay_min", 0))
        f_arr = datetime.fromisoformat(f["sta"]) + timedelta(minutes=f.get("delay_min", 0))
        if f_dep < now or f_arr > latest_arrival:
            continue
        if best is None or f_arr < best["arrives"]:
            best = {
                "carrier_flight_id": f["id"], "carrier_callsign": f["callsign"],
                "from": origin, "to": flight["origin"],
                "departs": f_dep.isoformat(), "arrives": f_arr,
                "block_min": f["block_min"],
            }
    if best:
        best["arrives"] = best["arrives"].isoformat()
    return best


def check_deadhead(state: dict, flight_id: str, crew_id: str | None = None) -> list[dict]:
    """Legality of positioning a crew onto `flight_id`. Same `check_*`
    contract as everything else."""
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    if not flight:
        return [{"code": "REF_NOT_FOUND", "severity": "critical",
                 "message": "Flight reference not found.", "rule_ref": "INTERNAL"}]

    crew = None
    if crew_id:
        crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    else:
        crew = _find_recovery_crew(state, flight, ("available", "standby"),
                                   ignore_position=True)
    if not crew:
        return [{
            "code": "DH_NO_CREW", "severity": "critical",
            "message": (
                f"No legal crew rated {flight['required_crew']['type_qual']} available to "
                f"position — positioning moves a crew, it does not create one."
            ),
            "rule_ref": "Operational — crew availability",
        }]

    plan = _deadhead_plan(state, flight, crew["id"])
    if plan is None:
        at = _crew_position_before(
            state, crew["id"], datetime.fromisoformat(flight["std"]))
        if at == flight["origin"]:
            return []                     # already in position — nothing to do
        return [{
            "code": "DH_NO_CONNECTION", "severity": "critical",
            "message": (
                f"No sector gets {crew['id']} from {at} to {flight['origin']} at least "
                f"{DEADHEAD_REPORT_BUFFER_MIN}min before {flight['callsign']} reports."
            ),
            "rule_ref": "Operational — positioning connection",
        }]
    return []


def preview_deadhead(state: dict, flight_id: str, crew_id: str | None = None) -> dict:
    """Read-only what-if for positioning a crew: who, on what, and the bill."""
    warnings = check_deadhead(state, flight_id, crew_id)
    has_critical = any(w["severity"] == "critical" for w in warnings)
    flight = next((f for f in state["flights"] if f["id"] == flight_id), None)
    if has_critical or not flight:
        return {"warnings": warnings, "has_critical": has_critical,
                "needs_positioning": False, "cost_usd": 0, "plan": None, "crew": None}

    crew = (next((c for c in state["crew"] if c["id"] == crew_id), None) if crew_id
            else _find_recovery_crew(state, flight, ("available", "standby"),
                                     ignore_position=True))
    plan = _deadhead_plan(state, flight, crew["id"]) if crew else None
    if plan is None:
        return {"warnings": warnings, "has_critical": False, "needs_positioning": False,
                "cost_usd": 0, "plan": None,
                "crew": {"id": crew["id"], "name": crew["name"], "rank": crew["rank"]} if crew else None}
    return {
        "warnings": warnings, "has_critical": False, "needs_positioning": True,
        "cost_usd": DEADHEAD_SEAT_USD + DEADHEAD_HANDLING_USD,
        "plan": plan,
        "crew": {"id": crew["id"], "name": crew["name"], "rank": crew["rank"]},
    }


def _ground_aircraft(state: dict, reg: str, reason: str, at_iso: str) -> dict | None:
    """Put a tail on the ground until maintenance clears it."""
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if ac is None:
        return None
    repair_min = random.randint(AOG_REPAIR_MIN_LOW, AOG_REPAIR_MIN_HIGH)
    ac["aog"] = {
        "reason": reason,
        "since": at_iso,
        "serviceable_at": _add_minutes_to_clock(at_iso, repair_min),
        "repair_min": repair_min,
    }
    return ac["aog"]


def _is_aog(ac: dict, clock_iso: str | None = None) -> bool:
    """Whether this tail is currently unserviceable."""
    aog = ac.get("aog")
    if not aog:
        return False
    if clock_iso is None:
        return True
    return datetime.fromisoformat(clock_iso) < datetime.fromisoformat(aog["serviceable_at"])


def _aog_warning(ac: dict, clock_iso: str) -> dict | None:
    """The house warning for dispatching a broken aeroplane, or None."""
    if not _is_aog(ac, clock_iso):
        return None
    aog = ac["aog"]
    eta = datetime.fromisoformat(aog["serviceable_at"]).strftime("%H:%MZ")
    return {
        "code": "AC_GROUNDED", "severity": "critical",
        "message": (
            f"{ac['reg']} is AOG — {aog['reason']} Maintenance estimate {eta}. "
            f"It cannot operate anything until it is fixed."
        ),
        "rule_ref": "Operational — aircraft unserviceable",
    }


def release_serviceable_aircraft(state: dict) -> list[str]:
    """Clear any AOG whose repair estimate has passed. Returns the tails that
    came back on line."""
    released = []
    for ac in state.get("fleet", FLEET):
        if ac.get("aog") and not _is_aog(ac, state.get("clock")):
            ac.pop("aog", None)
            released.append(ac["reg"])
    return released


def check_substitution(state: dict, pairing_id: str, reg: str) -> list[dict]:
    """Legality of covering `pairing_id` with an OFF-TYPE tail.

    This is check_aircraft_assignment with the type gate replaced rather than
    removed: AC_TYPE_MISMATCH becomes a priced option, and the constraints that
    are genuinely physical take its place. Upgauge only — a smaller aircraft
    cannot absorb a bigger one's passengers, and in this network it could not
    reach the destination either."""
    warnings = [w for w in check_aircraft_assignment(state, pairing_id, reg)
                if w["code"] != "AC_TYPE_MISMATCH"]
    sectors = _pairing_sectors(state, pairing_id)
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if not sectors or not ac:
        return warnings

    active = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]
    if not active:
        return warnings
    pairing_type = active[0]["aircraft_type"]
    if ac["type"] == pairing_type:
        warnings.append({
            "code": "AC_SAME_TYPE", "severity": "warning",
            "message": f"{reg} is already the right type — use a normal reassignment.",
            "rule_ref": "Operational",
        })
        return warnings

    sub_seats = AIRCRAFT_TYPES.get(ac["type"], {}).get("seats", 0)
    orig_seats = AIRCRAFT_TYPES.get(pairing_type, {}).get("seats", 0)
    if sub_seats < orig_seats:
        warnings.append({
            "code": "AC_DOWNGAUGE_UNSUPPORTED", "severity": "critical",
            "message": (
                f"{reg} ({ac['type']}, {sub_seats} seats) is smaller than the "
                f"{pairing_type} ({orig_seats}) this rotation needs. Downgauging means "
                f"offloading passengers — not offered."
            ),
            "rule_ref": "Operational — capacity",
        })

    # Range. max_block_hr was defined and referenced nowhere until now; this is
    # what stops an A320 being sent to Singapore.
    max_block = AIRCRAFT_TYPES.get(ac["type"], {}).get("max_block_hr", 0) * 60
    longest = max((s["block_min"] for s in active), default=0)
    if longest > max_block:
        warnings.append({
            "code": "AC_RANGE_INSUFFICIENT", "severity": "critical",
            "message": (
                f"{reg} ({ac['type']}) tops out at {max_block // 60}h block; the longest "
                f"sector on this rotation is {longest // 60}h{longest % 60:02d}m."
            ),
            "rule_ref": "Aircraft performance — max block",
        })

    # Stand and runway compatibility at every station the rotation touches.
    if AERODROME_CODE.get(ac["type"]) == "E":
        stations = {s["origin"] for s in active} | {s["destination"] for s in active}
        blocked = sorted(stations - CODE_E_STATIONS)
        if blocked:
            warnings.append({
                "code": "AC_STAND_INCOMPATIBLE", "severity": "critical",
                "message": (
                    f"{reg} is an ICAO code-E aircraft; {', '.join(blocked)} cannot take one "
                    f"on a stand at short notice."
                ),
                "rule_ref": "ICAO Annex 14 aerodrome reference code",
            })
    return warnings


def _substitution_crew_impact(state: dict, pairing_id: str, new_type: str) -> dict:
    """Who falls off the rotation if it becomes `new_type`, and what opens up.

    The aircraft is the easy part of an upgauge. Only 3 of 179 crew hold more
    than one type rating, so a substitution generally invalidates the entire
    rostered crew and demands a bigger complement than the one it just lost."""
    active = [s for s in _pairing_sectors(state, pairing_id)
              if s["status"] in _AC_ACTIVE_STATUSES]
    stood_down, open_ranks = [], {}
    for s in active:
        need = _required_crew_for(new_type, s["block_min"])
        for cid in s.get("assigned_crew_ids", []):
            c = next((x for x in state["crew"] if x["id"] == cid), None)
            if c and new_type not in c["qualifications"] and cid not in stood_down:
                stood_down.append(cid)
        for rank in ("CP", "FO", "SC", "CC"):
            open_ranks[rank] = max(open_ranks.get(rank, 0), need.get(rank, 0))
    rated = {
        rank: sum(1 for c in state["crew"]
                  if c["rank"] == rank and new_type in c["qualifications"]
                  and c["status"] in ("available", "standby"))
        for rank in ("CP", "FO", "SC", "CC")
    }
    return {
        "stood_down": stood_down,
        "open_ranks": open_ranks,
        "rated_available": rated,
        "crewable": all(rated[r] >= open_ranks.get(r, 0) for r in open_ranks),
    }


def preview_substitute_aircraft(state: dict, pairing_id: str, reg: str) -> dict:
    """Read-only price for covering a rotation with an off-type tail."""
    warnings = check_substitution(state, pairing_id, reg)
    has_critical = any(w["severity"] == "critical" for w in warnings)
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    active = [s for s in _pairing_sectors(state, pairing_id)
              if s["status"] in _AC_ACTIVE_STATUSES]
    if has_critical or not ac or not active:
        return {"warnings": warnings, "has_critical": has_critical,
                "cost_usd": 0, "crew_impact": None}

    orig_type = active[0]["aircraft_type"]
    # Operating-cost delta, from the per-minute rates the ferry lever already
    # uses. MIT Airline Data Project puts widebody:narrowbody block-hour cost
    # at ~1.9x; our 2.4-2.7x is in the right band, slightly steep.
    rate_sub = FERRY_COST_PER_MIN_USD.get(ac["type"], 15)
    rate_orig = FERRY_COST_PER_MIN_USD.get(orig_type, 15)
    block = sum(s["block_min"] for s in active)
    delta = max(0, block * (rate_sub - rate_orig))
    return {
        "warnings": warnings, "has_critical": False,
        "cost_usd": SUBSTITUTION_SETUP_USD + delta,
        "setup_usd": SUBSTITUTION_SETUP_USD,
        "block_cost_delta_usd": delta,
        "from_type": orig_type, "to_type": ac["type"],
        "seats_from": AIRCRAFT_TYPES.get(orig_type, {}).get("seats"),
        "seats_to": AIRCRAFT_TYPES.get(ac["type"], {}).get("seats"),
        "crew_impact": _substitution_crew_impact(state, pairing_id, ac["type"]),
    }


def substitute_aircraft(state: dict, pairing_id: str, reg: str) -> dict:
    """Cover a rotation with an off-type tail. Upgauge only."""
    warnings = check_substitution(state, pairing_id, reg)
    if any(w["severity"] == "critical" for w in warnings):
        return {"ok": False, "applied": False, "warnings": warnings,
                "pairing_id": pairing_id, "reg": reg}

    pv = preview_substitute_aircraft(state, pairing_id, reg)
    ac = next(a for a in state.get("fleet", FLEET) if a["reg"] == reg)
    active = [s for s in _pairing_sectors(state, pairing_id)
              if s["status"] in _AC_ACTIVE_STATUSES]
    inc = _pending_aircraft_decision_incident(state, pairing_id)
    grade = _grade_aircraft_decision(state, pairing_id, reg) if inc else None

    previous_reg = active[0]["aircraft_reg"]
    previous_type = active[0]["aircraft_type"]
    stood_down = pv["crew_impact"]["stood_down"]
    for s in active:
        s["aircraft_reg"] = reg
        s["aircraft_type"] = ac["type"]
        # The complement is sized off the new type's certified seating
        # (ORO.CC.100), not off how many passengers happen to be booked.
        s["required_crew"] = _required_crew_for(ac["type"], s["block_min"])
        for cid in list(s.get("assigned_crew_ids", [])):
            if cid in stood_down:
                s["assigned_crew_ids"].remove(cid)
    for cid in stood_down:
        c = next((x for x in state["crew"] if x["id"] == cid), None)
        if c:
            c["assigned_flight_id"] = None
            if c["status"] == "on_duty":
                c["status"] = "available"

    state["kpis"]["cost_usd"] += pv["cost_usd"]
    state["kpis"]["substitutions"] = state["kpis"].get("substitutions", 0) + 1
    reset_reactionary_delays(state)
    _log_cascade(state, propagate_reactionary_delays(state), "substitution", pairing_id)
    _recompute_kpis(state)

    result = {
        "ok": True, "applied": True, "warnings": warnings,
        "pairing_id": pairing_id, "reg": reg,
        "previous_reg": previous_reg, "from_type": previous_type, "to_type": ac["type"],
        "cost_usd": pv["cost_usd"], "stood_down_crew_ids": stood_down,
        "open_ranks": pv["crew_impact"]["open_ranks"], "kpis": state["kpis"],
    }
    if inc:
        inc["status"] = "resolved"
        inc["resolution"] = "aircraft_control_substitute"
        inc["resolution_label"] = f"Substituted {reg} ({ac['type']}) via Aircraft Control"
        inc["resolution_note"] = (
            f"{previous_type} rotation covered by {reg} ({ac['type']}); "
            f"{len(stood_down)} crew stood down as not type-rated. "
            f"Cost: ${pv['cost_usd']:,}."
        )
        inc["resolved_at"] = state["clock"]
        inc["decision_grade"] = grade
        state["decisions_log"].append({
            "ts": state["clock"], "incident_id": inc["id"],
            "action": "aircraft_control_substitute", "cost_usd": pv["cost_usd"],
            "otp_hit": 0, "flight_callsign": inc.get("flight_callsign"),
            "incident_type": inc.get("type"),
            "verdict": (grade or {}).get("verdict"),
        })
        result["incident_resolved"] = inc["id"]
        result["decision_grade"] = grade
    return result


def check_aircraft_assignment(state: dict, pairing_id: str, reg: str) -> list[dict]:
    """Legality of putting tail `reg` on a pairing. Aircraft constraints are
    HARD (a physical aircraft cannot be the wrong type, be in two places, or
    un-fly a sector already underway) — there is no override, unlike crew."""
    warnings: list[dict] = []
    sectors = _pairing_sectors(state, pairing_id)
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if not sectors or not ac:
        return [{
            "code": "REF_NOT_FOUND", "severity": "critical",
            "message": "Aircraft or rotation reference not found.", "rule_ref": "INTERNAL",
        }]

    aog = _aog_warning(ac, state.get("clock"))
    if aog:
        warnings.append(aog)

    expired_mel = [m for m in ac.get("mel_items", []) if m.get("expired")]
    if expired_mel:
        cats = ", ".join(f"Cat {m['category']}" for m in expired_mel)
        warnings.append({
            "code": "AC_MEL_EXPIRED", "severity": "critical",
            "message": (
                f"{reg} has a deferred defect past its MEL limit ({cats}) — "
                f"grounded until Maintenance Control clears it. Cannot dispatch."
            ),
            "rule_ref": "MEL deferral limit exceeded",
        })

    # Sectors already underway or finished keep whatever tail actually flew
    # them — a reassignment can only ever move the REMAINING sectors of a
    # pairing. This matters most for an out-and-back where the outbound has
    # already landed and only the return leg still needs a tail (e.g. after
    # the original aircraft goes tech mid-day): the completed leg must not
    # block, or retroactively change tail on, the leg that's still ahead.
    active_sectors = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]
    pairing_type = (active_sectors or sectors)[0]["aircraft_type"]
    if ac["type"] != pairing_type:
        warnings.append({
            "code": "AC_TYPE_MISMATCH", "severity": "critical",
            "message": (
                f"{reg} is a {ac['type']}; this rotation needs a {pairing_type}. "
                f"Crew type-ratings and gate/route planning are type-specific."
            ),
            "rule_ref": "Fleet / type compatibility",
        })

    # Only a hard block when NOTHING is left to reassign — a pairing with at
    # least one still-active sector is a legitimate mid-rotation tail swap.
    if not active_sectors:
        departed = sectors[-1]
        warnings.append({
            "code": "AC_DEPARTED", "severity": "critical",
            "message": (
                f"{departed['callsign']} is already {departed['status']} — "
                f"the rotation is underway and cannot be reassigned to another tail."
            ),
            "rule_ref": "Operational — sector in progress",
        })

    # Position + double-booking checks only make sense once the type matches
    # and there's an active sector left to actually place the tail on.
    if ac["type"] == pairing_type and active_sectors:
        win_start, win_end = _pairing_window(active_sectors)

        # Position: the tail must actually be at the (remaining) rotation's
        # departure station. An idle/spare tail sitting at the hub can't
        # operate a rotation that departs from an outstation (e.g. a
        # night-stopped long-haul aircraft's return leg, or a return leg
        # whose outbound already landed elsewhere).
        pairing_origin = active_sectors[0]["origin"]
        position = _aircraft_position_before(state, reg, win_start, exclude_pairing_id=pairing_id)
        if position != pairing_origin:
            warnings.append({
                "code": "AC_WRONG_STATION", "severity": "critical",
                "message": (
                    f"{reg} is at {position}, not {pairing_origin} — it cannot operate "
                    f"a rotation departing from a station it isn't at."
                ),
                "rule_ref": "Operational — aircraft position",
            })

        # Double-booking: the tail can't be committed to an overlapping rotation.
        turn = timedelta(minutes=MIN_TURNAROUND_MIN)
        other_pairings: dict[str, list[dict]] = {}
        for f in state["flights"]:
            opid = f.get("pairing_id")
            if opid and opid != pairing_id and f["aircraft_reg"] == reg \
                    and f["status"] != "cancelled":
                other_pairings.setdefault(opid, []).append(f)
        for opid, osecs in other_pairings.items():
            o_start, o_end = _pairing_window(osecs)
            # Conflict unless one finishes (+turnaround) before the other starts.
            if not (win_end + turn <= o_start or o_end + turn <= win_start):
                osecs_sorted = sorted(osecs, key=lambda f: f["std"])
                warnings.append({
                    "code": "AC_OVERLAP", "severity": "critical",
                    "message": (
                        f"{reg} is already committed to {osecs_sorted[0]['callsign']} "
                        f"({_pairing_route_label(osecs_sorted)}), which overlaps this "
                        f"rotation's ground-time (min {MIN_TURNAROUND_MIN}min turnaround)."
                    ),
                    "rule_ref": "Operational — aircraft double-booking",
                })
                break
    return warnings


def _pending_aircraft_decision_incident(state: dict, pairing_id: str) -> dict | None:
    """The open, clock-pausing TECH incident (if any) blocking this pairing —
    i.e. the one a reassignment here would resolve."""
    flight_ids = {s["id"] for s in _pairing_sectors(state, pairing_id)}
    for inc in state.get("incidents", []):
        if inc["status"] == "open" and inc.get("requires_aircraft_decision") \
                and inc["flight_id"] in flight_ids:
            return inc
    return None


def assign_aircraft(state: dict, pairing_id: str, reg: str) -> dict:
    """Assign tail `reg` to every REMAINING (not yet departed) sector of a
    pairing. Hard constraints only — a critical warning blocks the change (no
    force path). A sector that's already flown keeps its historical tail —
    this can legitimately be a mid-rotation swap (e.g. the outbound landed
    fine, the original tail then went tech, and the return leg needs a
    different one).

    If this pairing is under a grounded-aircraft incident (the sim is paused
    for it — see is_clock_paused), this reassignment IS the resolution: the
    choice is graded against the best feasible alternative at this moment
    before it's applied, and the incident is closed, lifting the pause."""
    warnings = check_aircraft_assignment(state, pairing_id, reg)
    if any(w["severity"] == "critical" for w in warnings):
        return {"ok": False, "applied": False, "warnings": warnings,
                "pairing_id": pairing_id, "reg": reg}

    inc = _pending_aircraft_decision_incident(state, pairing_id)
    # Grade BEFORE mutating — the what-if search needs the pre-swap world.
    grade = _grade_aircraft_decision(state, pairing_id, reg) if inc else None

    sectors = _pairing_sectors(state, pairing_id)
    active_sectors = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]
    previous = (active_sectors or sectors)[0]["aircraft_reg"] if sectors else None
    for s in active_sectors:
        s["aircraft_reg"] = reg

    result = {
        "ok": True, "applied": True, "warnings": warnings,
        "pairing_id": pairing_id, "reg": reg, "previous_reg": previous,
    }

    if inc:
        inc["status"] = "resolved"
        inc["resolution"] = "aircraft_control_reassign"
        inc["resolution_label"] = f"Reassigned to {reg} via Aircraft Control"
        inc["resolution_note"] = f"Aircraft swapped to {reg}."
        inc["resolved_at"] = state["clock"]
        inc["decision_grade"] = grade
        state["decisions_log"].append({
            "ts": state["clock"], "incident_id": inc["id"],
            "action": "aircraft_control_reassign", "cost_usd": 0, "otp_hit": 0,
        })
        result["incident_resolved"] = inc["id"]
        result["decision_grade"] = grade

    return result


def _is_tail_fully_free(state: dict, reg: str) -> bool:
    """True if `reg` has no active-status commitment anywhere in the day —
    the bar for being sent off empty on a positioning flight. A tail that's
    still mid-rotation elsewhere can't also be ferried."""
    return not any(
        f["aircraft_reg"] == reg and f["status"] in _AC_ACTIVE_STATUSES
        for f in state["flights"]
    )


def _curfew_clear_end(dt: datetime) -> datetime:
    """The next moment at/after `dt` (which must fall inside the LHR night
    curfew, 23:00-06:00Z wrapping midnight) when the curfew is no longer in
    effect."""
    end = dt.replace(hour=CURFEW_END_HOUR, minute=0, second=0, microsecond=0)
    if dt.hour >= CURFEW_START_HOUR:
        end += timedelta(days=1)
    return end


def _ferry_schedule_avoiding_curfew(
    origin: str, dest: str, earliest_std: datetime, block_min: int
) -> tuple[datetime, datetime]:
    """A positioning flight's (std, sta), pushed later if needed so neither
    end touches the LHR night curfew — a curfew means no aircraft movements
    at all, takeoff or landing, not just a fine to pay, so a deliberately
    planned ferry has to be scheduled around it. Every route in this network
    touches LHR at exactly one end, so at most one adjustment is ever
    needed (departure-side OR arrival-side, never both)."""
    std = earliest_std
    if origin == CURFEW_AIRPORT and _in_curfew_window(std):
        std = _curfew_clear_end(std)
    sta = std + timedelta(minutes=block_min)
    if dest == CURFEW_AIRPORT and _in_curfew_window(sta):
        std = max(std, _curfew_clear_end(sta) - timedelta(minutes=block_min))
        sta = std + timedelta(minutes=block_min)
    return std, sta


def _ferry_cost(ac_type: str, block_min: int) -> int:
    """What an empty positioning flight costs to run: a fixed dispatch fee
    (slot, handling, crew callout) plus a per-minute rate scaling with the
    type's fuel burn. Single source of truth so the price previewed before
    the decision is exactly the price charged after it."""
    return FERRY_DISPATCH_FEE_USD + block_min * FERRY_COST_PER_MIN_USD.get(ac_type, 15)


def _ferry_plan(state: dict, pairing_id: str, reg: str) -> dict | None:
    """If tail `reg` needs repositioning to operate `pairing_id`'s open
    leg(s), the planned (curfew-adjusted, crew not yet assigned) positioning
    flight — else None if it's already at the right station. Read-only."""
    sectors = _pairing_sectors(state, pairing_id)
    active_sectors = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if not active_sectors or not ac:
        return None
    pairing_origin = active_sectors[0]["origin"]
    now = datetime.fromisoformat(state["clock"])
    current_position = _aircraft_position_before(state, reg, now, exclude_pairing_id=pairing_id)
    if current_position == pairing_origin:
        return None
    block = _route_block_min(current_position, pairing_origin)
    std, sta = _ferry_schedule_avoiding_curfew(current_position, pairing_origin, now, block)
    return {
        "id": _hash_id("FLT"),
        "callsign": f"POS{reg.replace('-', '')}",
        "origin": current_position, "destination": pairing_origin,
        "std": std.isoformat(), "sta": sta.isoformat(), "block_min": block,
        "aircraft_reg": reg, "aircraft_type": ac["type"], "status": "scheduled",
        "delay_min": 0, "reactionary_min": 0, "pax_count": 0, "assigned_crew_ids": [],
        # A positioning flight carries no cabin crew (no pax) but DOES need a
        # minimum flight deck: one Captain, one First Officer.
        "required_crew": {"CP": 1, "FO": 1, "SC": 0, "CC": 0, "type_qual": ac["type"]},
        "pairing_id": None, "note": "POSITIONING FLIGHT (empty ferry)", "is_ferry": True,
    }


def _find_ferry_crew(state: dict, ferry_flight: dict) -> tuple[dict | None, dict | None]:
    """Legal (available/standby, freshest-fatigue-first) Captain and First
    Officer for a ferry's flight-deck-only crew — reuses check_assignment,
    the same EASA-FTL-inspired legality machinery (rest, FDP, 7d/28d duty,
    consecutive days) applied to any other duty. The ferry flight must
    temporarily be visible in state["flights"] for the overlap/FDP checks to
    see it; always removed again before returning — read-only overall."""
    state["flights"].append(ferry_flight)
    try:
        cp = _legal_candidates(state, ferry_flight, "CP", ("available", "standby"))
        fo = _legal_candidates(state, ferry_flight, "FO", ("available", "standby"))
    finally:
        state["flights"].remove(ferry_flight)
    return (cp[0] if cp else None), (fo[0] if fo else None)


def check_ferry(state: dict, pairing_id: str, reg: str) -> list[dict]:
    """Legality of ferrying tail `reg` EMPTY to reposition it onto
    `pairing_id`. Deliberately does NOT apply check_aircraft_assignment's
    position check — being in the wrong place is exactly the problem this
    exists to solve. Still hard on type, MEL grounding, an already-fully-flown
    pairing, requires the tail be genuinely free to send, AND — since flying
    it anywhere needs a minimum flight-deck crew — requires a legal (FTL
    and rest-compliant) Captain and First Officer to actually be available
    for the positioning flight itself, curfew-adjusted timing included."""
    sectors = _pairing_sectors(state, pairing_id)
    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    if not sectors or not ac:
        return [{
            "code": "REF_NOT_FOUND", "severity": "critical",
            "message": "Aircraft or rotation reference not found.", "rule_ref": "INTERNAL",
        }]

    warnings: list[dict] = []
    aog = _aog_warning(ac, state.get("clock"))
    if aog:
        warnings.append(aog)

    expired_mel = [m for m in ac.get("mel_items", []) if m.get("expired")]
    if expired_mel:
        cats = ", ".join(f"Cat {m['category']}" for m in expired_mel)
        warnings.append({
            "code": "AC_MEL_EXPIRED", "severity": "critical",
            "message": (
                f"{reg} has a deferred defect past its MEL limit ({cats}) — "
                f"grounded until Maintenance Control clears it. Cannot dispatch."
            ),
            "rule_ref": "MEL deferral limit exceeded",
        })

    active_sectors = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]
    if not active_sectors:
        departed = sectors[-1]
        warnings.append({
            "code": "AC_DEPARTED", "severity": "critical",
            "message": (
                f"{departed['callsign']} is already {departed['status']} — "
                f"the rotation is underway and there's nothing left to ferry onto."
            ),
            "rule_ref": "Operational — sector in progress",
        })
        return warnings

    pairing_type = active_sectors[0]["aircraft_type"]
    if ac["type"] != pairing_type:
        warnings.append({
            "code": "AC_TYPE_MISMATCH", "severity": "critical",
            "message": (
                f"{reg} is a {ac['type']}; this rotation needs a {pairing_type}. "
                f"A ferry repositions an aircraft — it can't change its type."
            ),
            "rule_ref": "Fleet / type compatibility",
        })

    if not _is_tail_fully_free(state, reg):
        warnings.append({
            "code": "AC_FERRY_BUSY", "severity": "critical",
            "message": f"{reg} is already committed to other flying today — it can't be freed for a positioning flight.",
            "rule_ref": "Operational — aircraft double-booking",
        })

    if any(w["severity"] == "critical" for w in warnings):
        return warnings

    plan = _ferry_plan(state, pairing_id, reg)
    if plan is None:
        return warnings  # already at the right station — no ferry needed, nothing more to check

    now = datetime.fromisoformat(state["clock"])
    std = datetime.fromisoformat(plan["std"])
    if std > now:
        delay = int((std - now).total_seconds() // 60)
        warnings.append({
            "code": "FERRY_CURFEW_DELAY", "severity": "warning",
            "message": (
                f"LHR night curfew pushes this positioning flight's departure to "
                f"{std.strftime('%H:%MZ')} ({delay}min later than the earliest possible) — "
                f"no movements are permitted {CURFEW_START_HOUR:02d}:00-{CURFEW_END_HOUR:02d}:00Z."
            ),
            "rule_ref": "Operational — LHR night curfew",
        })

    cp, fo = _find_ferry_crew(state, plan)
    if not cp:
        warnings.append({
            "code": "FERRY_NO_CAPTAIN", "severity": "critical",
            "message": (
                f"No legal Captain (available/standby, {ac['type']}-rated, within FTL rest/duty "
                f"limits) for a {plan['block_min']}min positioning flight departing "
                f"{std.strftime('%H:%MZ')}. A ferry needs a minimum flight-deck crew of two."
            ),
            "rule_ref": "ORO.FTL.205 — minimum flight-deck crew",
        })
    if not fo:
        warnings.append({
            "code": "FERRY_NO_FO", "severity": "critical",
            "message": (
                f"No legal First Officer (available/standby, {ac['type']}-rated, within FTL rest/duty "
                f"limits) for a {plan['block_min']}min positioning flight departing "
                f"{std.strftime('%H:%MZ')}. A ferry needs a minimum flight-deck crew of two."
            ),
            "rule_ref": "ORO.FTL.205 — minimum flight-deck crew",
        })

    return warnings


def preview_ferry(state: dict, pairing_id: str, reg: str) -> dict:
    """Read-only what-if for the ferry decision: legality warnings plus the
    price of the positioning flight, so the player sees what an empty
    repositioning actually costs BEFORE committing to it — the same way
    reset-to-zero previews its cancellation bill. Never mutates real state.

    cost_usd is 0 when needs_ferry is False: the tail is already at the right
    station, so a plain reassignment does the job and no ferry is flown."""
    warnings = check_ferry(state, pairing_id, reg)
    has_critical = any(w["severity"] == "critical" for w in warnings)

    plan = None if has_critical else _ferry_plan(state, pairing_id, reg)
    if plan is None:
        return {
            "warnings": warnings, "has_critical": has_critical,
            "needs_ferry": False, "cost_usd": 0, "ferry_flight": None,
        }

    # The cash figure is the small half of what a ferry costs. It also burns a
    # Captain and an FO out of a standby bank that is only four pilots deep —
    # spending your last legal standby Captain on an empty sector at 14:00 is
    # the decision that actually hurts, and the player could not see it.
    cp, fo = _find_ferry_crew(state, plan)
    remaining = {
        rank: sum(1 for c in state["crew"]
                  if c["rank"] == rank and c["status"] == "standby"
                  and c["id"] not in {cp["id"] if cp else None, fo["id"] if fo else None})
        for rank in ("CP", "FO")
    }
    return {
        "warnings": warnings, "has_critical": has_critical,
        "needs_ferry": True,
        "cost_usd": _ferry_cost(plan["aircraft_type"], plan["block_min"]),
        "ferry_flight": {
            "callsign": plan["callsign"], "origin": plan["origin"],
            "destination": plan["destination"], "std": plan["std"],
            "sta": plan["sta"], "block_min": plan["block_min"],
        },
        "crew": {
            "captain": f"{cp['id']} {cp['name']}" if cp else None,
            "first_officer": f"{fo['id']} {fo['name']}" if fo else None,
            "fdp_consumed_min": plan["block_min"],
            "standby_remaining": remaining,
        },
    }


def ferry_spare_aircraft(state: dict, pairing_id: str, reg: str) -> dict:
    """Dispatch tail `reg` EMPTY (a positioning/ferry flight, zero pax, no
    revenue) from wherever it currently is to the station this pairing's
    remaining sectors need it at, crewed by a legal Captain + First Officer,
    then hand those sectors to it. The ferry is recorded as a real flight —
    so the existing reactionary-delay engine naturally works out how much
    the pairing has to wait for it to land (no separate delay math needed
    here), and its crew accrue FDP/duty exactly like any other flight when
    it actually lands during tick() — no special-casing needed there either.

    Real-world grounding: dispatching a reserve/spare aircraft empty to cover
    a stranded rotation is a genuine (if expensive, last-resort) OCC recovery
    lever — see docs/research/Aircraft-Fleet-Management-Research.md §3."""
    warnings = check_ferry(state, pairing_id, reg)
    if any(w["severity"] == "critical" for w in warnings):
        return {"ok": False, "applied": False, "warnings": warnings, "pairing_id": pairing_id, "reg": reg}

    sectors = _pairing_sectors(state, pairing_id)
    active_sectors = [s for s in sectors if s["status"] in _AC_ACTIVE_STATUSES]

    inc = _pending_aircraft_decision_incident(state, pairing_id)
    # Grade BEFORE mutating — the what-if search needs the pre-ferry world.
    grade = _grade_aircraft_decision(state, pairing_id, reg) if inc else None

    ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == reg), None)
    ferry_flight = _ferry_plan(state, pairing_id, reg)
    crew_names = None
    ferry_cost = 0
    if ferry_flight is not None:
        ferry_cost = _ferry_cost(ac["type"], ferry_flight["block_min"])
        state["kpis"]["cost_usd"] += ferry_cost
        state["flights"].append(ferry_flight)
        cp, fo = _find_ferry_crew(state, ferry_flight)
        # check_ferry already confirmed both exist; re-validated here as an
        # internal consistency guard rather than trusted blindly.
        if not cp or not fo:
            state["flights"].remove(ferry_flight)
            return {"ok": False, "applied": False,
                    "warnings": [{"code": "INTERNAL", "severity": "critical",
                                   "message": "Ferry crew became unavailable between check and dispatch.",
                                   "rule_ref": "INTERNAL"}],
                    "pairing_id": pairing_id, "reg": reg}
        for crew in (cp, fo):
            assign_crew(state, ferry_flight["id"], crew["id"])
            crew["status"] = "on_duty"
        crew_names = f"{cp['id']} {cp['name']} (CP) / {fo['id']} {fo['name']} (FO)"

    previous = active_sectors[0]["aircraft_reg"]
    for s in active_sectors:
        s["aircraft_reg"] = reg

    reset_reactionary_delays(state)
    _log_cascade(state, propagate_reactionary_delays(state), "ferry", pairing_id)
    _recompute_kpis(state)

    result = {
        "ok": True, "applied": True, "warnings": warnings,
        "pairing_id": pairing_id, "reg": reg, "previous_reg": previous,
        "ferry_flight": ferry_flight, "cost_usd": ferry_cost,
    }

    if inc:
        if ferry_flight:
            note = (
                f"Empty positioning flight {ferry_flight['callsign']} dispatched "
                f"{ferry_flight['origin']}→{ferry_flight['destination']} "
                f"({ferry_flight['block_min']}min), crewed by {crew_names}. "
                f"Cost: ${ferry_cost:,}."
            )
        else:
            note = f"Aircraft swapped to {reg}."
        inc["status"] = "resolved"
        inc["resolution"] = "aircraft_control_ferry"
        inc["resolution_label"] = f"Ferried {reg} via Aircraft Control"
        inc["resolution_note"] = note
        inc["resolved_at"] = state["clock"]
        inc["decision_grade"] = grade
        state["decisions_log"].append({
            "ts": state["clock"], "incident_id": inc["id"],
            "action": "aircraft_control_ferry", "cost_usd": ferry_cost, "otp_hit": 0,
        })
        result["incident_resolved"] = inc["id"]
        result["decision_grade"] = grade

    return result


def aircraft_control(state: dict) -> dict:
    """Fleet-control view: every tail with its rotations for the day, plus a
    per-rotation list for the reassignment table."""
    fleet = state.get("fleet", FLEET)

    # Group flights into pairings once.
    pairings: dict[str, list[dict]] = {}
    for f in state["flights"]:
        pid = f.get("pairing_id")
        if pid:
            pairings.setdefault(pid, []).append(f)
    for pid in pairings:
        pairings[pid].sort(key=lambda f: f["std"])

    def _pairing_status(secs: list[dict]) -> str:
        statuses = {s["status"] for s in secs}
        if statuses <= {"cancelled"}:
            return "cancelled"
        if "airborne" in statuses:
            return "airborne"
        if all(s["status"] == "landed" for s in secs):
            return "landed"
        if "boarding" in statuses:
            return "boarding"
        if any(s.get("delay_min", 0) > 15 for s in secs):
            return "delayed"
        return "scheduled"

    rotations = []
    by_reg_rotations: dict[str, list[dict]] = {}
    for pid, secs in pairings.items():
        first, last = _pairing_window(secs)
        rot = {
            "pairing_id": pid,
            "aircraft_reg": secs[0]["aircraft_reg"],
            "aircraft_type": secs[0]["aircraft_type"],
            "callsigns": [s["callsign"] for s in secs],
            "route": _pairing_route_label(secs),
            "sectors": len(secs),
            "std": secs[0]["std"],
            "sta": secs[-1]["sta"],
            "first_dep": first.isoformat(),
            "last_arr": last.isoformat(),
            "block_min": sum(s["block_min"] for s in secs),
            "pax": sum(s.get("pax_count", 0) for s in secs),
            "status": _pairing_status(secs),
            "reactionary_min": sum(s.get("reactionary_min", 0) for s in secs),
            # Worst delay on any sector — the UI tones the rotation off this so
            # a 90-minute-down rotation reads the same colour here as it does
            # on the timeline and the roster board.
            "delay_min": max((s.get("delay_min", 0) for s in secs), default=0),
            # At least one sector still ahead of the tail — a rotation isn't
            # locked out just because an earlier leg in the same pairing has
            # already flown (see check_aircraft_assignment/assign_aircraft).
            "reassignable": any(s["status"] in _AC_ACTIVE_STATUSES for s in secs),
            # Whether reset_to_zero has anything left in this pairing to cancel.
            "resettable": any(s["status"] in ("scheduled", "delayed", "boarding") for s in secs),
        }
        rotations.append(rot)
        by_reg_rotations.setdefault(secs[0]["aircraft_reg"], []).append(rot)
    rotations.sort(key=lambda r: r["std"])

    fleet_view = []
    for ac in fleet:
        rots = sorted(by_reg_rotations.get(ac["reg"], []), key=lambda r: r["std"])
        block = sum(r["block_min"] for r in rots)
        mel_items = ac.get("mel_items", [])
        grounded = any(m.get("expired") for m in mel_items) or _is_aog(ac, state.get("clock"))
        if grounded and not rots:
            status = "grounded"
        elif not rots:
            status = "spare" if ac.get("spare") else "idle"
        elif all(r["status"] == "landed" for r in rots):
            status = "day done"
        elif any(r["status"] == "airborne" for r in rots):
            status = "airborne"
        elif any(r["status"] == "delayed" for r in rots):
            status = "delayed"
        else:
            status = "in service"
        fleet_view.append({
            "reg": ac["reg"],
            "type": ac["type"],
            "spare": bool(ac.get("spare")),
            "mel_items": mel_items,
            "grounded": grounded,
            "rotation_count": len(rots),
            "sectors": sum(r["sectors"] for r in rots),
            "block_min": block,
            "block_hours": round(block / 60, 1),
            "status": status,
            "rotations": rots,
        })

    return {
        "fleet": fleet_view,
        "rotations": rotations,
        "min_turnaround_min": MIN_TURNAROUND_MIN,
        "hub": AIRLINE["hub"],
    }


_RTZ_CANCELLABLE_STATUSES = ("scheduled", "delayed", "boarding")


def _network_reactionary_total(state: dict, exclude_ids: set[str] | None = None) -> int:
    """Total knock-on minutes across the network.

    `exclude_ids` drops specific flights from the count. Reset-to-zero needs
    this: a cancelled sector contributes zero reactionary minutes afterwards,
    so counting it on both sides of the before/after would credit the player
    for deleting the delay on the very flights they deleted. Only relief felt
    ELSEWHERE in the network is a benefit of the decision."""
    ex = exclude_ids or set()
    return sum(f.get("reactionary_min", 0) for f in state["flights"] if f["id"] not in ex)


def _sectors_relieved(before: list[dict], after: list[dict], exclude_ids: set[str]) -> int:
    """How many OTHER rotations actually got their knock-on delay cut. The
    number that tells the story a minute-total cannot: did this help anyone?"""
    after_by_id = {f["id"]: f.get("reactionary_min", 0) for f in after}
    return sum(
        1 for f in before
        if f["id"] not in exclude_ids
        and after_by_id.get(f["id"], 0) < f.get("reactionary_min", 0)
    )


def check_reset_to_zero(state: dict, pairing_ids: list[str]) -> list[dict]:
    """Feasibility check for a reset-to-zero action: pre-emptively
    cancelling a whole block of pairings in one deliberate move, rather
    than reacting to each one's incident individually. Unlike a normal
    incident cancellation, this isn't gated on an open incident at all —
    it's a standing option any time the network is going bad enough that
    resyncing the whole fleet beats digging out pairing by pairing."""
    warnings: list[dict] = []
    if not pairing_ids:
        warnings.append({
            "code": "RTZ_EMPTY", "severity": "critical",
            "message": "No pairings selected to reset.", "rule_ref": "INTERNAL",
        })
        return warnings
    for pid in pairing_ids:
        sectors = _pairing_sectors(state, pid)
        if not sectors:
            warnings.append({
                "code": "REF_NOT_FOUND", "severity": "critical",
                "message": f"Pairing {pid} not found.", "rule_ref": "INTERNAL",
            })
            continue
        if not any(s["status"] in _RTZ_CANCELLABLE_STATUSES for s in sectors):
            warnings.append({
                "code": "RTZ_NOTHING_TO_CANCEL", "severity": "critical",
                "message": (
                    f"{sectors[0]['callsign']} pairing has nothing left to cancel "
                    f"— every sector is already flown or cancelled."
                ),
                "rule_ref": "Operational",
            })
    return warnings


def preview_reset_to_zero(state: dict, pairing_ids: list[str]) -> dict:
    """Read-only what-if for the reset-to-zero decision: the guaranteed cost
    (cancellation + pax disruption, same per-sector/per-pax rate as any
    single cancellation) against the network reactionary-delay minutes
    avoided by resyncing the whole fleet on a scratch copy. Never mutates
    real state — this is the trade-off the player sees before committing."""
    warnings = check_reset_to_zero(state, pairing_ids)
    scratch = {"flights": copy.deepcopy(state["flights"])}
    cancel_sectors = 0
    cancel_pax = 0
    cancelled_ids: set[str] = set()
    for pid in pairing_ids:
        for f in scratch["flights"]:
            if f.get("pairing_id") == pid and f["status"] in _RTZ_CANCELLABLE_STATUSES:
                cancel_sectors += 1
                cancel_pax += f.get("pax_count", 0)
                cancelled_ids.add(f["id"])
                f["status"] = "cancelled"
    before_total = _network_reactionary_total(state, cancelled_ids)
    before_snapshot = copy.deepcopy(state["flights"])
    reset_reactionary_delays(scratch)
    propagate_reactionary_delays(scratch)
    after_total = _network_reactionary_total(scratch, cancelled_ids)
    cost = 15000 * cancel_sectors + cancel_pax * 280
    comp = _cancellation_compensation_due(state, cancelled_ids)
    care = sum(
        f.get("pax_count", 0) * (CARE_MEAL_USD_PER_PAX + CARE_HOTEL_USD_PER_PAX)
        for f in state["flights"]
        if f["id"] in cancelled_ids and not f.get("care_charged")
    )
    return {
        "warnings": warnings,
        "has_critical": any(w["severity"] == "critical" for w in warnings),
        "cancel_sectors": cancel_sectors,
        "cancel_pax": cancel_pax,
        "cost_usd": cost + comp + care,
        "cancellation_cost_usd": cost,
        "compensation_usd": comp,
        "duty_of_care_usd": care,
        "network_reactionary_before_min": before_total,
        "network_reactionary_after_min": after_total,
        "reactionary_avoided_min": max(0, before_total - after_total),
        "sectors_relieved": _sectors_relieved(before_snapshot, scratch["flights"], cancelled_ids),
    }


def reset_to_zero(state: dict, pairing_ids: list[str]) -> dict:
    """Pre-emptively cancel a whole block of pairings in one deliberate move
    to resynchronize the fleet with reality, rather than digging out
    incident-by-incident — the real "reset to zero" IROPS recovery tactic
    (Southwest, 26 Dec 2022; see
    docs/research/Aircraft-Fleet-Management-Research.md §5). Trades
    guaranteed up-front pain (the same per-sector/per-pax cancellation cost
    as any single cancellation) for stopping a compounding reactionary-delay
    cascade before it gets worse.

    Reactionary delay is rebuilt from scratch across the WHOLE network
    afterward, not just the cancelled pairings — freeing up a tail or crew
    that was stuck behind a late inbound which no longer exists can clear
    knock-on delay on completely unrelated rotations too, which is the
    entire point of the tactic."""
    warnings = check_reset_to_zero(state, pairing_ids)
    if any(w["severity"] == "critical" for w in warnings):
        return {"ok": False, "applied": False, "warnings": warnings, "pairing_ids": pairing_ids}

    cancelled_flight_ids: list[str] = []
    total_pax = 0
    released: set[str] = set()
    for pid in pairing_ids:
        for s in _pairing_sectors(state, pid):
            if s["status"] not in _RTZ_CANCELLABLE_STATUSES:
                continue
            s["status"] = "cancelled"
            cancelled_flight_ids.append(s["id"])
            total_pax += s.get("pax_count", 0)
            for cid in list(s["assigned_crew_ids"]):
                s["assigned_crew_ids"].remove(cid)
                released.add(cid)

    for cid in released:
        c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
        if c and not any(cid in f["assigned_crew_ids"] for f in state["flights"]):
            c["assigned_flight_id"] = None
            if c["status"] == "on_duty":
                c["status"] = "available"

    cancelled_ids = set(cancelled_flight_ids)
    before_total = _network_reactionary_total(state, cancelled_ids)
    before_snapshot = copy.deepcopy(state["flights"])

    cancel_cost = 15000 * len(cancelled_flight_ids) + total_pax * 280
    state["kpis"]["cost_usd"] += cancel_cost
    state["kpis"]["pax_disrupted"] += total_pax
    state["kpis"]["pax_delay_min"] += CANCEL_DELAY_EQUIVALENT_MIN_PER_PAX * total_pax
    cancelled_flights = [f for f in state["flights"] if f["id"] in cancelled_ids]
    comp = _charge_cancellation_compensation(state, cancelled_flights)
    care = _charge_cancellation_care(state, cancelled_flights)
    cost = cancel_cost + comp + care

    reset_reactionary_delays(state)
    _log_cascade(state, propagate_reactionary_delays(state), "reset_to_zero")
    _recompute_kpis(state)
    after_total = _network_reactionary_total(state, cancelled_ids)

    state["decisions_log"].append({
        "ts": state["clock"], "incident_id": f"RESET-TO-ZERO ({len(pairing_ids)} pairings)",
        "action": "reset_to_zero", "cost_usd": cost, "otp_hit": 0,
    })

    return {
        "ok": True, "applied": True, "warnings": warnings,
        "pairing_ids": pairing_ids, "cancelled_flight_ids": cancelled_flight_ids,
        "cost_usd": cost, "cancellation_cost_usd": cancel_cost,
        "compensation_usd": comp, "duty_of_care_usd": care,
        "pax_disrupted": total_pax,
        "reactionary_avoided_min": max(0, before_total - after_total),
        "sectors_relieved": _sectors_relieved(before_snapshot, state["flights"], cancelled_ids),
        "kpis": state["kpis"],
    }


# ------------------- Day-of-Ops simulation ------------------- #

# Type weights informed by real delay-cause data (US DOT/BTS Air Travel
# Consumer Report; Eurocontrol CODA). Of the delay actually attributable to a
# single flight's own disruption (i.e. excluding reactionary/knock-on delay,
# which is the single largest real cause at 46-48% of delay minutes per
# Eurocontrol and is already modelled separately by
# propagate_reactionary_delays), the remainder splits roughly evenly across
# airline-internal causes (crew + technical/maintenance, ~31% of delayed
# flights per BTS), ATC/airspace-system causes (~31%), and weather (smaller
# in BTS's narrow "extreme weather" bucket, but weather's true footprint is
# much larger once its contribution to ATC-flow and reactionary delay is
# included — CODA and FAA both attribute a majority of NAS delay to weather
# at the root). The previous weights over-indexed on crew-specific causes
# relative to this evidence.
INCIDENT_TYPES = [
    ("CREW_SICK", 0.15, "Crew reported sick before report time."),
    ("LATE_REPORT", 0.10, "Crew running late for report."),
    ("WEATHER", 0.25, "Weather disruption at destination."),
    ("TECH", 0.25, "Technical defect / MEL deferral on aircraft."),
    ("ATC_FLOW", 0.25, "ATC slot / flow restriction imposed."),
]

# A real OCC is a room of specialist desks (Duty Ops Manager, Flight Dispatch,
# Crew Control, Maintenance Control, network/ATC liaison) and every delay is
# logged under a standard two-digit IATA delay code. Incidents carry both: the
# desk that raised them and the code the delay would be filed under.
#   63 late/absent crew · 64 crew shortage · 41 aircraft defect
#   72 destination weather · 81 ATFM/ATC en-route restriction · 93 reactionary
INCIDENT_META = {
    "CREW_SICK":   {"desk": "CREW CONTROL", "delay_code": "64"},
    "LATE_REPORT": {"desk": "CREW CONTROL", "delay_code": "63"},
    "TECH":        {"desk": "MX CONTROL",   "delay_code": "41"},
    "WEATHER":     {"desk": "DISPATCH",     "delay_code": "72"},
    "ATC_FLOW":    {"desk": "NETWORK/ATC",  "delay_code": "81"},
    # Not randomly spawned — raised by the operation itself when accumulated
    # delay pushes a rostered crew past their FDP cap. IATA 63 is crew-shortage
    # rotation delay, which is what a timed-out duty becomes.
    "CREW_HOURS":  {"desk": "CREW CONTROL", "delay_code": "63"},
}

# The operation never pauses for a problem — but a problem you sit on gets
# worse. An open incident left unattended this long escalates: severity goes
# major, the flight takes further delay, and the recovery menu is re-priced
# from the (worse) live state. This replaces the old forced clock-pause with
# the time pressure a real duty controller actually faces.
ESCALATION_AFTER_MIN = 60
ESCALATION_EXTRA_DELAY_MIN = 30

# MEL (Minimum Equipment List) deferral categories. Real MELs run A/B/C/D with
# day-limits of item-specific/3/10/120 respectively; this sim uses B and C
# (A has no fixed interval to model, and D's 120-day window never matters at
# game timescales). A deferred defect stays on the TAIL, not the flight, and
# travels with it across days until an engineer clears it or the limit is hit.
MEL_CATEGORY_LIMITS_DAYS = {"B": 3, "C": 10}
MEL_CATEGORY_WEIGHTS = {"B": 0.3, "C": 0.7}
# Fraction of open, unexpired MEL items an overnight engineering shift
# rectifies before the next day's ops — most defects get fixed at the next
# opportunity rather than riding the full deferral window.
MEL_OVERNIGHT_CLEAR_PROB = 0.7

# A MAJOR tech defect is not MEL-deferrable (see mel_defer's feasibility gate)
# and cannot simply be held for — the tail is physically unusable. Rather than
# offer a one-click "swap from nearest spare" shortcut, this kind of incident
# sets `requires_aircraft_decision` on itself: the whole sim clock freezes
# (see is_clock_paused / tick) until the player either reassigns a real tail
# via the Aircraft Control desk (any legally clean tail, not just a spare) or
# cancels the rotation from the incident queue. Whichever they pick is graded
# against the best feasible alternative — see _grade_aircraft_decision.
CANCEL_DELAY_EQUIVALENT_MIN_PER_PAX = 240  # matches the cancellation pax-delay convention used elsewhere
# Grading currency. The old scale was delay-minutes with a cancellation
# converted at 240 min/pax, which made a cancel score ~70,000 against a tail
# swap's ~225 — a 346x gap, 96.5% of it the flat pax term. The grader
# therefore returned SUBOPTIMAL for every cancel including the ~10% where
# cancelling genuinely produced the better day, and could not tell two tails
# apart at all (median spread: 0 minutes). Grading in the same dollars the
# score uses puts the verdict and the scoreboard back in agreement.
DECISION_GOOD_THRESHOLD_USD = 15 * 110  # ~15 min of knock-on: "GOOD" keeps its old meaning

# EU261/UK261-style passenger compensation: due when a flight ARRIVES 3h+
# late, per passenger, scaled by haul — UNLESS the root cause is an
# "extraordinary circumstance" outside the airline's control (weather, ATC),
# mirroring the real regulation. This is what makes delay-vs-cancel a genuine
# economic decision in a real OCC.
# --- Article 9 duty of care -------------------------------------------------
# Art. 7 COMPENSATION is defeated by extraordinary circumstances. Art. 9 CARE
# is not: McDonagh v Ryanair (C-12/11) held the Eyjafjallajokull airspace
# closure created no "super-extraordinary" exemption, and that EU law places
# no temporal or monetary limit on the duty of care. So a weather day still
# bleeds cash even when no compensation is owed — without this, accepting
# delay is strictly dominant whenever the cause is weather or ATC.
# https://www.legislation.gov.uk/eur/2004/261/article/9
CARE_DELAY_THRESHOLD_SHORT_MIN = 120   # <=1500km
CARE_DELAY_THRESHOLD_MED_MIN = 180     # intra-EU >1500km / 1500-3500km
CARE_DELAY_THRESHOLD_LONG_MIN = 240    # everything else
CARE_MEAL_USD_PER_PAX = 22             # meals and refreshments
CARE_HOTEL_USD_PER_PAX = 145           # room plus airport transfer
# Past this, an onward departure is no longer realistic today and the airline
# is accommodating passengers overnight.
CARE_OVERNIGHT_DELAY_MIN = 420
COMP_ARR_DELAY_THRESHOLD_MIN = 180
COMP_SHORT_HAUL_USD = 250   # ≈ £220 per pax
COMP_LONG_HAUL_USD = 600    # ≈ £520 per pax
COMP_EXEMPT_INCIDENT_TYPES = ("WEATHER", "ATC_FLOW")

# Expected NEW (primary) incidents per sim-hour of active ops. Deliberately
# calibrated well above the bare real-world rate (BTS/CODA data implies
# roughly 2-4 primary-cause disruptions across an average ~20-25 flight day)
# for pacing — this is a "hardcore" simulation, not a punctuality replica —
# but a fraction of the previous per-tick rate, which scaled with the NUMBER
# of tick() calls rather than elapsed time and so produced wildly more
# incidents at fine tick granularity (e.g. +5M ticks) than coarse (+60M).
BASE_INCIDENT_RATE_PER_HOUR = 0.4  # ~6-8 primary incidents across a full ops day

# Survive-7 difficulty curve: a rate MULTIPLIER on BASE_INCIDENT_RATE_PER_HOUR
# (day 1 mild -> day 7 brutal), preserving the shape of the original per-tick
# weight tables but expressed as a continuous rate so it composes correctly
# with Poisson sampling over arbitrary tick lengths. Used only in challenge mode.
SURVIVE_7_CURVE = {
    1: {"rate_mult": 1.0, "weather_mult": 1.0, "tech_mult": 1.0, "sick_mult": 1.0},
    2: {"rate_mult": 1.2, "weather_mult": 1.1, "tech_mult": 1.0, "sick_mult": 1.0},
    3: {"rate_mult": 1.55, "weather_mult": 1.3, "tech_mult": 1.2, "sick_mult": 1.1},
    4: {"rate_mult": 1.95, "weather_mult": 1.6, "tech_mult": 1.4, "sick_mult": 1.3},
    5: {"rate_mult": 2.8, "weather_mult": 2.2, "tech_mult": 1.6, "sick_mult": 1.5},
    6: {"rate_mult": 3.2, "weather_mult": 2.0, "tech_mult": 2.0, "sick_mult": 1.6},
    7: {"rate_mult": 3.7, "weather_mult": 1.8, "tech_mult": 2.5, "sick_mult": 1.8},
}


def _poisson_sample(lam: float, cap: int = 4) -> int:
    """Sample an event count from a Poisson distribution (Knuth's algorithm —
    no numpy dependency), capped to keep any single tick from spawning an
    unreasonable pile-up. `lam` is the expected count for this interval."""
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= random.random()
        if p <= limit:
            return min(k - 1, cap)


def _in_curfew_window(dt: datetime) -> bool:
    """True if `dt` (any timezone-aware instant, compared by its hour) falls
    inside the LHR night curfew window, which wraps midnight."""
    h = dt.hour
    return h >= CURFEW_START_HOUR or h < CURFEW_END_HOUR


def _apply_curfew_violation(state: dict, flight: dict, kind: str) -> dict:
    """Record a curfew breach on `flight` (kind: 'departure' | 'arrival'),
    fine the operation, and return the violation record for the caller."""
    fine = CURFEW_FINE_BASE_USD + flight.get("pax_count", 0) * CURFEW_FINE_PER_PAX_USD
    state["kpis"]["curfew_violations"] = state["kpis"].get("curfew_violations", 0) + 1
    state["kpis"]["cost_usd"] += fine
    tag = f"LHR NIGHT CURFEW ({kind})"
    note = flight.get("note") or ""
    flight["note"] = f"{note} · {tag}" if note else tag
    flight["curfew_violation"] = kind
    return {
        "flight_id": flight["id"],
        "callsign": flight["callsign"],
        "kind": kind,
        "fine_usd": fine,
    }


def _maybe_charge_compensation(state: dict, flight: dict) -> dict | None:
    """EU261/UK261-style passenger compensation, assessed once when a flight
    lands: 3h+ arrival delay owes per-pax compensation scaled by haul, unless
    the flight was hit by an extraordinary-circumstances cause (weather/ATC),
    which exempts the airline — exactly the calculus a real OCC runs when
    weighing an airline-controllable delay against a cancellation."""
    if flight.get("comp_charged") or flight.get("comp_exempt"):
        return None
    if flight.get("delay_min", 0) < COMP_ARR_DELAY_THRESHOLD_MIN:
        return None
    rate = COMP_LONG_HAUL_USD if flight["block_min"] > 360 else COMP_SHORT_HAUL_USD
    amount = rate * flight.get("pax_count", 0)
    flight["comp_charged"] = True
    state["kpis"]["compensation_usd"] = state["kpis"].get("compensation_usd", 0) + amount
    state["kpis"]["cost_usd"] += amount
    note = flight.get("note") or ""
    tag = "EU261 COMP DUE"
    flight["note"] = f"{note} · {tag}" if note else tag
    return {
        "flight_id": flight["id"],
        "callsign": flight["callsign"],
        "amount_usd": amount,
        "pax": flight.get("pax_count", 0),
    }


def _cancellation_compensation_due(state: dict, flight_ids) -> int:
    """UK261/EU261 Art. 7 exposure for cancelling these sectors, WITHOUT
    charging it. Cancelling under 14 days' notice owes compensation exactly as
    a long delay does; only an extraordinary-circumstances cause exempts it.
    Read-only so the preview can price the real bill before the player
    commits."""
    ids = set(flight_ids)
    total = 0
    for f in state["flights"]:
        if f["id"] not in ids or f.get("comp_charged") or f.get("comp_exempt"):
            continue
        rate = COMP_LONG_HAUL_USD if f["block_min"] > 360 else COMP_SHORT_HAUL_USD
        total += rate * f.get("pax_count", 0)
    return total


def _charge_cancellation_care(state: dict, flights: list[dict]) -> int:
    """Art. 9 care for passengers whose flight was cancelled outright. Owed
    regardless of cause, so — unlike compensation — weather buys no relief."""
    total = 0
    for f in flights:
        if f.get("care_charged"):
            continue
        pax = f.get("pax_count", 0)
        if not pax:
            continue
        f["care_charged"] = True
        total += pax * (CARE_MEAL_USD_PER_PAX + CARE_HOTEL_USD_PER_PAX)
    if total:
        state["kpis"]["duty_of_care_usd"] = state["kpis"].get("duty_of_care_usd", 0) + total
        state["kpis"]["cost_usd"] += total
    return total


def _charge_cancellation_compensation(state: dict, flights: list[dict]) -> int:
    """Charge Art. 7 compensation on cancelled sectors.

    Without this, cancelling is a free way to escape compensation a flight had
    already earned by running late — the player is rewarded for making the
    passenger outcome worse. `tick()` skips cancelled flights before
    `_maybe_charge_compensation` can fire, so the charge has to happen at the
    moment of cancellation instead."""
    total = 0
    for f in flights:
        if f.get("comp_charged") or f.get("comp_exempt"):
            continue
        rate = COMP_LONG_HAUL_USD if f["block_min"] > 360 else COMP_SHORT_HAUL_USD
        amount = rate * f.get("pax_count", 0)
        if not amount:
            continue
        f["comp_charged"] = True
        total += amount
        note = f.get("note") or ""
        tag = "UK261 COMP DUE (CANCELLED)"
        f["note"] = f"{note} · {tag}" if note else tag
    if total:
        state["kpis"]["compensation_usd"] = state["kpis"].get("compensation_usd", 0) + total
        state["kpis"]["cost_usd"] += total
    return total


def _care_threshold_min(flight: dict) -> int:
    """Art. 9 care kicks in at a delay threshold banded by sector length."""
    block = flight["block_min"]
    if block <= 120:
        return CARE_DELAY_THRESHOLD_SHORT_MIN
    if block <= 360:
        return CARE_DELAY_THRESHOLD_MED_MIN
    return CARE_DELAY_THRESHOLD_LONG_MIN


def _maybe_charge_duty_of_care(state: dict, flight: dict) -> dict | None:
    """Charge Art. 9 care — meals, and a hotel where the delay has run long
    enough that passengers are staying the night.

    Deliberately NOT gated on `comp_exempt`: care is owed whatever the cause.
    That is the whole point of modelling it separately from compensation."""
    if flight.get("care_charged"):
        return None
    delay = flight.get("delay_min", 0)
    if delay < _care_threshold_min(flight):
        return None
    pax = flight.get("pax_count", 0)
    if not pax:
        return None
    overnight = delay >= CARE_OVERNIGHT_DELAY_MIN
    amount = pax * (CARE_MEAL_USD_PER_PAX + (CARE_HOTEL_USD_PER_PAX if overnight else 0))
    flight["care_charged"] = True
    state["kpis"]["duty_of_care_usd"] = state["kpis"].get("duty_of_care_usd", 0) + amount
    state["kpis"]["cost_usd"] += amount
    note = flight.get("note") or ""
    tag = "ART.9 CARE — MEALS + HOTAC" if overnight else "ART.9 CARE — MEALS"
    flight["note"] = f"{note} · {tag}" if note else tag
    return {
        "flight_id": flight["id"], "callsign": flight["callsign"],
        "amount_usd": amount, "pax": pax, "overnight": overnight,
    }


def _aircraft_decision_still_open(state: dict, inc: dict) -> bool:
    """Whether a grounding decision still has anything to decide.

    A pairing can be cancelled from the incident queue while the pause is open
    on one of its sibling sectors. The rotation is then gone, check_ferry
    returns AC_DEPARTED for every tail, and Aircraft Control has nothing to
    offer — but the clock stayed frozen. Measured at 20% of clock-pausing
    groundings, which is the worst possible pacing failure in a game whose
    whole pressure model is the clock."""
    flight = next((f for f in state["flights"] if f["id"] == inc.get("flight_id")), None)
    if flight is None:
        return False
    pairing_id = flight.get("pairing_id")
    sectors = _pairing_sectors(state, pairing_id) if pairing_id else [flight]
    return any(s["status"] in _AC_ACTIVE_STATUSES for s in sectors)


def release_superseded_aircraft_decisions(state: dict) -> list[dict]:
    """Close any grounding decision whose rotation no longer exists, so the
    clock can run again. Resolved rather than deleted — it still happened, and
    the debrief should say so."""
    released = []
    for inc in state.get("incidents", []):
        if inc["status"] != "open" or not inc.get("requires_aircraft_decision"):
            continue
        if _aircraft_decision_still_open(state, inc):
            continue
        inc["status"] = "resolved"
        inc["resolution"] = "superseded"
        inc["resolution_label"] = "Superseded — rotation no longer active"
        inc["resolution_note"] = (
            f"{inc.get('flight_callsign')} was cancelled or completed before the "
            f"grounded tail was decided; there was nothing left to reassign."
        )
        inc["resolved_at"] = state.get("clock")
        inc["requires_aircraft_decision"] = False
        released.append(inc)
    return released


def is_clock_paused(state: dict) -> bool:
    """True while any open incident requires an aircraft decision — a
    grounded tail (major TECH) that can only be resolved by the player
    reassigning a real tail via Aircraft Control or cancelling the rotation.
    Nothing else about the operation is allowed to move while this is true.

    A decision whose rotation has since gone does not count: it is not a
    decision any more, it is a dead end."""
    return any(
        i["status"] == "open" and i.get("requires_aircraft_decision")
        and _aircraft_decision_still_open(state, i)
        for i in state.get("incidents", [])
    )


def tick(state: dict, minutes: int = 30) -> dict:
    """Advance the simulation clock by `minutes`. May spawn incidents."""
    if state["phase"] != "OPS":
        return {"ok": False, "reason": "Not in OPS phase"}
    # Close out any grounding decision whose rotation has gone before deciding
    # whether the clock is frozen, or the sim wedges on a dead end.
    superseded = release_superseded_aircraft_decisions(state)
    if is_clock_paused(state):
        blocking = [
            i["id"] for i in state["incidents"]
            if i["status"] == "open" and i.get("requires_aircraft_decision")
        ]
        return {
            "ok": True, "paused": True, "blocking_incidents": blocking,
            "new_incidents": [], "reactionary_delays": [], "curfew_violations": [],
            "escalations": [], "compensation_events": [],
            "superseded_decisions": [i["id"] for i in superseded],
        }
    state["tick_count"] += 1
    clock = datetime.fromisoformat(state["clock"]) + timedelta(minutes=minutes)
    state["clock"] = clock.isoformat()

    # ---- Flight lifecycle progression ----
    curfew_violations = []
    comp_events = []
    care_events = []
    for f in state["flights"]:
        if f["status"] in ("cancelled", "diverted", "landed"):
            continue
        delay = f.get("delay_min", 0)
        std_dt = datetime.fromisoformat(f["std"]) + timedelta(minutes=delay)
        sta_dt = datetime.fromisoformat(f["sta"]) + timedelta(minutes=delay)

        # Curfew is checked once, at the first tick the effective time is
        # crossed — decoupled from the status label so a delay-inflated
        # departure/arrival still gets caught even if status stalls at
        # "boarding" rather than flipping to "airborne".
        if clock >= std_dt and not f.get("curfew_dep_checked"):
            f["curfew_dep_checked"] = True
            if f["origin"] == CURFEW_AIRPORT and _in_curfew_window(std_dt):
                curfew_violations.append(_apply_curfew_violation(state, f, "departure"))
        if clock >= sta_dt and not f.get("curfew_arr_checked"):
            f["curfew_arr_checked"] = True
            if f["destination"] == CURFEW_AIRPORT and _in_curfew_window(sta_dt):
                curfew_violations.append(_apply_curfew_violation(state, f, "arrival"))

        if clock >= sta_dt:
            prev = f["status"]
            f["status"] = "landed"
            # Accumulate FDP for crew on this flight when it lands
            if prev != "landed":
                comp = _maybe_charge_compensation(state, f)
                if comp:
                    comp_events.append(comp)
                care = _maybe_charge_duty_of_care(state, f)
                if care:
                    care_events.append(care)
                for cid in f["assigned_crew_ids"]:
                    c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
                    if c:
                        c["fdp_used_min"] = c.get("fdp_used_min", 0) + f["block_min"]
                        # The duty period this crew has now completed — what
                        # tomorrow's minimum rest is measured against.
                        duty_clock = crew_duty_clock(state, cid)
                        c["last_duty_min"] = max(
                            c.get("last_duty_min", 0),
                            duty_clock["fdp_projected_min"] if duty_clock and duty_clock["on_duty"]
                            else c["fdp_used_min"],
                        )
                        c["duty_7d_hr"] = round(
                            c.get("duty_7d_hr", 0) + f["block_min"] / 60, 2
                        )
                        if c["status"] == "on_duty":
                            c["status"] = "available"
                        c["assigned_flight_id"] = None
        elif clock >= std_dt:
            if f["status"] not in ("airborne", "boarding"):
                f["status"] = "airborne"
        elif clock >= std_dt - timedelta(minutes=30):
            if f["status"] == "scheduled":
                f["status"] = "boarding"

    new_incidents = []
    # Spawn incidents at a rate scaled by elapsed sim-time (not by number of
    # tick() calls — a flat per-tick chance made incident count depend on how
    # finely the player ticked, e.g. far more incidents/day at +5M than +60M
    # for the same span of ops). Challenge mode escalates the rate with day.
    if state.get("is_challenge"):
        day = state.get("day_number", 1)
        curve = SURVIVE_7_CURVE.get(day, SURVIVE_7_CURVE[7])
        rate_mult = curve["rate_mult"]
        type_weight_mult = {
            "CREW_SICK": curve["sick_mult"],
            "WEATHER": curve["weather_mult"],
            "TECH": curve["tech_mult"],
        }
    else:
        rate_mult = 1.0
        type_weight_mult = {}
    lam = BASE_INCIDENT_RATE_PER_HOUR * rate_mult * (minutes / 60.0)
    n = _poisson_sample(lam)
    for _ in range(n):
        adj_weights = [
            i[1] * type_weight_mult.get(i[0], 1.0)
            for i in INCIDENT_TYPES
        ]
        kind, _w, desc = random.choices(
            INCIDENT_TYPES,
            weights=adj_weights,
            k=1
        )[0]
        # Pick an affected flight that has not yet departed
        upcoming = [f for f in state["flights"] if f["status"] in ("scheduled","delayed","boarding") and datetime.fromisoformat(f["std"]) > clock - timedelta(hours=2)]
        if not upcoming:
            continue
        flight = random.choice(upcoming)
        sev = random.choice(["minor", "major"])
        meta = INCIDENT_META.get(kind, {})
        inc = {
            "id": _hash_id("INC"),
            "type": kind,
            "severity": sev,
            "description": desc,
            "raised_at": state["clock"],
            "flight_id": flight["id"],
            "flight_callsign": flight["callsign"],
            "status": "open",
            "resolution": None,
            "options": [],
            "reported_by": meta.get("desk"),
            "delay_code": meta.get("delay_code"),
            "escalated": False,
        }
        if kind == "TECH" and sev == "major":
            inc["requires_aircraft_decision"] = True
            # The aeroplane is broken. Without this the player could "resolve"
            # the grounding by assigning the rotation back to the very tail
            # that had just failed — a no-op that cleared the incident and
            # unfroze the clock — and the failed tail stayed available for its
            # later rotations.
            _ground_aircraft(state, flight["aircraft_reg"], desc, state["clock"])
            inc["grounded_reg"] = flight["aircraft_reg"]
        # Weather/ATC are "extraordinary circumstances" under EU261/UK261 —
        # a flight disrupted by them owes no passenger compensation however
        # late it eventually arrives.
        if kind in COMP_EXEMPT_INCIDENT_TYPES:
            flight["comp_exempt"] = True
        # Apply immediate impact
        if kind == "CREW_SICK" and flight["assigned_crew_ids"]:
            # mark one assigned crew as sick — off the whole pairing (one duty)
            cid = random.choice(flight["assigned_crew_ids"])
            c = next(cc for cc in state["crew"] if cc["id"] == cid)
            c["status"] = "sick"
            c["assigned_flight_id"] = None
            pairing_id = flight.get("pairing_id")
            for pf in state["flights"]:
                if (pf["id"] == flight["id"] or (pairing_id and pf.get("pairing_id") == pairing_id)) \
                        and cid in pf["assigned_crew_ids"]:
                    pf["assigned_crew_ids"].remove(cid)
            inc["affected_crew_id"] = cid
            inc["affected_crew_name"] = c["name"]
        elif kind == "WEATHER":
            flight["delay_min"] += 45 if sev == "minor" else 120
            flight["status"] = "delayed"
        elif kind == "TECH":
            flight["delay_min"] += 60 if sev == "minor" else 240
            flight["status"] = "delayed"
        elif kind == "ATC_FLOW":
            flight["delay_min"] += 30 if sev == "minor" else 90
            flight["status"] = "delayed"
        elif kind == "LATE_REPORT":
            flight["delay_min"] += 20 if sev == "minor" else 60
            flight["status"] = "delayed"

        # Options are computed AFTER the impact so they see the real gap
        inc["options"] = _recovery_options_for(state, flight, kind, sev)

        new_incidents.append(inc)
        state["incidents"].append(inc)

    # ---- Escalate unattended incidents (the price of not deciding) ----
    escalations = []
    for inc in state["incidents"]:
        if inc["status"] != "open" or inc.get("escalated"):
            continue
        raised = datetime.fromisoformat(inc["raised_at"])
        if (clock - raised).total_seconds() / 60 < ESCALATION_AFTER_MIN:
            continue
        fl = next((f for f in state["flights"] if f["id"] == inc["flight_id"]), None)
        if not fl or fl["status"] not in ("scheduled", "delayed", "boarding"):
            continue  # overtaken by events — nothing left to escalate into
        inc["escalated"] = True
        inc["severity"] = "major"
        if inc["type"] == "TECH":
            inc["requires_aircraft_decision"] = True
            # An unattended defect that escalates grounds the tail exactly as
            # one that arrives major does — this is the commoner of the two
            # routes into a clock-freezing grounding, and it must not leave
            # the failed aeroplane quietly available.
            _ground_aircraft(state, fl["aircraft_reg"], inc["description"], state["clock"])
            inc["grounded_reg"] = fl["aircraft_reg"]
        fl["delay_min"] += ESCALATION_EXTRA_DELAY_MIN
        if fl["status"] == "scheduled":
            fl["status"] = "delayed"
        # Re-price the menu from the now-worse live state (major severity also
        # closes doors, e.g. MEL deferral is minor-only).
        inc["options"] = _recovery_options_for(state, fl, inc["type"], "major")
        inc["escalation_note"] = (
            f"Unattended {ESCALATION_AFTER_MIN}min — severity raised to MAJOR, "
            f"{fl['callsign']} +{ESCALATION_EXTRA_DELAY_MIN}min"
        )
        escalations.append({
            "incident_id": inc["id"],
            "flight_callsign": fl["callsign"],
            "added_min": ESCALATION_EXTRA_DELAY_MIN,
        })

    # Maintenance finishing a rectification puts the tail back on line.
    released = release_serviceable_aircraft(state)

    reactionary = _log_cascade(state, propagate_reactionary_delays(state), "tick")

    # ---- Crew timing out (the operation breaking its own duties) ----
    # Run AFTER propagation so the delays are settled, and only for pairings
    # still open. One incident per pairing per day: a duty can only bust once.
    crew_timeouts = []
    seen_pairings = {inc.get("pairing_id") for inc in state["incidents"] if inc["type"] == "CREW_HOURS"}
    for f in state["flights"]:
        if f["status"] not in ("scheduled", "delayed", "boarding"):
            continue
        pid = f.get("pairing_id")
        if pid in seen_pairings:
            continue
        hours_warnings = check_crew_hours(state, f)
        if not hours_warnings:
            continue
        seen_pairings.add(pid)
        meta = INCIDENT_META["CREW_HOURS"]
        inc = {
            "id": _hash_id("INC"),
            "type": "CREW_HOURS",
            "severity": "major",
            "description": hours_warnings[0]["message"],
            "raised_at": state["clock"],
            "flight_id": f["id"],
            "flight_callsign": f["callsign"],
            "pairing_id": pid,
            "status": "open",
            "resolution": None,
            "options": _recovery_options_for(state, f, "CREW_HOURS", "major"),
            "reported_by": meta["desk"],
            "delay_code": meta["delay_code"],
            "escalated": False,
            "crew_warnings": hours_warnings,
        }
        state["incidents"].append(inc)
        new_incidents.append(inc)
        crew_timeouts.append({
            "incident_id": inc["id"], "flight_callsign": f["callsign"],
            "crew_ids": [w["crew_id"] for w in hours_warnings],
        })

    _recompute_kpis(state)
    return {
        "ok": True,
        "new_incidents": new_incidents,
        "reactionary_delays": reactionary,
        "crew_timeouts": crew_timeouts,
        "aircraft_released": released,
        "superseded_decisions": [i["id"] for i in superseded],
        "curfew_violations": curfew_violations,
        "escalations": escalations,
        "compensation_events": comp_events,
        "duty_of_care_events": care_events,
        "clock": state["clock"],
    }


def _missing_ranks(state: dict, flight: dict) -> list[str]:
    """Ranks (in seniority order) where the flight is short of required crew."""
    req = flight["required_crew"]
    counts = {"CP": 0, "FO": 0, "SC": 0, "CC": 0}
    for cid in flight["assigned_crew_ids"]:
        c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
        if c:
            counts[c["rank"]] += 1
    return [r for r in ("CP", "FO", "SC", "CC") if counts[r] < req[r]]


def _legal_candidates(state: dict, flight: dict, rank: str, statuses: tuple[str, ...],
                      ignore_position: bool = False) -> list[dict]:
    """Crew of `rank` in one of `statuses`, type-rated for the flight, passing a
    full legality check. Sorted by fatigue (freshest first).

    `ignore_position` drops CREW_WRONG_STATION from the filter — used when the
    caller intends to POSITION the crew there, which is the one legitimate
    answer to being in the wrong place."""
    type_q = flight["required_crew"]["type_qual"]
    ignorable = {"CREW_WRONG_STATION"} if ignore_position else set()
    out = []
    for c in state["crew"]:
        if c["rank"] != rank or c["status"] not in statuses:
            continue
        if type_q not in c["qualifications"]:
            continue
        blocking = [w for w in check_assignment(state, flight["id"], c["id"])
                    if w["severity"] == "critical" and w["code"] not in ignorable]
        if blocking:
            continue
        out.append(c)
    out.sort(key=lambda c: c["fatigue_score"])
    return out


def _find_recovery_crew(state: dict, flight: dict, statuses: tuple[str, ...],
                        ignore_position: bool = False):
    """First legal crew member covering the flight's worst rank gap, or None."""
    for rank in _missing_ranks(state, flight):
        cands = _legal_candidates(state, flight, rank, statuses, ignore_position)
        if cands:
            return cands[0]
    return None


def _cancellable_pairing_sectors(state: dict, flight: dict) -> list[dict]:
    """This flight plus any not-yet-departed sibling sectors in its pairing —
    cancelling the outbound cancels the crew's return too."""
    pairing_id = flight.get("pairing_id")
    sectors = [flight]
    for f in state["flights"]:
        if (pairing_id and f.get("pairing_id") == pairing_id and f["id"] != flight["id"]
                and f["status"] in ("scheduled", "delayed", "boarding")):
            sectors.append(f)
    return sectors


def _simulate_pairing_impact(state: dict, pairing_id: str, new_reg: str | None, cancel: bool = False) -> int:
    """Read-only what-if: on a SCRATCH copy of the day's flights, either
    re-tail `pairing_id`'s remaining active sectors onto `new_reg` or cancel
    them, then price the result in DOLLARS, so every candidate — swap onto
    tail X, or cancel — is comparable on the same scale the score itself uses.

    Knock-on minutes are charged at DELAY_COST_PER_MIN_USD. A cancellation is
    charged what it actually costs: the per-sector and per-pax cancellation
    bill, UK261 Art. 7 compensation, and Art. 9 care — all of which the engine
    already computes for the real thing. The old delay-minute proxy priced a
    cancel at ~346x any tail swap and made the grader unable to credit a
    correct cancellation.

    If `new_reg` isn't currently at the pairing's departure station, this
    automatically inserts a scratch positioning (ferry) sector first — the
    same repositioning-cost math ferry_spare_aircraft applies for real — so a
    tail that needs ferrying and one that's already in place are graded on
    equal footing. Never mutates the real state."""
    sectors = _pairing_sectors(state, pairing_id)
    flight_ids = {s["id"] for s in sectors}
    scratch = {"flights": copy.deepcopy(state["flights"])}
    reset_reactionary_delays(scratch)

    if cancel:
        cancelled_ids = set()
        cancel_pax = 0
        cancel_sectors = 0
        for f in scratch["flights"]:
            if f["id"] in flight_ids and f["status"] != "cancelled":
                cancel_pax += f.get("pax_count", 0)
                cancel_sectors += 1
                cancelled_ids.add(f["id"])
                f["status"] = "cancelled"
        propagate_reactionary_delays(scratch)
        # Knock-on left in the network AFTER the cancellation, excluding the
        # sectors we just deleted — deleting a flight's own delay is the price
        # of the decision, not a benefit of it (same rule as reset-to-zero).
        knock_on = sum(f.get("reactionary_min", 0) for f in scratch["flights"]
                       if f["id"] not in cancelled_ids)
        bill = 15000 * cancel_sectors + 280 * cancel_pax
        bill += _cancellation_compensation_due(state, cancelled_ids)
        bill += sum(
            f.get("pax_count", 0) * (CARE_MEAL_USD_PER_PAX + CARE_HOTEL_USD_PER_PAX)
            for f in state["flights"]
            if f["id"] in cancelled_ids and not f.get("care_charged")
        )
        return knock_on * DELAY_COST_PER_MIN_USD + bill

    if new_reg:
        plan = _ferry_plan(state, pairing_id, new_reg)
        if plan is not None:
            scratch["flights"].append({
                "id": "SCRATCH-FERRY", "callsign": "FERRY", "aircraft_reg": new_reg,
                "std": plan["std"], "sta": plan["sta"], "block_min": plan["block_min"],
                "status": "scheduled", "delay_min": 0, "reactionary_min": 0, "pax_count": 0,
            })

    for f in scratch["flights"]:
        if f["id"] in flight_ids and f["status"] in _AC_ACTIVE_STATUSES:
            f["aircraft_reg"] = new_reg
    propagate_reactionary_delays(scratch)
    knock_on = sum(f.get("reactionary_min", 0) for f in scratch["flights"])
    return knock_on * DELAY_COST_PER_MIN_USD


def _best_aircraft_decision(state: dict, pairing_id: str) -> dict:
    """Search every tail that could take this pairing right now — either
    directly or via a positioning ferry — plus cancellation, and return
    whichever minimizes total network reactionary delay: the benchmark the
    player's own aircraft decision is graded against. `choice` is a tail
    reg, or the literal string 'cancel'. Uses check_ferry (not
    check_aircraft_assignment) as the candidate filter since ferrying makes
    position a non-issue — a same-type, genuinely free tail is always a
    valid candidate, just possibly an expensive one once its positioning
    time is counted."""
    sectors = _pairing_sectors(state, pairing_id)
    ac_type = sectors[0]["aircraft_type"] if sectors else None
    current_reg = sectors[0]["aircraft_reg"] if sectors else None
    candidates = []
    for ac in state.get("fleet", FLEET):
        if ac["reg"] == current_reg:
            continue
        if ac["type"] == ac_type:
            if any(w["severity"] == "critical" for w in check_ferry(state, pairing_id, ac["reg"])):
                continue
            candidates.append({
                "choice": ac["reg"],
                "impact_usd": _simulate_pairing_impact(state, pairing_id, ac["reg"]),
            })
            continue
        # Off-type tails are real candidates now that substitution exists. If
        # the benchmark pretends they do not, a player who correctly upgauges
        # is graded against a world where their option was impossible.
        if any(w["severity"] == "critical" for w in check_substitution(state, pairing_id, ac["reg"])):
            continue
        sub_pv = preview_substitute_aircraft(state, pairing_id, ac["reg"])
        candidates.append({
            "choice": ac["reg"],
            "substitution": True,
            # The knock-on cost plus what the substitution itself costs — an
            # upgauge is not free, so it must not grade as though it were.
            "impact_usd": (_simulate_pairing_impact(state, pairing_id, ac["reg"])
                           + sub_pv["cost_usd"]),
        })
    candidates.append({
        "choice": "cancel",
        "impact_usd": _simulate_pairing_impact(state, pairing_id, None, cancel=True),
    })
    candidates.sort(key=lambda c: c["impact_usd"])
    return candidates[0]


def _grade_aircraft_decision(state: dict, pairing_id: str, chosen: str) -> dict:
    """Grade the player's aircraft decision (`chosen`: a tail reg, or the
    literal 'cancel') against the best feasible alternative available at the
    moment of the decision. Must be called BEFORE the chosen action mutates
    `state` — it reads live state to find candidates but only ever simulates
    on scratch copies."""
    best = _best_aircraft_decision(state, pairing_id)
    player_impact = _simulate_pairing_impact(
        state, pairing_id, None if chosen == "cancel" else chosen, cancel=(chosen == "cancel")
    )
    delta = player_impact - best["impact_usd"]
    if delta <= 0:
        verdict = "OPTIMAL"
    elif delta <= DECISION_GOOD_THRESHOLD_USD:
        verdict = "GOOD"
    else:
        verdict = "SUBOPTIMAL"
    return {
        "player_choice": chosen,
        "player_impact_usd": player_impact,
        "best_choice": best["choice"],
        "best_impact_usd": best["impact_usd"],
        "delta_usd": delta,
        "verdict": verdict,
    }


def _standby_label(standby: dict | None) -> str:
    if not standby:
        return "Call Out Standby Crew"
    kind = "Airport" if standby.get("standby_type") == STANDBY_AIRPORT else "Home"
    return f"Call Out {kind} Standby (+{standby_response_min(standby)}min)"


def _standby_detail(standby: dict | None) -> str | None:
    if not standby:
        return None
    kind = "airport standby" if standby.get("standby_type") == STANDBY_AIRPORT else "home standby"
    return (
        f"{standby['id']} {standby['name']} ({standby['rank']}) — {kind}, "
        f"{standby_response_min(standby)}min to report"
    )


def _positioning_option(state: dict, flight: dict) -> dict:
    """The positioning lever, priced and feasibility-checked against a real
    inbound sector rather than offered unconditionally."""
    pv = preview_deadhead(state, flight["id"])
    blocking = next((w for w in pv["warnings"] if w["severity"] == "critical"), None)
    crew = pv.get("crew")
    if blocking:
        return {
            "action": "deadhead", "label": "Position Crew (Deadhead)",
            "cost_usd": 0, "otp_hit": 0, "fatigue": 0, "pax_disrupt": False,
            "feasible": False, "reason": blocking["message"], "detail": None,
        }
    plan = pv.get("plan")
    if not pv["needs_positioning"] or not plan:
        return {
            "action": "deadhead", "label": "Position Crew (Deadhead)",
            "cost_usd": 0, "otp_hit": 0, "fatigue": 0, "pax_disrupt": False,
            "feasible": False,
            "reason": (
                f"{crew['id']} is already at {flight['origin']} — reassign them directly, "
                f"there is nothing to position." if crew else "Nobody available to position."
            ),
            "detail": None,
        }
    return {
        "action": "deadhead",
        "label": f"Position Crew via {plan['carrier_callsign']}",
        "cost_usd": pv["cost_usd"], "otp_hit": 6, "fatigue": 8, "pax_disrupt": False,
        "feasible": True, "reason": None,
        "detail": (
            f"{crew['id']} {crew['name']} ({crew['rank']}) rides {plan['carrier_callsign']} "
            f"{plan['from']}→{plan['to']}, in at {plan['arrives'][11:16]}Z"
        ),
    }


def _recovery_options_for(state: dict, flight: dict, kind: str, sev: str) -> list[dict]:
    """Build the decision menu for an incident from the CURRENT state of the
    operation: infeasible actions are flagged (with the reason), costs scale
    with pax count / sector length / severity, and feasible recovery options
    name the actual resource (crew member, spare tail) they would use."""
    pax = flight.get("pax_count", 0)
    block = flight.get("block_min", 0)
    sev_mult = 1.5 if sev == "major" else 1.0

    def opt(action, label, cost, otp_hit=0, fatigue=0, pax_disrupt=False,
            feasible=True, reason=None, detail=None):
        return {
            "action": action, "label": label, "cost_usd": int(cost),
            "otp_hit": otp_hit, "fatigue": fatigue, "pax_disrupt": pax_disrupt,
            "feasible": feasible, "reason": reason, "detail": detail,
        }

    cancel_sectors = _cancellable_pairing_sectors(state, flight)
    cancel_pax = sum(f.get("pax_count", 0) for f in cancel_sectors)
    base = [
        opt("delay", "Hold / Accept Delay", (1500 + pax * 12) * sev_mult, otp_hit=8, fatigue=2),
        opt(
            "cancel",
            "Cancel Flight" if len(cancel_sectors) == 1 else f"Cancel Pairing ({len(cancel_sectors)} sectors)",
            15000 * len(cancel_sectors) + cancel_pax * 280,
            pax_disrupt=True,
            detail=f"{cancel_pax} pax disrupted, crew released",
        ),
    ]

    if kind == "CREW_SICK":
        type_q = flight["required_crew"]["type_qual"]
        gaps = _missing_ranks(state, flight)
        gap_str = "/".join(gaps) if gaps else "crew"
        standby = _find_recovery_crew(state, flight, ("standby",))
        swap = _find_recovery_crew(state, flight, ("available",))
        return [
            opt("callout_standby", _standby_label(standby),
                2500 + (2500 if block > 360 else 0), otp_hit=2, fatigue=5,
                feasible=standby is not None,
                reason=None if standby else f"No legal standby {gap_str} rated {type_q}",
                detail=_standby_detail(standby)),
            opt("swap_crew", "Reassign Available Crew", 1200, otp_hit=4, fatigue=3,
                feasible=swap is not None,
                reason=None if swap else f"No legal available {gap_str} rated {type_q}",
                detail=f"{swap['id']} {swap['name']} ({swap['rank']})" if swap else None),
            _positioning_option(state, flight),
            *base,
        ]
    if kind == "CREW_HOURS":
        type_q = flight["required_crew"]["type_qual"]
        standby = _find_recovery_crew(state, flight, ("standby",))
        swap = _find_recovery_crew(state, flight, ("available",))
        return [
            opt("swap_crew", "Replace With Fresh Crew", 1800, otp_hit=6, fatigue=3,
                feasible=swap is not None,
                reason=None if swap else f"No legal available crew rated {type_q} with the hours left",
                detail=f"{swap['id']} {swap['name']} ({swap['rank']})" if swap else None),
            opt("callout_standby", _standby_label(standby),
                3000 + (2500 if block > 360 else 0), otp_hit=4, fatigue=5,
                feasible=standby is not None,
                reason=None if standby else f"No legal standby crew rated {type_q} with the hours left",
                detail=_standby_detail(standby)),
            # No "hold" option: accepting more delay is what timed the duty out.
            opt("cancel",
                "Cancel Flight" if len(cancel_sectors) == 1 else f"Cancel Pairing ({len(cancel_sectors)} sectors)",
                15000 * len(cancel_sectors) + cancel_pax * 280,
                pax_disrupt=True,
                detail=f"{cancel_pax} pax disrupted, crew stand down out of hours"),
        ]
    if kind == "TECH":
        if sev == "major":
            # Grounded — not MEL-deferrable, can't be held for. The only
            # options resolvable from this card are below; getting the tail
            # flying again means going to Aircraft Control (see
            # requires_aircraft_decision / is_clock_paused), which the whole
            # sim is frozen for until the player acts.
            cancel_label = (
                "Cancel Flight" if len(cancel_sectors) == 1
                else f"Cancel Pairing ({len(cancel_sectors)} sectors)"
            )
            return [
                opt("cancel", cancel_label,
                    15000 * len(cancel_sectors) + cancel_pax * 280,
                    pax_disrupt=True,
                    detail=f"{cancel_pax} pax disrupted, crew released"),
            ]
        return [
            opt("mel_defer", "Accept MEL Deferral", 800, otp_hit=4),
            *base,
        ]
    if kind == "WEATHER":
        return [
            opt("reroute", "Reroute / Alternate Airport", (6000 + pax * 35) * sev_mult,
                otp_hit=25, fatigue=4, pax_disrupt=True),
            *base,
        ]
    if kind == "ATC_FLOW":
        return [
            opt("request_slot", "Request Earlier CTOT Slot", 600, otp_hit=6),
            *base,
        ]
    if kind == "LATE_REPORT":
        return [
            opt("warn_crew", "Issue Verbal Warning", 0, otp_hit=2, fatigue=1),
            *base,
        ]
    return base


def resolve_incident(state: dict, incident_id: str, action: str) -> dict:
    inc = next((i for i in state["incidents"] if i["id"] == incident_id), None)
    if not inc:
        return {"ok": False, "reason": "incident not found"}
    if inc["status"] != "open":
        return {"ok": False, "reason": "already resolved"}
    chosen = next((o for o in inc["options"] if o["action"] == action), None)
    if not chosen:
        return {"ok": False, "reason": "invalid action"}

    flight = next((f for f in state["flights"] if f["id"] == inc["flight_id"]), None)

    # ---- Validate BEFORE charging: the world may have moved on since the
    # options were generated, so feasibility is re-checked live. On failure the
    # incident stays open and nothing is paid.
    replacement = None
    if flight:
        if action == "callout_standby":
            replacement = _find_recovery_crew(state, flight, ("standby",))
            if not replacement:
                return {"ok": False, "incident": inc,
                        "reason": chosen.get("reason") or
                        f"No legal standby crew rated {flight['required_crew']['type_qual']} available."}
        elif action == "swap_crew":
            replacement = _find_recovery_crew(state, flight, ("available",))
            if not replacement:
                return {"ok": False, "incident": inc,
                        "reason": chosen.get("reason") or
                        f"No legal available crew rated {flight['required_crew']['type_qual']}."}
        elif chosen.get("feasible") is False:
            return {"ok": False, "incident": inc,
                    "reason": chosen.get("reason") or "Option not feasible."}

    # A grounded-aircraft incident resolved by cancelling (rather than by a
    # reassignment via Aircraft Control — see assign_aircraft) is graded here,
    # before the cancellation mutates the schedule out from under the
    # what-if search.
    if flight and action == "cancel" and inc.get("requires_aircraft_decision"):
        pairing_id = flight.get("pairing_id")
        if pairing_id:
            inc["decision_grade"] = _grade_aircraft_decision(state, pairing_id, "cancel")

    # ---- Apply (success guaranteed from here)
    cost = chosen.get("cost_usd", 0)
    otp_hit = chosen.get("otp_hit", 0)
    fatigue = chosen.get("fatigue", 0)
    pax_disrupt = chosen.get("pax_disrupt", False)

    state["kpis"]["cost_usd"] += cost
    state["kpis"]["fatigue_index"] = min(100, state["kpis"]["fatigue_index"] + fatigue)
    if flight:
        if action == "cancel":
            # Cancelling the outbound kills the rest of the pairing too, and
            # releases the rostered crew back to the pool.
            to_cancel = _cancellable_pairing_sectors(state, flight)
            released: set[str] = set()
            for cf in to_cancel:
                cf["status"] = "cancelled"
                state["kpis"]["pax_disrupted"] += cf.get("pax_count", 0)
                state["kpis"]["pax_delay_min"] += 240 * cf.get("pax_count", 0)
                for cid in list(cf["assigned_crew_ids"]):
                    cf["assigned_crew_ids"].remove(cid)
                    released.add(cid)
            cost += _charge_cancellation_compensation(state, to_cancel)
            cost += _charge_cancellation_care(state, to_cancel)
            for cid in released:
                c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
                if c and not any(cid in f["assigned_crew_ids"] for f in state["flights"]):
                    c["assigned_flight_id"] = None
                    if c["status"] == "on_duty":
                        c["status"] = "available"
            if len(to_cancel) > 1 or released:
                inc["resolution_note"] = (
                    f"{len(to_cancel)} sector(s) cancelled; "
                    f"{len(released)} crew released to the pool."
                )
        elif action in ("callout_standby", "swap_crew"):
            if inc["type"] == "CREW_HOURS":
                # Out of hours is not "available" — release them from every
                # remaining sector of the pairing and put them into rest, or
                # the replacement just joins a crew that still cannot fly.
                pairing_id = flight.get("pairing_id")
                timed_out = [w["crew_id"] for w in inc.get("crew_warnings", [])]
                for pf in state["flights"]:
                    if pf["id"] != flight["id"] and not (pairing_id and pf.get("pairing_id") == pairing_id):
                        continue
                    if pf["status"] in ("landed", "cancelled"):
                        continue
                    for cid in timed_out:
                        if cid in pf["assigned_crew_ids"]:
                            pf["assigned_crew_ids"].remove(cid)
                for cid in timed_out:
                    c = next((cc for cc in state["crew"] if cc["id"] == cid), None)
                    if c:
                        c["status"] = "rest"
                        c["assigned_flight_id"] = None
                inc["stood_down_crew_ids"] = timed_out
            # assign_crew handles the whole pairing + legality bookkeeping
            assign_crew(state, flight["id"], replacement["id"])
            replacement["status"] = "on_duty"
            inc["replacement_crew_id"] = replacement["id"]
            inc["replacement_crew_name"] = replacement["name"]
            if action == "swap_crew":
                flight["delay_min"] += 20
            elif action == "callout_standby":
                # Getting them from the crew room or from home is not free.
                notice = standby_response_min(replacement)
                flight["delay_min"] += notice
                flight["status"] = "delayed"
                inc["callout_notice_min"] = notice
        elif action == "reroute":
            flight["status"] = "diverted"
            flight["delay_min"] += 180
            state["kpis"]["pax_disrupted"] += int(flight.get("pax_count", 0) * 0.5)
        elif action == "delay":
            flight["delay_min"] += 30
            flight["status"] = "delayed"
        elif action == "mel_defer":
            ac = next((a for a in state.get("fleet", FLEET) if a["reg"] == flight["aircraft_reg"]), None)
            if ac is not None:
                cats, weights = zip(*MEL_CATEGORY_WEIGHTS.items())
                cat = random.choices(cats, weights=weights)[0]
                item = {
                    "id": _hash_id("MEL"),
                    "category": cat,
                    "note": inc["description"],
                    "days_remaining": MEL_CATEGORY_LIMITS_DAYS[cat],
                    "expired": False,
                }
                ac.setdefault("mel_items", []).append(item)
                flight["note"] = f"MEL deferral accepted (Cat {cat}, {item['days_remaining']}d limit)"
            else:
                flight["note"] = "MEL deferral accepted"
        elif action == "request_slot":
            flight["delay_min"] = max(0, flight["delay_min"] - 15)
        elif action == "warn_crew":
            pass
        elif action == "deadhead":
            pv = preview_deadhead(state, flight["id"])
            plan, dh_crew = pv.get("plan"), pv.get("crew")
            if plan and dh_crew:
                crew_obj = next(c for c in state["crew"] if c["id"] == dh_crew["id"])
                crew_obj.setdefault("positioning", []).append(plan)
                # ORO.FTL.215: positioning counts as duty and as FDP, but it is
                # NOT a sector — it does not push the crew down the FDP table.
                crew_obj["fdp_used_min"] = crew_obj.get("fdp_used_min", 0) + plan["block_min"]
                crew_obj["duty_7d_hr"] = round(
                    crew_obj.get("duty_7d_hr", 0) + plan["block_min"] / 60, 2)
                # They arrive when they arrive; the duty cannot start before.
                arrives = datetime.fromisoformat(plan["arrives"])
                report_by = arrives + timedelta(minutes=DEADHEAD_REPORT_BUFFER_MIN)
                std = datetime.fromisoformat(flight["std"]) + timedelta(
                    minutes=flight.get("delay_min", 0))
                if report_by > std:
                    flight["delay_min"] += int((report_by - std).total_seconds() // 60)
                    flight["status"] = "delayed"
                assign_crew(state, flight["id"], crew_obj["id"], force=True)
                crew_obj["status"] = "on_duty"
                inc["positioned_crew_id"] = crew_obj["id"]
                inc["positioning_plan"] = plan
            else:
                # Nothing connects — the option should not have been offered,
                # but never silently succeed if it was.
                flight["delay_min"] += 45

        if pax_disrupt and action != "cancel":
            state["kpis"]["pax_disrupted"] += int(flight.get("pax_count", 0) * 0.4)
        state["kpis"]["pax_delay_min"] += flight.get("delay_min", 0)

    inc["status"] = "resolved"
    inc["resolution"] = action
    inc["resolution_label"] = chosen["label"]
    inc["resolved_at"] = state["clock"]
    reactionary_before = _network_reactionary_total(state)
    state["decisions_log"].append({
        "ts": state["clock"], "incident_id": incident_id, "action": action,
        "cost_usd": cost, "otp_hit": otp_hit,
        "flight_callsign": inc.get("flight_callsign"),
        "incident_type": inc.get("type"),
        "verdict": (inc.get("decision_grade") or {}).get("verdict"),
    })
    reactionary = _log_cascade(state, propagate_reactionary_delays(state),
                               f"incident_{action}", incident_id)
    # Knock-on minutes this specific decision put into the network — the
    # number that makes the debrief able to rank decisions by damage.
    state["decisions_log"][-1]["reactionary_caused_min"] = max(
        0, _network_reactionary_total(state) - reactionary_before)
    _recompute_kpis(state)
    return {
        "ok": True,
        "incident": inc,
        "kpis": state["kpis"],
        "reactionary_delays": reactionary,
    }


def reset_reactionary_delays(state: dict) -> None:
    """Strip previously-applied reactionary delay back to its non-reactionary
    baseline (whatever delay an incident etc. directly caused).

    `propagate_reactionary_delays` only ever adds — it has no way to know a
    knock-on it applied earlier is no longer warranted once its root cause is
    gone. That happens when a tail is reassigned mid-OPS: the rotation that
    picked up delay from a late inbound aircraft may now be flown by a
    different, on-time tail. Call this before re-propagating after any change
    to the aircraft-to-rotation mapping, so delay is rebuilt from scratch
    rather than compounding on top of stale knock-on.
    """
    for f in state["flights"]:
        extra = f.get("reactionary_min", 0)
        if not extra:
            continue
        f["delay_min"] = max(0, f.get("delay_min", 0) - extra)
        f["reactionary_min"] = 0
        if (f.get("note") or "").startswith("REACTIONARY"):
            f["note"] = ""
        if f["status"] == "delayed" and f["delay_min"] <= 0:
            f["status"] = "scheduled"


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "advisory": 2}


def _time_pressure_severity(state: dict, flight: dict | None,
                            warn_min: int) -> str:
    """How urgent a condition on `flight` is, from how long is left before it
    goes. A problem four hours out is a task; the same problem twenty minutes
    out is blocking. Without this, three of five codes were flat `critical`
    and the BLOCKING count carried no information at all."""
    if flight is None:
        return "critical"
    try:
        dep = datetime.fromisoformat(flight["std"]) + timedelta(
            minutes=flight.get("delay_min", 0))
        left = (dep - datetime.fromisoformat(state["clock"])).total_seconds() / 60
    except (KeyError, ValueError):
        return "critical"
    if left <= 60:
        return "critical"
    if left <= warn_min:
        return "warning"
    return "advisory"


def crew_irregularities(state: dict) -> list[dict]:
    """Everything currently wrong with the crewing picture, derived from the
    RULES rather than from random events.

    Every exception the player sees today is an incident card — something that
    happened to them. Real crew tracking leads with a live irregularities list
    (AIMS "Live Display of all Irregularities that need to be actioned",
    NetLine/Crew's Problem Monitor, Jeppesen's Alert Monitor): open sectors,
    duties about to bust, crew out of position. Those are conditions, not
    events, and nothing surfaced them.

    Returns the house `{code, severity, message, rule_ref}` shape, worst first.
    """
    out: list[dict] = []
    # Flights and pairings the game has already put on a card. Presenting the
    # same condition in both streams is the canonical nuisance-alarm pattern —
    # one busted duty rendered as a card AND as one monitor line per crew
    # member, six lines for one card on a 2+4 crew.
    incident_flights = {
        i.get("flight_id") for i in state.get("incidents", []) if i["status"] == "open"
    }
    incident_pairings = {
        i.get("pairing_id") for i in state.get("incidents", []) if i["status"] == "open"
    }
    suppressed: list[dict] = []

    def emit(w, covered=False):
        (suppressed if covered else out).append(w)

    # Open sectors — uncovered flying. The real desk's first question.
    completeness = roster_completeness(state)
    for m in completeness["missing"]:
        gaps = ", ".join(f"{n}x {r}" for r, n in m["need"].items() if n)
        if not gaps:
            continue
        fl = next((f for f in state["flights"] if f["id"] == m["flight_id"]), None)
        emit({
            "code": "OPEN_SECTOR",
            "severity": _time_pressure_severity(state, fl, warn_min=240),
            "message": f"{m['callsign']} is uncovered — short {gaps}.",
            "rule_ref": "Operational — crew complement",
            "flight_id": m["flight_id"],
            "pairing_id": fl.get("pairing_id") if fl else None,
        }, covered=m["flight_id"] in incident_flights)

    # Duties that will not make it at the delays standing right now.
    seen_pairings: set = set()
    for f in state["flights"]:
        if f["status"] not in ("scheduled", "delayed", "boarding"):
            continue
        pid = f.get("pairing_id")
        if pid in seen_pairings:
            continue
        for w in check_crew_hours(state, f):
            seen_pairings.add(pid)
            info = crew_duty_clock(state, w["crew_id"])
            slack = info["slack_min"] if info and info["on_duty"] else None
            emit({
                **w, "code": "FDP_TIMEOUT_PENDING",
                # Graded off the room actually left, not a flat critical.
                "severity": ("critical" if slack is None or slack < 0
                             else "warning" if slack <= 60 else "advisory"),
                "flight_id": f["id"], "pairing_id": pid,
            }, covered=pid in incident_pairings or f["id"] in incident_flights)

    # Crew rostered somewhere they physically are not.
    for f in state["flights"]:
        if f["status"] not in ("scheduled", "delayed", "boarding"):
            continue
        dep = datetime.fromisoformat(f["std"]) + timedelta(minutes=f.get("delay_min", 0))
        for cid in f.get("assigned_crew_ids", []):
            if _crew_position_before(state, cid, dep) != f["origin"]:
                crew = next((c for c in state["crew"] if c["id"] == cid), None)
                emit({
                    "code": "CREW_OUT_OF_POSITION",
                    # Blocking only once there is no longer time to position
                    # them; the deadhead report buffer is the real lead time.
                    "severity": _time_pressure_severity(
                        state, f, warn_min=DEADHEAD_REPORT_BUFFER_MIN * 4),
                    "crew_id": cid,
                    "message": (
                        f"{cid} {crew['name'] if crew else ''} is rostered on {f['callsign']} "
                        f"out of {f['origin']} but will not be there — position them or replace them."
                    ),
                    "rule_ref": "Operational — crew positioning",
                    "flight_id": f["id"], "pairing_id": f.get("pairing_id"),
                }, covered=f["id"] in incident_flights)

    # Crew at the consecutive-duty limit.
    for c in state["crew"]:
        if c.get("days_since_off", 0) >= MAX_CONSECUTIVE_DUTY_DAYS:
            emit({
                "code": "DAYS_OFF_DUE", "severity": "advisory",
                "message": (
                    f"{c['id']} {c['name']} has worked {c['days_since_off']} consecutive "
                    f"duty days — a day off is due."
                ),
                "rule_ref": "ORO.FTL.235 / industrial agreement",
            })

    # The reserve bank itself. Running it to zero is how a small problem
    # becomes an unrecoverable one.
    for rank in ("CP", "FO"):
        pool = [c for c in state["crew"] if c["rank"] == rank and c["status"] == "standby"]
        if len(pool) <= 1:
            emit({
                "code": "STANDBY_POOL_LOW",
                "severity": "warning" if len(pool) == 0 else "advisory",
                "message": (
                    f"{len(pool)} {rank} left on standby. The next sickness or timeout has "
                    f"nowhere to go."
                ),
                "rule_ref": "Operational — reserve cover",
            })

    state["_suppressed_irregularities"] = suppressed
    out.sort(key=lambda w: _SEVERITY_ORDER.get(w["severity"], 3))
    return out


def crew_irregularities_full(state: dict) -> dict:
    """Irregularities plus the ones held back because an incident already
    covers them. Returned separately rather than dropped, so the desk can say
    "3 held by open incidents" and nothing is ever hidden from the player."""
    live = crew_irregularities(state)
    return {
        "irregularities": live,
        "suppressed": state.pop("_suppressed_irregularities", []),
    }


# ------------------- Crew disposition desk ------------------- #
#
# Where a stranded crew gets DEALT WITH. The engine has always known that crew
# have a physical position; until now the only thing it did with that knowledge
# was raise a warning ending "position them or replace them" — neither of which
# the player could actually do. Real crew tracking works this population as a
# queue with a fixed option set, and these are those options.

_DISPOSITION_ACTIONS = ("position_home", "hold_downroute", "recrew_local", "night_stop")


def _next_duty_for(state: dict, crew_id: str) -> dict | None:
    """The next sector this crew is rostered to operate, if any."""
    upcoming = [
        f for f in state["flights"]
        if crew_id in f.get("assigned_crew_ids", [])
        and f["status"] in ("scheduled", "delayed", "boarding")
    ]
    upcoming.sort(key=lambda f: f["std"])
    return upcoming[0] if upcoming else None


def _disposition_options(state: dict, crew: dict, at: str) -> list[dict]:
    """The priced, feasibility-checked menu for one out-of-position crew.

    Same `{action, label, cost_usd, feasible, reason, detail}` shape the
    incident queue already renders, so the desk reuses that component."""
    base = crew.get("base", AIRLINE["hub"])
    hotac = CREW_HOTEL_USD + CREW_TRANSPORT_USD + CREW_PERDIEM_USD
    next_duty = _next_duty_for(state, crew["id"])
    opts = []

    # 1. Position home — fly them back as passengers. ORO.FTL.215: counts as
    #    duty and FDP but not as a sector.
    leg = _positioning_leg(state, crew["id"], base)
    opts.append({
        "action": "position_home",
        "label": f"Position Home via {leg['carrier_callsign']}" if leg else "Position Home",
        "cost_usd": DEADHEAD_SEAT_USD + DEADHEAD_HANDLING_USD if leg else 0,
        "feasible": leg is not None,
        "reason": None if leg else f"No sector from {at} to {base} left today.",
        "detail": (
            f"rides {leg['carrier_callsign']} {leg['from']}->{leg['to']}, "
            f"in at {leg['arrives'][11:16]}Z; +{leg['block_min']}min FDP, not a sector"
        ) if leg else None,
    })

    # 2. Hold down-route — leave them to operate the return. Looks free; it is
    #    a hotel bill and it locks the crew out of everything else.
    opts.append({
        "action": "hold_downroute",
        "label": "Hold Down-Route For The Return",
        "cost_usd": hotac,
        "feasible": next_duty is not None and next_duty["origin"] == at,
        "reason": (
            None if next_duty is not None and next_duty["origin"] == at
            else f"Nothing rostered for them out of {at} to hold for."
        ),
        "detail": (
            f"holds for {next_duty['callsign']} {next_duty['std'][11:16]}Z; "
            f"HOTAC {hotac} USD, unavailable elsewhere until then"
        ) if next_duty else None,
    })

    # 3. Re-crew locally — use somebody already at that station instead. For a
    #    single-base airline this is usually impossible, and saying so plainly
    #    is more useful than hiding the option.
    local = None
    if next_duty is not None:
        for rank in ("CP", "FO", "SC", "CC"):
            cands = [
                c for c in _legal_candidates(state, next_duty, rank, ("available", "standby"))
                if c["id"] != crew["id"]
                and _crew_position_before(state, c["id"], datetime.fromisoformat(next_duty["std"])) == at
            ]
            if cands:
                local = cands[0]
                break
    opts.append({
        "action": "recrew_local",
        "label": "Re-Crew Locally",
        "cost_usd": 1200 if local else 0,
        "feasible": local is not None,
        "reason": None if local else f"No legal crew already at {at} to take it.",
        "detail": f"{local['id']} {local['name']} ({local['rank']}) is at {at}" if local else None,
        "replacement_crew_id": local["id"] if local else None,
    })

    # 4. Night-stop — book the hotel, stand them down, pick them up tomorrow.
    #    This is what happens today by default, silently and for free.
    opts.append({
        "action": "night_stop",
        "label": "Night-Stop On Hotel Account",
        "cost_usd": hotac,
        "feasible": True,
        "reason": None,
        "detail": f"HOTAC {hotac} USD at {at}; released to rest, off tomorrow's roster",
    })
    return opts


def crew_disposition(state: dict) -> list[dict]:
    """Every crew member who is not where they need to be, with what can be
    done about each of them.

    One row per crew, worst first: those with a duty they cannot make ahead of
    those merely away from base."""
    rows = []
    handled = 0
    now = datetime.fromisoformat(state["clock"])
    for c in state["crew"]:
        if c["status"] in ("sick", "off"):
            continue
        # Already dealt with today. This is a worklist, so a resolved item
        # leaves it — otherwise the player cannot tell what they have done.
        # Cleared at the day rollover.
        if c.get("disposition"):
            handled += 1
            continue
        base = c.get("base", AIRLINE["hub"])
        at = _crew_position_before(state, c["id"], now)
        next_duty = _next_duty_for(state, c["id"])
        # A crew down-route with their next duty departing from where they
        # actually are is not a problem — that is an ordinary long-haul
        # night-stop, and 49 of them would bury the handful that need a call.
        # The desk is for crew who need a DECISION: a duty they cannot reach,
        # or nowhere to go from where they are.
        misplaced = next_duty is not None and next_duty["origin"] != at
        adrift = at != base and next_duty is None
        if not misplaced and not adrift:
            continue
        clock_info = crew_duty_clock(state, c["id"])
        rows.append({
            "crew_id": c["id"], "name": c["name"], "rank": c["rank"],
            "base": base, "at": at,
            "why": "unreachable_duty" if misplaced else "no_way_back",
            "status": c["status"],
            "disposition": c.get("disposition"),
            "next_duty": {
                "flight_id": next_duty["id"], "callsign": next_duty["callsign"],
                "origin": next_duty["origin"], "destination": next_duty["destination"],
                "std": next_duty["std"],
                "reachable": not misplaced,
            } if next_duty else None,
            "slack_min": clock_info["slack_min"] if clock_info and clock_info["on_duty"] else None,
            "options": _disposition_options(state, c, at),
        })
    # A crew who cannot make a duty they are rostered on is the urgent case.
    rows.sort(key=lambda r: (0 if (r["next_duty"] and not r["next_duty"]["reachable"]) else 1,
                             r["at"], r["crew_id"]))
    for r in rows:
        r["handled_today"] = handled
    return rows


def preview_crew_disposition(state: dict, crew_id: str, action: str) -> dict:
    """Read-only price for one disposition action, per the preview convention
    every costly lever in this engine follows."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not crew:
        return {"ok": False, "reason": "Crew not found."}
    if action not in _DISPOSITION_ACTIONS:
        return {"ok": False, "reason": f"Unknown disposition action '{action}'."}
    at = _crew_position_before(state, crew_id, datetime.fromisoformat(state["clock"]))
    opt = next((o for o in _disposition_options(state, crew, at) if o["action"] == action), None)
    return {"ok": True, "crew_id": crew_id, "at": at, "option": opt}


def dispose_crew(state: dict, crew_id: str, action: str) -> dict:
    """Act on an out-of-position crew. Mirrors resolve_incident: validate
    live, then apply, then log."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not crew:
        return {"ok": False, "applied": False, "reason": "Crew not found."}
    if action not in _DISPOSITION_ACTIONS:
        return {"ok": False, "applied": False, "reason": f"Unknown action '{action}'."}

    now = datetime.fromisoformat(state["clock"])
    at = _crew_position_before(state, crew_id, now)
    opt = next((o for o in _disposition_options(state, crew, at) if o["action"] == action), None)
    if not opt or not opt["feasible"]:
        return {"ok": False, "applied": False,
                "reason": (opt or {}).get("reason") or "Option not available."}

    base = crew.get("base", AIRLINE["hub"])
    cost = opt["cost_usd"]
    note = None

    if action == "position_home":
        leg = _positioning_leg(state, crew_id, base)
        if not leg:
            return {"ok": False, "applied": False,
                    "reason": "The connection went while you were deciding."}
        crew.setdefault("positioning", []).append(leg)
        # ORO.FTL.215: positioning is duty and FDP, but not a sector.
        crew["fdp_used_min"] = crew.get("fdp_used_min", 0) + leg["block_min"]
        crew["duty_7d_hr"] = round(crew.get("duty_7d_hr", 0) + leg["block_min"] / 60, 2)
        crew["station"] = base
        # They are going home, so they are not operating whatever they were on.
        _release_crew_from_future_sectors(state, crew_id)
        note = (f"{crew_id} positioned {leg['from']}->{leg['to']} on "
                f"{leg['carrier_callsign']}, in {leg['arrives'][11:16]}Z")

    elif action == "hold_downroute":
        crew["station"] = at
        crew["hotac_nights"] = crew.get("hotac_nights", 0) + 1
        note = f"{crew_id} held at {at} for the return"

    elif action == "recrew_local":
        next_duty = _next_duty_for(state, crew_id)
        replacement = next(
            (c for c in state["crew"] if c["id"] == opt.get("replacement_crew_id")), None)
        if not next_duty or not replacement:
            return {"ok": False, "applied": False, "reason": "Local crew no longer available."}
        _release_crew_from_future_sectors(state, crew_id)
        assign_crew(state, next_duty["id"], replacement["id"])
        replacement["status"] = "on_duty"
        note = f"{replacement['id']} took {next_duty['callsign']} at {at}; {crew_id} released"

    elif action == "night_stop":
        crew["station"] = at
        crew["hotac_nights"] = crew.get("hotac_nights", 0) + 1
        crew["status"] = "rest"
        _release_crew_from_future_sectors(state, crew_id)
        note = f"{crew_id} night-stopping at {at}, released to rest"

    crew["disposition"] = {"action": action, "at": at, "ts": state["clock"]}
    state["kpis"]["cost_usd"] += cost
    if action in ("hold_downroute", "night_stop"):
        state["kpis"]["hotac_usd"] = state["kpis"].get("hotac_usd", 0) + cost
    state["decisions_log"].append({
        "ts": state["clock"], "incident_id": f"DISPOSITION {crew_id}",
        "action": f"disposition_{action}", "cost_usd": cost, "otp_hit": 0,
        "flight_callsign": None, "incident_type": "CREW_DISPOSITION",
    })
    reactionary = _log_cascade(state, propagate_reactionary_delays(state),
                               f"disposition_{action}", crew_id)
    _recompute_kpis(state)
    return {"ok": True, "applied": True, "crew_id": crew_id, "action": action,
            "cost_usd": cost, "note": note, "reactionary_delays": reactionary,
            "kpis": state["kpis"]}


def _release_crew_from_future_sectors(state: dict, crew_id: str) -> None:
    """Take a crew off everything they have not yet operated."""
    for f in state["flights"]:
        if f["status"] in ("landed", "cancelled", "airborne"):
            continue
        if crew_id in f.get("assigned_crew_ids", []):
            f["assigned_crew_ids"].remove(crew_id)
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if crew:
        crew["assigned_flight_id"] = None


def crew_duty_clock(state: dict, crew_id: str) -> dict | None:
    """Live duty picture for one crew member: how much FDP their current
    pairing will consume at the delays standing right now, what their cap is,
    how much slack is left, and the latest the pairing can go off-blocks
    before they bust it.

    This is the number a real crew controller watches all shift — "when do
    they go illegal" — and it moves every time the operation slips."""
    crew = next((c for c in state["crew"] if c["id"] == crew_id), None)
    if not crew:
        return None
    assigned = [f for f in state["flights"]
                if crew_id in f.get("assigned_crew_ids", []) and f["status"] != "cancelled"]
    # A duty that has fully landed is finished, not running.
    if not any(f["status"] != "landed" for f in assigned):
        assigned = []
    if not assigned:
        return {
            "crew_id": crew_id, "on_duty": False, "fdp_used_min": crew.get("fdp_used_min", 0),
            "fdp_projected_min": crew.get("fdp_used_min", 0), "fdp_cap_min": None,
            "slack_min": None, "latest_off_blocks": None, "delay_min": 0,
        }
    assigned.sort(key=lambda f: f["std"])
    lead = assigned[0]
    total, scheduled, delay, sectors = _pairing_fdp_min(state, lead)
    cap, basis = _fdp_cap_for_flight(
        lead, sectors=sectors, acclimatised=_crew_acclimatised(state, crew, lead))
    # `_pairing_fdp_min` spans the WHOLE pairing, report to final on-blocks —
    # including sectors already flown. Those sectors have also been added to
    # fdp_used_min as they landed, so only duty from OTHER pairings may be
    # carried on top, or the flown legs get counted twice.
    flown_here = sum(f["block_min"] for f in assigned if f["status"] == "landed")
    prior_duty = max(0, crew.get("fdp_used_min", 0) - flown_here)
    projected = prior_duty + total
    slack = cap - projected

    # Report is 60 min before the first STD; the FDP must end by report + cap,
    # and it ends at the final on-blocks plus 30 min post-flight.
    report = datetime.fromisoformat(lead["std"]) - timedelta(minutes=60)
    latest_off_blocks = report + timedelta(minutes=cap - prior_duty - 30)
    return {
        "crew_id": crew_id, "on_duty": True,
        "fdp_used_min": crew.get("fdp_used_min", 0), "prior_duty_min": prior_duty,
        "fdp_projected_min": projected, "fdp_cap_min": cap, "fdp_basis": basis,
        "fdp_scheduled_min": scheduled, "delay_min": delay,
        "slack_min": slack, "legal": slack >= 0,
        "latest_off_blocks": latest_off_blocks.isoformat(),
        "pairing_id": lead.get("pairing_id"),
    }


def check_crew_hours(state: dict, flight: dict) -> list[dict]:
    """Whether the crew already rostered on `flight` can still legally finish
    the pairing at the delays standing right now. Same `check_*` contract as
    every other legality gate — a list of `{code, severity, message,
    rule_ref}` warnings, critical meaning the duty busts.

    Distinct from `check_assignment`, which asks "may I put this crew on this
    flight?" at rostering time. This asks the question a delay creates:
    "is the crew I already have still legal?"."""
    warnings: list[dict] = []
    if flight["status"] in ("cancelled", "landed"):
        return warnings
    for cid in flight.get("assigned_crew_ids", []):
        clock_info = crew_duty_clock(state, cid)
        if not clock_info or not clock_info["on_duty"] or clock_info["legal"]:
            continue
        crew = next((c for c in state["crew"] if c["id"] == cid), None)
        over = -clock_info["slack_min"]
        warnings.append({
            "code": "FDP_TIMEOUT", "severity": "critical",
            "message": (
                f"{cid} {crew['name'] if crew else ''} ({crew['rank'] if crew else '?'}) "
                f"times out {over}min before this pairing can finish — "
                f"{clock_info['delay_min']}min of accumulated delay has pushed the duty to "
                f"{clock_info['fdp_projected_min']//60}h{clock_info['fdp_projected_min']%60:02d}m "
                f"against a {clock_info['fdp_cap_min']//60}h cap. "
                f"Off-blocks by {datetime.fromisoformat(clock_info['latest_off_blocks']).strftime('%H:%MZ')} or the duty is illegal."
            ),
            "rule_ref": "ORO.FTL.205 / CS FTL.1.205",
            "crew_id": cid, "over_by_min": over,
        })
    return warnings


def _log_cascade(state: dict, affected: list[dict], trigger: str,
                 trigger_id: str | None = None) -> list[dict]:
    """Persist the causal edges `propagate_reactionary_delays` just produced.

    The engine already knows exactly which inbound made which outbound late;
    without this the player only ever sees the resulting number and
    experiences reactionary delay as weather rather than as consequence.
    `trigger` names what the player did (or what happened to them) so the
    debrief can attribute the cascade to a decision."""
    if not affected:
        return affected
    log = state.setdefault("cascade_log", [])
    for edge in affected:
        log.append({
            "ts": state.get("clock"),
            "trigger": trigger,
            "trigger_id": trigger_id,
            **edge,
        })
    return affected


def propagate_reactionary_delays(state: dict) -> list[dict]:
    """Roll knock-on (reactionary) delays down each aircraft's day.

    For every tail, walk its sectors in schedule order tracking when the
    aircraft is actually ready again (estimated arrival + minimum turnaround).
    Any later sector that would depart before its aircraft is ready picks up
    the difference as reactionary delay. Re-running only ever adds delay on
    top of what's already applied — it cannot shrink a knock-on whose cause
    has gone away (e.g. a tail swap). Call `reset_reactionary_delays` first
    when the aircraft-to-rotation mapping has changed.
    """
    affected: list[dict] = []
    by_reg: dict[str, list[dict]] = {}
    for f in state["flights"]:
        by_reg.setdefault(f["aircraft_reg"], []).append(f)

    for _reg, sectors in by_reg.items():
        sectors.sort(key=lambda f: f["std"])
        ready_at: datetime | None = None
        inbound: dict | None = None
        for f in sectors:
            if f["status"] == "cancelled":
                # Sector never flies; the tail stays wherever it was.
                continue
            std = datetime.fromisoformat(f["std"])
            eff_dep = std + timedelta(minutes=f.get("delay_min", 0))
            if (
                ready_at is not None
                and eff_dep < ready_at
                and f["status"] in ("scheduled", "delayed", "boarding")
            ):
                extra = int((ready_at - eff_dep).total_seconds() // 60)
                if extra > 0:
                    f["delay_min"] += extra
                    f["reactionary_min"] = f.get("reactionary_min", 0) + extra
                    if f["status"] == "scheduled":
                        f["status"] = "delayed"
                    note = f.get("note") or ""
                    if not note or note.startswith("REACTIONARY"):
                        f["note"] = (
                            f"REACTIONARY (IATA 93) · inbound {inbound['callsign']} late"
                            if inbound else "REACTIONARY (IATA 93) · aircraft late"
                        )
                    affected.append({
                        "flight_id": f["id"],
                        "callsign": f["callsign"],
                        "added_min": extra,
                        "inbound_callsign": inbound["callsign"] if inbound else None,
                    })
                    eff_dep = std + timedelta(minutes=f["delay_min"])
            eff_arr = eff_dep + timedelta(minutes=f["block_min"])
            turnaround = MIN_TURNAROUND_MIN + (
                DIVERSION_RECOVERY_MIN if f["status"] == "diverted" else 0
            )
            ready_at = eff_arr + timedelta(minutes=turnaround)
            inbound = f
    return affected


def _recompute_kpis(state: dict) -> None:
    flights = state["flights"]
    if not flights:
        return
    # OTP is measured on OPERATED flights, the way airlines actually report it
    # — a cancelled sector is not a late sector. Cancelling instead shows up in
    # the completion factor, so the two levers are priced separately rather
    # than a cancellation being punished twice through one number.
    operated = [f for f in flights if f["status"] != "cancelled"]
    on_time = sum(1 for f in operated if f.get("delay_min", 0) <= 15)
    state["kpis"]["otp_pct"] = round(100.0 * on_time / len(operated), 1) if operated else 100.0
    state["kpis"]["completion_factor_pct"] = round(100.0 * len(operated) / len(flights), 1)

    # Reactionary minutes are the currency every recovery lever trades in, so
    # they have to cost something. The engine already computes them; this is
    # simply the first time the player is charged for them.
    reactionary = sum(f.get("reactionary_min", 0) for f in flights)
    state["kpis"]["reactionary_min"] = reactionary
    state["kpis"]["delay_cost_usd"] = reactionary * DELAY_COST_PER_MIN_USD

    # Score
    s = 1000
    s -= state["kpis"]["legality_breaches"] * 80
    s -= int(state["kpis"]["cost_usd"] / 1000)
    s -= int(state["kpis"]["delay_cost_usd"] / 1000)
    s -= int(state["kpis"]["pax_disrupted"] / 5)
    s -= max(0, int((75 - state["kpis"]["otp_pct"]) * 5))
    s -= max(0, int((TARGET_COMPLETION_FACTOR_PCT - state["kpis"]["completion_factor_pct"]) * 8))
    state["kpis"]["score"] = s


def start_day(state: dict) -> dict:
    if state["phase"] != "ROSTER":
        return {"ok": False, "reason": "already started"}
    state["phase"] = "OPS"
    return {"ok": True}


def restart_day(state: dict) -> dict:
    """Reset the current day to its start: clock back to 04:00Z, incidents
    cleared, decisions wiped, flight delays/status reset, KPIs reset to fresh.
    The roster (crew assignments to flights) is preserved.
    """
    state["clock"] = state["day_start"]
    state["incidents"] = []
    state["decisions_log"] = []
    state["cascade_log"] = []
    state["tick_count"] = 0
    state["phase"] = "OPS"
    state["kpis"] = {
        "otp_pct": 100.0,
        "legality_breaches": 0,
        "curfew_violations": 0,
        "compensation_usd": 0,
        "fatigue_index": int(sum(c["fatigue_score"] for c in state["crew"]) / max(1, len(state["crew"]))),
        "cost_usd": 0,
        "pax_delay_min": 0,
        "pax_disrupted": 0,
        "reactionary_min": 0,
        "duty_of_care_usd": 0,
        "hotac_usd": 0,
        "discretion_used_count": 0,
        "discretion_reports": 0,
        "delay_cost_usd": 0,
        "completion_factor_pct": 100.0,
        "score": 1000,
    }
    # Reset flight runtime fields, keep crew assignments
    for f in state["flights"]:
        f["status"] = "scheduled"
        f["delay_min"] = 0
        f["reactionary_min"] = 0
        # One-shot per-day flags must re-arm on a restart (the curfew-checked
        # flags previously survived restarts, so a restarted day was never
        # curfew-checked again — latent bug fixed alongside the comp flags)
        f.pop("curfew_dep_checked", None)
        f.pop("curfew_arr_checked", None)
        f.pop("curfew_violation", None)
        f.pop("comp_charged", None)
        f.pop("comp_exempt", None)
        # Don't clobber the night-stop return note
        if not (f.get("note") or "").startswith("RETURN FROM NIGHT-STOP"):
            f["note"] = ""
    # Restore any sick crew that became sick during this day's ops back to on-duty
    # Cleanest approach: if a crew was assigned to any flight, they're on_duty again
    assigned_ids = {cid for f in state["flights"] for cid in f["assigned_crew_ids"]}
    for c in state["crew"]:
        c["fdp_used_min"] = 0  # reset FDP accumulation for the fresh restart
        if c["id"] in assigned_ids:
            c["status"] = "on_duty"
            # Make sure assigned_flight_id is set to one of the assigned flights
            c["assigned_flight_id"] = next(
                (f["id"] for f in state["flights"] if c["id"] in f["assigned_crew_ids"]),
                None,
            )
        elif c["status"] == "sick":
            # Crew that called in sick AT DAY START stay sick; this is a coarse approximation
            pass
    return {"ok": True, "clock": state["clock"]}


def end_day(state: dict) -> dict:
    state["phase"] = "DEBRIEF"
    _recompute_kpis(state)
    open_inc = [i for i in state["incidents"] if i["status"] == "open"]
    return {
        "ok": True,
        "kpis": state["kpis"],
        "flights": state["flights"],
        "open_incidents": len(open_inc),
        "decisions": state["decisions_log"],
    }


def summarize_state_for_advisor(state: dict, focus_incident_id: str | None = None) -> dict:
    """Compact state summary for the LLM advisor."""
    upcoming = []
    clock = datetime.fromisoformat(state["clock"])
    for f in state["flights"]:
        std = datetime.fromisoformat(f["std"])
        if std >= clock - timedelta(hours=1) and std <= clock + timedelta(hours=4):
            upcoming.append({
                "callsign": f["callsign"],
                "ac_type": f["aircraft_type"],
                "route": f"{f['origin']}-{f['destination']}",
                "std": f["std"][11:16],
                "status": f["status"],
                "delay_min": f["delay_min"],
                "crew_assigned": len(f["assigned_crew_ids"]),
                "crew_required_total": sum(f["required_crew"][r] for r in ("CP","FO","SC","CC")),
            })
    standby = {
        "CP": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="CP"),
        "FO": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="FO"),
        "SC": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="SC"),
        "CC": sum(1 for c in state["crew"] if c["status"]=="standby" and c["rank"]=="CC"),
    }
    sick = sum(1 for c in state["crew"] if c["status"]=="sick")
    open_inc = [i for i in state["incidents"] if i["status"]=="open"]
    focus = None
    if focus_incident_id:
        focus = next((i for i in state["incidents"] if i["id"]==focus_incident_id), None)
    return {
        "airline": state["airline"]["name"],
        "phase": state["phase"],
        "clock_utc": state["clock"][11:16],
        "kpis": state["kpis"],
        "standby_pool": standby,
        "sick_count": sick,
        "open_incidents": [{
            "id": i["id"], "type": i["type"], "severity": i["severity"],
            "flight": i["flight_callsign"], "desc": i["description"],
        } for i in open_inc[:6]],
        "upcoming_flights": upcoming[:8],
        "focus_incident": focus,
    }


# ------------------- MongoDB-safe sanitiser ------------------- #

def strip_mongo_id(doc: dict) -> dict:
    if not doc:
        return doc
    doc = dict(doc)
    doc.pop("_id", None)
    return doc
