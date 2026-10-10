"""
Confocal Laser Scanning Microscopy (CLSM) Image Analysis.

Create representations of CLSM-TTTR data, select pixels interactively, and
export fluorescence-decay histograms for analysis in ChiSurf.

Architecture (mirrors the other ``microscopy`` plugins):

- ``core/``    — Qt-free algorithms (image representations, decay
  extraction, setup presets). Safe to import headlessly.
- ``api/``     — dataclasses, RPC contract, and orchestration functions.
- ``backend/`` — ``register_services`` wiring ``clsm.*`` RPC methods.
- ``client.py``— transport-agnostic :class:`ClsmClient` (local or ZMQ).
- ``cli/``     — ``csc clsm …`` Click commands.
- ``gui/``     — the native emtk app: view-spec panels plus the interactive
  image/brush/decay canvas.

Importing this package is intentionally light: nothing here pulls in Qt or
``tttrlib`` so the CLI and headless services stay fast. The GUI is the native
emtk app (``gui/app.py``), loaded through the manifest ``emtk`` entrypoint.
"""

from __future__ import annotations

#: Plugin-menu label (``Category:Name``).
name = "Imaging:CLSM-Draw"

#: Hidden from the top-level plugin menu (launched via Imaging Tools).
menu_hidden = True

#: ``csc`` CLI registration (AST-scanned; see ``chisurf/core/cli.py``).
cli_entrypoint = "clsm=chisurf.plugins.microscopy.clsm.cli:cli"


if __name__ == "__main__":
    from chisurf.emtk.__main__ import main as _launch

    _launch(["--plugin", "clsm"])
