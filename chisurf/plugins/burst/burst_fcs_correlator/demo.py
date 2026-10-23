"""A deterministic demonstration data set the burst-wise FCS correlator can generate itself.

``make_demo(folder)`` writes one container (``burst_fcs_demo.pto``): the photon stream (a Becker & Hickl SPC-130
file, embedded) with one burst-search run, so the tool, its guide and its tests have something to correlate without
the user's own files. The tool reads containers; the legacy ``.bst``/``.bur`` layouts are reached only through the
legacy import/export plugins, so the demo is what a real input looks like. The photons are drawn from a seeded
generator: eight bursts, each an inhomogeneous Poisson process whose rate has a Gaussian envelope (a molecule
crossing the focus, 1 ms wide) on a weak background, split at random between two detectors with a 4 ns fluorescence
decay. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict

import numpy as np

SEED = 20261002
N_BURSTS = 8
PHOTONS_PER_BURST = 1500
#: Macro-time tick (s) and micro-time channel count of the written file (a 13.5 ns / 3.3 ps SPC-130 header, so the file reads back by itself).
MACRO_RES = 13.5e-9
MICRO_RES = 3.2958984375e-12
N_MICRO = 4096
LIFETIME_S = 4.0e-9
STREAM_NAME = "burst_fcs_demo.spc"
#: The one file the demo puts in the folder: stream and bursts in one container.
CONTAINER_NAME = "burst_fcs_demo.pto"
#: The container's single burst-search run.
RUN_NAME = "runFull#1"


SPC_FILENAME = STREAM_NAME
MEMBERS = (CONTAINER_NAME,)


class DemoConfig(TypedDict):
    """The generator's parameters, as recorded in ``demo.json``."""

    seed: int
    n_bursts: int
    photons_per_burst: int
    macro_resolution_s: float
    micro_resolution_s: float
    micro_channels: int
    lifetime_s: float
    initial_ticks: int
    centre_ticks: int
    width_ticks: int
    width_base: float
    width_range: float
    signal_fraction: float
    burst_span_ticks: int
    gap_ticks: int
    routing_channels: int
    format: str


DEMO: DemoConfig = {
    "seed": SEED,
    "n_bursts": N_BURSTS,
    "photons_per_burst": PHOTONS_PER_BURST,
    "macro_resolution_s": MACRO_RES,
    "micro_resolution_s": MICRO_RES,
    "micro_channels": N_MICRO,
    "lifetime_s": LIFETIME_S,
    "initial_ticks": 5000000,
    "centre_ticks": 370000,
    "width_ticks": 74000,
    "width_base": 0.7,
    "width_range": 0.6,
    "signal_fraction": 0.8,
    "burst_span_ticks": 740000,
    "gap_ticks": 3700000,
    "routing_channels": 2,
    "format": "SPC-130",
}


def photon_stream(seed: int = SEED, n_bursts: int = N_BURSTS, *, config: DemoConfig | None = None):
    """The photons and the burst ranges: ``(macro, micro, routing, ranges)`` as numpy arrays and (first, last) index pairs."""
    values = DEMO.copy() if config is None else config
    rng = np.random.default_rng(seed)
    macro: list[np.ndarray] = []
    micro: list[np.ndarray] = []
    routing: list[np.ndarray] = []
    ranges: list[tuple[int, int]] = []
    t0, index = values["initial_ticks"], 0
    for _ in range(n_bursts):
        centre = (
            t0 + values["centre_ticks"]
        )  # a burst 10 ms (370 000 ticks) long, its envelope 1 ms wide
        width = values["width_ticks"] * (
            values["width_base"] + values["width_range"] * rng.random()
        )
        n = values["photons_per_burst"]
        times = np.sort(
            np.concatenate(
                [
                    rng.normal(centre, width, int(values["signal_fraction"] * n)),
                    rng.uniform(
                        t0, t0 + values["burst_span_ticks"], n - int(values["signal_fraction"] * n)
                    ),
                ]
            )
        )
        times = np.clip(times, t0, t0 + values["burst_span_ticks"]).astype(np.uint64)
        macro.append(times)
        micro.append(
            np.clip(
                rng.exponential(values["lifetime_s"] / values["micro_resolution_s"], n),
                0,
                values["micro_channels"] - 1,
            ).astype(np.uint16)
        )
        routing.append(rng.integers(0, values["routing_channels"], n).astype(np.int8))
        ranges.append((index, index + n - 1))
        index += n
        t0 += values["burst_span_ticks"] + values["gap_ticks"]  # 50 ms of nothing between bursts
    return (np.concatenate(macro), np.concatenate(micro), np.concatenate(routing), ranges)


