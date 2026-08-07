"""The ``tttr_to_pto`` drop guard: nag once before a vendor file gets read raw.

Registered under the name ``"tttr_to_pto"`` in
:mod:`chisurf.gui.widgets.dropguard`. A drop zone opts in with
``guards=["tttr_to_pto"]`` (a ``data_source``/``path_list`` view-spec option,
or the same keyword on ``PathListWidget``); nothing else in the registry or in
``apply_drop_guards`` knows this guard, or `.pto`, exists.

Offers **Convert, keep original** / **Convert, delete original** / **Use as
dropped**, once, with a "remember my choice" tick box that persists a
tri-state (``ask`` / ``always_keep`` / ``always_delete`` / ``never``) under
``data_loading.drop_guards.tttr_to_pto``. Headless/non-interactive runs never
see the dialog and take the safe answer -- use the file as dropped, convert
nothing -- so an unattended run is never blocked on a prompt nobody is there
to answer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from chisurf.core.fio import staging
from chisurf.core.fio.pto import is_measurement
from chisurf.core.settings.settings_utils import set_data_loading_settings
from chisurf.gui import dialogs
from chisurf.gui.widgets.dropguard import DropGuard, register_drop_guard

logger = logging.getLogger(__name__)

#: Valid persisted choices; anything else read back is treated as "ask".
_CHOICES = ("ask", "always_keep", "always_delete", "never")

#: answer.key (dialog) -> persisted choice, for the "remember my choice" tick.
_REMEMBER_AS = {"keep": "always_keep", "delete": "always_delete", "asis": "never"}


def _choice() -> str:
    """Return the persisted tri-state for this guard (default ``"ask"``)."""
    drop_guards = staging._settings().get("drop_guards") or {}
    value = str(drop_guards.get("tttr_to_pto", "ask"))
    return value if value in _CHOICES else "ask"


def _remember(value: str) -> None:
    """Persist *value* under ``data_loading.drop_guards.tttr_to_pto``.

    Reads and rewrites the whole ``drop_guards`` mapping rather than a flat
    key, so a second guard's own persisted choice is never at risk of being
    clobbered by this one's write.
    """
    drop_guards = dict(staging._settings().get("drop_guards") or {})
    drop_guards["tttr_to_pto"] = value
    set_data_loading_settings({"drop_guards": drop_guards})


def _convert_one(path: str, *, keep_original: bool) -> str:
    from chisurf.plugins.core.tttr_to_pto import api

    try:
        return str(api.convert(path, keep_original=keep_original))
    except Exception:
        logger.exception("tttr_to_pto: could not convert %s, using it as dropped", path)
        return path


@register_drop_guard("tttr_to_pto")
class TttrToPtoGuard(DropGuard):
    """Offer to convert a dropped vendor photon file into a `.pto` container."""

    def applies(self, path: str) -> bool:
        """Care about vendor-suffixed files that are not already a container."""
        suffix = Path(path).suffix.lower()
        return suffix in staging.VENDOR_EXTENSIONS and not is_measurement(path)

    def resolve(self, parent, paths: list[str]) -> list[str]:
        """Convert, per the persisted choice or a one-time dialog."""
        remembered = _choice()
        if remembered == "never":
            return list(paths)
        if remembered in ("always_keep", "always_delete"):
            keep = remembered == "always_keep"
            return [_convert_one(p, keep_original=keep) for p in paths]

        # "ask": one dialog for the whole dropped batch. `default="asis"` is
        # deliberately the *headless* answer (never converts unattended); the
        # dict order below still puts "keep" first, the option an interactive
        # user is expected to want most often.
        names = ", ".join(Path(p).name for p in paths)
        plural = "s" if len(paths) > 1 else ""
        answer = dialogs.ChiSurfMessageBox.choice(
            parent,
            "Convert to .pto?",
            f"{names}\n\nVendor photon file{plural}, not yet a ChiSurf container.",
            {
                "keep": "Convert, keep original",
                "delete": "Convert, delete original",
                "asis": "Use as dropped",
            },
            default="asis",
            informative=(
                "A .pto keeps the instrument data and every result computed "
                "from it in one file. Your original is never touched unless "
                "you choose to delete it, and only after the copy verifies."
            ),
            checkbox="Remember my choice",
        )
        if answer.checked and answer.key in _REMEMBER_AS:
            _remember(_REMEMBER_AS[answer.key])
        if answer.key in ("keep", "delete"):
            return [_convert_one(p, keep_original=(answer.key == "keep")) for p in paths]
        return list(paths)  # "asis", dismissed, or headless
