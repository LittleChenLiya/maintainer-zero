import pytest

from maintainer_zero.simulation import SimulationConfig, SimulationEvent, run_simulation


def test_capacity_outage_accumulates_and_recovers_deterministically():
    config = SimulationConfig(days=5, initial_capacity=1, daily_demand=1)
    events = [
        SimulationEvent(1, "outage", capacity_delta=-1),
        SimulationEvent(3, "restored", capacity_delta=1),
    ]
    result = run_simulation(events, config)

    assert [row["backlog"] for row in result.timeline] == [0, 1, 2, 2, 2, 2]
    assert result.ending_backlog == 2
    assert result.peak_backlog == 2
    assert result.service_level == pytest.approx(4 / 6)


def test_same_day_events_are_sorted_and_out_of_range_events_ignored():
    config = SimulationConfig(days=1, initial_capacity=0, daily_demand=0)
    result = run_simulation(
        [
            SimulationEvent(1, "z-last", capacity_delta=2),
            SimulationEvent(1, "a-first", capacity_delta=-1),
            SimulationEvent(99, "ignored", capacity_delta=100),
        ],
        config,
    )

    assert result.timeline[1]["events"] == ["a-first", "z-last"]
    # Capacity is clamped after each event: -1 from zero stays zero, then +2.
    assert result.timeline[1]["capacity"] == 2
    assert all("ignored" not in row["events"] for row in result.timeline)


def test_invalid_inputs_are_rejected():
    with pytest.raises(ValueError):
        SimulationConfig(days=-1)
    with pytest.raises(ValueError):
        run_simulation([SimulationEvent(-1, "bad")])
