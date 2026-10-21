"""A PicoQuant PTU whose header tags the editor can list, change and save — the photons only ride along.

The photons come from the shared ``tttr`` generator
(:mod:`chisurf.plugins.tttr.demo_lib`): a deterministic µs-ALEX stream —
donor (routing channel 0) and acceptor (channel 1) detectors, single-molecule
bursts over a weak background, micro times from exponential decays that begin
at each channel's rise bin — with a PTU header with editable tags,Nothing here is a measurement; the
file is byte-identical on every run, and its JSON sidecar records ``DEMO`` while
a checksum sidecar rejects partial or modified cached data.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from chisurf.plugins.tttr import demo_lib

STEM = "header_demo.ptu"
#: The generator parameters of this plugin's stream, recorded beside the file.
DEMO: dict[str, Any] = {
    "version": 1,
    **demo_lib.config(seed=20261026),
    "filename": STEM,
    "file_type": "PTU",
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "tttr_header_edit"


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and the complete recorded photon file."""
    try:
        parameters = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
        data = path.read_bytes()
        return (
            parameters == DEMO
            and len(checksum) == 2
            and len(data) > 4
            and checksum == [str(len(data)), hashlib.sha256(data).hexdigest()]
        )
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the deterministic demonstration stream and its sidecars.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and file checksum match.

    Returns
    -------
    pathlib.Path
        The demonstration stream file.
    """
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / DEMO["filename"]
    if not overwrite and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    macro, micro, routing = demo_lib.photon_stream(DEMO)
    writer = demo_lib.write_ptu if DEMO["file_type"] == "PTU" else demo_lib.write_spc
    writer(path, DEMO, macro, micro, routing)
    path.with_suffix(".json").write_text(
        json.dumps(DEMO, sort_keys=True, indent=2), encoding="utf-8"
    )
    data = path.read_bytes()
    path.with_suffix(".sha256").write_text(
        f"{len(data)} {hashlib.sha256(data).hexdigest()}\n", encoding="ascii"
    )
    return path


def expected_counts() -> dict[str, int]:
    """The exact photon totals of the demonstration stream (per routing channel)."""
    return demo_lib.expected_counts(DEMO)
