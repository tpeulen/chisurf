"""A folder with two small simulated photon files the trace browser tour (and its e2e check) can list.

``make_demo()`` writes ``trace_1.spc`` and ``trace_2.spc`` (Becker & Hickl SPC-130) into the settings cache.
Each is the switching molecule of the intensity-trace demo (:mod:`chisurf.plugins.tttr.intensity_trace.demo`):
a donor and an acceptor channel whose brightness hops between two states with exponential dwell times, on a
weak background, so the trace has something to show. The two files differ in their seed only. They are plain
photon streams, not scans: the browser lists non-image files only, and a scan would be skipped. Nothing here
is a measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: The simulation, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    #: One file per seed: ``trace_1.spc``, ``trace_2.spc``.
    "seeds": [20261005, 20261006],
    "file_type": "SPC-130",
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("trace_browser")


def _names() -> list[str]:
    """Return the file names, one per seed."""
    return [f"trace_{index}.spc" for index in range(1, len(DEMO["seeds"]) + 1)]


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the two simulated photon files.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Simulate again even when the stamped parameters and checksums match.

    Returns
    -------
    Path
        *folder*, which Open accepts.
    """
    import numpy as np
    import tttrlib

    from chisurf.plugins.demo_cache import is_current, record
    from chisurf.plugins.tttr.intensity_trace import demo as source

    folder = demo_folder() if folder is None else Path(folder)
    names = _names()
    if not overwrite and all((folder / n).is_file() for n in names) and is_current(folder, names, DEMO):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    for name, seed in zip(names, DEMO["seeds"]):
        macro, micro, routing = source.photon_stream(int(seed))
        stream = tttrlib.TTTR()
        stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
        header = stream.header
        header.set_macro_time_resolution(source.DEMO["macro_resolution_s"])
        header.set_micro_time_resolution(source.DEMO["micro_resolution_s"])
        if not stream.write(str(folder / name), DEMO["file_type"], header):
            raise OSError(f"could not write {folder / name}")
    record(folder, names, DEMO)
    return folder
