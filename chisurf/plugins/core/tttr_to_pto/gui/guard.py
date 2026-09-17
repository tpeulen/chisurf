"""The ``tttr_to_pto`` drop guard: nag once before a vendor file gets read raw.

Registered under the name ``"tttr_to_pto"`` in
:mod:`chisurf.gui.widgets.dropguard`. A drop zone opts in with
``guards=["tttr_to_pto"]`` (a ``data_source``/``path_list`` view-spec option,
or the same keyword on ``PathListWidget``); nothing else in the registry or in
``apply_drop_guards`` knows this guard, or `.pto`, exists.

Offers **Convert, keep original** (the default, both for a real dialog and
headlessly -- it never deletes anything, so it is always the safe answer) /
**Convert, delete original** / **Use as dropped**, once, with a "remember my
choice" tick box that persists a tri-state (``ask`` / ``always_keep`` /
``always_delete`` / ``never``) under ``data_loading.drop_guards.tttr_to_pto``.

When several vendor files are dropped together (a measurement split across
`m000.spc`, `m001.spc`, ...), all of them are embedded into **one** `.pto`,
in lexical order by file name -- not one container per file -- via
:func:`chisurf.plugins.core.tttr_to_pto.api.convert`'s multi-file form. A
dropped `.set` is never itself a candidate: it is a Becker & Hickl `.spc`'s
sidecar, undecodable alone, and gets embedded automatically alongside its
`.spc` regardless of whether it was dropped at all.
"""

from __future__ import annotations

import logging
from pathlib import Path

from chisurf.core.fio import staging
from chisurf.core.fio.pto import SIDECAR_ONLY_EXTENSIONS, is_measurement
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


def _convert_batch(parent, paths: list[str], *, keep_original: bool) -> list[str]:
    """Embed every path in *paths* into one `.pto`, or fall back to *paths*.

    Shown as a busy task while it runs. Embedding copies the instrument file in
    verbatim and then verifies its checksum, so a 45 MB `.sm` takes a couple of
    minutes — on the GUI thread, with no repaint, which is indistinguishable
    from the application having hung. It is not cancellable (a half-written
    container is worse than a slow one), but it says what it is doing.
    """
    from chisurf.gui.progress import ChiSurfProgress
    from chisurf.plugins.core.tttr_to_pto import api

    names = ", ".join(sorted(Path(p).name for p in paths))
    total = sum(_size(p) for p in paths)
    size = f" ({total / 1e6:.0f} MB)" if total else ""
    progress = None
    try:
        progress = ChiSurfProgress(
            parent, text=f"Embedding {names}{size} into a .pto container…", maximum=0
        )
    except Exception:
        progress = None
    try:
        return [str(api.convert(paths, keep_original=keep_original))]
    except Exception:
        logger.exception("tttr_to_pto: could not convert %r, using them as dropped", paths)
        return list(paths)
    finally:
        if progress is not None:
            try:
                progress.close()
            except Exception:
                pass


def _size(path: str) -> int:
    """Size of *path* in bytes, or 0 when it cannot be read."""
    try:
        return Path(path).stat().st_size
    except OSError:
        return 0


@register_drop_guard("tttr_to_pto")
class TttrToPtoGuard(DropGuard):
    """Offer to convert dropped vendor photon file(s) into one `.pto` container."""

    def applies(self, path: str) -> bool:
        """Care about vendor-suffixed files that are not a container or sidecar."""
        suffix = Path(path).suffix.lower()
        if suffix in SIDECAR_ONLY_EXTENSIONS:
            return False
        return suffix in staging.VENDOR_EXTENSIONS and not is_measurement(path)

    def resolve(self, parent, paths: list[str]) -> list[str]:
        """Convert the whole dropped batch into one `.pto`, or leave it as dropped."""
        remembered = _choice()
        if remembered == "never":
            return list(paths)
        if remembered in ("always_keep", "always_delete"):
            return _convert_batch(parent, paths, keep_original=(remembered == "always_keep"))

        names = ", ".join(sorted(Path(p).name for p in paths))
        plural = "s" if len(paths) > 1 else ""
        informative = (
            "A .pto keeps the instrument data and every result computed "
            "from it in one file. Your original is never touched unless "
            "you choose to delete it, and only after the copy verifies.\n\n"
            "Converting copies the whole file and checksums it, so a large "
            "measurement takes a minute or two."
        )
        if len(paths) > 1:
            informative = (
                "All dropped files are embedded into one .pto, in name order. "
            ) + informative
        answer = dialogs.ChiSurfMessageBox.choice(
            parent,
            "Convert to .pto?",
            f"{names}\n\nVendor photon file{plural}, not yet a ChiSurf container.",
            {
                "keep": "Convert, keep original",
                "delete": "Convert, delete original",
                "asis": "Use as dropped",
            },
            default="keep",  # never deletes anything -- safe headlessly too.
            informative=informative,
            checkbox="Remember my choice",
        )
        if answer.checked and answer.key in _REMEMBER_AS:
            _remember(_REMEMBER_AS[answer.key])
        if answer.key in ("keep", "delete"):
            return _convert_batch(parent, paths, keep_original=(answer.key == "keep"))
        return list(paths)  # "asis" or dismissed
