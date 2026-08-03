"""A demo measurement whose split passages are known, so the tool can teach itself.

Fusion is hard to judge on your own data the first time: the burst count falls,
the histograms move, and there is nothing to check any of it against. This module
removes that problem by simulating a measurement in which the answer is declared
up front — a known number of molecules, a known fraction of them cut into a known
number of fragments, separated by gaps drawn from a known distribution.

It is a **real measurement**, not a shortcut. Photons are written as an ordinary
``.ht3`` file with macro times, micro times and routing channels, and the burst
folder beside it is produced by the *actual* burst search
(:func:`chisurf.plugins.burst.burst_selection.api.selection.analyze_file`) — not
by writing the simulator's own burst boundaries into a table. So the fragments in
the demo folder are fragments because a count-rate search cut them, exactly as on
a real measurement, and the whole read path (including the reading manifest the
fused folder needs) is exercised with them.

What is simulated, and what is not:

* Each molecule crosses the focus once, with a Gaussian intensity profile in
  time — the transit through a Gaussian volume.
* A fraction of the crossings is **interrupted**: for a few hundred microseconds
  to a few milliseconds the molecule drops to a dim rate — well below what the
  search will accept as a burst, well above background — and then comes back.
  That is the effect fusion exists to repair, and it is put in deliberately
  rather than hoped for.

  Dimming rather than going dark is the point, and it took a wrong first
  version to see why. The burst search joins runs of accepted photons that are
  within ``max_gap`` **photons** of each other, and a genuinely dark 0.8 ms gap
  at a few kHz of background holds only two or three photons — fewer than that
  tolerance — so the search bridges it itself and there is nothing to fuse. A
  molecule that keeps emitting weakly fills the gap with photons the search
  rejects, which is both what happens on real data and what actually splits the
  burst.
* Photons are split between two detectors by **one** FRET efficiency, on top of
  a constant Poisson background in both. One state, not two, on purpose: with
  two well-separated populations the histogram's width is their separation, and
  the shot-noise broadening fusion actually removes is invisible beside it.
* Nothing else. There is no diffusion model, no photophysics and no
  instrument response worth the name: this demonstrates *the fusion decision*,
  and a simulator elaborate enough to be mistaken for physics would be the wrong
  tool for that. Anything measured on it is a statement about the code.

The result is cached, so pressing the demo button a second time is instant.
"""

from __future__ import annotations

import json
import logging
import pathlib
from collections.abc import Callable
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

#: The demo's ground truth, in one place so the help text, the guide and the
#: tests cannot drift apart.
DEMO: dict[str, Any] = {
    #: Chosen so the three thresholds the guide walks through tell the whole
    #: story on this one file: 0.9 under-fuses, 0.7 lands on the truth, 0.5
    #: overshoots it by merging molecules that only *look* like recurrences.
    "n_molecules": 300,
    "duration_s": 12.0,
    #: Fraction of crossings the search is meant to cut in two or three.
    "split_fraction": 0.6,
    #: Gap between two fragments of one crossing, log-normal around this (ms).
    "gap_ms": 0.8,
    "gap_spread": 0.5,
    #: Emission rate *during* the gap (kHz): too low for the search to accept,
    #: high enough that the photons it rejects separate the two fragments.
    "dim_rate_khz": 30.0,
    #: One crossing: how long it lasts and how bright it is.
    "transit_ms": 1.6,
    "peak_rate_khz": 260.0,
    #: **One** FRET population, on purpose. With two well-separated states the
    #: histogram's width is the separation, and the shot-noise broadening that
    #: fusion actually removes is invisible next to it. With one state the width
    #: you see *is* shot noise — so the histogram narrowing when fragments are
    #: put back together is the effect itself, not a decoration.
    "efficiency": 0.45,
    #: Background per detector, kHz.
    "background_khz": 1.5,
    "macro_time_resolution": 20e-9,
    "micro_time_channels": 4096,
    "seed": 11,
}

#: Routing channels of the two detectors, matching the setup written beside the data.
GREEN_CHANNEL = 0
RED_CHANNEL = 1

#: Burst-search settings the demo folder is produced with. Deliberately ordinary:
#: the demo must be split by a search anyone would have run, not by one tuned to
#: split it.
SEARCH = {"min_photons": 30, "photon_window": 5, "time_window_ms": 0.5}

