"""Batch-Analysis plugin.

Apply one pre-optimised *template* fit to many datasets/files at once. The
plugin is split into a Qt-free :mod:`.core` (the batch runner + exporters, driven
by both the GUI and the CLI), a native emtk app in :mod:`.gui.app` over the view model in
:mod:`.gui.view_model`, and a :mod:`.cli`.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Main:Tools:Batch-Analysis"
