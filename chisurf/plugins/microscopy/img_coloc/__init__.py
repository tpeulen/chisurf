"""Two-channel image colocalization plugin (TIFF stacks and photon-stream images).

Importing this package stays light: nothing here pulls in Qt, ``tifffile`` or
``tttrlib``, so the CLI and headless use stay fast. The GUI is loaded only when
the plugin is launched (``__name__ == "plugin"``), run as a script, or resolved
through the manifest ``gui`` entrypoint.
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Imaging:Colocalization"


def __getattr__(attr_name: str):
    """Import the Qt tool lazily so a bare package import stays Qt-free."""
    if attr_name == "ImgColocTool":
        from .gui.tool import ImgColocTool as _cls

        globals()["ImgColocTool"] = _cls
        return _cls
    raise AttributeError(f"module {__name__!r} has no attribute {attr_name!r}")


if __name__ == "plugin":
    from .gui.tool import ImgColocTool

    window = ImgColocTool()
    window.show()

if __name__ == "__main__":
    import sys

    from qtpy.QtWidgets import QApplication

    from chisurf.plugins.microscopy.img_coloc.gui.tool import ImgColocTool

    app = QApplication(sys.argv)
    win = ImgColocTool()
    win.show()
    sys.exit(app.exec())

__all__ = ["ImgColocTool"]
