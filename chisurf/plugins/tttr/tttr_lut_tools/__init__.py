"""TTTR LUT Tools Plugin."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "TTTR:LUT Tools"
    cli_entrypoint = ""

__all__ = ["TTRLutToolsWidget"]


def __getattr__(name):
    if name == "TTRLutToolsWidget":
        from .gui.tool import TTRLutToolsWidget

        return TTRLutToolsWidget
    raise AttributeError(name)


if __name__ == "plugin":
    from .gui.tool import TTRLutToolsWidget

    window = TTRLutToolsWidget()
    window.show()
