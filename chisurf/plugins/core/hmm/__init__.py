"""Hidden Markov models for binned time traces — ChiSurf's shared HMM tool.

Fits a Gaussian HMM (:mod:`chisurf.core.math.hmm`) to one or more binned
traces and reports what a kinetic analysis needs: the emission of each state,
the decoded state path, dwell times, transition probabilities and rates, and an
AIC/BIC scan over the number of states.

The plugin is the seam, not a private analysis: the Qt-free core
(:mod:`.core.analysis`) is what other plugins call so that state ordering,
dwell-time definition and model selection are the same everywhere states are
reported, and the same code answers the ``hmm.fit`` / ``hmm.scan`` RPC methods
and the ``csc hmm`` command line.

For photon-by-photon kinetics without binning use the H2MM plugin; for an
empirical-Bayes treatment of many short FRET traces, ebFRET.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Spectroscopy:Kinetics:Hidden Markov model"
cli_entrypoint = "hmm=chisurf.plugins.core.hmm.cli.main:cli"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text(encoding="utf-8"))
    name = _manifest.get("display_name", name)

__all__ = ["name", "cli_entrypoint"]
