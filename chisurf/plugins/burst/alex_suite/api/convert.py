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

import numpy as np

__all__ = ["alex_to_pto", "detect_and_convert", "MIN_CONFIDENCE"]

#: Below this alternation contrast the stream is not alternating and the
#: "period" is just the largest peak of a noise spectrum. Converting on it would
#: rewrite every measurement into a meaningless micro-time, so the batch stops
#: instead. Alternating data comes back in the thousands; the threshold is two
#: orders of magnitude below that.
MIN_CONFIDENCE = 50.0

logger = logging.getLogger("chisurf.plugins.burst")


def alex_to_pto(
    paths,
    *,
    alex_period: int,
    period_shift: int = 0,
    out_dir: str | pathlib.Path | None = None,
    suffix: str = "_alex",
) -> pathlib.Path:
    """Fold the alternation of every file into the micro-time; return one `.pto`.

    **One container for the whole set**, not one per file. A run recorded as
    ``001.sm`` … ``006.sm`` is one measurement the acquisition software chopped
    up, and the container is ChiSurf's unit of *measurement*: embedding each
    piece separately would make six analyses of one experiment, six burst
    searches to run and six sets of results to pool by hand. `.pto` is built for
    exactly this — :meth:`chisurf.core.fio.pto.Measurement.create` takes a list
    and embeds them all, in lexical order by name.

    Parameters
    ----------
    paths : path-like or sequence of path-like
        The µs-ALEX measurement(s) — any container ``tttrlib`` reads, including
        the ``.sm`` files the old ALEX-Suite worked on.
    alex_period : int
        Alternation period in macro-time units (see
        :func:`~chisurf.plugins.tttr.ptu_alex_creator.core.detect_alex_period`).
    period_shift : int
        Phase offset applied before folding.
    out_dir : str or pathlib.Path, optional
        Where the container goes; defaults to beside the first source.
    suffix : str
        Appended to the stem, so the sources and the converted measurement can
        sit in one folder without either shadowing the other.

    Returns
    -------
    pathlib.Path
        The written ``.pto``.

    Raises
    ------
    ValueError
        If no path was given.
    """
    from chisurf.plugins.core.tttr_to_pto.api import convert as pack_container
    from chisurf.plugins.tttr.ptu_alex_creator import core

    if isinstance(paths, (str, pathlib.Path)):
        paths = [paths]
    sources = sorted((pathlib.Path(p) for p in paths), key=lambda p: p.name)
    if not sources:
        raise ValueError("no files to convert")

    target_dir = pathlib.Path(out_dir) if out_dir is not None else sources[0].parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # The folding is written as PTU rather than straight into the container:
    # `.pto` embeds an instrument file verbatim and never rewrites it, so each
    # converted stream has to *be* a file before it can be embedded.
    intermediates = []
    for source in sources:
        intermediate = target_dir / f"{source.stem}{suffix}.ptu"
        core.convert_file(
            str(source), str(intermediate),
            alex_period=int(alex_period), period_shift=int(period_shift),
            output_format="PTU", input_format="Auto",
        )
        intermediates.append(intermediate)

    # keep_original=False deletes the intermediates — but only after the
    # container has verified its own checksum, so a failed write costs nothing.
    return pack_container(intermediates, keep_original=False, out_dir=target_dir)


