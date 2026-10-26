"""A container to export: the Burst Selection demo stream with two analysis runs.

The legacy export needs a ``.pto`` that holds analyses, and the user should not
need one of their own to learn the window. :func:`make_demo` writes one whose
contents are known:

* the Burst Selection demo stream (``bs_demo.spc``, 12 planted bursts) embedded;
* a burst search (``min_photons`` 30 in a 0.5 ms window) as the run ``burstwise``
  -- it finds all 12 bursts and becomes ``burstwise/bi4_bur/bs_demo.bur``;
* tttrlib's burst variance analysis of those bursts as the run ``bva`` -- it
  becomes the companion ``bv4/bs_demo.bv4``, one row per burst.

The container is cached in the settings tree beside a JSON sidecar holding the
declared parameters and the container's checksum; a stale or edited copy is
written again.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

#: Everything that decides the container's bytes; the sidecar compares against it.
DEMO: dict[str, Any] = {
    "stream": "burst_selection demo (bs_demo.spc)",
    "search": {"min_photons": 30, "T": 5e-4},
    "factors": {"gamma": 1.0, "beta": 1.0, "alpha": 0.0, "delta": 0.0},
    "burst_run": "burstwise",
    "bva": {"window": 5},
}

CONTAINER_NAME = "bs_demo.pto"
SIDECAR_NAME = "demo.json"


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "legacy_export"


def _digest(path: Path) -> str:
    """SHA-256 of *path*'s bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_is_good(folder: Path) -> bool:
    """Reuse only a container whose sidecar matches :data:`DEMO` and its bytes."""
    try:
        record = json.loads((folder / SIDECAR_NAME).read_text(encoding="utf-8"))
        return record == {"demo": DEMO, "sha256": _digest(folder / CONTAINER_NAME)}
    except (OSError, ValueError):
        return False


def _write_container(folder: Path) -> Path:
    """Build the container in *folder*: the stream, the burst-search run and the BVA run."""
    import numpy as np
    import tttrlib

    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.burst.burst_bva.core.computation import (
        compute_bva,
        write_bva_container,
    )
    from chisurf.plugins.burst.burst_selection import demo as stream_demo
    from chisurf.plugins.burst.burst_selection.api.io import write_container
    from chisurf.plugins.burst.fret_check import entry as fret_check
    from chisurf.plugins.burst.fret_check import jobs as fret_jobs

    spc = stream_demo.make_demo(folder)
    with Measurement.create(spc, title="Legacy export demo"):
        pass
    search = DEMO["search"]
    result = fret_check.analyse(
        path=str(spc),
        key=str(spc),
        settings=search,
        correct=False,
        factors=DEMO["factors"],
        auto_calibrate=False,
    )
    bursts = fret_jobs.bursts_from_dict(result["bursts"])
    if bursts.n != stream_demo.N_BURSTS:
        raise RuntimeError(
            f"the demo search found {bursts.n} bursts, {stream_demo.N_BURSTS} are planted"
        )
    table = {**bursts.columns(), "First File": [spc.name] * bursts.n}
    container = Path(
        write_container(
            spc,
            table,
            parameters={"min_photons": search["min_photons"], "T_s": search["T"]},
            run=DEMO["burst_run"],
        )
    )
    store = store_from_arrays({k: np.asarray(v) for k, v in table.items()})
    bva = compute_bva(
        store,
        {spc.name: tttrlib.TTTR(str(spc), stream_demo.DEMO["file_type"])},
        donor_channels=(stream_demo.DEMO["green_channel"],),
        acceptor_channels=(stream_demo.DEMO["red_channel"],),
    )
    write_bva_container(bva, parameters=DEMO["bva"], analysis_folder=container)
    return container


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Create or reuse the demonstration container.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Write the container again even when the cached copy is valid.

    Returns
    -------
    pathlib.Path
        ``bs_demo.pto``: the embedded stream, the run ``burstwise`` (12 bursts) and
        the run ``bva``. Its JSON sidecar holds :data:`DEMO` and a checksum.
    """
    folder = demo_folder() if folder is None else Path(folder)
    if not overwrite and _cache_is_good(folder):
        return folder / CONTAINER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    # Build in a staging directory and publish the finished container: a failed
    # build never leaves a half-written container where a good one was.
    with tempfile.TemporaryDirectory(prefix=".demo-", dir=folder) as staging:
        staged = Path(staging)
        container = _write_container(staged)
        record = {"demo": DEMO, "sha256": _digest(container)}
        (staged / SIDECAR_NAME).write_text(
            json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(container, folder / CONTAINER_NAME)
        os.replace(staged / SIDECAR_NAME, folder / SIDECAR_NAME)
    return folder / CONTAINER_NAME


__all__ = ["DEMO", "demo_folder", "make_demo"]
