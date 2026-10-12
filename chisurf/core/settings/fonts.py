"""The window's font settings: ``gui.fonts`` in ``settings_chisurf.yaml``.

The block is emtk's font configuration as a plain dict (:class:`emtk.fonts.FontConfig`,
``to_dict`` / ``from_dict``): per role -- ``ui``, ``code``, ``prose``, ``heading``,
``math``, ``caption`` -- a family, a size in points (``0`` follows the interface
size) and a weight, plus ``zoom``, ``oversample``, ``antialias``, ``heading_step``
and ``fallbacks``. The packaged defaults are today's look.

:func:`apply_stored` hands the stored block to emtk at startup; :func:`save` writes
a changed block to the user's settings file and the live settings, so the next
start applies it too. Qt-free: the Settings ▸ Fonts panel binds to these.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

_log = logging.getLogger(__name__)

#: Key of the block under ``gui``.
SECTION = "fonts"


def stored() -> dict:
    """The ``gui.fonts`` block of the live settings (packaged defaults under the user's)."""
    try:
        from chisurf.core.settings import cs_settings
    except Exception:  # noqa: BLE001 - unreadable settings: emtk's defaults
        return {}
    block = (cs_settings.get("gui") or {}).get(SECTION)
    return copy.deepcopy(block) if isinstance(block, dict) else {}


def apply_stored() -> Any:
    """Apply the stored font settings to emtk; returns the configuration in force (or ``None``)."""
    try:
        from emtk import fonts
    except ImportError:  # an emtk without font settings: nothing to apply
        return None
    try:
        return fonts.apply(stored())
    except Exception:  # noqa: BLE001 - fonts must never stop the window from starting
        _log.exception("Could not apply the font settings; using emtk's defaults")
        return fonts.reset()


def save(block: dict) -> bool:
    """Persist *block* as ``gui.fonts`` in the user's settings file and the live settings.

    Parameters
    ----------
    block : dict
        :meth:`emtk.fonts.FontConfig.to_dict` output.

    Returns
    -------
    bool
        True when the file was written.
    """
    from chisurf.core.settings.settings_utils import update_settings_section

    block = copy.deepcopy(block)
    try:
        import chisurf.core.settings as settings

        settings.cs_settings.setdefault("gui", {})[SECTION] = copy.deepcopy(block)
        settings.gui[SECTION] = copy.deepcopy(block)
    except Exception:  # noqa: BLE001 - the file is what persists
        pass
    return update_settings_section("gui", {SECTION: block})


__all__ = ["SECTION", "apply_stored", "save", "stored"]
