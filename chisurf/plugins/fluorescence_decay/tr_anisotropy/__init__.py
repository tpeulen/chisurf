"""Time-resolved anisotropy wizard plugin.

Guided construction of a linked VV/VH global anisotropy fit. The plugin follows
the new standard: a Qt-free :mod:`.core` (IRF correction, spectrum I/O, the VV/VH
link plan) reused by both the GUI and CLI, a native emtk :mod:`.gui` (steps from
``anisotropy.view.json``, forms from ``gui/anisotropy_emtk.view.json``) and a :mod:`.cli`.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Wizards:Anisotropy Wizard"
