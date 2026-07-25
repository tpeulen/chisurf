"""Three-colour PDA fitting models (PRD-65).

Compute lives in :mod:`chisurf.core.fluorescence.pda3c`; this package is the
ChiSurf model layer around it, with editor layouts in the co-located
``*.view.json`` files (PRD-38 model/view-spec split).
"""

from __future__ import annotations

from .tcpda import TcPdaModel, TcPdaSetup, TcPdaSpecies  # noqa: F401

__all__ = ["TcPdaModel", "TcPdaSetup", "TcPdaSpecies"]
