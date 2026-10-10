"""A small simulated confocal scan so CLSM-Draw can teach itself.

``make_demo(folder)`` writes ``clsm_demo.ptu``: a short laminar-flow scan (molecules diffuse and are
advected under a rastering beam), with line/frame markers and the PTU image-header tags a reader needs.
It is the same simulator as the Flow-map demo, shrunk so it builds in seconds; the tool opens it like
any measurement. Nothing here is a measurement.
"""

from __future__ import annotations

import pathlib
from typing import Any

#: The simulation, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {"n_pixel": 32, "n_frames": 8, "n_molecules": 300.0, "seed": 11}

FILENAME = "clsm_demo.ptu"


def demo_folder() -> pathlib.Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "clsm"


def make_demo(
    folder: str | pathlib.Path | None = None, *, overwrite: bool = False, **overrides: Any
) -> pathlib.Path:
    """Write or reuse the small simulated scan.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when a matching file is cached.
    **overrides
        Any key of :data:`DEMO`.

    Returns
    -------
    pathlib.Path
        The PTU file; a JSON sidecar beside it records the settings and the true flow.
    """
    from chisurf.plugins.microscopy.img_flow.demo import make_demo as simulate

    cfg = {**DEMO, **{k: v for k, v in overrides.items() if k in DEMO}}
    target = pathlib.Path(folder) if folder is not None else demo_folder()
    return simulate(target, overwrite=overwrite, filename=FILENAME, **cfg)
