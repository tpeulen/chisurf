"""Two-channel image colocalization plugin (TIFF stacks and photon-stream images).

Importing this package stays light: nothing here pulls in Qt, image readers or
``tttrlib``, so the CLI and headless use stay fast. The window is the native emtk
app in :mod:`.gui.app`, resolved through the manifest ``emtk`` entrypoint.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Imaging:Colocalization"
