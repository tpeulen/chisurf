"""The FCS workflow's hand-off: **Filter Calc...** opens the fFCS Filter Calculator with the workflow's files.

The Filter Calculator is its own tool (its own dock in the emtk shell); it declares the ``fcs_correlator_files``
payload in its manifest's ``accepts``. Without a host window there is no hand-off and the button is greyed
(:func:`available`). No toolkit is imported.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.plugin import handoff

#: The plugin ``Filter Calc...`` opens.
FILTER_CALCULATOR = "fcs_filter_calculator"
#: The payload kind it takes the workflow's files as: ``files`` (checked, folders expanded), ``microtime_binning``.
FILES_HANDOFF = "fcs_correlator_files"

HandoffError = handoff.HandoffError


def available(plugin_id: str = FILTER_CALCULATOR) -> bool:
    """Whether a window is open that can open *plugin_id* with the workflow's files."""
    return handoff.available(plugin_id, FILES_HANDOFF)


def open_with_files(payload: dict[str, Any], plugin_id: str = FILTER_CALCULATOR) -> Any:
    """Open *plugin_id* as its own tool and give it *payload*; raises :class:`HandoffError` when it cannot."""
    return handoff.hand_off(plugin_id, FILES_HANDOFF, payload)


__all__ = ["FILES_HANDOFF", "FILTER_CALCULATOR", "HandoffError", "available", "open_with_files"]
