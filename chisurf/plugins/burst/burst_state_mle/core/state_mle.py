"""Burst- *and* state-wise maximum-likelihood lifetime fitting.

The burst-wise MLE step fits one decay per burst per colour. When a burst
contains dynamics that is the wrong unit: a burst that spends half its time in a
low-FRET state and half in a high-FRET one yields a lifetime that belongs to
neither. H2MM already answers which photon was emitted in which state, so the
fit can be done at the unit the kinetics actually has —

    one decay per (burst, state, colour)

— which is what this module does. It is a *post*-H2MM step by construction: it
consumes an H2MM analysis rather than redoing one.

Everything it needs is already written into the analysis folder by the two steps
before it, so nothing has to be re-derived and nothing can silently disagree:

* ``h2mm_photons.csv`` / ``.h5`` — per-photon ``Burst``, ``State``, ``Channel``,
  ``Micro Time`` (written by H2MM);
* ``h2mm_result.json`` — the stream definitions, i.e. which routing channels
  make up "green" (written by H2MM);
* ``b{g,r,y}4/channel_settings.json`` — the per-detector fit settings, i.e. the
  *instrument*: micro-time window and binning, dt, period, G, l1/l2, start
  values (written by the burst-wise MLE);
* ``Info/experiment_settings.json`` — the IRF and background, i.e. the
  *experiment*: measured per sample, shared by every colour's results, and
  deliberately not part of the channel definition, which outlives any one
  measurement (also written by the burst-wise MLE).

Results are written back in the **same ``.b?4`` format one folder deeper**:
``bg4_s0/``, ``bg4_s1/``, … one folder per state, one file per measurement, one
row per burst. That choice is deliberate: every reader that opens a ``.bg4``
today — the burst browser, ndX, ``bid_to_analysis`` — opens a state folder
unchanged, and because the row order is the burst order in all of them, joining
state 0 to state 1 for the same burst is a row-wise join with no keys. A burst
with too few photons in a state gets the same "no data" sentinel the burst-wise
export already uses, so the row grid stays aligned.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "DetectorFit",
    "STATE_FOLDER_TEMPLATE",
    "detectors_from_analysis",
    "h2mm_output_dir",
    "read_experiment_settings",
    "fit_state_wise",
    "read_photon_table",
    "read_stream_channels",
    "write_state_results",
]

#: How a per-state result folder is named next to ``bg4``/``br4``/``by4``.
STATE_FOLDER_TEMPLATE = "b{letter}4_s{state}"

#: The historical fit23 column layout, so a per-state file is byte-compatible
#: with what every existing reader expects from a ``.b?4``.
def _fit23_columns(colour: str) -> list[str]:
    return [
        "Ng-p-all", "Ng-s-all",
        f"Number of Photons (fit window) ({colour})",
        f"2I*  ({colour})", f"Tau ({colour})", f"gamma ({colour})",
        f"r0 ({colour})", f"rho ({colour})", f"BIFL scatter? ({colour})",
        f"2I*: P+2S? ({colour})", f"r Scatter ({colour})",
        f"r Experimental ({colour})",
    ]


@dataclass
class DetectorFit:
    """Everything needed to fit one colour, resolved from the analysis folder.

    Attributes
    ----------
    name : str
        Detector/colour name as the earlier steps spell it (``"green"``).
    channels : list of int
        Routing channels of this colour. The parallel (VV) channels are
        ``channels[::2]`` and the perpendicular (VH) ones ``channels[1::2]`` —
        the same alternating convention the burst-wise export and the IRF
        extraction use.
    n_bins : int
        Micro-time bins per polarisation (half the VV/VH array length).
    binning : int
        Raw micro-time channels per bin.
    sb, eb : int
        Fit window in binned units.
    dt, period : float
        Bin width and excitation period, nanoseconds.
    irf, background : numpy.ndarray
        VV/VH-stacked instrument response and background, length ``2 * n_bins``.
    g_factor, l1, l2 : float
        Polarisation corrections.
    x0 : list of float
        Initial parameter values.
    fixed : list of int
        Per-parameter fix mask.
    min_photons : int
        Below this, a (burst, state) unit is not fitted.
    p2s_twoIstar, bifl_scatter : bool
        Estimator options.
    """

    name: str
    channels: list[int]
    n_bins: int
    binning: int
    sb: int
    eb: int
    dt: float
    period: float
    irf: np.ndarray
    background: np.ndarray
    g_factor: float = 1.0
    l1: float = 0.0
    l2: float = 0.0
    x0: list[float] = field(default_factory=lambda: [4.0, 0.1, 0.38, 1.22])
    fixed: list[int] = field(default_factory=lambda: [0, 1, 1, 1])
    min_photons: int = 10
    p2s_twoIstar: bool = True
    bifl_scatter: bool = False

    @property
    def letter(self) -> str:
        """The single letter naming this colour's folder (``g`` for green)."""
        return self.name[:1].lower()

    @property
    def vv_channels(self) -> list[int]:
        """Parallel routing channels."""
        return list(self.channels[::2])

    @property
    def vh_channels(self) -> list[int]:
        """Perpendicular routing channels."""
        return list(self.channels[1::2])


