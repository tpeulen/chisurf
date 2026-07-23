"""Single-molecule FRET-2CDE / ALEX-2CDE burst-dynamics feature plugin.

2CDE (Tomov et al., Biophys. J. 2012) is a model-free per-burst feature that
flags within-burst kinetics from per-photon kernel-density estimates of two
photon streams. This plugin computes the feature; downstream code selects or
filters bursts on the returned values.

The heavy computation runs in the tttrlib ``TwoCDE`` burst feature (parallel,
bit-exact port of the FRETBursts reference), with a pure-NumPy fallback.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Single-Molecule:2CDE"

__all__ = ["name"]
