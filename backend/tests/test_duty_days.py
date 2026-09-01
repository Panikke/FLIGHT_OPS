"""Multi-pairing duty days: a crew's day is bounded by hours, not by pairings.

The engine used to give every crew exactly one pairing. `auto_roster` marked
them on_duty on assignment and never reconsidered them, and the crew pool was
sized to match, so headcount — not FTL — was what limited a roster. That is
backwards: the whole purpose of an FDP scheme is that duty *hours* are the
binding constraint, and a real short-haul crew flies two, three or four
sectors across one duty.

The change that makes this safe is that FDP is now measured across the whole
duty. ORO.FTL.205 runs a Flight Duty Period from report to the final
on-blocks as one continuous span; it does not restart because the crew
changed aircraft. Summing pairings with a nominal turnaround — what the
engine did before — let a crew sit at an airport for hours between two
out-and-backs and register none of it as duty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402
from test_tier3 import _crew, _flight, _state  # noqa: E402


def _two_pairing_day(second_std="20:00", second_block=120):
    """A crew already rostered on an early LHR out-and-back, plus a second
    pairing out of LHR they are being considered for.

    EGW100 06:00 LHR-CDG (75) lands 07:15; EGW101 08:15 CDG-LHR (75) lands
    09:30. Report was 05:00.
    """
    p1a = _flight("EGW100", "G-AAAA", "A320", "06:00", 75, "PAIR-1",
                  origin="LHR", destination="CDG", crew_ids=["CP1"])
    p1b = _flight("EGW101", "G-AAAA", "A320", "08:15", 75, "PAIR-1",
                  origin="CDG", destination="LHR", crew_ids=["CP1"])
    p2 = _flight("EGW200", "G-BBBB", "A320", second_std, second_block, "PAIR-2",
                 origin="LHR", destination="MAD")
    return _state([p1a, p1b, p2], crew=[_crew("CP1", "CP", "A Commander")])


def _codes(warnings, severity="critical"):
    return {w["code"] for w in warnings if w["severity"] == severity}


# --------------------------------------------------------------------------
# FDP spans the duty, not the pairing
# --------------------------------------------------------------------------

def test_the_duty_clock_counts_the_ground_time_between_two_pairings():
    # Report 05:00, final on-blocks 22:00, +30 post-flight = 17h30. The old
    # per-pairing sum saw only the two blocks plus a nominal turn and would
    # have called this a little over 5 hours of duty.
    st = _two_pairing_day(second_std="20:00", second_block=120)
    sectors = st["flights"]
    total, scheduled, delay, count = sim._duty_fdp_min(sectors)

    assert count == 3
    assert scheduled == 17 * 60 + 30
    assert delay == 0 and total == scheduled

    naive = sum(f["block_min"] for f in sectors) + 60 + 30 + 2 * 60
    assert scheduled > naive, "the sit between pairings has to count as duty"


def test_a_second_pairing_that_bursts_the_duty_is_refused():
    # 05:00 report against a 20:00 departure is a 17h30 duty. No short-haul
    # FDP cap reaches that, whatever the sector count.
    st = _two_pairing_day(second_std="20:00")
    warnings = sim.check_assignment(st, "FLT-EGW200", "CP1")

    assert "FDP_EXCEED" in _codes(warnings)
    msg = next(w for w in warnings if w["code"] == "FDP_EXCEED")["message"]
    assert "duty" in msg
    assert "ORO.FTL.205" in msg or "ORO.FTL.205" in next(
        w for w in warnings if w["code"] == "FDP_EXCEED")["rule_ref"]


def test_a_second_pairing_that_fits_inside_the_duty_is_allowed():
    # Back at LHR 09:30, out again at 10:30, done by 12:00. Report 05:00, so
    # a 7h30 duty — a perfectly ordinary short-haul four-sector day.
    st = _two_pairing_day(second_std="10:30", second_block=90)
    warnings = sim.check_assignment(st, "FLT-EGW200", "CP1")

    assert _codes(warnings) == set(), (
        f"expected a legal second pairing, got {warnings}")


def test_the_fdp_cap_is_set_by_when_the_duty_started():
    # A crew who reported at 05:00 stays on the 05:00 band all day. Reading
    # the band off the sector being added instead would hand a crew a fresh,
    # more generous cap every time they changed aircraft.
    st = _two_pairing_day(second_std="10:30", second_block=90)
    sim.assign_crew(st, "FLT-EGW200", "CP1")
    clock = sim.crew_duty_clock(st, "CP1")

    lead = next(f for f in st["flights"] if f["callsign"] == "EGW100")
    expected_cap, _ = sim._fdp_cap_for_flight(lead, sectors=3)
    assert clock["fdp_cap_min"] == expected_cap
    assert clock["fdp_projected_min"] == 7 * 60 + 30


def test_the_duty_clock_follows_the_crew_across_both_pairings():
    st = _two_pairing_day(second_std="10:30", second_block=90)
    before = sim.crew_duty_clock(st, "CP1")["fdp_projected_min"]
    sim.assign_crew(st, "FLT-EGW200", "CP1")
    after = sim.crew_duty_clock(st, "CP1")["fdp_projected_min"]

    # Adding a sector that lands at 12:00 extends a duty that previously
    # ended at 09:30 by exactly those two and a half hours.
    assert after - before == 150


# --------------------------------------------------------------------------
# Crew connection time
# --------------------------------------------------------------------------

def test_a_connection_the_crew_cannot_physically_make_is_refused():
    # In at 09:30, out at 09:45. They are in the right city and the duty is
    # short, but they cannot get off one aircraft and onto another in 15min.
    st = _two_pairing_day(second_std="09:45", second_block=90)
    warnings = sim.check_assignment(st, "FLT-EGW200", "CP1")

    assert "CREW_CONNECTION" in _codes(warnings)
    msg = next(w for w in warnings if w["code"] == "CREW_CONNECTION")["message"]
    assert "15min connection" in msg


def test_the_connection_minimum_is_exactly_that_a_minimum():
    st = _two_pairing_day(second_std="10:00", second_block=90)
    assert "CREW_CONNECTION" not in _codes(sim.check_assignment(
        st, "FLT-EGW200", "CP1")), "09:30 in, 10:00 out is exactly 30min"


def test_a_tight_connection_is_a_judgement_call_not_a_wall():
    # Crew constraints are overridable; physical ones are not. A controller
    # may back a tight connection and wear the consequence.
    st = _two_pairing_day(second_std="09:45", second_block=90)
    res = sim.assign_crew(st, "FLT-EGW200", "CP1", force=True)
    assert res["ok"] and res["applied"]
    assert "CP1" in next(
        f for f in st["flights"] if f["callsign"] == "EGW200")["assigned_crew_ids"]


# --------------------------------------------------------------------------
# What the roster actually builds
# --------------------------------------------------------------------------

def _rostered_crew(state):
    by_crew = {}
    for f in state["flights"]:
        for cid in f.get("assigned_crew_ids", []):
            by_crew.setdefault(cid, []).append(f)
    for fs in by_crew.values():
        fs.sort(key=lambda f: f["std"])
    return by_crew


def test_auto_roster_builds_duty_days_rather_than_one_pairing_per_crew():
    # Whether any single generated day happens to contain a workable double
    # depends on how that day's banks fall, so this is an aggregate claim:
    # across a spread of days the roster must be building duties, not
    # spending one crew per pairing the way it used to.
    doubles = 0
    for seed in range(1, 9):
        st = sim.new_game("free_play", seed=seed)
        sim.auto_roster(st)
        doubles += sum(1 for fs in _rostered_crew(st).values()
                       if len({f.get("pairing_id") for f in fs}) > 1)

    assert doubles > 0, "no crew anywhere was given a second pairing"


def test_an_extended_duty_keeps_a_planning_margin():
    # A duty rostered right up to the cap times out on the first minute of
    # delay. Planners build below the legal limit, and so does this.
    for seed in range(1, 9):
        st = sim.new_game("free_play", seed=seed)
        sim.auto_roster(st)
        for cid, fs in _rostered_crew(st).items():
            if len({f.get("pairing_id") for f in fs}) < 2:
                continue            # a single pairing is the schedule's shape
            total, _s, _d, n = sim._duty_fdp_min(fs)
            cap, _b = sim._fdp_cap_for_flight(fs[0], sectors=n)
            assert cap - total >= sim.ROSTER_FDP_BUFFER_MIN, (
                f"seed {seed}: {cid} rostered to within {cap - total}min of "
                f"the cap, under the {sim.ROSTER_FDP_BUFFER_MIN}min margin")


def test_no_rostered_duty_is_illegal():
    # The greedy may only extend a duty where the full legality check passes,
    # so a finished roster must contain no crew already over their cap.
    for seed in (1, 4, 7):
        st = sim.new_game("free_play", seed=seed)
        sim.auto_roster(st)
        for c in st["crew"]:
            clock = sim.crew_duty_clock(st, c["id"])
            if clock and clock["on_duty"]:
                assert clock["legal"], (
                    f"seed {seed}: {c['id']} rostered over cap by "
                    f"{-clock['slack_min']}min")


def test_a_crew_is_never_rostered_somewhere_they_cannot_be():
    # Station continuity and connection time across a whole rostered day.
    for seed in (1, 4, 7):
        st = sim.new_game("free_play", seed=seed)
        sim.auto_roster(st)
        by_crew = {}
        for f in st["flights"]:
            for cid in f.get("assigned_crew_ids", []):
                by_crew.setdefault(cid, []).append(f)
        for cid, fs in by_crew.items():
            fs.sort(key=lambda f: f["std"])
            for prev, nxt in zip(fs, fs[1:]):
                if prev["destination"] != nxt["origin"]:
                    continue        # a night-stop or a positioning problem
                gap = sim._add_minutes_to_clock(
                    prev["std"], prev["block_min"])
                from datetime import datetime
                arr = datetime.fromisoformat(gap)
                dep = datetime.fromisoformat(nxt["std"])
                mins = (dep - arr).total_seconds() / 60
                assert mins >= sim.MIN_CREW_TURNAROUND_MIN, (
                    f"seed {seed}: {cid} has a {mins:.0f}min connection "
                    f"{prev['callsign']}->{nxt['callsign']}")
