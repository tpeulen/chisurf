"""Fold µs-ALEX alternation into the micro-time and land in a `.pto` container.

One function, because it is one decision: a µs-ALEX measurement becomes a
*normal* PIE measurement the moment its macro-time alternation is folded into the
micro-time, and from there ChiSurf's ordinary burst pipeline applies unchanged —
same burst search, same ``.bur``, same companions, same container. The ALEX Suite
does not have its own analysis path; it has this conversion at the front.

The container is the output because that is what a measurement is here
(``okf/architecture/`` — one `.pto` per measurement, vendor files are import
sources). The intermediate vendor file the folding is written through is a
transport detail and is removed once the container verifies.

Qt-free.
"""

from __future__ import annotations

import logging
import pathlib

__all__ = ["alex_to_pto", "detect_and_convert", "MIN_CONFIDENCE"]

#: Below this alternation contrast the stream is not alternating and the
#: "period" is just the largest peak of a noise spectrum. Converting on it would
#: rewrite every measurement into a meaningless micro-time, so the batch stops
#: instead. Alternating data comes back in the thousands; the threshold is two
#: orders of magnitude below that.
MIN_CONFIDENCE = 50.0

logger = logging.getLogger("chisurf.plugins.burst")


def alex_to_pto(
    path: str | pathlib.Path,
    *,
    alex_period: int,
    period_shift: int = 0,
    out_dir: str | pathlib.Path | None = None,
    suffix: str = "_alex",
) -> pathlib.Path:
    """Fold one file's alternation into the micro-time; return its `.pto`.

    Parameters
    ----------
    path : str or pathlib.Path
        The µs-ALEX measurement — any container ``tttrlib`` reads, including the
        ``.sm`` files the old ALEX-Suite worked on.
    alex_period : int
        Alternation period in macro-time units (see
        :func:`~chisurf.plugins.tttr.ptu_alex_creator.core.detect_alex_period`).
    period_shift : int
        Phase offset applied before folding.
    out_dir : str or pathlib.Path, optional
        Where the container goes; defaults to beside the source.
    suffix : str
        Appended to the stem, so the source and the converted measurement can
        sit in one folder without either shadowing the other.

    Returns
    -------
    pathlib.Path
        The written ``.pto``.
    """
    from chisurf.plugins.core.tttr_to_pto.api import convert as pack_container
    from chisurf.plugins.tttr.ptu_alex_creator import core

    path = pathlib.Path(path)
    target_dir = pathlib.Path(out_dir) if out_dir is not None else path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # The folding is written as PTU rather than straight into the container:
    # `.pto` embeds an instrument file verbatim and never rewrites it, so the
    # converted stream has to *be* a file before it can be embedded.
    intermediate = target_dir / f"{path.stem}{suffix}.ptu"
    core.convert_file(
        str(path), str(intermediate),
        alex_period=int(alex_period), period_shift=int(period_shift),
        output_format="PTU", input_format="Auto",
    )
    # keep_original=False deletes the intermediate — but only after the
    # container has verified its own checksum, so a failed write costs nothing.
    return pack_container(intermediate, keep_original=False, out_dir=target_dir)


def detect_and_convert(
    paths,
    *,
    donor_channels,
    acceptor_channels,
    out_dir: str | pathlib.Path | None = None,
    progress=None,
    min_confidence: float = MIN_CONFIDENCE,
) -> dict:
    """Detect the alternation on the first file and convert all of them.

    The period and the laser gates are properties of the *instrument*, not of
    the sample, so they are measured once and applied to the whole batch — which
    is also what makes a series comparable.

    Parameters
    ----------
    paths : sequence of path-like
        The measurements, in the order they were selected.
    donor_channels, acceptor_channels : sequence of int
        Routing channels of the two detectors.
    out_dir : path-like, optional
        Where the containers go.
    progress : callable, optional
        Called as ``progress(index, total, name)`` before each conversion.
    min_confidence : float
        Refuse to convert below this alternation contrast (see
        :data:`MIN_CONFIDENCE`). Pass ``0`` to convert regardless.

    Returns
    -------
    dict
        ``{"period", "confidence", "windows", "converted", "failed"}``.

    Raises
    ------
    ValueError
        If no paths were given, or the stream does not alternate clearly enough
        to be µs-ALEX data.
    """
    from chisurf.plugins.tttr.ptu_alex_creator import core

    paths = [pathlib.Path(p) for p in paths]
    if not paths:
        raise ValueError("no files to convert")

    first = paths[0]
    tttr = core.load(str(first), core.resolve_filetype("Auto", str(first)))
    detected = core.detect_alex_period(
        tttr.macro_times, tttr.routing_channels,
        donor_channels=donor_channels, acceptor_channels=acceptor_channels,
    )
    period = int(detected["period"])
    confidence = float(detected["confidence"])
    if confidence < min_confidence:
        raise ValueError(
            f"no clear laser alternation in {first.name} "
            f"(contrast {confidence:.0f}x, expected > {min_confidence:.0f}x). "
            "Either the donor/acceptor channels are wrong, or this is not "
            "µs-ALEX data — PIE / ns-ALEX needs no conversion."
        )
    folded = core.apply_alex(tttr, period, 0)
    windows = core.auto_alex_windows(
        folded.micro_times, folded.routing_channels,
        donor_channels=donor_channels, acceptor_channels=acceptor_channels,
        alex_period=period,
    )

    converted: list[pathlib.Path] = []
    failed: list[tuple[pathlib.Path, str]] = []
    for i, path in enumerate(paths):
        if progress is not None:
            progress(i, len(paths), path.name)
        try:
            converted.append(alex_to_pto(path, alex_period=period, out_dir=out_dir))
        except Exception as exc:
            logger.warning(f"ALEX Suite: could not convert {path.name} — {exc}")
            failed.append((path, str(exc)))
    return {
        "period": period,
        "confidence": confidence,
        "windows": {"green": windows["green"], "red": windows["red"]},
        "converted": converted,
        "failed": failed,
    }
