"""Burst IRF & Background plugin.

Extracts a per-detector IRF and background rate from the **non-burst** photons of
a single-molecule measurement — the scatter and dark counts between molecules
(see :mod:`chisurf.core.fluorescence.burst.irf_bg`) — and can hand the resulting
IRF/background patterns to the burst-MLE lifetime fit, so no separate scatter or
buffer acquisition is needed.

New-style AutoForm + JSON tool: a Qt-free
:class:`~.gui.view_model.IrfBackgroundViewModel` drives the detector channel-
definition page, the file list, the IRF plot and the results table laid out from
``gui/irf_bg.view.json``. It is aggregated into the ``burst_analysis`` workflow
shell (``menu_hidden`` keeps it off the ribbon) but stays importable and
standalone-launchable.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "📉"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = (
    _manifest.display_name
    if _manifest is not None
    else "Spectroscopy:Single-Molecule:Burst IRF & Background"
)

menu_hidden = True

__all__ = ["BurstIrfBackgroundTool"]


def __getattr__(attr_name: str):
    """Lazily expose the GUI tool without importing Qt at package import."""
    if attr_name == "BurstIrfBackgroundTool":
        from chisurf.plugins.burst.burst_irf_bg.gui.tool import BurstIrfBackgroundTool

        return BurstIrfBackgroundTool
    raise AttributeError(attr_name)
