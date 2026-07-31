"""Flow maps: the velocity field of a sample, read off its own correlations.

Layout (the client-server plugin standard):

- ``core.py``    — Qt-free compute over the shared image-source seam.
- ``demo.py``    — a simulated photon stream with a *known* flow, for learning
                   and for the closed-loop test.
- ``api/``       — transport-agnostic functions + the RPC contract constants.
- ``backend/``   — RPC service registration (``img_flow.*`` methods).
- ``client.py``  — typed client used by the CLI and the GUI alike.
- ``cli/``       — the headless ``img-flow`` command.
- ``gui/``       — AutoForm view spec, Qt-free view model, guided tour, thin tool.

There is no fit and no model here: a velocity is read off where a correlation
peak *is*, not off a parameter released in a transport model.
"""

from .core import FlowAnalysis, analyse, analyse_file, scan_timing

__all__ = ["FlowAnalysis", "analyse", "analyse_file", "scan_timing"]
