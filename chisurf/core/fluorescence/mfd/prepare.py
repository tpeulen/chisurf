"""Turn a burst-analysis folder into the arrays a 2D MFD fit consumes.

A burst folder is a set of pointers back into photon streams: every ``.bur`` row is
a ``(first_photon, last_photon)`` interval in a named measurement, beside per-detector
counts, observation spans and — since the writer learned to emit it — the mean micro
time. Everything the fit needs is either in those columns or reachable through them,
so this module's job is to read them consistently and to say loudly when it cannot.

Three things here are deliberate rather than incidental.

**The photon sources are resolved, not guessed.** The chain is the recorded manifest
(``Info/analysis.json``, written while the file was open), then the legacy
``Info/*.mti`` sidecar, then a look for a file of that name beside the analysis
folder. Every open goes through :func:`chisurf.core.fio.staging.open_tttr`, the one
seam that resolves container types and applies per-channel corrections. **A read that
yields zero photons raises** :class:`UnresolvedPhotonSource`. That is the one
deliberate behaviour change of PRD-72: the failure this replaces was not an error at
all, but an analysis that ran on nothing and looked like a measurement with no signal.

**The photon-index convention is detected, not assumed.** ``Number of Photons``
should equal ``Last Photon − First Photon + 1``, and in folders written by the
current writer it does. Older folders wrote the exclusive count. Slicing an old
folder with the new convention adds one stray photon to every burst — small enough
to survive every assertion and large enough to shift a mean micro time. So the
convention is read off the table (:class:`PhotonIndexConvention`) and honoured.

**D12 holds times, not counts.** The nuisance measure is ``P(S, t_G, t_R)``: the
burst signal jointly with the per-channel *observation spans*. Weighting by the joint
count matrix instead would make the FRET axis reproduce itself and carry no
information at all — a mistake that is silent, because the fit still converges.
``Duration (<detector>) (ms)`` is exactly the first-to-last span of that detector's
photons, so no new file format is needed.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from chisurf.core.fio.fluorescence.burst import DETECTOR_SENTINEL
from chisurf.core.fio.fluorescence.burst_manifest import (
    read_analysis_manifest,
    reading_settings_for,
)
from chisurf.core.fluorescence.burst.photons import (
    StreamDef,
    default_streams,
    is_sentinel_file_reference,
    load_bur_dataframe,
    stream_index_arrays,
    streams_from_dicts,
)

__all__ = [
    "BurstPreparation",
    "NuisanceMeasure",
    "PhotonIndexConvention",
    "SourceResolution",
    "UnresolvedPhotonSource",
    "burst_directory",
    "detector_names",
    "infer_streams",
    "nuisance_measure",
    "photon_bursts",
    "photon_index_convention",
    "prepare_burst_folder",
    "resolve_sources",
    "window_columns",
]

#: Detector names understood without a recorded channel definition, mapped onto the
#: routing channels of the conventional two-colour, two-polarization confocal setup.
#: Used **only** as a last resort, and always checked against the ``.bur`` count
#: columns afterwards — a mapping that disagrees with the table leaves that detector
#: *unverified* and unusable, never quietly wrong (see :func:`prepare_burst_folder`).
#:
#: A name not listed here gets no channels rather than a plausible guess. An
#: acceptor-excitation ("yellow") detector in particular is a micro-time window on
#: the *same* channels as the acceptor, and which window cannot be recovered from
#: the name — guessing the channels alone would attribute every delayed photon to
#: the prompt detector.
FALLBACK_CHANNELS: dict[str, tuple[int, ...]] = {
    "green": (0, 8),
    "red": (1, 9),
}

#: Fraction of bursts whose recomputed per-detector count must match the ``.bur``
#: column before a channel definition is accepted.
COUNT_AGREEMENT_REQUIRED = 0.98


class UnresolvedPhotonSource(RuntimeError):
    """A burst folder's photon stream could not be located, opened, or read.

    Raised rather than returning an empty stream. ``tttrlib`` answers an
    unusable container type by printing to stderr and handing back an object with
    zero photons, so the analysis that follows runs on nothing and reports a
    measurement with no signal instead of a failure.
    """


@dataclass(frozen=True)
class PhotonIndexConvention:
    """Whether a ``.bur`` table's ``Last Photon`` is inclusive of the burst.

    Attributes
    ----------
    inclusive : bool
        ``True`` when ``Number of Photons == Last Photon − First Photon + 1``, which
        is what both current writer paths emit. ``False`` for older folders, whose
        count excludes the last photon.
    agreement : float
        Fraction of non-sentinel rows consistent with the chosen convention. Below
        1.0 means some rows fit neither; they are reported rather than hidden.
    """

    inclusive: bool
    agreement: float

    @property
    def stop_offset(self) -> int:
        """Return what to add to ``Last Photon`` to get an exclusive slice end."""
        return 1 if self.inclusive else 0


@dataclass
class SourceResolution:
    """Where a burst folder's photons were found, and how.

    Attributes
    ----------
    paths : dict
        Maps each ``First File`` value in the burst tables to the measurement it
        resolves to.
    origin : dict
        Maps the same keys to ``"manifest"``, ``"mti"`` or ``"sibling"`` — how the
        path was found. Recorded because the three carry different confidence: a
        manifest was written while the file was open, a sibling lookup is a guess
        that happened to work.
    container_type : dict
        Recorded container type per key, where the manifest supplies one. ``None``
        means auto-detection, which is the right default.
    """

    paths: dict[str, pathlib.Path] = field(default_factory=dict)
    origin: dict[str, str] = field(default_factory=dict)
    container_type: dict[str, Any] = field(default_factory=dict)


@dataclass
class BurstPreparation:
    """A burst folder read into the arrays a 2D MFD fit consumes.

    One row per burst throughout, in the order the burst tables list them, with the
    interleaved all-zero sentinel rows of the ``.bur`` format already removed.

    Attributes
    ----------
    channels : tuple of str
        Detector names, in the column order of ``counts`` / ``spans`` / ``mean_micro_time``.
    counts : numpy.ndarray
        ``(n_bursts, n_channels)`` int64 photon counts per detector.
    spans : numpy.ndarray
        ``(n_bursts, n_channels)`` float64 observation spans in **seconds** — the
        first-to-last photon span of that detector within the burst. ``0.0`` where
        the detector has fewer than two photons; see ``span_is_sentinel``.
    span_is_sentinel : numpy.ndarray
        ``(n_bursts, n_channels)`` bool, ``True`` where the span is the ``-1.0``
        placeholder rather than a measured value. Kept as a mask rather than folded
        into the span, because a burst the analysis could not measure is never a
        missing row.
    mean_micro_time : numpy.ndarray
        ``(n_bursts, n_channels)`` float64 mean micro time in **nanoseconds**, NaN
        where the detector has no photons.
    duration : numpy.ndarray
        ``(n_bursts,)`` float64 whole-burst span in seconds.
    total_counts : numpy.ndarray
        ``(n_bursts,)`` int64 photons per burst over all detectors.
    first_photon, last_photon : numpy.ndarray
        ``(n_bursts,)`` int64 photon indices into the source measurement. ``last_photon``
        is stored **inclusive** regardless of the file's own convention.
    file_key : numpy.ndarray
        ``(n_bursts,)`` object array of the ``First File`` value each burst came from.
    rows : numpy.ndarray
        ``(n_bursts,)`` int64 positions in the concatenated burst table, so a result
        can be written back beside the ``.bur`` files without shifting rows.
    streams : tuple of StreamDef
        The channel definition used, one per entry of ``channels``.
    convention : PhotonIndexConvention
        The photon-index convention detected in the tables.
    sources : SourceResolution
        Where the photons were found.
    folder : pathlib.Path
        The analysis folder.
    summary : dict
        Diagnostics — see :meth:`report`. Never empty, and never silent about a
        degraded path.
    """

    channels: tuple[str, ...]
    counts: np.ndarray
    spans: np.ndarray
    span_is_sentinel: np.ndarray
    mean_micro_time: np.ndarray
    duration: np.ndarray
    total_counts: np.ndarray
    first_photon: np.ndarray
    last_photon: np.ndarray
    file_key: np.ndarray
    rows: np.ndarray
    streams: tuple[StreamDef, ...]
    convention: PhotonIndexConvention
    sources: SourceResolution
    folder: pathlib.Path
    summary: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of bursts."""
        return int(self.counts.shape[0])

    @property
    def verified_channels(self) -> tuple[str, ...]:
        """Detectors whose channel definition was checked against the burst tables.

        A definition is verified when the per-detector counts recomputed from the
        photons reproduce the ``Number of Photons (<detector>)`` column. Detectors
        that were not checked — because the folder carried its mean micro time and
        no photons were read — count as verified: nothing was inferred about them.
        """
        agreement = self.summary.get("count_agreement") or {}
        if not agreement:
            return tuple(self.channels)
        return tuple(
            name
            for name in self.channels
            if agreement.get(name, 1.0) >= COUNT_AGREEMENT_REQUIRED
        )

    def require_verified(self, names: Sequence[str]) -> None:
        """Raise unless every named detector has a verified channel definition.

        Called by everything that turns a detector into physics. An unverified
        detector is not merely undocumented: its photons would be attributed to the
        wrong colour, and every number downstream would be wrong *and plausible*.

        Parameters
        ----------
        names : sequence of str
            Detector names the caller is about to use.

        Raises
        ------
        ValueError
            Naming the detectors, their agreement, and how to fix it.
        """
        agreement = self.summary.get("count_agreement") or {}
        bad = [n for n in names if n not in self.verified_channels]
        if not bad:
            return
        detail = ", ".join(f"{n} {agreement.get(n, float('nan')):.3f}" for n in bad)
        raise ValueError(
            f"the channel definition for {', '.join(bad)} does not describe "
            f"{self.folder}: counts recomputed from the photons agree with the .bur "
            f"columns for only {detail} (needs {COUNT_AGREEMENT_REQUIRED}). The "
            f"definition came from {self.summary.get('stream_origin', 'unknown')}. "
            "Pass streams= explicitly, or record the detectors in the analysis "
            "manifest. An acceptor-excitation detector is usually a micro-time "
            "window on the acceptor channels, which no detector name can convey."
        )

    def channel_index(self, name: str) -> int:
        """Return the column of a detector.

        Parameters
        ----------
        name : str
            Detector name, matched case-insensitively.

        Returns
        -------
        int

        Raises
        ------
        KeyError
            If the folder has no such detector.
        """
        lowered = [c.lower() for c in self.channels]
        try:
            return lowered.index(str(name).lower())
        except ValueError as exc:
            raise KeyError(
                f"no detector {name!r} in {self.folder} (have {list(self.channels)})"
            ) from exc

    def report(self) -> str:
        """Return a human-readable summary of what was read and what was degraded.

        Returns
        -------
        str
            One line per fact, suitable for a log, a CLI, or a GUI status box.
        """
        s = self.summary
        lines = [
            f"burst folder: {self.folder}",
            f"bursts: {len(self)} ({s.get('n_sentinel_rows', 0)} interleaved "
            f"sentinel rows removed)",
            f"detectors: {', '.join(self.channels)}",
            "photon index: "
            f"{'inclusive' if self.convention.inclusive else 'exclusive'} "
            f"(agreement {self.convention.agreement:.4f})",
            f"mean micro time from: {s.get('mean_micro_time_source', 'unknown')}",
        ]
        for key, path in self.sources.paths.items():
            lines.append(f"  {key} -> {path} [{self.sources.origin.get(key, '?')}]")
        for channel in self.channels:
            empty = s.get("n_empty", {}).get(channel, 0)
            lines.append(f"  {channel}: {empty} bursts with no photons")
        agreement = s.get("count_agreement", {})
        for channel, value in agreement.items():
            mark = "ok" if value >= COUNT_AGREEMENT_REQUIRED else "UNVERIFIED"
            lines.append(f"  {channel}: count agreement {value:.4f} [{mark}]")
        unverified = s.get("unverified_channels") or ()
        if unverified:
            lines.append(
                "  unusable until defined: " + ", ".join(unverified)
            )
        return "\n".join(lines)


