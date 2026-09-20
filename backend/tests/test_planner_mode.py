import simulation as sim


def test_planner_mode_opens_a_28_day_roster_window():
    state = sim.new_game("planner_28", seed=120)

    assert state["is_planner_mode"] is True
    assert state["planning_horizon_days"] == 28
    assert state["phase"] == "ROSTER"

    roster = sim.crew_roster(state)
    assert len(roster["columns"]) == 28
    assert roster["columns"][0]["day"] == 1
    assert roster["columns"][-1]["day"] == 28
