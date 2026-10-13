from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "📂"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Open Project"

if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "project_browser"])

if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.core.project_browser.gui.app import make_app

    window = ControlHost(make_app())
    window.show()