DEMO_STEM = "burst_fusion_demo"


def demo_directory(directory: str | pathlib.Path | None = None) -> pathlib.Path:
    """Return the folder the demo measurement lives in.

    Parameters
    ----------
    directory : path-like, optional
        Where to keep it. Defaults to ChiSurf's own settings directory, so the
        demo survives between sessions and is never written into the user's data.

    Returns
    -------
    pathlib.Path
        The directory, whether or not it exists yet.
    """
    if directory is not None:
        return pathlib.Path(directory)
    base = None
    try:
        import chisurf.core.settings as settings_mod

        base = getattr(settings_mod, "chisurf_settings_path", None)
    except Exception:  # pragma: no cover - settings unavailable
        base = None
    # An absolute path is required, not merely a truthy one: a missing setting
    # would otherwise leave ``Path("")``, whose ``str`` is ``"."``, and the demo
    # would be written relative to the working directory.
    root = pathlib.Path(base) if base else pathlib.Path.home() / ".chisurf"
    if not root.is_absolute():
        root = pathlib.Path.home() / ".chisurf"
    return root / "demo" / "burst_fusion"


def _fragment_plan(rng, settings: dict) -> list[list[float]]:
    """Per molecule, the gap (ms) before each fragment after the first.

    An empty list is a crossing the search will see whole; one entry is a
    crossing cut in two, two entries one cut in three.
    """
    plan: list[list[float]] = []
    for _ in range(int(settings["n_molecules"])):
        if rng.random() >= float(settings["split_fraction"]):
            plan.append([])
            continue
        # Three-fragment crossings are the minority, as they are in real data.
        n_gaps = 1 if rng.random() < 0.75 else 2
        gaps = np.exp(
            np.log(float(settings["gap_ms"]))
            + float(settings["gap_spread"]) * rng.normal(size=n_gaps)
        )
        plan.append([float(g) for g in gaps])
    return plan


def _simulate_photons(settings: dict) -> dict[str, Any]:
    """Generate the photon stream and the truth that generated it.

    Returns
    -------
    dict
        ``macro_times`` (ticks), ``micro_times``, ``channels``, and ``truth``.
    """
    rng = np.random.default_rng(int(settings["seed"]))
    resolution = float(settings["macro_time_resolution"])
    duration = float(settings["duration_s"])
    transit = float(settings["transit_ms"]) * 1e-3
    peak_rate = float(settings["peak_rate_khz"]) * 1e3
    plan = _fragment_plan(rng, settings)

    # Crossings are spread over the acquisition; sorted so the stream is written
    # in time order even before the background is merged in.
    starts = np.sort(rng.uniform(0.0, duration - 0.05, size=len(plan)))
    efficiency = float(settings["efficiency"])
    efficiencies = np.full(len(plan), efficiency)

    times: list[np.ndarray] = []
    channels: list[np.ndarray] = []
    n_fragments = 0
    for index, (start, gaps) in enumerate(zip(starts, plan)):
        pieces = len(gaps) + 1
        # The crossing keeps its total length: cutting it into fragments must not
        # make the molecule brighter, or fusion would be repairing a burst that
        # never existed.
        piece_duration = transit / pieces
        cursor = start
        for piece in range(pieces):
            # Photons of one fragment: a Gaussian envelope in time, sampled by
            # thinning a uniform stream, so the fragment has the shape of a
            # transit rather than a flat block.
            expected = peak_rate * piece_duration * 0.6
            n_photons = int(rng.poisson(expected))
            if n_photons:
                offsets = np.clip(
                    rng.normal(0.5, 0.22, size=n_photons), 0.0, 1.0
                ) * piece_duration
                photon_times = cursor + np.sort(offsets)
                red = rng.random(n_photons) < efficiencies[index]
                times.append(photon_times)
                channels.append(np.where(red, RED_CHANNEL, GREEN_CHANNEL))
                n_fragments += 1
            cursor += piece_duration
            if piece < len(gaps):
                # The dim interval: the same molecule, still emitting, but too
                # weakly for the search to keep. These are the photons that make
                # the search cut the crossing in two — and the photons a fused
                # burst gets back, because a fused burst is the whole span.
                gap_seconds = gaps[piece] * 1e-3
                n_dim = int(rng.poisson(float(settings["dim_rate_khz"]) * 1e3 * gap_seconds))
                if n_dim:
                    dim_times = cursor + np.sort(rng.uniform(0.0, gap_seconds, size=n_dim))
                    dim_red = rng.random(n_dim) < efficiencies[index]
                    times.append(dim_times)
                    channels.append(np.where(dim_red, RED_CHANNEL, GREEN_CHANNEL))
                cursor += gap_seconds

    # Background: uncorrelated in both detectors, the thing that makes a bridged
    # gap cost something.
    for channel in (GREEN_CHANNEL, RED_CHANNEL):
        n_background = int(rng.poisson(float(settings["background_khz"]) * 1e3 * duration))
        background = np.sort(rng.uniform(0.0, duration, size=n_background))
        times.append(background)
        channels.append(np.full(n_background, channel))

    macro_seconds = np.concatenate(times)
    routing = np.concatenate(channels)
    order = np.argsort(macro_seconds, kind="stable")
    macro_seconds = macro_seconds[order]
    routing = routing[order]

    macro_times = np.asarray(macro_seconds / resolution, dtype=np.uint64)
    micro_times = rng.integers(
        0, int(settings["micro_time_channels"]), size=macro_times.size, dtype=np.uint16
    )
    truth = {
        "n_molecules": len(plan),
        "n_crossings_split": int(sum(1 for gaps in plan if gaps)),
        "n_fragments_generated": n_fragments,
        "mean_fragments_per_molecule": float(n_fragments / max(len(plan), 1)),
        "gap_ms": [float(g) for gaps in plan for g in gaps],
        "efficiency": efficiency,
        "n_photons": int(macro_times.size),
        "duration_s": duration,
    }
    return {
        "macro_times": macro_times,
        "micro_times": micro_times,
        "channels": np.asarray(routing, dtype=np.int8),
        "truth": truth,
    }


