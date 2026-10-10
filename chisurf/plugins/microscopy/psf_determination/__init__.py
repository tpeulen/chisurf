"""PSF Determination plugin — new-style, AutoForm-based.

The plugin is split into Qt-free and GUI layers (like ``burst_selection`` /
``flc_2d`` / ``clsm``):

- :mod:`.api`      — pure PSF computation (``gaussian_3d``, ``extract_roi``,
  ``fit_3d_gaussian``, ``detect_beads``, ``fit_all_beads``) + dataclasses + contract.
- :mod:`.backend`  — ZMQ/JSON-RPC service handlers.
- :mod:`.cli`      — ``psf-determination`` command-line interface.
- :mod:`.gui`      — the interactive tool: a Qt-free :class:`~.gui.view_model.PsfViewModel`
  drawn by the native emtk app (:mod:`.gui.app`) from ``gui/psf.view.json``.

Importing this package needs no Qt binding.
"""

from __future__ import annotations

import json as _json
from pathlib import Path as _Path

from .api import gaussian_3d  # noqa: F401  (re-exported for back-compat)

name = "Imaging:PSF Determination"

_manifest_path = _Path(__file__).parent / "manifest.json"
if _manifest_path.exists():
    _manifest = _json.loads(_manifest_path.read_text(encoding="utf-8"))
    name = _manifest.get("display_name", name)

cli_entrypoint = "psf-determination=chisurf.plugins.microscopy.psf_determination.cli:cli"


__all__ = ["gaussian_3d"]
