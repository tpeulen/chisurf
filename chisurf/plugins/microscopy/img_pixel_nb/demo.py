"""A demo photon stream whose brightness is known, so the N&B tool can teach itself.

Number & Brightness is easiest to believe on the textbook case it was invented
for: two regions of the **same intensity** that differ only in how the photons
are packaged. The left half of the demo image holds monomers (``N`` molecules of
brightness ``ε``), the right half dimers (``N/2`` molecules of brightness
``2ε``). An intensity image cannot tell them apart; the brightness map shows the
factor of two, and the number map the factor of one half.

Each pixel of each frame draws a molecule number ``n ~ Poisson(N)`` and a photon
count ``k ~ Poisson(ε n)`` — the statistics N&B assumes, so ``ε = σ²/⟨k⟩ − 1``
recovers the truth exactly up to sampling noise. The counts are written as an
ordinary confocal photon stream (PTU): every photon a macro time inside its
pixel's dwell and a random micro time, frame / line-start / line-stop markers as
a scanner writes them, and the image-header tags a reader needs to know which
marker is which. Opening the demo therefore also exercises the full read path.
"""

from __future__ import annotations

import json
import pathlib
import tempfile
from typing import Any

import numpy as np

#: PTU tag type for a signed 8-byte integer.
_TY_INT8 = 0x10000008

#: Ground truth of the demo, in one place for the help text, the tour and the tests.
DEMO = {
    "n_pixel": 32,
    "n_frames": 300,
    "number_monomer": 6.0,
    "brightness_monomer": 0.5,
    "pixel_dwell_s": 20.0e-6,
    "seed": 11,
}


