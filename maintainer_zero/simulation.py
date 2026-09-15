"""Deterministic discrete-event engine used by continuity drills.

The engine models work units rather than GitHub objects. A scenario converts
an incident into dated events; this keeps simulations reproducible and
explainable without network access.

At each simulated day, events are applied, new demand is added, and available
capacity services the backlog. No random numbers or wall-clock timestamps are
used, so identical inputs always produce identical results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True, order=True)
class SimulationEvent:
    """A change applied at the beginning of a simulated day.

    capacity_delta and demand_delta are work units per day. Deltas persist
    until another event changes them. Metadata is copied into the result
    timeline for human-readable reports.
    """

    day: int
    name: str
    capacity_delta: float = 0.0
    demand_delta: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class SimulationConfig:
    """Initial conditions and bounds for a simulation."""

    days: int = 90
    initial_capacity: float = 1.0
    daily_demand: float = 1.0
    initial_backlog: float = 0.0

    def __post_init__(self) -> None:
        if self.days < 0:
            raise ValueError("days must be non-negative")
        if self.initial_capacity < 0 or self.daily_demand < 0 or self.initial_backlog < 0:
            raise ValueError("capacity, demand, and backlog must be non-negative")


@dataclass
class SimulationResult:
    """Time series and aggregate metrics emitted by run_simulation."""

    days: int
    completed: float
    ending_backlog: float
    peak_backlog: float
    first_zero_backlog_day: int | None
    timeline: list[dict[str, Any]]

    @property
    def service_level(self) -> float:
        """Fraction of generated demand completed during the drill."""

        generated = sum(float(row["demand"]) for row in self.timeline)
        return 1.0 if generated == 0 else min(1.0, self.completed / generated)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["service_level"] = round(self.service_level, 4)
        return data


def run_simulation(
    events: Iterable[SimulationEvent] = (),
    config: SimulationConfig | None = None,
) -> SimulationResult:
    """Run a deterministic backlog simulation.

    Events outside 0..days are ignored, while negative event days are
    rejected as likely authoring errors. Multiple events on one day are
    applied in name order, making results independent of input iteration
    order. Capacity is clamped at zero after each change.
    """

    cfg = config or SimulationConfig()
    normalized: list[SimulationEvent] = []
    for event in events:
        if event.day < 0:
            raise ValueError("event day must be non-negative")
        if event.day <= cfg.days:
            normalized.append(event)
    normalized.sort(key=lambda event: (event.day, event.name))
    by_day: dict[int, list[SimulationEvent]] = {}
    for event in normalized:
        by_day.setdefault(event.day, []).append(event)

    capacity = cfg.initial_capacity
    demand_rate = cfg.daily_demand
    backlog = cfg.initial_backlog
    completed = 0.0
    peak = backlog
    # Record the first day *after servicing* on which backlog is zero.  An
    # initially empty queue is not considered recovered if day-zero demand
    # immediately creates work that cannot be serviced.
    first_zero: int | None = None
    timeline: list[dict[str, Any]] = []

    for day in range(cfg.days + 1):
        applied = by_day.get(day, [])
        for event in applied:
            capacity = max(0.0, capacity + event.capacity_delta)
            demand_rate = max(0.0, demand_rate + event.demand_delta)
        demand = demand_rate
        backlog += demand
        serviced = min(backlog, capacity)
        backlog -= serviced
        completed += serviced
        peak = max(peak, backlog)
        if backlog == 0 and first_zero is None:
            first_zero = day
        timeline.append(
            {
                "day": day,
                "events": [event.name for event in applied],
                "capacity": round(capacity, 6),
                "demand": round(demand, 6),
                "serviced": round(serviced, 6),
                "backlog": round(backlog, 6),
            }
        )

    return SimulationResult(
        days=cfg.days,
        completed=completed,
        ending_backlog=backlog,
        peak_backlog=peak,
        first_zero_backlog_day=first_zero,
        timeline=timeline,
    )


__all__ = ["SimulationConfig", "SimulationEvent", "SimulationResult", "run_simulation"]