def _write_tttr(stream: dict, path: pathlib.Path, settings: dict):
    """Write the simulated photons as a real ``.ht3`` file and return the object."""
    import tttrlib

    tttr = tttrlib.TTTR()
    tttr.append_events(
        np.asarray(stream["macro_times"], dtype=np.uint64),
        np.asarray(stream["micro_times"], dtype=np.uint16),
        np.asarray(stream["channels"], dtype=np.int8),
        np.zeros(stream["channels"].size, dtype=np.int8),
        shift_macro_time=False,
    )
    header = tttr.header
    header.set_macro_time_resolution(float(settings["macro_time_resolution"]))
    header.set_micro_time_resolution(1e-11)
    header.set_number_of_micro_time_channels(int(settings["micro_time_channels"]))
    tttr.set_header(header)
    path.parent.mkdir(parents=True, exist_ok=True)
    tttr.write(str(path))
    return tttr


def _run_burst_search(source: pathlib.Path, settings: dict) -> pathlib.Path:
    """Produce the demo's burst folder with the ordinary burst search.

    Going through the real search is the point: the fragments in the folder are
    fragments because a count-rate search cut them, and the folder carries the
    reading manifest a fused folder is regenerated from — so the demo also shows
    the path a current burst analysis takes, not a special case.
    """
    from chisurf.plugins.burst.burst_selection.api.models import AnalysisSettings
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_file

    analysis = source.parent / "burstwise_demo"
    bur_dir = analysis / "bi4_bur"
    bur_dir.mkdir(parents=True, exist_ok=True)

    analysis_settings = AnalysisSettings()
    analysis_settings.burst_detection.min_photons = int(SEARCH["min_photons"])
    analysis_settings.burst_detection.photon_window = int(SEARCH["photon_window"])
    analysis_settings.burst_detection.time_window = float(SEARCH["time_window_ms"]) * 1e-3
    analysis_settings.photon_filter.used_filter = "burst"
    analysis_settings.photon_filter.filter_active = True
    # The whole micro-time axis: the demo's micro times carry no information, and
    # a window would silently discard photons.
    analysis_settings.photon_filter.microtime_ranges = [
        (0, int(settings["micro_time_channels"]))
    ]
    analysis_settings.photon_filter.delta_macro_time_filter.dT_max_active = False
    analysis_settings.photon_filter.delta_macro_time_filter.dT_min_active = False

    analyze_file(
        source,
        settings=analysis_settings,
        filetype="HT3",
        windows={"prompt": (0, int(settings["micro_time_channels"]))},
        detectors=demo_detectors(),
        output_dir=bur_dir,
        mti_output_dir=analysis,
    )
    return analysis