def detect_and_convert(
    paths,
    *,
    donor_channels=None,
    acceptor_channels=None,
    period: int | None = None,
    out_dir: str | pathlib.Path | None = None,
    progress=None,
    min_confidence: float = MIN_CONFIDENCE,
    dry_run: bool = False,
) -> dict:
    """Detect the alternation on the first file and convert all of them.

    The period and the laser gates are properties of the *instrument*, not of
    the sample, so they are measured once and applied to the whole batch — which
    is also what makes a series comparable.

    Parameters
    ----------
    paths : sequence of path-like
        The measurements, in the order they were selected.
    donor_channels, acceptor_channels : sequence of int, optional
        Routing channels of the two detectors. ``None`` (the default) works them
        out from the data — see
        :func:`~chisurf.plugins.tttr.ptu_alex_creator.core.detect_alex_channels`,
        which is the old "channel flip" checkbox decided by physics. Detecting
        rather than asking matters because a swapped assignment is the error
        nothing downstream reports: *E* comes out reflected about ½ and every
        fit statistic is happy.
    period : int, optional
        Alternation period in macro-time units. ``None`` (the default) measures
        it. Give one only when the instrument's is known exactly: one unit out,
        over 10⁵ cycles, walks the phase across a laser window. A given period
        is used as-is and its contrast is still reported, so a wrong one is
        visible rather than silently accepted.
    out_dir : path-like, optional
        Where the containers go.
    progress : callable, optional
        Called as ``progress(done, total, what)`` — ``done`` counts files
        finished, so the last call is ``(total, total, <container name>)``.
    min_confidence : float
        Refuse to convert below this alternation contrast (see
        :data:`MIN_CONFIDENCE`). Pass ``0`` to convert regardless.
    dry_run : bool
        Detect and report without writing anything — the same code path, so
        what is reported is what a real run would use.

    Returns
    -------
    dict
        ``{"period", "confidence", "windows", "donor_channels",
        "acceptor_channels", "channel_contrast", "converted", "failed"}``.
        ``channel_contrast`` is ``None`` when the assignment was given rather
        than detected.

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

    # The period does not depend on which detector is called the donor -- the
    # signed stream only changes sign, and a power spectrum does not care -- so
    # the period can be found before the assignment is known, and the assignment
    # can then be made on the folded phase.
    auto = donor_channels is None or acceptor_channels is None
    if auto:
        present, counts = np.unique(np.asarray(tttr.routing_channels),
                                    return_counts=True)
        if present.size < 2:
            raise ValueError(
                f"only routing channel {present.tolist()} carries photons; "
                "µs-ALEX needs two detectors"
            )
        busiest = sorted(int(present[i]) for i in np.argsort(counts)[::-1][:2])
        donor_channels, acceptor_channels = [busiest[0]], [busiest[1]]

    detected = core.detect_alex_period(
        tttr.macro_times, tttr.routing_channels,
        donor_channels=donor_channels, acceptor_channels=acceptor_channels,
    )
    confidence = float(detected["confidence"])
    if period is None:
        period = int(detected["period"])
    else:
        # A given period is not second-guessed, but the contrast is still the
        # measured one -- it is what says whether this is alternating data at
        # all, which does not become true because a number was typed.
        period = int(period)
    if confidence < min_confidence:
        raise ValueError(
            f"no clear laser alternation in {first.name} "
            f"(contrast {confidence:.0f}x, expected > {min_confidence:.0f}x). "
            "Either the donor/acceptor channels are wrong, or this is not "
            "µs-ALEX data — PIE / ns-ALEX needs no conversion."
        )
    folded = core.apply_alex(tttr, period, 0)
    contrast = None
    if auto:
        assignment = core.detect_alex_channels(
            folded.micro_times, folded.routing_channels, alex_period=period,
            channels=list(donor_channels) + list(acceptor_channels),
        )
        donor_channels = assignment["donor"]
        acceptor_channels = assignment["acceptor"]
        contrast = assignment["contrast"]
        logger.info(
            f"ALEX: donor = channel {donor_channels[0]}, acceptor = "
            f"{acceptor_channels[0]} (the donor is {contrast:.0%} as bright "
            "under acceptor excitation)"
        )
    windows = core.auto_alex_windows(
        folded.micro_times, folded.routing_channels,
        donor_channels=donor_channels, acceptor_channels=acceptor_channels,
        alex_period=period,
    )

    converted: list[pathlib.Path] = []
    failed: list[tuple[pathlib.Path, str]] = []
    if not dry_run:
        if progress is not None:
            progress(0, len(paths), f"{len(paths)} file(s)")
        try:
            converted.append(alex_to_pto(
                paths, alex_period=period, out_dir=out_dir))
        except Exception as exc:
            logger.warning(f"ALEX Suite: could not convert the measurement — {exc}")
            failed.extend((path, str(exc)) for path in paths)
        else:
            if progress is not None:
                progress(len(paths), len(paths), converted[0].name)
    return {
        "period": period,
        "confidence": confidence,
        "windows": {"green": windows["green"], "red": windows["red"]},
        "donor_channels": list(donor_channels),
        "acceptor_channels": list(acceptor_channels),
        "channel_contrast": contrast,
        "converted": converted,
        "failed": failed,
    }
