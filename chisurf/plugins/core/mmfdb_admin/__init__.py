"""mmfdb-admin: Multiparametric Fluorescence Database management."""

from __future__ import annotations
from chisurf.gui import dialogs

try:
    from qtpy import sip
except ImportError:
    try:
        import sip
    except ImportError:
        sip = None

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

from .gui.tool import MMFDBWidget

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:mmfdb-admin"

# Headless fluorophore curation CLI (`csc fluorophore`), migrated here from the
# standalone fluorophore_db plugin (PRD-06).
cli_entrypoint = "fluorophore=mmfdb.admin.cli:cli"

__all__ = ["MMFDBWidget", "name", "cli_entrypoint"]


if __name__ == "plugin":
    existing = globals().get("window")
    if existing is not None and sip is not None and sip.isdeleted(existing):
        existing = None
    if existing is None:
        try:
            window = MMFDBWidget()
        except PermissionError as exc:

            dialogs.error(
                None,
                "mmfdb-admin — Access denied",
                str(exc) or "Administrator privileges are required to open mmfdb-admin.",
            )
            window = None
        else:
            if _manifest is not None:
                apply_manifest_statefulness(window, _manifest)
    else:
        window = existing
    if window is not None:
        window.show()
        try:
            window.raise_()
            window.activateWindow()
        except Exception:
            pass
