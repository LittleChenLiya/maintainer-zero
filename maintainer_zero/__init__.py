"""Continuity drills for open-source projects."""

from .simulation import SimulationConfig, SimulationEvent, SimulationResult, run_simulation

__version__ = "0.1.0"

__all__ = [
    "SimulationConfig",
    "SimulationEvent",
    "SimulationResult",
    "run_simulation",
    "__version__",
]
