"""Writing a simulation as a burst-analysis folder the ordinary reader accepts.

This is the half of simulation that is *not* the simulator's business. The TTTR
library produces photons and burst boundaries; the folder layout around them —
``burstwise_.../bi4_bur/*.bur`` beside the photon file, with an analysis manifest
— is a ChiSurf format, and the writers for it already exist in
:mod:`chisurf.core.fio.fluorescence.burst`.

What did not exist was one way of *assembling* them, so each simulator grew its
own sixty-line version. They agreed on almost everything, which is what made the
places they disagreed dangerous: the photon-index convention is **inclusive**
(``Last Photon`` is the last photon of the burst, not one past it), consumers
assume it, and at least one generator wrote it exclusive. The assertion below is
there because that difference is invisible in every test that does not count
photons.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

__all__ = ["write_burst_folder"]

#: The analysis-folder name a simulated measurement is written under. The suffix
#: is a burst-search setting, not a format requirement, but readers key on the
#: layout inside rather than on this, so one fixed name keeps simulated folders
#: recognisable.
ANALYSIS_NAME = "burstwise_All 0.1000#15"


def write_burst_folder(
    tttr,
    bursts,
    detectors: dict[str, Any],
    directory: pathlib.Path | str,
    *,
    stem: str = "sim",
    suffix: str = ".ht3",
    windows: dict[str, tuple[int, int]] | None = None,
    settings: dict[str, Any] | None = None,
) -> pathlib.Path:
    """Write a photon stream and its bursts as a readable analysis folder.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        The photon stream. Written beside the analysis folder, because a burst
        table refers to photons by index into it.
    bursts : array_like
        ``(n_bursts, 2)`` of ``(first_photon, last_photon)`` indices, **inclusive
        at both ends**.
    detectors : dict
        Detector definitions, ``{name: {"chs": [...], ...}}``, recorded in the
        manifest so the reader does not have to guess the channel layout.
    directory : path-like
        Created if absent.
    stem : str
        Base name of the photon file.
    suffix : str
        Its container suffix; anything the TTTR writer supports.
    windows : dict, optional
        Micro-time windows per name. Defaults to one ``prompt`` window spanning
        the whole range, which is what a non-PIE measurement has.
    settings : dict, optional
        Extra manifest settings, merged over the detectors and the simulated flag.

    Returns
    -------
    pathlib.Path
        The analysis folder, ready to hand to the reader.

    Raises
    ------
    ValueError
        If no bursts were given, or an index falls outside the photon stream —
        which is what an off-by-one in the caller's burst definition looks like.
    """
    from chisurf.core.fio.fluorescence.burst import write_bur_file
    from chisurf.core.fio.fluorescence.burst_manifest import (
        describe_tttr_source,
        write_analysis_manifest,
    )

    start_stop = np.asarray(bursts, dtype=np.int64).reshape(-1, 2)
    if start_stop.size == 0:
        raise ValueError("no bursts to write")

    n_photons = int(np.asarray(tttr.macro_times).size)
    # Inclusive at both ends. An exclusive `last` passes every test that only
    # counts bursts and quietly shifts every per-burst quantity by one photon.
    if start_stop.min() < 0 or int(start_stop[:, 1].max()) >= n_photons:
        raise ValueError(
            f"burst photon indices must lie in [0, {n_photons - 1}] and be "
            f"inclusive of the last photon; got "
            f"[{int(start_stop.min())}, {int(start_stop[:, 1].max())}]"
        )
    if np.any(start_stop[:, 1] < start_stop[:, 0]):
        raise ValueError("a burst ends before it starts")

    directory = pathlib.Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / f"{stem}{suffix}"
    tttr.write(str(source))

    analysis = directory / ANALYSIS_NAME
    bur_dir = analysis / "bi4_bur"
    bur_dir.mkdir(parents=True, exist_ok=True)

    if windows is None:
        n_channels = int(np.asarray(tttr.micro_times).max()) + 1
        windows = {"prompt": (0, n_channels)}

    write_bur_file(bur_dir / f"{stem}.bur", start_stop, source.name, tttr, windows, detectors)
    manifest_settings: dict[str, Any] = {"detectors": detectors, "simulated": True}
    manifest_settings.update(settings or {})
    write_analysis_manifest(
        analysis,
        [describe_tttr_source(source, tttr, settings={"detectors": detectors})],
        settings=manifest_settings,
    )
    return analysis
