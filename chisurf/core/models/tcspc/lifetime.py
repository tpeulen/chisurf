"""Lifetime models by their classic dotted paths, now BFF-described views.

ChiSurf's classic ``LifetimeModel`` and ``LifetimeMixtureModel`` computed the
decay in Python; the engine now owns the model (``tcspc_lifetime``,
``tcspc_mixture``) and ChiSurf shows a view on it
(:mod:`chisurf.core.models.description`). The names stay importable because
user copies of ``experiment_configs.yaml`` and saved projects name classes by
path.
"""
from __future__ import annotations

from chisurf.core.models.description import for_family

LifetimeModel = for_family("tcspc_lifetime")
LifetimeMixtureModel = for_family("tcspc_mixture")
LifetimeNewModel = LifetimeModel
LifetimeMixtureNewModel = LifetimeMixtureModel

__all__ = ["LifetimeModel", "LifetimeMixtureModel", "LifetimeNewModel", "LifetimeMixtureNewModel"]