@dataclass
class NuisanceMeasure:
    """The empirical nuisance measure ``D12 = P(S, t_G, t_R)``.

    Photon-distribution analysis takes the measured signal distribution ``P(S)`` per
    fixed time window and models only how that signal partitions between channels.
    Bursts have no fixed window, so the measure is resolved by time: per burst, the
    signal jointly with the observation span of each channel.

    **These are times, not counts.** The green and red *spans* are what makes the
    background Poisson mean (``bg_rate · t``) per-burst and per-channel, and what
    lets an asymmetry between the channels express acceptor bleaching. Weighting the
    partition by the measured *counts* of each channel instead would make the FRET
    axis reproduce itself exactly and carry zero information — while still
    converging, which is what makes the mistake dangerous.

    Attributes
    ----------
    signal : numpy.ndarray
        ``(n,)`` int64 signal per burst, summed over ``channels``.
    spans : numpy.ndarray
        ``(n, n_channels)`` float64 observation spans in seconds.
    counts : numpy.ndarray
        ``(n, n_channels)`` int64 per-channel counts. Carried for the partition
        *target*, never as the weight of the measure itself.
    duration : numpy.ndarray
        ``(n,)`` whole-burst span in seconds — first to last photon over *all*
        detectors. This, not a channel's own span, is the window a molecule spent
        in the focus, so it is the window the occupation-time law is computed over.
    channels : tuple of str
        Detector names of the span/count columns.
    rows : numpy.ndarray
        ``(n,)`` positions in the preparation, so an excluded burst is traceable.
    summary : dict
        How many bursts were excluded and why.
    """

    signal: np.ndarray
    spans: np.ndarray
    counts: np.ndarray
    duration: np.ndarray
    channels: tuple[str, ...]
    rows: np.ndarray
    summary: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        """Return the number of bursts in the measure."""
        return int(self.signal.shape[0])

    def binned(
        self,
        *,
        n_signal_bins: int = 24,
        n_span_bins: int = 8,
    ) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
        """Compress the measure onto a grid, for the histogram scoring source.

        The histogram source's cost is independent of the number of bursts because
        the bursts enter only through this object. Binning it keeps the per-evaluation
        work proportional to the grid rather than to the measurement.

        Parameters
        ----------
        n_signal_bins : int
            Number of logarithmically spaced signal bins.
        n_span_bins : int
            Number of span bins per channel.

        Returns
        -------
        weights : numpy.ndarray
            Flattened bin weights, summing to the number of bursts.
        signal_centres : numpy.ndarray
            Representative signal per bin (the weighted mean, not the bin centre —
            the signal distribution is steep and a geometric centre biases it).
        span_centres : list of numpy.ndarray
            Representative span per bin, one array per channel. The last entry is
            the whole-burst duration, which the occupation-time law needs.
        """
        signal = self.signal.astype(float)
        edges = np.geomspace(
            max(1.0, signal.min()), max(2.0, signal.max() + 1.0), n_signal_bins + 1
        )
        signal_bin = np.clip(np.digitize(signal, edges[1:-1]), 0, n_signal_bins - 1)

        span_bins = []
        for c in range(self.spans.shape[1]):
            column = self.spans[:, c]
            positive = column[column > 0.0]
            if positive.size == 0:
                span_bins.append(np.zeros_like(signal_bin))
                continue
            span_edges = np.quantile(positive, np.linspace(0.0, 1.0, n_span_bins + 1))
            span_edges = np.unique(span_edges)
            span_bins.append(
                np.clip(
                    np.digitize(column, span_edges[1:-1]),
                    0,
                    max(0, span_edges.size - 2),
                )
            )

        shape = [n_signal_bins] + [int(b.max()) + 1 for b in span_bins]
        flat = np.ravel_multi_index([signal_bin, *span_bins], shape)
        size = int(np.prod(shape))
        weights = np.bincount(flat, minlength=size).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"):
            signal_centres = np.bincount(flat, weights=signal, minlength=size)
            signal_centres = np.where(weights > 0, signal_centres / weights, 0.0)
            span_centres = []
            for c in range(self.spans.shape[1]):
                total = np.bincount(flat, weights=self.spans[:, c], minlength=size)
                span_centres.append(np.where(weights > 0, total / weights, 0.0))
            total = np.bincount(flat, weights=self.duration, minlength=size)
            span_centres.append(np.where(weights > 0, total / weights, 0.0))
        return weights, signal_centres, span_centres