def h2mm_output_dir(analysis_dir) -> pathlib.Path:
    """Where an H2MM run left its tables, under *analysis_dir*.

    The CLI, the RPC service and the GUI all write into an ``h2mm/`` subfolder of
    the analysis folder, but a hand-run export may have written into the folder
    itself. Both are searched, subfolder first, so "H2MM has been run" is
    answered by looking rather than by assuming a layout — the mistake that made
    the state-wise step report a finished H2MM as missing.

    Parameters
    ----------
    analysis_dir : path-like

    Returns
    -------
    pathlib.Path
        The directory holding the tables, or *analysis_dir* itself when neither
        candidate has any (so callers raise against a sensible path).
    """
    root = pathlib.Path(analysis_dir)
    marks = ("h2mm_photons.h5", "h2mm_photons.csv", "h2mm_result.json")
    for candidate in (root / "h2mm", root):
        if any((candidate / m).is_file() for m in marks):
            return candidate
    return root


def read_photon_table(analysis_dir):
    """Load H2MM's per-photon table from an analysis folder.

    Prefers the HDF5 the H2MM step writes and falls back to the CSV, because
    which of the two exists depends on whether pytables was importable when the
    fit ran.

    Parameters
    ----------
    analysis_dir : path-like
        The burst-analysis folder (the one holding ``bi4_bur``).

    Returns
    -------
    pandas.DataFrame
        Columns ``Burst``, ``State``, ``Channel``, ``Micro Time`` at least.

    Raises
    ------
    FileNotFoundError
        If neither table is present — H2MM has not been run, or was run with
        photon writing switched off.
    """
    import pandas as pd

    root = h2mm_output_dir(analysis_dir)
    h5 = root / "h2mm_photons.h5"
    csv = root / "h2mm_photons.csv"
    if h5.is_file():
        try:
            return pd.read_hdf(h5, key="results")
        except Exception:  # pragma: no cover - pytables optional
            pass
    if csv.is_file():
        return pd.read_csv(csv)
    raise FileNotFoundError(
        f"no H2MM photon table in {root} — run H2MM first (with 'write photons' on); "
        "the state-wise fit needs the per-photon state assignment"
    )


def read_stream_channels(analysis_dir) -> dict[str, list[int]]:
    """Return ``{colour: routing channels}`` from the H2MM result JSON.

    The stream definitions are the authority on which detectors make up a
    colour, and H2MM records the ones it actually ran with.

    Parameters
    ----------
    analysis_dir : path-like

    Returns
    -------
    dict
        Empty when the result file is absent or carries no stream settings, in
        which case the caller must supply the mapping itself.
    """
    p = h2mm_output_dir(analysis_dir) / "h2mm_result.json"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    streams = (payload.get("settings_applied") or {}).get("streams") or []
    out: dict[str, list[int]] = {}
    for entry in streams:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        channels = [int(c) for c in entry.get("channels", [])]
        if name and channels and name not in out:
            out[name] = channels
    return out


