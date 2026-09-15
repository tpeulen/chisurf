"""Maximum-entropy TCSPC models by their classic dotted paths: BFF's MaxEnt descriptions.

The inversion runs in the engine (``tcspc_maxent_lifetime``,
``tcspc_maxent_fret``): a maximum-entropy distribution over the instrument's
own basis, with the L-curve and the model-weighted chi-square on the view.
"""
from __future__ import annotations

from chisurf.core.models.description import for_family

MaxEntLifetimeModel = for_family("tcspc_maxent_lifetime")
MaxEntFRETModel = for_family("tcspc_maxent_fret")

__all__ = ["MaxEntLifetimeModel", "MaxEntFRETModel"]