# ──────────────────────────────────────────────────────────────────────────────
# Folder layout
# ──────────────────────────────────────────────────────────────────────────────
def burst_directory(folder: pathlib.Path | str) -> tuple[pathlib.Path, pathlib.Path]:
    """Return the analysis folder and the directory holding its ``.bur`` tables.

    Callers hold different things — the analysis folder, the ``bi4_bur`` directory
    inside it, or a single ``.bur`` file — so all three are accepted.

    Parameters
    ----------
    folder : path-like
        Any of the three.

    Returns
    -------
    analysis_dir, bur_dir : pathlib.Path

    Raises
    ------
    FileNotFoundError
        If no ``.bur`` tables can be found.
    """
    path = pathlib.Path(folder)
    if path.is_file() and path.suffix.lower() == ".bur":
        bur_dir = path.parent
    elif path.is_dir() and any(path.glob("*.bur")):
        bur_dir = path
    elif path.is_dir():
        candidates = sorted(
            child
            for child in path.iterdir()
            if child.is_dir() and any(child.glob("*.bur"))
        )
        if not candidates:
            raise FileNotFoundError(f"no .bur tables under {path}")
        bur_dir = candidates[0]
    else:
        raise FileNotFoundError(f"{path} is neither a .bur file nor a directory")

    analysis_dir = (
        bur_dir.parent if bur_dir.name.lower() in ("bi4_bur", "bur") else bur_dir
    )
    return analysis_dir, bur_dir


