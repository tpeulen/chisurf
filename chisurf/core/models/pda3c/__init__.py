"""Three-colour PDA fitting models (PRD-65).

Compute lives in :mod:`chisurf.core.fluorescence.pda3c`; this package is the
ChiSurf model layer around it, with editor layouts in the co-located
``*.view.json`` files (PRD-38 model/view-spec split).
"""

from __future__ import annotations

from .pda3c import Pda3cModel, Pda3cSetup, Pda3cSpecies  # noqa: F401

__all__ = ["Pda3cModel", "Pda3cSetup", "Pda3cSpecies"]