def demo_detectors() -> dict[str, Any]:
    """Return the detector definition the demo is written with."""
    return {
        "green": {"chs": [GREEN_CHANNEL], "micro_time_ranges": []},
        "red": {"chs": [RED_CHANNEL], "micro_time_ranges": []},
    }


def create_demo(
    directory: str | pathlib.Path | None = None,
    settings: dict[str, Any] | None = None,
    progress: Callable[[float, str], None] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create (or reuse) the demo measurement and its burst folder.

    Parameters
    ----------
    directory : path-like, optional
        Where the demo lives; defaults to :func:`demo_directory`.
    settings : dict, optional
        Overrides of :data:`DEMO`.
    progress : callable, optional
        Called with ``(fraction, message)`` while generating.
    force : bool
        Regenerate even when a cached demo is present.

    Returns
    -------
    dict
        ``folder`` (the burst-analysis folder to fuse), ``source`` (the photon
        file), ``truth`` (what generated it) and ``bursts`` (what the search
        found).
    """
    values = dict(DEMO)
    values.update(settings or {})
    root = demo_directory(directory)
    record = root / f"{DEMO_STEM}.json"

    if record.is_file() and not force:
        try:
            cached = json.loads(record.read_text(encoding="utf-8"))
            folder = pathlib.Path(cached["folder"])
            if folder.is_dir() and any(folder.glob("bi4_bur/*.bur")):
                logger.info("Burst fusion: reusing the cached demo at %s", folder)
                return cached
        except (OSError, ValueError, KeyError):
            logger.debug("burst fusion: unusable demo cache, regenerating", exc_info=True)

    def _step(fraction: float, message: str) -> None:
        if progress is not None:
            try:
                progress(fraction, message)
            except Exception:  # pragma: no cover - a reporter must not stop the demo
                logger.debug("burst fusion: demo progress reporter failed", exc_info=True)

    _step(0.05, "Simulating molecules crossing the focus…")
    stream = _simulate_photons(values)

    _step(0.55, "Writing the photon file…")
    source = root / f"{DEMO_STEM}.ht3"
    _write_tttr(stream, source, values)

    _step(0.75, "Running the burst search…")
    folder = _run_burst_search(source, values)

    n_bursts = _count_bursts(folder)
    truth = dict(stream["truth"])
    truth["search"] = dict(SEARCH)
    result = {
        "folder": str(folder),
        "source": str(source),
        "truth": truth,
        "bursts": n_bursts,
        "detectors": demo_detectors(),
    }
    record.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _step(1.0, f"{n_bursts} bursts from {truth['n_molecules']} molecules.")
    logger.info(
        "Burst fusion demo: %d molecules (%d of them cut up) -> %d bursts in %s",
        truth["n_molecules"], truth["n_crossings_split"], n_bursts, folder,
    )
    return result


def _count_bursts(folder: pathlib.Path) -> int:
    """Count the bursts the search wrote into a demo folder."""
    from ..burst_fusion.core.fusion import read_measurements  # noqa: PLC0415

    try:
        return int(sum(len(frame) for frame in read_measurements(folder).values()))
    except Exception:  # pragma: no cover - reported as zero rather than raised
        logger.debug("burst fusion: could not count the demo's bursts", exc_info=True)
        return 0


def describe(result: dict[str, Any]) -> str:
    """One-paragraph statement of what the loaded demo contains.

    Written for the tool's status block, so the number to check the analysis
    against is on screen next to the analysis.
    """
    truth = result.get("truth", {})
    gaps = np.asarray(truth.get("gap_ms", []), dtype=float)
    median_gap = float(np.median(gaps)) if gaps.size else float("nan")
    return (
        f"<b>Demo loaded.</b> {truth.get('n_molecules', 0)} molecules crossed the "
        f"focus; the search cut {truth.get('n_crossings_split', 0)} of those "
        f"crossings up and found <b>{result.get('bursts', 0)} bursts</b>. The gaps "
        f"it cut at have a median of {median_gap:.2f} ms, so fusing should bring "
        f"the burst count back towards {truth.get('n_molecules', 0)}."
    )


__all__ = [
    "DEMO",
    "SEARCH",
    "create_demo",
    "demo_detectors",
    "demo_directory",
    "describe",
]
