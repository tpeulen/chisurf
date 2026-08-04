"""The one place ChiSurf drives the photon simulator.

The simulator itself is not here and is not ChiSurf's. Diffusion through a focus,
kinetic exchange during a transit, micro-time patterns, anisotropy, ALEX, flow and
scanning all live in the TTTR library's ``SimEngine`` — C++ written for that
purpose, with its own tests and its own documentation
(``doc/simulator-guide.rst`` there is the reference for what a config means).

What lives here is the *shim*: the small amount of glue that every ChiSurf caller
needs and that was, until this module existed, written out again at each of them —
four copies of the engine's configuration dictionary, four ways of asking whether
the simulator is available at all, three spellings of a seed, and two
implementations of "write this simulation as a burst-analysis folder".

The rule that keeps it small: **anything that is physics goes to the simulator,
anything that is a ChiSurf file format stays here.** So the burst-folder writer is
here, because the ``.bur`` layout is a ChiSurf concern the TTTR library has no
opinion about; but there is deliberately no code here that samples a decay, walks
a kinetic scheme or places a molecule, because all three would be a second
implementation of something that already exists.

See :doc:`the species encoding reference </okf/references/simengine-species-encoding>`
for how to express a measurement in the engine's terms — the recurring mistake is
to look for a parameter named after the phenomenon rather than to encode it.
"""

from chisurf.core.fluorescence.simulation.engine import (
    build_engine,
    decay_spec,
    default_config,
    gaussian_focus,
    have_simulator,
    settings,
)
from chisurf.core.fluorescence.simulation.folders import write_burst_folder
from chisurf.core.fluorescence.simulation.rng import seeds

__all__ = [
    "build_engine",
    "decay_spec",
    "default_config",
    "gaussian_focus",
    "have_simulator",
    "seeds",
    "settings",
    "write_burst_folder",
]
