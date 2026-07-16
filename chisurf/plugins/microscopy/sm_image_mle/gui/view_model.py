"""Qt-free view-model for the molecule-wise MLE tool.

Holds the CLSM/IRF file lists and analysis settings edited through the AutoForm
view (``molecule_mle.view.json``), runs the Qt-free core
(:func:`...core.molecule_mle.fit_molecules_from_files`) over the selected files,
and exposes the segmentation image, molecule markers and per-molecule table for
display.  No Qt imports — the heavy ``run`` is driven from a background thread by
the tool.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
from collections.abc import Callable

import numpy as np

from ..core.molecule_mle import MoleculeMleResult, MoleculeMleSettings

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "molecule_mle.view.json"


class MoleculeMleViewModel:
    """State + logic for the molecule-wise MLE tool (no Qt)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.irf_files: list[str] = []
        self.settings = MoleculeMleSettings()
        self.status_text: str = ""
        #: Per-file results of the last run (display uses the first).
        self.results: list[MoleculeMleResult] = []
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── observer hook ──
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb*, called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers that state changed."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("molecule-MLE observer failed", exc_info=True)

    # ── shared-setup hook (Imaging Tools aggregator) ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt detector channels / micro-time range from a shared definition."""
        if not payload:
            return
        detectors = payload.get("detectors") or {}
        channels: list[int] = []
        micro_range = None
        for det in detectors.values():
            if not isinstance(det, dict):
                continue
            for ch in det.get("chs", []) or []:
                if ch not in channels:
                    channels.append(ch)
            if micro_range is None:
                ranges = det.get("mtr") or det.get("microtime_ranges")
                if ranges:
                    micro_range = ranges[0]
        if channels:
            self.settings.detector_chs = channels
        if micro_range and len(micro_range) == 2:
            self.settings.micro_time_range = (int(micro_range[0]), int(micro_range[1]))
        self.notify("setup")

    # ── path-list bindings ──
    @property
    def sel_files(self) -> list:
        """CLSM imaging files to analyse (bound to the `path_list`)."""
        return list(self.files)

    @sel_files.setter
    def sel_files(self, value) -> None:
        self.files = [str(v) for v in (value or [])]

    @property
    def sel_irf_files(self) -> list:
        """IRF file(s); the first is used (bound to the `path_list`)."""
        return list(self.irf_files)

    @sel_irf_files.setter
    def sel_irf_files(self, value) -> None:
        self.irf_files = [str(v) for v in (value or [])]

    # ── scalar settings bindings (AutoForm value/choice/toggle sections) ──
    @property
    def detector_chs_text(self) -> str:
        """Detector channels as a space-separated string (even=∥, odd=⊥)."""
        return " ".join(str(c) for c in self.settings.detector_chs)

    @detector_chs_text.setter
    def detector_chs_text(self, value) -> None:
        try:
            self.settings.detector_chs = [int(x) for x in str(value).replace(",", " ").split()]
        except ValueError:
            logger.debug("invalid detector-channel text: %r", value)

    @property
    def mtr_start(self) -> int:
        """Fit-window start (binned micro-time channel)."""
        return int(self.settings.micro_time_range[0])

    @mtr_start.setter
    def mtr_start(self, value) -> None:
        self.settings.micro_time_range = (int(value), self.settings.micro_time_range[1])

    @property
    def mtr_stop(self) -> int:
        """Fit-window stop (binned micro-time channel)."""
        return int(self.settings.micro_time_range[1])

    @mtr_stop.setter
    def mtr_stop(self, value) -> None:
        self.settings.micro_time_range = (self.settings.micro_time_range[0], int(value))

    def _scalar(name, cast, doc):  # noqa: N805 - descriptor factory
        """Build a property proxying ``self.settings.<name>``."""

        def getter(self):
            return cast(getattr(self.settings, name))

        def setter(self, value):
            setattr(self.settings, name, cast(value))

        getter.__doc__ = doc
        return property(getter, setter)

    micro_time_binning = _scalar("micro_time_binning", int, "Micro-time down-binning factor.")
    seg_sigma = _scalar("seg_sigma", float, "Segmentation Gaussian sigma.")
    seg_threshold = _scalar("seg_threshold", float, "Segmentation threshold (<0 = Otsu).")
    peak_footprint_size = _scalar("peak_footprint_size", int, "Peak-detection footprint size.")
    min_photons = _scalar("min_photons", int, "Minimum photons per molecule to fit.")
    min_area = _scalar("min_area", int, "Minimum molecule area (pixels).")
    tau = _scalar("tau", float, "Initial lifetime (ns).")
    gamma = _scalar("gamma", float, "Initial scatter fraction.")
    r0 = _scalar("r0", float, "Initial fundamental anisotropy.")
    rho = _scalar("rho", float, "Initial rotational correlation time (ns).")
    fix_tau = _scalar("fix_tau", bool, "Fix the lifetime.")
    fix_gamma = _scalar("fix_gamma", bool, "Fix the scatter fraction.")
    fix_r0 = _scalar("fix_r0", bool, "Fix the fundamental anisotropy.")
    fix_rho = _scalar("fix_rho", bool, "Fix the rotational correlation time.")
    l1 = _scalar("l1", float, "Polarisation mixing correction l1.")
    l2 = _scalar("l2", float, "Polarisation mixing correction l2.")
    p2s_twoIstar = _scalar("p2s_twoIstar", bool, "Optimise P+2S (2I*).")
    soft_bifl_scatter = _scalar("soft_bifl_scatter", bool, "Soft BIFL scatter.")

    del _scalar

    # ── results accessors (AutoForm image / table / info) ──
    def _display_result(self) -> MoleculeMleResult | None:
        return self.results[0] if self.results else None

    def segmentation_image(self):
        """2-D total-intensity image of the displayed file (for the image dock)."""
        result = self._display_result()
        if result is None:
            return None
        return np.asarray(result.intensity_image)

    def molecule_markers(self) -> list:
        """Molecule centroids as ``(z, y, x)`` markers on the segmentation image."""
        result = self._display_result()
        if result is None or result.centroids.size == 0:
            return []
        return [(0, float(r), float(c)) for r, c in result.centroids]

    def molecule_rows(self) -> list[dict]:
        """Per-molecule rows (all files) for the results table."""
        rows: list[dict] = []
        for result in self.results:
            for rec in result.dataframe.to_dict("records"):
                rows.append(
                    {
                        "label": int(rec.get("label", 0)),
                        "tau": round(float(rec.get("tau", float("nan"))), 3),
                        "gamma": round(float(rec.get("gamma", float("nan"))), 3),
                        "rho": round(float(rec.get("rho", float("nan"))), 3),
                        "photons": int(rec.get("n_photons_total", 0)),
                        "2I*": round(float(rec.get("2I*", float("nan"))), 3),
                    }
                )
        return rows

    def info_html(self) -> str:
        """Status / summary text shown above the results."""
        if self.status_text:
            return f"<i>{self.status_text}</i>"
        if not self.results:
            return (
                "<i>Add CLSM imaging file(s) and an IRF, set the detector channels "
                "and fit window, then press <b>Run</b>. Each molecule is segmented "
                "and fitted with a single-lifetime Poisson-MLE (Fit23).</i>"
            )
        n_mol = sum(r.n_molecules for r in self.results)
        taus = [float(t) for r in self.results for t in r.dataframe.get("tau", [])]
        median = float(np.median(taus)) if taus else float("nan")
        return (
            f"<b>{n_mol}</b> molecule(s) in <b>{len(self.results)}</b> file(s); "
            f"median &tau; = <b>{median:.2f}</b> ns."
        )

    # ── the run action ──
    def request_run(self) -> None:
        """Button action: ask the host to start the analysis on a worker thread.

        The actual (blocking) :meth:`run` is launched by the tool in response to
        the ``start_run`` event, so the UI never blocks on the button click.
        """
        self.notify("start_run")

    def can_run(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether a run is possible."""
        if not self.files:
            return False, "No imaging files selected."
        if not self.irf_files:
            return False, "No IRF file selected."
        return True, ""

    def run(self) -> None:
        """Analyse every selected file (BLOCKING — call from a worker thread).

        Segments and fits each file, writes a per-file ``molecule_data.tsv`` and a
        merged ``joint_output.tsv``, and keeps the results for display.
        """
        import pandas as pd

        from ..core.molecule_mle import fit_molecules_from_files

        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return

        irf = self.irf_files[0]
        self.results = []
        frames: list[pd.DataFrame] = []
        for i, path in enumerate(self.files):
            self.status_text = f"Analysing {pathlib.Path(path).name} ({i + 1}/{len(self.files)})…"
            self.notify("progress")
            try:
                result = fit_molecules_from_files(path, irf, dataclasses.replace(self.settings))
            except Exception as exc:  # noqa: BLE001 - surfaced in the status line
                logger.debug("molecule MLE failed for %s", path, exc_info=True)
                self.status_text = f"{pathlib.Path(path).name}: {exc}"
                continue
            self.results.append(result)
            frames.append(self._write_tsv(path, result.dataframe))

        # Merged joint TSV next to the first file.
        frames = [f for f in frames if f is not None and not f.empty]
        if frames:
            try:
                joint = pathlib.Path(self.files[0]).parent / "joint_output.tsv"
                pd.concat(frames, ignore_index=True).to_csv(joint, sep="\t", index=False)
            except Exception:
                logger.debug("joint TSV export failed", exc_info=True)

        self.status_text = ""
        self.notify("done")

    @staticmethod
    def _write_tsv(path: str, dataframe):
        """Write one file's molecule table next to it; return the labelled frame."""
        if dataframe is None or dataframe.empty:
            return dataframe
        df = dataframe.copy()
        df.insert(0, "source_ptu", str(path))
        out_dir = pathlib.Path(path).parent / f"{pathlib.Path(path).stem}_analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_dir / "molecule_data.tsv", sep="\t", index=False)
        return df
