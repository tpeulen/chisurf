"""How a plugin's maturity (``experimental``, ``deprecated`` in its manifest) is shown. Qt-free.

One table, read wherever a tool is listed -- the Qt ribbon and panel shell, the emtk shell's
ribbon, menus and Tools dock -- so the same tool carries the same marker and warning everywhere.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NamedTuple

__all__ = ["MATURITY_FLAGS", "maturity_markers", "maturity_message", "maturity_warnings"]


class _MaturityFlag(NamedTuple):
    """How one manifest maturity flag is presented by the panel shell."""

    #: Appended to the navigation label of a flagged panel.
    marker: str
    #: Panel/manifest key holding the tool-specific message, if any.
    message_key: str
    #: Banner text when the manifest carries no message of its own.
    default_message: str
    #: Banner background / bottom-border colours.
    background: str
    border: str


#: The maturity flags a panel may carry, in the order they are rendered. Both are
#: written by :func:`apply_manifest_flags` from the plugin manifest, so a tool's
#: maturity is declared once — in its manifest — and surfaced here.
MATURITY_FLAGS: dict[str, _MaturityFlag] = {
    "deprecated": _MaturityFlag(
        marker="⛔",
        message_key="deprecation_message",
        default_message="{name} is DEPRECATED — it will be removed, do not build new work on it",
        background="#8a5300",
        border="#5c3700",
    ),
    "experimental": _MaturityFlag(
        marker="⚠️",
        message_key="experimental_message",
        default_message="{name} is EXPERIMENTAL and UNTESTED — results are not validated",
        background="#b30000",
        border="#7d0000",
    ),
}


def maturity_markers(meta: Mapping[str, Any]) -> list[str]:
    """Return the marker glyph of every maturity flag *meta* sets, in render order.

    *meta* is anything carrying the manifest's flags under their own names — a
    panel definition, or a plugin discovery record. Keeping the lookup here means
    the ribbon entry and the navigation entry of the same tool are marked from
    one table.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record.

    Returns
    -------
    list of str
        One marker per set flag; empty when the tool declares no maturity flag.
    """
    return [spec.marker for flag, spec in MATURITY_FLAGS.items() if meta.get(flag)]


def maturity_message(meta: Mapping[str, Any], flag: str, name: str = "This tool") -> str:
    """Return the warning sentence for one maturity *flag* set on *meta*.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record, optionally carrying the flag's own
        message under ``MATURITY_FLAGS[flag].message_key``.
    flag : str
        Key in :data:`MATURITY_FLAGS` — ``"deprecated"`` or ``"experimental"``.
    name : str, optional
        Tool name filled into the fallback wording when the manifest carries no
        message of its own.

    Returns
    -------
    str
        The tool's own wording when it has one, else the flag's default sentence.
    """
    spec = MATURITY_FLAGS[flag]
    return str(meta.get(spec.message_key) or spec.default_message.format(name=name))


def maturity_warnings(meta: Mapping[str, Any], name: str = "This tool") -> list[str]:
    """Return ``marker + message`` for every maturity flag set on *meta*.

    Parameters
    ----------
    meta : Mapping
        Panel definition or discovery record.
    name : str, optional
        Tool name filled into any fallback wording.

    Returns
    -------
    list of str
        One line per set flag, hardest warning first; empty when none is set.
    """
    return [
        f"{spec.marker}  {maturity_message(meta, flag, name)}"
        for flag, spec in MATURITY_FLAGS.items()
        if meta.get(flag)
    ]
