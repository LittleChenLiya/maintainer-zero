"""Continuity drills for open-source projects."""

from .simulation import SimulationConfig, SimulationEvent, SimulationResult, run_simulation
from .metadata_mapping import normalize_metadata

__version__ = "0.2.0"

__all__ = [
    "SimulationConfig",
    "SimulationEvent",
    "SimulationResult",
    "run_simulation",
    "normalize_metadata",
    "__version__",
]
