"""FRET models by their classic dotted paths, now BFF-described views.

One description per distance family (``tcspc_fret_gaussian``, ``_discrete``,
``_worm_like_chain``, ``_saw_nu``, ``_ising_chain``); a fixed distance is the
discrete family with one distance. The names stay importable for saved
configurations and projects.
"""
from __future__ import annotations

import chisurf.core.fluorescence
from chisurf.core.models.description import for_family
from chisurf.core.models.fret_parameters import FRETParameters, set_forster_radius_from_probes

GaussianModel = for_family("tcspc_fret_gaussian")
FRETrateModel = for_family("tcspc_fret_discrete")
SingleDistanceModel = FRETrateModel
WormLikeChainModel = for_family("tcspc_fret_worm_like_chain")
SawNuModel = for_family("tcspc_fret_saw_nu")
IsingChainModel = for_family("tcspc_fret_ising_chain")


def __getattr__(name: str):
    # The distance axis lives in chisurf.core.fluorescence, and settings can rebuild it.
    if name == "rda_axis":
        return chisurf.core.fluorescence.rda_axis
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["GaussianModel", "FRETrateModel", "SingleDistanceModel", "WormLikeChainModel", "SawNuModel",
           "IsingChainModel", "FRETParameters", "set_forster_radius_from_probes"]
