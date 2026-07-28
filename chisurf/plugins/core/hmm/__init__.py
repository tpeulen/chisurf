"""Hidden Markov models for binned time traces — ChiSurf's shared HMM tool.

Fits a Gaussian HMM (:mod:`chisurf.core.math.hmm`) to one or more binned
traces and reports what a kinetic analysis needs: the emission of each state,
the decoded state path, dwell times, transition probabilities and rates, and an
AIC/BIC scan over the number of states.

The plugin is the seam, not a private analysis: the Qt-free core
(:mod:`.core.analysis`) is what other plugins call so that state ordering,
dwell-time definition and model selection are the same everywhere states are
reported, and the same code answers the ``hmm.fit`` / ``hmm.scan`` RPC methods
and the ``csg-hmm`` command line.

For photon-by-photon kinetics without binning use the H2MM plugin; for an
empirical-Bayes treatment of many short FRET traces, ebFRET.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Analysis:Kinetics:Hidden Markov model"
cli_entrypoint = "hmm=chisurf.plugins.core.hmm.cli.main:cli"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text())
    name = _manifest.get("display_name", name)


def __getattr__(attr_name: str):
    """Lazy Qt gate for the GUI entrypoint (keeps the package import Qt-free)."""
    if attr_name == "HmmTool":
        from .gui.tool import HmmTool as _cls

        globals()["HmmTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


def run():
    """Open the hidden-Markov-model tool (standalone window)."""
    from .gui.tool import HmmTool

    tool = HmmTool()
    tool.show()
    return tool


__all__ = ["HmmTool", "run"]