def read_experiment_settings(analysis_dir) -> dict[str, dict]:
    """Return ``{detector: {"irf": [...], "background": [...]}}`` for the experiment.

    The IRF and background are sample-dependent and belong to the measurement,
    not to the channel definition, so they are recorded once per analysis folder
    rather than inside each ``b?4``'s instrument description.

    Parameters
    ----------
    analysis_dir : path-like

    Returns
    -------
    dict
        Empty when the record is missing — which means the burst-wise MLE ran
        before this was written, and the folder cannot say which IRF it used.
    """
    p = pathlib.Path(analysis_dir) / "Info" / "experiment_settings.json"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    detectors = (payload or {}).get("detectors") or {}
    return {str(k): v for k, v in detectors.items() if isinstance(v, dict)}


def detectors_from_analysis(analysis_dir, *, channels=None) -> list[DetectorFit]:
    """Resolve one :class:`DetectorFit` per colour from the analysis folder.

    Three records are combined, each owned by the step that knows it: the
    *instrument* settings the burst-wise MLE wrote (``b?4/channel_settings.json``),
    the *experiment*'s IRF and background (``Info/experiment_settings.json``),
    and the stream definitions H2MM recorded.

    Parameters
    ----------
    analysis_dir : path-like
    channels : dict, optional
        ``{colour: routing channels}``, overriding what the H2MM result records.

    Returns
    -------
    list of DetectorFit
        Only colours that have settings, channels and an IRF; a colour that was
        never fitted burst-wise cannot be fitted state-wise either.

    Raises
    ------
    FileNotFoundError
        If no ``b?4/channel_settings.json`` exists at all.
    """
    root = pathlib.Path(analysis_dir)
    settings_files = sorted(root.glob("b?4/channel_settings.json"))
    if not settings_files:
        raise FileNotFoundError(
            f"no b?4/channel_settings.json in {root} — run the burst-wise MLE "
            "first; its settings are what the state-wise fit repeats"
        )

    merged: dict[str, dict] = {}
    for path in settings_files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for det, st in (payload or {}).items():
            if isinstance(st, dict):
                merged.setdefault(str(det), st)

    experiment = read_experiment_settings(root)
    stream_channels = dict(read_stream_channels(root))
    if channels:
        stream_channels.update({str(k): [int(c) for c in v] for k, v in channels.items()})

    out: list[DetectorFit] = []
    for name, st in merged.items():
        chans = stream_channels.get(name)
        if not chans:
            continue
        exp = experiment.get(name, {})
        irf = np.asarray(exp.get("irf", []), dtype=float).ravel()
        bg = np.asarray(exp.get("background", []), dtype=float).ravel()
        if irf.size < 2:
            continue
        n_bins = int(irf.size // 2)
        if bg.size != irf.size:
            bg = np.zeros_like(irf)
        binning = max(int(st.get("micro_time_binning", 1) or 1), 1)
        sb = int(st.get("micro_time_start", 0)) // binning
        eb = int(st.get("micro_time_stop", n_bins * binning)) // binning
        out.append(
            DetectorFit(
                name=name,
                channels=list(chans),
                n_bins=n_bins,
                binning=binning,
                sb=max(0, min(sb, n_bins)),
                eb=max(0, min(eb, n_bins)),
                dt=float(st.get("dt", 0.0)),
                period=float(st.get("excitation_period", 0.0)),
                irf=irf,
                background=bg,
                g_factor=float(st.get("g_factor", 1.0)),
                l1=float(st.get("l1", 0.0)),
                l2=float(st.get("l2", 0.0)),
                x0=[float(v) for v in st.get("initial_x0", [4.0, 0.1, 0.38, 1.22])],
                fixed=[int(v) for v in st.get("fixed_flags", [0, 1, 1, 1])],
                min_photons=int(st.get("min_photons", 10)),
                p2s_twoIstar=bool(st.get("p2s_twoIstar", True)),
                bifl_scatter=bool(st.get("BIFL_scatter", False)),
            )
        )
    return out


def _decay(micro_binned, channel, det: DetectorFit) -> tuple[np.ndarray, int, int]:
    """VV/VH-stacked histogram of one photon selection, plus the two sums."""
    n = det.n_bins
    out = np.zeros(2 * n, dtype=np.float64)
    vv = np.isin(channel, det.vv_channels)
    vh = np.isin(channel, det.vh_channels)
    cp = np.bincount(micro_binned[vv], minlength=n)[:n]
    cs = np.bincount(micro_binned[vh], minlength=n)[:n]
    s0, s1 = det.sb, det.eb
    if s1 > s0:
        out[s0:s1] = cp[s0:s1]
        out[n + s0 : n + s1] = cs[s0:s1]
    return out, int(cp.sum()), int(cs.sum())


def fit_state_wise(photons, detectors, *, model: str = "fit23", progress=None):
    """Fit one decay per ``(burst, state, colour)``.

    Parameters
    ----------
    photons : pandas.DataFrame
        H2MM's per-photon table (``Burst``, ``State``, ``Channel``,
        ``Micro Time``), from :func:`read_photon_table`.
    detectors : sequence of DetectorFit
        One per colour, from :func:`detectors_from_analysis`.
    model : str, optional
        fit2x estimator name (``"fit23"``).
    progress : callable, optional
        Called as ``progress(done, total)`` after each burst.

    Returns
    -------
    pandas.DataFrame
        One row per fitted ``(Burst, State, Detector)`` with the estimated
        parameters, ``2I*`` and the photon counts. Units below
        ``min_photons`` are reported with the "no data" sentinel rather than
        dropped, so a caller can tell "too few photons" from "never tried".
    """
    import pandas as pd

    from chisurf.core.fluorescence.mle import Fit2x, Fit2xModel, Fit2xSettings

    burst = np.asarray(photons["Burst"], dtype=np.int64)
    state = np.asarray(photons["State"], dtype=np.int64)
    chan = np.asarray(photons["Channel"], dtype=np.int64)
    micro = np.asarray(photons["Micro Time"], dtype=np.int64)

    fitters = {}
    for det in detectors:
        settings = Fit2xSettings(
            dt=det.dt, period=det.period, irf=det.irf, background=det.background,
            g_factor=det.g_factor, l1=det.l1, l2=det.l2,
            p2s_twoIstar=det.p2s_twoIstar, soft_bifl_scatter=det.bifl_scatter,
        )
        fitters[det.name] = Fit2x(settings, Fit2xModel(model))

    order = np.lexsort((state, burst))
    burst, state, chan, micro = burst[order], state[order], chan[order], micro[order]
    # One boundary per (burst, state) run — the units to fit.
    change = np.flatnonzero(np.diff(burst) | np.diff(state)) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [burst.size]))

    rows = []
    total = starts.size
    for k, (a, b) in enumerate(zip(starts, stops)):
        bi, si = int(burst[a]), int(state[a])
        m_all, c_all = micro[a:b], chan[a:b]
        for det in detectors:
            binned = np.clip(m_all // det.binning, 0, det.n_bins - 1)
            data, cp, cs = _decay(binned, c_all, det)
            row = {
                "Burst": bi, "State": si, "Detector": det.name,
                "Ng-p-all": cp, "Ng-s-all": cs,
            }
            if cp + cs < det.min_photons:
                row.update({
                    "Number of Photons (fit window)": cp + cs,
                    "2I*": np.nan, "Tau": np.nan, "gamma": np.nan,
                    "r0": np.nan, "rho": np.nan, "Fitted": 0,
                })
            else:
                res = fitters[det.name].fit(data, det.x0, det.fixed)
                x = np.asarray(res.x, dtype=float)
                row.update({
                    "Number of Photons (fit window)": float(data.sum()),
                    "2I*": float(res.twoIstar),
                    "Tau": float(x[0]) if x.size > 0 else np.nan,
                    "gamma": float(x[1]) if x.size > 1 else np.nan,
                    "r0": float(x[2]) if x.size > 2 else np.nan,
                    "rho": float(x[3]) if x.size > 3 else np.nan,
                    "Fitted": 1,
                })
            rows.append(row)
        if progress is not None and (k % 64 == 0 or k == total - 1):
            progress(k + 1, total)
    return pd.DataFrame(rows)


def write_state_results(results, analysis_dir, detectors, *, file_stem=None) -> list:
    """Write per-state ``.b?4`` folders next to the burst-wise ones.

    One folder per ``(colour, state)`` — ``bg4_s0``, ``bg4_s1``, … — each holding
    the same zero-interleaved layout and column names as the burst-wise export,
    so an existing reader opens it without knowing states exist. Every folder
    carries **every** burst, so the row index is the burst index in all of them
    and two states can be joined row-wise.

    Parameters
    ----------
    results : pandas.DataFrame
        From :func:`fit_state_wise`.
    analysis_dir : path-like
        The burst-analysis folder.
    detectors : sequence of DetectorFit
    file_stem : str, optional
        Base name of the written file. Defaults to the measurement stem when a
        single ``bi4_bur`` file exists, else ``"all"``.

    Returns
    -------
    list of pathlib.Path
        Every file written.
    """
    root = pathlib.Path(analysis_dir)
    if file_stem is None:
        burs = sorted((root / "bi4_bur").glob("*.bur")) if (root / "bi4_bur").is_dir() else []
        file_stem = burs[0].stem if len(burs) == 1 else "all"

    n_bursts = int(results["Burst"].max()) + 1 if len(results) else 0
    written = []
    by_det = {d.name: d for d in detectors}
    for (det_name, st), grp in results.groupby(["Detector", "State"], sort=True):
        det = by_det.get(det_name)
        if det is None:
            continue
        colour = det.name.lower()
        cols = _fit23_columns(colour)
        # A full burst grid, so every state folder has the same rows in the same
        # order and a burst missing from a state reads as "no data", not as a
        # shifted row.
        table = np.zeros((n_bursts, len(cols)), dtype=float)
        table[:] = 0.0
        idx = grp["Burst"].to_numpy(dtype=int)
        table[idx, 0] = grp["Ng-p-all"].to_numpy(dtype=float)
        table[idx, 1] = grp["Ng-s-all"].to_numpy(dtype=float)
        table[idx, 2] = grp["Number of Photons (fit window)"].to_numpy(dtype=float)
        table[idx, 3] = np.nan_to_num(grp["2I*"].to_numpy(dtype=float))
        table[idx, 4] = np.nan_to_num(grp["Tau"].to_numpy(dtype=float))
        table[idx, 5] = np.nan_to_num(grp["gamma"].to_numpy(dtype=float))
        table[idx, 6] = np.nan_to_num(grp["r0"].to_numpy(dtype=float))
        table[idx, 7] = np.nan_to_num(grp["rho"].to_numpy(dtype=float))
        table[idx, 8] = float(det.bifl_scatter)
        table[idx, 9] = float(det.p2s_twoIstar)

        out_dir = root / STATE_FOLDER_TEMPLATE.format(letter=det.letter, state=int(st))
        out_dir.mkdir(parents=True, exist_ok=True)
        interleaved = np.zeros((table.shape[0] * 2 + 1, table.shape[1]), dtype=float)
        interleaved[1::2] = table
        out_file = out_dir / f"{file_stem}.b{det.letter}4"
        with open(out_file, "w", newline="") as fh:
            fh.write("\t".join(cols) + "\t\n")
            np.savetxt(fh, interleaved, delimiter="\t", fmt="%.6f")
        written.append(out_file)

    # One tidy table beside them: every state of every burst in long form, which
    # is the shape to filter and group, where the .b?4 grid is the shape existing
    # readers expect.
    if len(results):
        info = root / "Info"
        info.mkdir(parents=True, exist_ok=True)
        tidy = info / "state_mle.csv"
        results.to_csv(tidy, index=False)
        written.append(tidy)
    return written
