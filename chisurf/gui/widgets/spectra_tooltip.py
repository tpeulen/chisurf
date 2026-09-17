"""Fluorescence-spectra tooltips (absorption / emission / transmission).

The generic machinery — the lazily-rendered tooltip items and the mini-plot
painter — lives in :mod:`chisurf.gui.widgets.tooltip_plot`; this module only adds
the spectra-specific renderer used by the light-path simulator. Pair them as
``TooltipItem(name, key, render_fn=lambda k: render_spectra_thumbnail(k, adapter))``.
``SpectraTooltipItem`` is kept as a backwards-compatible alias.
"""

from __future__ import annotations

from chisurf.gui.widgets.tooltip_plot import (  # noqa: F401  (re-exported)
    TooltipItem,
    TooltipTreeItem,
    render_series_thumbnail,
)

#: Backwards-compatible alias from when this item was spectra-specific.
SpectraTooltipItem = TooltipItem

#: Colours of the absorption / emission / transmission traces.
_SPECTRA_COLORS = ("#4488ff", "#ff4444", "#44cc44")


def render_spectra_thumbnail(probe_id: int, adapter) -> str:
    """Render abs/em/transmission spectra as a small PNG in an HTML img tag.

    Parameters
    ----------
    probe_id : int
        Probe identifier in the MMFDB.
    adapter : MFDatabaseAdapter or None
        Database adapter used to fetch spectra.

    Returns
    -------
    str
        HTML ``<img>`` tag with a base64-encoded PNG, or ``""`` when no
        spectra are available.
    """
    if adapter is None:
        return ""
    spectra = [
        adapter.get_probe_spectrum(probe_id, kind)
        for kind in ("absorption", "emission", "transmission")
    ]
    series = [(spec[0], spec[1], color) for spec, color in zip(spectra, _SPECTRA_COLORS) if spec]
    if not series:
        return ""
    return render_series_thumbnail(series, width=300, height=130, x_tick_step=50)
