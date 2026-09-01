"""Reactionary delay that travels with the crew, not only with the metal.

Until this existed `propagate_reactionary_delays` chained knock-on down each
tail and nothing else, so a crew landing an hour late was, as far as the
engine was concerned, available to operate their next sector on time. That
made the network far too forgiving in one direction (crew lateness simply
vanished) and made recovery levers look worthless in the other: cancelling a
pairing could only ever relieve later sectors on the *same* tail, so
reset-to-zero routinely showed no benefit at all.

The chain binds only where a crew connection actually exists — same station,
sector not cancelled — because a crew whose next sector leaves from somewhere
else is an out-of-position crew, which is a different problem with its own
checks (see test_disposition.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulation as sim  # noqa: E402
from test_tier3 import _crew, _flight, _state  # noqa: E402


CREW = ["CP1", "FO1"]


def _connected_day(first_delay=0, second_std="08:30", second_reg="G-BBBB"):
    """One crew, an inbound and an onward, connecting through LHR.

    EGW100 CDG->LHR 06:00 (75min) lands 07:15, so with MIN_CREW_TURNAROUND_MIN
    of 30 the crew are ready to go again at 07:45 and the 08:30 departure is
    comfortable. Delay the inbound and the connection tightens minute for
    minute; the onward is a different tail, so nothing here is the aircraft
    chain's doing.
    """
    inbound = _flight("EGW100", "G-AAAA", "A320", "06:00", 75, "PAIR-1",
                      origin="CDG", destination="LHR", crew_ids=CREW,
                      delay_min=first_delay,
                      status="delayed" if first_delay else "scheduled")
    onward = _flight("EGW200", second_reg, "A320", second_std, 90, "PAIR-2",
                     origin="LHR", destination="MAD", crew_ids=CREW)
    crew = [_crew("CP1", "CP", "A Commander"), _crew("FO1", "FO", "A Officer")]
    return _state([inbound, onward], crew=crew)


def _by_callsign(state, callsign):
    return next(f for f in state["flights"] if f["callsign"] == callsign)


# --------------------------------------------------------------------------
# The chain itself
# --------------------------------------------------------------------------

def test_a_late_crew_makes_their_next_sector_late():
    # Inbound runs 60 late: off at 07:00, in at 08:15, crew ready 08:45
    # against an 08:30 departure they are rostered on.
    st = _connected_day(first_delay=60, second_std="08:30")
    sim.propagate_reactionary_delays(st)

    nxt = _by_callsign(st, "EGW200")
    assert nxt["delay_min"] == 15
    assert nxt["reactionary_min"] == 15
    assert nxt["status"] == "delayed"


def test_the_delay_is_attributed_to_the_crew_not_the_aircraft():
    # The point of the cascade log is that the player can see *why*. A sector
    # held for its crew and one held for its aircraft are different problems
    # and lead to different recovery decisions.
    st = _connected_day(first_delay=60, second_std="08:30")
    edges = sim.propagate_reactionary_delays(st)

    crew_edges = [e for e in edges if e["kind"] == "crew"]
    assert len(crew_edges) == 1
    assert crew_edges[0]["callsign"] == "EGW200"
    assert crew_edges[0]["inbound_callsign"] == "EGW100"
    assert "crew off EGW100 late" in _by_callsign(st, "EGW200")["note"]


def test_a_comfortable_connection_is_left_alone():
    # Same hour of delay, but a 10:00 departure. Crew ready 08:45; nothing due.
    st = _connected_day(first_delay=60, second_std="10:00")
    sim.propagate_reactionary_delays(st)

    nxt = _by_callsign(st, "EGW200")
    assert nxt["delay_min"] == 0
    assert nxt["status"] == "scheduled"


def test_an_on_time_crew_delays_nothing():
    st = _connected_day(first_delay=0, second_std="08:30")
    edges = sim.propagate_reactionary_delays(st)
    assert [e for e in edges if e["kind"] == "crew"] == []


def test_a_crew_whose_next_sector_leaves_elsewhere_is_not_a_delay():
    # They land at LHR and are rostered out of MAD. That is an out-of-position
    # crew — a positioning decision, not a sector to be held. Charging delay
    # here would quietly hide the real problem behind a plausible number.
    st = _connected_day(first_delay=120, second_std="08:30")
    _by_callsign(st, "EGW200")["origin"] = "MAD"
    edges = sim.propagate_reactionary_delays(st)

    assert [e for e in edges if e["kind"] == "crew"] == []
    assert _by_callsign(st, "EGW200")["delay_min"] == 0


def test_a_sector_waits_for_its_last_crew_member():
    # Two crew joining the same sector off different inbounds: the departure
    # is held by the later of the two, and charged once rather than once per
    # crew member.
    st = _connected_day(first_delay=60, second_std="08:30")
    _by_callsign(st, "EGW100")["assigned_crew_ids"] = ["CP1"]   # captain only
    # The FO comes off a long sector landing LHR at 09:30, ready 10:00.
    st["flights"].append(
        _flight("EGW300", "G-CCCC", "A320", "07:00", 150, "PAIR-3",
                origin="MAD", destination="LHR", crew_ids=["FO1"]))

    edges = sim.propagate_reactionary_delays(st)
    crew_edges = [e for e in edges if e["kind"] == "crew"
                  and e["callsign"] == "EGW200"]

    assert len(crew_edges) == 1, "charged once for the sector, not per crew"
    # The FO's 10:00 against an 08:30 departure is 90, and beats the
    # captain's 15.
    assert _by_callsign(st, "EGW200")["delay_min"] == 90
    assert crew_edges[0]["inbound_callsign"] == "EGW300"


# --------------------------------------------------------------------------
# The two chains feed each other
# --------------------------------------------------------------------------

def test_crew_delay_carries_on_into_the_aircraft_it_boards():
    # This is why the passes have to reach a fixed point. A late crew delays
    # G-BBBB's departure; G-BBBB is then late back for its own next rotation,
    # which no single pass of either chain alone would catch.
    st = _connected_day(first_delay=120, second_std="08:30")
    st["flights"].append(
        _flight("EGW201", "G-BBBB", "A320", "11:00", 90, "PAIR-4",
                origin="MAD", destination="LHR"))

    edges = sim.propagate_reactionary_delays(st)

    # Crew ready 09:45 against 08:30 => EGW200 +75, into MAD 11:15, tail ready
    # 12:00 against EGW201's 11:00 => +60 on a tail nothing was wrong with.
    assert _by_callsign(st, "EGW200")["delay_min"] == 75
    assert _by_callsign(st, "EGW201")["delay_min"] == 60
    kinds = {e["callsign"]: e["kind"] for e in edges}
    assert kinds["EGW200"] == "crew"
    assert kinds["EGW201"] == "aircraft"


def test_propagation_settles_and_does_not_run_away():
    # Every pass only ever adds, so a bug in the loop shows up as delay that
    # keeps climbing. Re-running a settled network must change nothing.
    st = _connected_day(first_delay=120, second_std="08:30")
    st["flights"].append(
        _flight("EGW201", "G-BBBB", "A320", "11:00", 90, "PAIR-4",
                origin="MAD", destination="LHR"))
    sim.propagate_reactionary_delays(st)
    settled = {f["callsign"]: f["delay_min"] for f in st["flights"]}

    assert sim.propagate_reactionary_delays(st) == []
    assert {f["callsign"]: f["delay_min"] for f in st["flights"]} == settled


# --------------------------------------------------------------------------
# What this unblocks: cancelling now releases a crew, not just a tail
# --------------------------------------------------------------------------

def test_cancelling_a_pairing_releases_its_crew_for_what_they_fly_next():
    # The reason reset-to-zero so often showed no benefit: relief could only
    # travel down the same tail, and most chosen pairings had no later sector
    # on that tail. Standing a pairing down also frees its crew, and that
    # relief is now visible.
    st = _connected_day(first_delay=120, second_std="08:30")
    sim.propagate_reactionary_delays(st)
    assert _by_callsign(st, "EGW200")["delay_min"] == 75

    st2 = _connected_day(first_delay=120, second_std="08:30")
    for f in st2["flights"]:
        if f["pairing_id"] == "PAIR-1":
            f["status"] = "cancelled"
    sim.reset_reactionary_delays(st2)
    sim.propagate_reactionary_delays(st2)

    assert _by_callsign(st2, "EGW200")["delay_min"] == 0, (
        "the crew never flew the cancelled pairing, so they make the 08:30")


def test_reset_strips_crew_chained_delay_too():
    # reset_reactionary_delays has to undo everything propagation applied, or
    # a tail swap leaves stale crew knock-on behind and delay compounds.
    st = _connected_day(first_delay=120, second_std="08:30")
    sim.propagate_reactionary_delays(st)
    sim.reset_reactionary_delays(st)

    nxt = _by_callsign(st, "EGW200")
    assert nxt["delay_min"] == 0
    assert nxt["reactionary_min"] == 0
    assert nxt["status"] == "scheduled"
    assert _by_callsign(st, "EGW100")["delay_min"] == 120, (
        "the incident's own delay is not reactionary and must survive")


def test_a_cancelled_sector_does_not_position_a_crew():
    # A cancelled sector never flew, so it cannot be the inbound that makes
    # anything late.
    st = _connected_day(first_delay=300, second_std="08:30")
    _by_callsign(st, "EGW100")["status"] = "cancelled"
    edges = sim.propagate_reactionary_delays(st)

    assert [e for e in edges if e["inbound_callsign"] == "EGW100"] == []
    assert _by_callsign(st, "EGW200")["delay_min"] == 0


# --------------------------------------------------------------------------
# Guards on the surrounding machinery
# --------------------------------------------------------------------------

def test_flights_with_no_crew_assigned_are_simply_skipped():
    # Preview/what-if paths build scratch states, and one of them appends a
    # synthetic ferry leg carrying no crew keys at all.
    st = _connected_day(first_delay=60, second_std="08:30")
    st["flights"].append({
        "id": "SCRATCH-FERRY", "callsign": "FERRY", "aircraft_reg": "G-ZZZZ",
        "std": "2026-06-12T09:00:00+00:00", "sta": "2026-06-12T10:00:00+00:00",
        "block_min": 60, "status": "scheduled", "delay_min": 0,
        "reactionary_min": 0, "pax_count": 0,
    })
    sim.propagate_reactionary_delays(st)      # must not raise
    assert _by_callsign(st, "FERRY")["delay_min"] == 0


def test_a_crew_staying_with_their_aircraft_is_not_charged_twice():
    # The tail's 45-minute turn already covers the 30-minute crew connection,
    # so on a straight out-and-back the crew chain must be a no-op and the
    # delay must be the aircraft's alone.
    assert sim.MIN_CREW_TURNAROUND_MIN < sim.MIN_TURNAROUND_MIN

    inbound = _flight("EGW100", "G-AAAA", "A320", "06:00", 75, "PAIR-1",
                      origin="CDG", destination="LHR", crew_ids=CREW,
                      delay_min=60, status="delayed")
    # Same tail, same crew, a realistic 60-minute scheduled turn at LHR.
    back = _flight("EGW101", "G-AAAA", "A320", "08:15", 75, "PAIR-1",
                   origin="LHR", destination="CDG", crew_ids=CREW)
    st = _state([inbound, back],
                crew=[_crew("CP1", "CP", "A"), _crew("FO1", "FO", "B")])

    edges = sim.propagate_reactionary_delays(st)

    assert [e for e in edges if e["kind"] == "crew"] == []
    # In at 08:15, tail ready 09:00, against an 08:15 departure => 45.
    assert _by_callsign(st, "EGW101")["delay_min"] == 45