def detector_names(frame) -> tuple[str, ...]:
    """Return the detector names a burst table carries, in column order.

    Taken from the ``Number of Photons (<detector>)`` columns, which every writer
    emits for every detector including the ones a burst has nothing in.

    Parameters
    ----------
    frame : pandas.DataFrame or mapping of str to array
        A burst table.

    Returns
    -------
    tuple of str
    """
    pattern = re.compile(r"^Number of Photons \((?P<name>[^)]+)\)$")
    names = []
    for column in frame.columns:
        match = pattern.match(str(column).strip())
        if match:
            names.append(match.group("name"))
    return tuple(names)


def photon_index_convention(frame) -> PhotonIndexConvention:
    """Detect whether ``Last Photon`` is counted inside ``Number of Photons``.

    Both current writer paths emit ``Number of Photons = Last − First + 1``. Folders
    written earlier emit ``Last − First``. Slicing one with the other's convention
    adds a stray photon to every burst: too small to fail an assertion, large enough
    to move a mean micro time and, through it, a fitted lifetime.

    Parameters
    ----------
    frame : pandas.DataFrame or mapping of str to array
        A burst table with the sentinel rows already removed.

    Returns
    -------
    PhotonIndexConvention
    """
    first = frame["First Photon"].to_numpy(dtype=np.int64)
    last = frame["Last Photon"].to_numpy(dtype=np.int64)
    counted = frame["Number of Photons"].to_numpy(dtype=np.int64)
    if counted.size == 0:
        return PhotonIndexConvention(inclusive=True, agreement=1.0)
    span = last - first
    inclusive = float(np.mean(counted == span + 1))
    exclusive = float(np.mean(counted == span))
    if inclusive >= exclusive:
        return PhotonIndexConvention(inclusive=True, agreement=inclusive)
    return PhotonIndexConvention(inclusive=False, agreement=exclusive)


