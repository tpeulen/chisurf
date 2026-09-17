"""Reported quantities of the PDDEM model (energy migration between two chromophores).

The kinetics runs in IMP.bff (``tcspc_pddem``); what is here is not in a fit's
hot loop and is evaluated by the view on demand, as the description's
``reports`` name it.
"""

from __future__ import annotations

import math

__all__ = ["emission_share"]


def emission_share(own: float, other: float) -> float:
    """A chromophore's share of the detected emission, ``own / (own + other)``.

    ChiSurf's classic PDDEM reported this as ``alpha_A`` (``mA / (mA + mB)``) and
    ``alpha_B``; NaN when the two emission probabilities do not sum to a positive
    finite number, as it did.
    """
    total = float(own) + float(other)
    if total > 0.0 and math.isfinite(total):
        return float(own) / total
    return float("nan")
