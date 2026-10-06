"""ndX's slot in ChiSurf's Global View, without Qt.

The ndX app registers its constants group under :data:`GLOBAL_VIEW_OWNER`; the
window that hosts it -- the Qt ``NdxWindow`` or the emtk app -- withdraws it when
it closes, unless a later window has taken the slot.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

__all__ = ["GLOBAL_VIEW_OWNER", "withdraw_constants", "constants_group", "published_group"]

#: The Global View slot of ChiSurf's ndX window -- the owner id the app's
#: constants group is registered under (``ndxplorer.app.features.overlays``).
GLOBAL_VIEW_OWNER = "ndxplorer"


def withdraw_constants(app) -> None:
    """Empty the Global View slot if it still holds *app*'s constants."""
    try:
        from ndxplorer.core import parameters

        group = constants_group(app)
        held = {owner: g for owner, _label, g in parameters.registered_groups()}
        if group is not None and held.get(GLOBAL_VIEW_OWNER) is group:
            parameters.unregister_group(GLOBAL_VIEW_OWNER)  # ndX's registry and ChiSurf's
    except Exception:
        logger.warning("Could not withdraw the ndX constants from the Global View", exc_info=True)


def constants_group(app):
    """The app's constants :class:`~ndxplorer.core.parameters.ParameterGroup`, or ``None``."""
    for feature in getattr(app, "features", ()):
        constants = getattr(feature, "constants", None)
        group = getattr(constants, "group", None)
        if group is not None:
            return group
    return None


def published_group():
    """The ChiSurf group in the ndX Global View slot (``None``: empty)."""
    from chisurf.core.registry.parameter_groups import iter_registered_parameter_groups

    for owner_id, _label, group in iter_registered_parameter_groups():
        if owner_id == GLOBAL_VIEW_OWNER:
            return group
    return None