def demo_folder() -> pathlib.Path:
    """Return this plugin's demo folder within the current settings directory."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "img_pixel_nb"


def truth(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """The expected N&B readout of the demo, region by region.

    Returns
    -------
    dict
        ``monomer`` / ``dimer`` entries with ``number``, ``epsilon`` (counts per
        pixel dwell) and ``B``, plus the settings.
    """
    c = {**DEMO, **(cfg or {})}
    n, eps = float(c["number_monomer"]), float(c["brightness_monomer"])
    return {
        "settings": c,
        "monomer": {"columns": "left half", "number": n, "epsilon": eps, "B": 1.0 + eps},
        "dimer": {
            "columns": "right half",
            "number": n / 2.0,
            "epsilon": 2.0 * eps,
            "B": 1.0 + 2.0 * eps,
        },
        "mean_counts": n * eps,
    }


def simulate_counts(cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Draw the ``(frames, lines, pixels)`` photon counts of the demo."""
    c = {**DEMO, **(cfg or {})}
    rng = np.random.default_rng(int(c["seed"]))
    size = int(c["n_pixel"])
    frames = int(c["n_frames"])
    number = np.full((size, size), float(c["number_monomer"]))
    brightness = np.full((size, size), float(c["brightness_monomer"]))
    number[:, size // 2 :] /= 2.0
    brightness[:, size // 2 :] *= 2.0
    molecules = rng.poisson(number, size=(frames, size, size))
    return rng.poisson(brightness * molecules)


def counts_to_tttr(counts: np.ndarray, pixel_dwell_s: float, seed: int = 0):
    """Write a ``(frames, lines, pixels)`` count stack as a confocal photon stream.

    Macro times tick twice per pixel dwell, photons sit mid-dwell, each line is
    bracketed by a line-start and a line-stop marker and each frame starts with a
    frame marker one tick before its first line.
    Markers use the routing-channel codes 4 (frame), 1 (line start) and 2 (line
    stop).

    Returns
    -------
    tttrlib.TTTR
    """
    import tttrlib

    frames, lines, pixels = counts.shape
    rng = np.random.default_rng(seed)
    # Two ticks per pixel dwell. One scan line occupies `2·pixels + 2` ticks: the
    # frame marker (first line of a frame only) on tick 0, the line start on
    # tick 1, pixel p's photons mid-dwell on tick 2 + 2p and the line stop on
    # tick 1 + 2·pixels. No marker shares a tick with a photon or another
    # marker: the reader pairs a stop with a start on the same tick (every line
    # zero ticks long) and drops photons on the tick of their line start.
    period = np.uint64(2 * pixels + 2)
    bases = np.arange(frames * lines, dtype=np.uint64) * period
    line_starts = bases + np.uint64(1)
    frame_starts = bases[::lines]
    pixel_ticks = (
        line_starts[:, None]
        + np.uint64(1)
        + np.uint64(2) * np.arange(pixels, dtype=np.uint64)[None, :]
    ).reshape(-1)
    flat = counts.reshape(-1).astype(np.int64)
    photon_macro = np.repeat(pixel_ticks, flat)
    macro = np.concatenate(
        [
            photon_macro,
            line_starts,
            line_starts + np.uint64(2 * pixels),
            frame_starts,
        ]
    )
    priority = np.concatenate(
        [
            np.zeros(photon_macro.size, np.int8),
            np.full(line_starts.size, 1, np.int8),
            np.full(line_starts.size, 1, np.int8),
            np.full(frame_starts.size, 1, np.int8),
        ]
    )
    channel = np.concatenate(
        [
            np.zeros(photon_macro.size, np.int8),
            np.full(line_starts.size, 1, np.int8),
            np.full(line_starts.size, 2, np.int8),
            np.full(frame_starts.size, 4, np.int8),
        ]
    )
    event = np.concatenate(
        [
            np.zeros(photon_macro.size, np.int8),
            np.ones(2 * line_starts.size + frame_starts.size, np.int8),
        ]
    )
    micro = np.concatenate(
        [
            rng.integers(0, 256, photon_macro.size).astype(np.uint16),
            np.zeros(2 * line_starts.size + frame_starts.size, np.uint16),
        ]
    )
    order = np.lexsort((priority, macro))
    tttr = tttrlib.TTTR(macro[order], micro[order], channel[order], event[order])
    header = tttr.header
    header.set_macro_time_resolution(0.5 * float(pixel_dwell_s))
    header.set_micro_time_resolution(0.032e-9)
    for name, value in (
        ("ImgHdr_LineStart", 1),
        ("ImgHdr_LineStop", 2),
        ("ImgHdr_Frame", 3),
        ("ImgHdr_PixX", pixels),
        ("ImgHdr_PixY", lines),
        ("ImgHdr_BiDirect", 0),
    ):
        header.set_tag(name, int(value), _TY_INT8)
    return tttr


def make_demo(
    folder: str | pathlib.Path | None = None, *, overwrite: bool = False, **overrides: Any
) -> pathlib.Path:
    """Simulate the monomer/dimer demo and write it as a PTU file (cached).

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Folder for the photon stream and truth sidecar; defaults to :func:`demo_folder`.
    overwrite : bool
        Regenerate even if a file made with the same settings exists.
    **overrides
        Any key of :data:`DEMO`.

    Returns
    -------
    pathlib.Path
        Primary PTU file. Its JSON sidecar records the settings and :func:`truth`.
    """
    cfg = {**DEMO, **{k: v for k, v in overrides.items() if k in DEMO}}
    directory = pathlib.Path(folder) if folder is not None else demo_folder()
    target = directory / "nb_demo_monomer_dimer.ptu"
    sidecar = target.with_suffix(".json")
    expected = truth(cfg)
    if not overwrite and target.exists() and sidecar.exists():
        try:
            if json.loads(sidecar.read_text(encoding="utf-8")).get("settings") == cfg:
                return target
        except Exception:  # noqa: BLE001 - a broken sidecar means regenerate
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    tttr = counts_to_tttr(simulate_counts(cfg), float(cfg["pixel_dwell_s"]), int(cfg["seed"]))
    # Some writer versions refuse an existing path while still reporting success.
    # Generate beside the dedicated cache, then publish only completed files.
    with tempfile.TemporaryDirectory(prefix=".nb-demo-", dir=target.parent) as temporary:
        generated = pathlib.Path(temporary) / target.name
        metadata = pathlib.Path(temporary) / sidecar.name
        if not tttr.write(str(generated), "PTU"):
            raise RuntimeError(f"could not write the demo photon stream to {target}")
        metadata.write_text(json.dumps(expected, indent=2), encoding="utf-8")
        generated.replace(target)
        metadata.replace(sidecar)
    return target


__all__ = ["DEMO", "counts_to_tttr", "demo_folder", "make_demo", "simulate_counts", "truth"]
