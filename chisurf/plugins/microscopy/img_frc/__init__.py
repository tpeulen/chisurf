"""FRC resolution calculator: how fine a detail an image actually resolves.

Layout (the client-server plugin standard):

- ``core.py``    — Qt-free compute over the shared image-source seam.
- ``api/``       — transport-agnostic functions + the RPC contract constants.
- ``backend/``   — RPC service registration (``img_frc.*`` methods).
- ``client.py``  — typed client used by the CLI and the GUI alike.
- ``cli/``       — the headless ``frc-resolution`` command.
- ``gui/``       — AutoForm view spec + Qt-free view model + thin tool window.
"""

from .core import FrcAnalysis, analyse, halves

__all__ = ["FrcAnalysis", "analyse", "halves"]
