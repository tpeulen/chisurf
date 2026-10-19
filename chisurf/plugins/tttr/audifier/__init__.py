"""TTTR Audifier plugin.

Convert TTTR photon streams to audio, with a live micro-time / lifetime waterfall
preview. Native emtk app (``gui/``): a Qt-free
:class:`~.gui.view_model.AudifierViewModel` drives the detector setup, the
per-detector/channel mixer, declarative audio + waterfall parameter panels, and
the reusable general ``waterfall`` section, laid out from
``audifier.view.json``.

Ribbon: Tools › Photon data › Audifier.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Qt-free lifetime-analysis helpers exposed for direct access (numpy only at import;
# the plotting helpers import emtk when called).
from chisurf.plugins.tttr.audifier.lifetime_analysis import (
    compute_lifetime_waterfall,
    lifetime_spectrum_ilt,
    plot_lifetime_waterfall,
    plot_lifetime_waterfall_multichannel,
)

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Photon data:Audifier"

icon = "🎵"


__all__ = [
    "name",
    "icon",
    "lifetime_spectrum_ilt",
    "compute_lifetime_waterfall",
    "plot_lifetime_waterfall",
    "plot_lifetime_waterfall_multichannel",
]
