"""Three-colour PDA fitting models (PRD-65).

Compute lives in :mod:`chisurf.core.fluorescence.c3pda`; this package is the
ChiSurf model layer around it, with editor layouts in the co-located
``*.view.json`` files (PRD-38 model/view-spec split).
"""

from __future__ import annotations

from .c3pda import C3PdaModel, C3PdaSetup, C3PdaSpecies  # noqa: F401

__all__ = ["C3PdaModel", "C3PdaSetup", "C3PdaSpecies"]