def demo_folder() -> Path:
    """Return this tool's generated-data directory in the settings tree."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "burst_fcs_correlator"


def _cache_is_good(folder: Path, config: Mapping[str, object]) -> bool:
    """Reuse only a complete artifact set with matching parameters and byte hashes."""
    try:
        record = json.loads((folder / "demo.json").read_text(encoding="utf-8"))
        return (
            record["parameters"] == config
            and set(record["sha256"]) == set(MEMBERS)
            and all(
                (folder / name).is_file()
                and hashlib.sha256((folder / name).read_bytes()).hexdigest()
                == record["sha256"][name]
                for name in MEMBERS
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Create or reuse the declared synthetic input and its provenance sidecar.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Generated-data directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate this demo's declared files even when its cache is valid.

    Returns
    -------
    pathlib.Path
        The container: the photon stream embedded, one burst-search run beside it.
    """
    import tttrlib

    from chisurf.plugins.burst.burst_selection.api.io import write_container

    folder = Path(folder) if folder is not None else demo_folder()
    config = DEMO.copy()
    if not overwrite and _cache_is_good(folder, config):
        return folder / CONTAINER_NAME
    folder.mkdir(parents=True, exist_ok=True)
    # Publish only complete newly written files. A failed writer cannot corrupt
    # the previously usable input; no unrelated folder members are removed.
    with tempfile.TemporaryDirectory(prefix=".demo-", dir=folder) as staging:
        staged = Path(staging)
        macro, micro, routing, ranges = photon_stream(
            config["seed"], config["n_bursts"], config=config
        )
        stream = tttrlib.TTTR()
        stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
        header = stream.header
        header.set_macro_time_resolution(config["macro_resolution_s"])
        header.set_micro_time_resolution(config["micro_resolution_s"])
        if not stream.write(str(staged / SPC_FILENAME), config["format"], header):
            raise OSError(f"could not write {staged / SPC_FILENAME}")
        container = Path(
            write_container(
                staged / SPC_FILENAME,
                demo_burst_table(ranges),
                parameters={"demo": True, "bursts": int(len(ranges))},
                out_dir=staged,
                run=RUN_NAME,
            )
        )
        record = {
            "parameters": config,
            "sha256": {
                name: hashlib.sha256((staged / name).read_bytes()).hexdigest()
                for name in (CONTAINER_NAME,)
            },
        }
        (staged / "demo.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        for name in (CONTAINER_NAME, "demo.json"):
            os.replace(staged / name, folder / name)
    return folder / CONTAINER_NAME


def demo_burst_table(ranges):
    """A burst table as the container stores it: zero rows between the bursts, as a ``.bur`` has them."""
    import pandas as pd

    n = len(ranges)
    table = pd.DataFrame(
        {
            "First Photon": np.zeros(2 * n + 1),
            "Last Photon": np.zeros(2 * n + 1),
            "First File": [STREAM_NAME] * (2 * n + 1),
        }
    )
    table.loc[1::2, "First Photon"] = [a for a, _ in ranges]
    table.loc[1::2, "Last Photon"] = [b for _, b in ranges]
    return table
