"""Spot and region detection for imaging data.

Finds objects in an image and writes them — with their pixels — into the
measurement's own container, so that an analysis downstream fits the regions
that were found rather than deriving its own. The Qt-free detection core is
:mod:`.core.spots`; the persistence contract is
:mod:`chisurf.core.fio.fluorescence.region_container`.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

name = "Imaging:Spot Finder"
cli_entrypoint = "spot-finder=chisurf.plugins.microscopy.spot_finder.cli:cli"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text())
    name = _manifest.get("display_name", name)

__all__ = ["name", "cli_entrypoint"]
