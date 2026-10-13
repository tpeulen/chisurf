"""F-test / χ²-max calculator plugin.

Compare two nested model fits (confidence ↔ χ² threshold) and compute the
χ²-max upper limit of a single fit at a confidence level. The GUI is a
emtk app over its AutoForm spec (:mod:`chisurf.plugins.core.f_test.gui.app`,
``gui/ftest.view.json``).
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Main:Tools:F-Test"


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "f_test"])

if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.core.f_test.gui.app import make_app

    window = ControlHost(make_app())
    window.show()
