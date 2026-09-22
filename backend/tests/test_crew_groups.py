import simulation as sim


def test_crew_groups_are_saved_by_id_and_can_be_replaced():
    state = sim.new_game("planner_28", seed=4)
    ids = [crew["id"] for crew in state["crew"][:3]]

    saved = sim.save_crew_group(state, "A320 Early", ids, "SHORT_HAUL")
    replaced = sim.save_crew_group(state, "A320 Early", ids[:2])

    assert saved["ok"] is True
    assert replaced["replaced"] is True
    assert sim.crew_groups(state) == [{"id": "a320-early", "name": "A320 Early", "crew_ids": sorted(ids[:2]), "operation": "SHORT_HAUL"}]


def test_crew_group_requires_a_name_and_known_crew():
    state = sim.new_game("planner_28", seed=4)

    assert sim.save_crew_group(state, "", ["missing"])["error"] == "group_name_required"
    assert sim.save_crew_group(state, "Empty", ["missing"])["error"] == "group_requires_crew"