# ──────────────────────────────────────────────────────────────────────────────
# Photon sources
# ──────────────────────────────────────────────────────────────────────────────
def _mti_entries(analysis_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    """Return ``{file name: path}`` from the legacy ``Info/*.mti`` sidecars."""
    out: dict[str, pathlib.Path] = {}
    info = analysis_dir / "Info"
    if not info.is_dir():
        return out
    for sidecar in sorted(info.glob("*.mti")):
        try:
            text = sidecar.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            parts = line.split("\t")
            if not parts or not parts[0].strip():
                continue
            path = pathlib.Path(parts[0].strip())
            out.setdefault(path.name, path)
    return out


def resolve_sources(
    folder: pathlib.Path | str,
    keys: Sequence[str],
) -> SourceResolution:
    """Locate the measurement each burst table points back into.

    The chain is manifest → legacy ``.mti`` sidecar → a file of that name beside the
    analysis folder. It deliberately stops there: the step that used to follow was
    mapping an extension onto a container type, which is how ``.spc`` became
    ``"SPC"`` — a type ``tttrlib`` does not accept and does not reject either.

    Parameters
    ----------
    folder : path-like
        The analysis folder, its ``bi4_bur`` directory, or a ``.bur`` file.
    keys : sequence of str
        The distinct ``First File`` values to resolve.

    Returns
    -------
    SourceResolution

    Raises
    ------
    UnresolvedPhotonSource
        If any key cannot be resolved to an existing file, naming the key, the
        places that were searched, and why it matters.
    """
    analysis_dir, _ = burst_directory(folder)
    manifest = read_analysis_manifest(analysis_dir)
    mti = _mti_entries(analysis_dir)
    data_dir = analysis_dir.parent

    resolution = SourceResolution()
    missing: list[str] = []
    for key in keys:
        if is_sentinel_file_reference(key):
            continue
        name = pathlib.Path(str(key)).name

        recorded = reading_settings_for(name, manifest)
        candidate = pathlib.Path(str(recorded["path"])) if recorded.get("path") else None
        origin = "manifest"
        container = recorded.get("container_type")

        if candidate is None or not candidate.is_file():
            if candidate is not None and (data_dir / name).is_file():
                # The manifest names the file but the analysis has been moved; the
                # recorded container type is still good.
                candidate = data_dir / name
            elif name in mti and mti[name].is_file():
                candidate, origin, container = mti[name], "mti", None
            elif (analysis_dir / "Info" / name).is_file():
                candidate, origin, container = analysis_dir / "Info" / name, "mti", None
            elif (data_dir / name).is_file():
                candidate, origin, container = data_dir / name, "sibling", None
            else:
                missing.append(name)
                continue

        resolution.paths[str(key)] = candidate
        resolution.origin[str(key)] = origin
        resolution.container_type[str(key)] = container

    if missing:
        raise UnresolvedPhotonSource(
            "cannot locate the photon stream(s) "
            + ", ".join(sorted(set(missing)))
            + f" for the burst analysis {analysis_dir}. Searched the manifest "
            f"({analysis_dir / 'Info' / 'analysis.json'}), the .mti sidecars in "
            f"{analysis_dir / 'Info'}, and {data_dir}. A burst table is only a set "
            "of pointers into a photon stream, so without it every photon-bearing "
            "quantity would be computed from nothing."
        )
    return resolution


def open_sources(resolution: SourceResolution) -> dict[str, Any]:
    """Open every resolved measurement, failing loudly on an empty read.

    Parameters
    ----------
    resolution : SourceResolution
        From :func:`resolve_sources`.

    Returns
    -------
    dict
        Maps each ``First File`` value to its open ``tttrlib.TTTR``.

    Raises
    ------
    UnresolvedPhotonSource
        If a file opens with zero photons — which ``tttrlib`` reports by printing to
        stderr and returning an empty object, not by raising.
    """
    from chisurf.core.fio.staging import open_tttr

    opened: dict[str, Any] = {}
    for key, path in resolution.paths.items():
        tttr = open_tttr(path, resolution.container_type.get(key))
        if len(tttr) == 0:
            raise UnresolvedPhotonSource(
                f"{path} was opened but holds zero photons"
                + (
                    f" (container type {resolution.container_type[key]!r} from the "
                    "manifest)"
                    if resolution.container_type.get(key)
                    else " (container type auto-detected)"
                )
                + ". An empty read is how an unusable container type presents, and "
                "it would otherwise look like a measurement with no signal."
            )
        opened[key] = tttr
    return opened


# ──────────────────────────────────────────────────────────────────────────────
# Channel definitions
# ──────────────────────────────────────────────────────────────────────────────
def _streams_from_manifest(
    analysis_dir: pathlib.Path, names: Sequence[str]
) -> list[StreamDef] | None:
    """Return the recorded detector definitions, or ``None`` if absent."""
    manifest = read_analysis_manifest(analysis_dir) or {}
    settings = manifest.get("settings") or {}
    detectors = settings.get("detectors")
    if not isinstance(detectors, Mapping) or not detectors:
        return None
    out: list[StreamDef] = []
    for name in names:
        entry = detectors.get(name)
        if not isinstance(entry, Mapping):
            return None
        out.append(
            StreamDef(
                name=name,
                channels=[int(c) for c in entry.get("chs", entry.get("channels", []))],
                micro_time_ranges=[
                    (int(a), int(b)) for a, b in (entry.get("micro_time_ranges") or [])
                ],
            )
        )
    return out


def window_columns(frame) -> list[tuple[int, int]]:
    """Return the micro-time windows a burst table names in its own headers.

    The ``.bur`` writer emits one column per (window, detector) pair, headed
    ``S <window> <detector> (kHz) | <lo>-<hi>``. Those bounds are the windows the
    analysis actually used, so they are the right candidates to try when the
    detector definitions themselves were not recorded — read off the file rather
    than assumed.

    Parameters
    ----------
    frame : pandas.DataFrame or mapping of str to array
        A burst table.

    Returns
    -------
    list of tuple
        Half-open ``(start, stop)`` windows, de-duplicated.
    """
    pattern = re.compile(r"\|\s*(\d+)\s*-\s*(\d+)\s*$")
    out: list[tuple[int, int]] = []
    for column in frame.columns:
        match = pattern.search(str(column))
        if match:
            window = (int(match.group(1)), int(match.group(2)))
            if window not in out:
                out.append(window)
    return out


def infer_streams(
    frame,
    names: Sequence[str],
    tttrs: Mapping[str, Any],
    convention: PhotonIndexConvention,
    *,
    n_probe: int = 250,
    seed: int = 0,
) -> list[StreamDef] | None:
    """Work out each detector's channel definition from the burst table itself.

    A detector *name* does not determine its definition, and the same name means
    different things in different folders: ``red`` is the acceptor channels ungated
    in one analysis and gated to the prompt window in another. Guessing from the
    name is therefore wrong roughly as often as it is right — which is why the
    guess was verified, and why failing verification used to leave a folder
    unreadable with no way forward.

    So infer instead. The candidate space is small and comes from the file: the
    routing channels the measurement actually contains, and the micro-time windows
    the burst table names in its own column headers. A candidate is accepted only
    if it reproduces the detector's count column **exactly** over a probe sample —
    which makes the result a measurement rather than a guess, and is the same
    acceptance the full verification applies afterwards.

    Parameters
    ----------
    frame : pandas.DataFrame or mapping of str to array
        The burst table, sentinel rows removed.
    names : sequence of str
        Detector names to infer.
    tttrs : Mapping
        Open photon streams, keyed by ``First File``.
    convention : PhotonIndexConvention
        How to slice a burst out of the stream.
    n_probe : int
        Bursts to test each candidate on. Exactness over a couple of hundred bursts
        is not something a wrong definition achieves by luck.
    seed : int
        Seed for the probe sample, so inference is deterministic.

    Returns
    -------
    list of StreamDef or None
        ``None`` when any detector could not be reproduced, so the caller can fall
        back and report rather than proceed on a partial answer.
    """
    files = frame["First File"].to_numpy(dtype=object)
    first = frame["First Photon"].to_numpy(dtype=np.int64)
    last = frame["Last Photon"].to_numpy(dtype=np.int64)
    stop_offset = convention.stop_offset

    rows = np.nonzero(np.array([f in tttrs for f in files]))[0]
    if rows.size == 0:
        return None
    if rows.size > n_probe:
        rows = np.sort(
            np.random.default_rng(seed).choice(rows, size=n_probe, replace=False)
        )

    cache = {
        key: (np.asarray(t.routing_channels), np.asarray(t.micro_times))
        for key, t in tttrs.items()
    }
    present = sorted({int(c) for channels, _ in cache.values() for c in np.unique(channels)})
    if not present or len(present) > 8:
        return None

    # Channel subsets worth trying: singletons and pairs cover the conventional
    # colour and polarization layouts, and the full set covers an ungated detector.
    candidates_channels: list[list[int]] = [[c] for c in present]
    for a in range(len(present)):
        for b in range(a + 1, len(present)):
            candidates_channels.append([present[a], present[b]])
    candidates_channels.append(list(present))

    windows: list[tuple[int, int] | None] = [None]
    for window in window_columns(frame):
        windows.append(window)

    def counts_for(channels, window):
        """Return the per-burst count a candidate definition would produce."""
        out = np.empty(rows.size, dtype=np.int64)
        for i, row in enumerate(rows):
            routing, micro = cache[files[row]]
            lo = int(first[row])
            hi = int(last[row]) + stop_offset
            mask = np.isin(routing[lo:hi], channels)
            if window is not None:
                slice_micro = micro[lo:hi]
                mask &= (slice_micro >= window[0]) & (slice_micro < window[1])
            out[i] = int(mask.sum())
        return out

    resolved: list[StreamDef] = []
    for name in names:
        truth = frame[f"Number of Photons ({name})"].to_numpy(dtype=np.int64)[rows]
        found = None
        for channels in candidates_channels:
            for window in windows:
                if np.array_equal(counts_for(channels, window), truth):
                    found = StreamDef(
                        name=name,
                        channels=list(channels),
                        # StreamDef windows are inclusive; the writer's are
                        # half-open, so the upper bound moves by one.
                        micro_time_ranges=(
                            [] if window is None else [(window[0], window[1] - 1)]
                        ),
                    )
                    break
            if found is not None:
                break
        if found is None:
            return None
        resolved.append(found)
    return resolved


def _fallback_streams(names: Sequence[str]) -> list[StreamDef]:
    """Return channel definitions guessed from conventional detector names."""
    known = {s.name: s for s in default_streams()}
    out: list[StreamDef] = []
    for name in names:
        lowered = str(name).lower()
        if lowered in known:
            out.append(
                StreamDef(name=name, channels=list(known[lowered].channels))
            )
        elif lowered in FALLBACK_CHANNELS:
            out.append(
                StreamDef(name=name, channels=list(FALLBACK_CHANNELS[lowered]))
            )
        else:
            out.append(StreamDef(name=name, channels=[]))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# The preparation itself
# ──────────────────────────────────────────────────────────────────────────────
def _detector_masks(
    channels: np.ndarray,
    micro_times: np.ndarray,
    streams: Sequence[StreamDef],
) -> np.ndarray:
    """Return one independent selection mask per detector.

    Detectors in a ``.bur`` table are **not** a partition: the acceptor-excitation
    detector is a micro-time window *inside* the acceptor detector, so the same
    photon belongs to both. That is how the writer computes its columns, and
    reproducing them requires the same independence.

    This is deliberately not
    :func:`~chisurf.core.fluorescence.burst.photons.stream_index_arrays`, which
    assigns each photon to exactly one stream — the right rule for a photon-by-photon
    layout, where a photon counted twice would be a duplicated observation, and the
    wrong one here, where it would leave the delayed detector empty.

    Parameters
    ----------
    channels : numpy.ndarray
        Per-photon routing channel.
    micro_times : numpy.ndarray
        Per-photon micro time, in raw channels.
    streams : sequence of StreamDef
        Detector definitions. Micro-time ranges are inclusive, as
        :class:`~chisurf.core.fluorescence.burst.photons.StreamDef` documents.

    Returns
    -------
    numpy.ndarray
        ``(n_streams, n_photons)`` boolean array.
    """
    out = np.zeros((len(streams), channels.shape[0]), dtype=bool)
    for s, stream in enumerate(streams):
        if not stream.channels:
            continue
        mask = np.isin(channels, np.asarray(stream.channels, dtype=channels.dtype))
        if stream.micro_time_ranges:
            windowed = np.zeros_like(mask)
            for lo, hi in stream.micro_time_ranges:
                windowed |= (micro_times >= lo) & (micro_times <= hi)
            mask &= windowed
        out[s] = mask
    return out


def _mean_micro_time_from_photons(
    frame,
    streams: Sequence[StreamDef],
    tttrs: Mapping[str, Any],
    convention: PhotonIndexConvention,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute per-burst per-detector mean micro time and count from the photons.

    Used for folders written before the writer emitted the column, and as the check
    that a channel definition actually describes this measurement.

    Returns
    -------
    mean_ns, counts : numpy.ndarray
        ``(n_bursts, n_streams)`` arrays; ``mean_ns`` is NaN where the detector has
        no photons.
    """
    n = len(frame)
    k = len(streams)
    mean_ns = np.full((n, k), np.nan)
    counts = np.zeros((n, k), dtype=np.int64)

    first = frame["First Photon"].to_numpy(dtype=np.int64)
    last = frame["Last Photon"].to_numpy(dtype=np.int64)
    files = frame["First File"].to_numpy(dtype=object)
    stop_offset = convention.stop_offset

    cache: dict[str, tuple[np.ndarray, np.ndarray, float]] = {}
    for key, tttr in tttrs.items():
        resolution = float(getattr(tttr.header, "micro_time_resolution", 0.0) or 0.0)
        cache[key] = (
            np.asarray(tttr.routing_channels),
            np.asarray(tttr.micro_times),
            resolution * 1e9,
        )

    for row in range(n):
        key = files[row]
        entry = cache.get(key)
        if entry is None:
            continue
        channels, micro, ns_per_channel = entry
        lo = int(first[row])
        hi = int(last[row]) + stop_offset
        if hi <= lo:
            continue
        mt = micro[lo:hi]
        masks = _detector_masks(channels[lo:hi], mt, streams)
        for s in range(k):
            selected = masks[s]
            n_selected = int(selected.sum())
            counts[row, s] = n_selected
            if n_selected and ns_per_channel > 0.0:
                mean_ns[row, s] = float(np.mean(mt[selected])) * ns_per_channel
    return mean_ns, counts


def prepare_burst_folder(
    folder: pathlib.Path | str,
    *,
    streams: Sequence[StreamDef] | Sequence[dict] | None = None,
    with_photons: bool = False,
    require_channel_agreement: bool = True,
) -> BurstPreparation:
    """Read a burst-analysis folder into the arrays a 2D MFD fit consumes.

    Parameters
    ----------
    folder : path-like
        The analysis folder, its ``bi4_bur`` directory, or a single ``.bur`` file.
    streams : sequence, optional
        Channel definitions, as :class:`~chisurf.core.fluorescence.burst.photons.StreamDef`
        objects or plain dictionaries. When omitted they are taken from the folder's
        manifest, and failing that guessed from the detector names and **checked
        against the count columns**.
    with_photons : bool
        Also load the photon streams and keep them on the result, for the
        pooled-decay and burst-wise scoring sources. The histogram source needs no
        photons at all when the ``.bur`` carries its mean micro time.
    require_channel_agreement : bool
        Raise when a guessed channel definition disagrees with the ``.bur`` count
        columns. Turning it off is for inspecting a folder whose setup is genuinely
        unknown, never for fitting one.

    Returns
    -------
    BurstPreparation

    Raises
    ------
    UnresolvedPhotonSource
        If the photon streams cannot be located or read, and they are needed.
    ValueError
        If the channel definition disagrees with the burst tables.
    """
    analysis_dir, bur_dir = burst_directory(folder)
    paths = sorted(bur_dir.glob("*.bur"))
    if not paths:
        raise FileNotFoundError(f"no .bur tables in {bur_dir}")
    frame = load_bur_dataframe(paths)

    # The .bur format interleaves an all-zero sentinel row between bursts so that
    # the "…4" companions align to it by position. Those rows are not bursts.
    real = ~np.array(
        [is_sentinel_file_reference(v) for v in frame["First File"].to_numpy(object)]
    )
    rows = np.nonzero(real)[0].astype(np.int64)
    n_sentinel = int(real.size - rows.size)
    frame = frame.loc[real].reset_index(drop=True)

    names = detector_names(frame)
    if not names:
        raise ValueError(f"{bur_dir} has no per-detector columns to read")

    convention = photon_index_convention(frame)

    if streams is None:
        resolved_streams = _streams_from_manifest(analysis_dir, names)
        stream_origin = "manifest"
        if resolved_streams is None:
            # Deferred until the photons are open — inference needs them. The
            # name-based guess is only the last resort, because a detector name
            # does not determine its definition: ``red`` is ungated in one
            # analysis and gated to the prompt window in another.
            resolved_streams = None
            stream_origin = "inferred"
    else:
        first_item = next(iter(streams), None)
        resolved_streams = (
            list(streams)
            if isinstance(first_item, StreamDef)
            else streams_from_dicts(list(streams))
        )
        stream_origin = "caller"

    counts = np.column_stack(
        [frame[f"Number of Photons ({n})"].to_numpy(dtype=np.int64) for n in names]
    )
    span_ms = np.column_stack(
        [frame[f"Duration ({n}) (ms)"].to_numpy(dtype=float) for n in names]
    )
    span_is_sentinel = span_ms <= DETECTOR_SENTINEL / 2.0
    spans = np.where(span_is_sentinel, 0.0, span_ms) * 1e-3

    duration = frame["Duration (ms)"].to_numpy(dtype=float) * 1e-3
    total_counts = frame["Number of Photons"].to_numpy(dtype=np.int64)
    first_photon = frame["First Photon"].to_numpy(dtype=np.int64)
    last_photon = frame["Last Photon"].to_numpy(dtype=np.int64)
    if not convention.inclusive:
        last_photon = last_photon - 1
    file_key = frame["First File"].to_numpy(dtype=object)

    micro_columns = [f"Mean Microtime ({n}) (ns)" for n in names]
    has_micro_columns = all(c in frame.columns for c in micro_columns)

    summary: dict[str, Any] = {
        "n_sentinel_rows": n_sentinel,
        "n_bursts": int(len(frame)),
        "stream_origin": stream_origin,
        "count_agreement": {},
        "n_empty": {
            name: int((counts[:, i] == 0).sum()) for i, name in enumerate(names)
        },
    }

    # Inference needs the photons, so a folder that records no detectors has to
    # read them even when its mean-micro-time column would otherwise suffice.
    need_photons = with_photons or not has_micro_columns or resolved_streams is None
    sources = SourceResolution()
    tttrs: dict[str, Any] = {}
    if need_photons:
        sources = resolve_sources(analysis_dir, list(dict.fromkeys(file_key.tolist())))
        tttrs = open_sources(sources)

    if resolved_streams is None:
        resolved_streams = infer_streams(frame, names, tttrs, convention)
        if resolved_streams is None:
            resolved_streams = _fallback_streams(names)
            stream_origin = "detector names (inference failed)"
        else:
            summary["inferred_streams"] = {
                s.name: {
                    "channels": list(s.channels),
                    "micro_time_ranges": [list(r) for r in s.micro_time_ranges],
                }
                for s in resolved_streams
            }
    resolved_streams = list(resolved_streams)

    # Whenever the photons are open, the channel definition is checked against the
    # count columns — including when the mean micro time comes from the file, where
    # the check costs one pass and is the only thing standing between a wrong
    # detector definition and a plausible wrong answer.
    recomputed = None
    if need_photons:
        photon_micro, recomputed = _mean_micro_time_from_photons(
            frame, resolved_streams, tttrs, convention
        )
        for i, name in enumerate(names):
            summary["count_agreement"][name] = float(
                np.mean(recomputed[:, i] == counts[:, i])
            )

    if has_micro_columns:
        mean_micro_time = np.column_stack(
            [frame[c].to_numpy(dtype=float) for c in micro_columns]
        )
        mean_micro_time = np.where(
            mean_micro_time <= DETECTOR_SENTINEL / 2.0, np.nan, mean_micro_time
        )
        summary["mean_micro_time_source"] = "bur column"
    else:
        mean_micro_time = photon_micro
        summary["mean_micro_time_source"] = "photons"

    if recomputed is not None:
        verified = [
            name
            for name in names
            if summary["count_agreement"].get(name, 0.0) >= COUNT_AGREEMENT_REQUIRED
        ]
        summary["unverified_channels"] = tuple(n for n in names if n not in verified)
        if require_channel_agreement and not verified:
            raise ValueError(
                f"no channel definition (from {stream_origin}) describes "
                f"{analysis_dir}: per-detector counts recomputed from the photons "
                "agree with the .bur columns for "
                + ", ".join(
                    f"{k} {v:.3f}" for k, v in summary["count_agreement"].items()
                )
                + ". Pass streams= explicitly, or record the detectors in the "
                "analysis manifest."
            )

    preparation = BurstPreparation(
        channels=tuple(names),
        counts=counts,
        spans=spans,
        span_is_sentinel=span_is_sentinel,
        mean_micro_time=mean_micro_time,
        duration=duration,
        total_counts=total_counts,
        first_photon=first_photon,
        last_photon=last_photon,
        file_key=file_key,
        rows=rows,
        streams=tuple(resolved_streams),
        convention=convention,
        sources=sources,
        folder=analysis_dir,
        summary=summary,
    )
    if with_photons:
        preparation.summary["photons"] = {
            key: int(len(tttr)) for key, tttr in tttrs.items()
        }
        preparation.summary["_tttrs"] = tttrs
    return preparation


def nuisance_measure(
    preparation: BurstPreparation,
    *,
    channels: Sequence[str] = ("green", "red"),
    min_signal: int = 1,
) -> NuisanceMeasure:
    """Build ``D12 = P(S, t_G, t_R)`` from the burst-table columns.

    No new file format and no photon read: ``Duration (<detector>) (ms)`` *is* the
    first-to-last span of that detector's photons within the burst, and
    ``Number of Photons (<detector>)`` is its count, both already written with the
    ``-1.0`` / ``0`` sentinel for a detector a burst has nothing in.

    The span is a **biased** estimator of the true observation time — by roughly
    ``(n − 1) / (n + 1)``, a factor that depends on brightness and therefore on
    something being fitted. It is left biased on purpose: the forward model predicts
    the *observed* span, exactly as it predicts raw axes rather than corrected ones.
    Correcting it here would make the nuisance depend on the parameters.

    Parameters
    ----------
    preparation : BurstPreparation
        From :func:`prepare_burst_folder`.
    channels : sequence of str
        The detectors whose signal and spans make up the measure.
    min_signal : int
        Bursts with less total signal than this are excluded — and **counted** in
        the summary, so a folder where half the bursts are unusable cannot present
        as a clean one.

    Returns
    -------
    NuisanceMeasure
    """
    preparation.require_verified(channels)
    index = [preparation.channel_index(name) for name in channels]
    counts = preparation.counts[:, index]
    spans = preparation.spans[:, index]
    sentinel = preparation.span_is_sentinel[:, index]

    signal = counts.sum(axis=1)
    keep = signal >= int(min_signal)

    # A burst whose channel has fewer than two photons has no measurable span. It is
    # kept — it still carries signal — but its span is the sentinel, and the model
    # must be told which spans are measured rather than inferring it from a zero.
    n_sentinel_spans = {
        name: int(sentinel[keep, i].sum()) for i, name in enumerate(channels)
    }

    summary = {
        "n_input": int(signal.size),
        "n_kept": int(keep.sum()),
        "n_excluded_low_signal": int((~keep).sum()),
        "n_sentinel_spans": n_sentinel_spans,
        "signal_median": float(np.median(signal[keep])) if keep.any() else 0.0,
        "signal_max": int(signal[keep].max()) if keep.any() else 0,
    }
    return NuisanceMeasure(
        signal=signal[keep].astype(np.int64),
        spans=spans[keep],
        counts=counts[keep],
        duration=preparation.duration[keep],
        channels=tuple(channels),
        rows=preparation.rows[keep],
        summary=summary,
    )


def photon_bursts(
    preparation: BurstPreparation,
    *,
    min_photons: int = 2,
    with_micro_times: bool = True,
):
    """Build the packed :class:`PhotonBursts` layout from a prepared folder.

    The photon-bearing scoring sources (pooled per-bin decays, and the burst-wise
    maximum-likelihood reference) need the individual photons rather than their
    per-burst summaries. This is the one loader for them, so the channel and
    micro-time conventions cannot drift between the sources that use it.

    Parameters
    ----------
    preparation : BurstPreparation
        Must have been built with ``with_photons=True``.
    min_photons : int
        Bursts with fewer assigned photons are dropped, as
        :meth:`PhotonBursts.from_lists` requires.
    with_micro_times : bool
        Also return the per-burst micro times, in the same photon order.

    Returns
    -------
    bursts : PhotonBursts
        Times in seconds, colours indexed by ``preparation.streams``.
    micro_times : list of numpy.ndarray, optional
        Only when *with_micro_times* — raw micro-time channels per burst.
    rows : numpy.ndarray
        Positions in *preparation* of the bursts that survived, so a per-burst
        result stays aligned with the burst table.

    Raises
    ------
    ValueError
        If the preparation carries no photons.
    """
    from chisurf.core.fluorescence.burst.gopich_szabo import PhotonBursts

    tttrs = preparation.summary.get("_tttrs")
    if not tttrs:
        raise ValueError(
            "this preparation carries no photons; call prepare_burst_folder(..., "
            "with_photons=True)"
        )

    cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}
    for key, tttr in tttrs.items():
        cache[key] = (
            np.asarray(tttr.macro_times, dtype=np.int64),
            np.asarray(tttr.routing_channels),
            np.asarray(tttr.micro_times),
            float(getattr(tttr.header, "macro_time_resolution", 1.0) or 1.0),
        )

    streams = list(preparation.streams)
    times: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    micro: list[np.ndarray] = []
    kept: list[int] = []
    for row in range(len(preparation)):
        entry = cache.get(preparation.file_key[row])
        if entry is None:
            continue
        macro, channels, micro_times, resolution = entry
        lo = int(preparation.first_photon[row])
        hi = int(preparation.last_photon[row]) + 1
        if hi <= lo:
            continue
        index = stream_index_arrays(channels[lo:hi], micro_times[lo:hi], streams)
        keep = index >= 0
        if int(keep.sum()) < max(int(min_photons), 2):
            continue
        times.append(macro[lo:hi][keep].astype(np.float64) * resolution)
        colors.append(index[keep].astype(np.int32))
        if with_micro_times:
            micro.append(micro_times[lo:hi][keep])
        kept.append(row)

    bursts = PhotonBursts.from_lists(
        times, colors, n_colors=len(streams), min_photons=min_photons
    )
    rows = np.asarray(kept, dtype=np.int64)
    if with_micro_times:
        return bursts, micro, rows
    return bursts, rows
