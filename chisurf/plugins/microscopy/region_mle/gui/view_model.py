"""Qt-free view-model for the molecule-wise MLE tool.

Holds the CLSM/IRF file lists and analysis settings edited through the AutoForm
view (``region_mle.view.json``), runs the Qt-free core
(:func:`...core.region_mle.fit_regions_from_files`) over the selected files,
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

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    numeric_column,
    read_csv_table,
    row_count,
    rows_from_table,
    take_where,
    write_csv_table,
)
from chisurf.core.roi import RegionCollection
from chisurf.plugins.microscopy.mle_common.base import MleObserverMixin, scalar

from ..core.region_mle import (
    RegionMleResult,
    RegionMleSettings,
    with_source_column,
)

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "region_mle.view.json"


class RegionMleViewModel(MleObserverMixin):
    """State + logic for the molecule-wise MLE tool (no Qt)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        self.irf_files: list[str] = []
        #: The analysis region, as the shared named list every ROI GUI edits.
        #: Empty (or all switched off) means the whole frame.
        self.regions = RegionCollection(combine="and", name="analysis region")
        self.settings = RegionMleSettings()
        self.status_text: str = ""
        #: Per-file results of the last run.
        self.results: list[RegionMleResult] = []
        #: Flat index of the molecule shown in the browser.
        self.current_molecule: int = 0
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── observer hook ──

    # ── shared-setup hook (Imaging Tools aggregator) ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt detector channels, micro-time range and polarisation corrections.

        Channels, fit window **and** the G-factor / l1 / l2 mixing corrections
        come from the shared detector definition; previously the corrections
        were dropped here and the fit silently ran at ``g=1, l1=l2=0``.
        """
        from chisurf.core.fluorescence.mle import parse_detector_setup

        setup = parse_detector_setup(payload)
        if not payload:
            return
        if setup.channels:
            self.settings.detector_chs = setup.channels
        if setup.micro_range is not None:
            self.settings.micro_time_range = setup.micro_range
        if setup.g_factor is not None:
            self.settings.g_factor = setup.g_factor
            # The setup value is authoritative; do not overwrite it with the
            # IRF-tail estimate during the fit.
            self.settings.auto_g_factor = False
        if setup.l1 is not None:
            self.settings.l1 = setup.l1
        if setup.l2 is not None:
            self.settings.l2 = setup.l2
        self.notify("setup")

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the imaging pipeline's source TTTR as the file to analyse."""
        source = (payload or {}).get("source")
        if source and str(source) not in self.files:
            self.files.append(str(source))
            self.notify("pipeline")

    def apply_calibration(self, calibration: dict) -> None:
        """Adopt IRF file + convolution window from the shared IRF & BG step.

        Uses the first calibrated detector's IRF file(s) as the tool's IRF and its
        convolution range as the micro-time fit window, so the calibration carries
        on instead of being re-entered here.
        """
        entry = next((v for v in (calibration or {}).values() if v), None)
        if not entry:
            return
        irf_files = entry.get("irf") or []
        if isinstance(irf_files, str):
            irf_files = [irf_files]
        if irf_files:
            self.irf_files = [str(f) for f in irf_files]
        start, stop = int(entry.get("conv_start") or 0), int(entry.get("conv_stop") or 0)
        if stop > start:
            self.settings.micro_time_range = (start, stop)
        self.notify("calibration")

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

    # ── the analysis region ──
    def apply_regions(self) -> None:
        """Push the combined region into the settings the analysis reads.

        ``RegionMleSettings`` takes a single region because it crosses an RPC
        boundary as plain data; the list is the editing surface, and this is
        where it collapses to the one region the segmentation is confined to.
        ``None`` — nothing enabled — means the whole frame.
        """
        self.settings.roi = self.regions.combined()
        self.notify("region")

    def analysis_extent(self) -> tuple:
        """Where a newly drawn region should be placed: the frame's own box."""
        image = self.segmentation_image()
        if image is None:
            return (0.0, 100.0, 0.0, 100.0)
        return (0.0, float(image.shape[-1]), 0.0, float(image.shape[-2]))

    def molecule_regions(self) -> RegionCollection:
        """Return the segmented molecules as regions, drawn from their properties.

        Each molecule becomes the ellipse with the same second moments as the
        object — its centroid, its major and minor axis lengths and its
        orientation, which are the numbers already in the result table. That is
        what makes the outline worth drawing: it shows what was *measured*, so a
        segmentation can be checked against the image it came from rather than
        trusted. It is also the loop the region subsystem is for — a measured
        object becomes a region that can be gated with, combined and stored like
        a drawn one.
        """
        collection = RegionCollection(combine="or", name="molecules")
        for ri, result in enumerate(self.results):
            tag = f"F{ri + 1}·" if len(self.results) > 1 else ""
            for props in result.region_properties():
                collection.add(props.as_ellipse(f"{tag}Mol {props.label}"))
        return collection

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

    micro_time_binning = scalar("micro_time_binning", int, "Micro-time down-binning factor.")
    min_photons = scalar("min_photons", int, "Minimum photons per region to fit.")
    region_set = scalar("region_set", str, "Which detection in the container to fit.")
    tau = scalar("tau", float, "Initial lifetime (ns).")
    gamma = scalar("gamma", float, "Initial scatter fraction.")
    r0 = scalar("r0", float, "Initial fundamental anisotropy.")
    rho = scalar("rho", float, "Initial rotational correlation time (ns).")
    fix_tau = scalar("fix_tau", bool, "Fix the lifetime.")
    fix_gamma = scalar("fix_gamma", bool, "Fix the scatter fraction.")
    fix_r0 = scalar("fix_r0", bool, "Fix the fundamental anisotropy.")
    fix_rho = scalar("fix_rho", bool, "Fix the rotational correlation time.")
    l1 = scalar("l1", float, "Polarisation mixing correction l1.")
    l2 = scalar("l2", float, "Polarisation mixing correction l2.")
    p2s_twoIstar = scalar("p2s_twoIstar", bool, "Optimise P+2S (2I*).")
    soft_bifl_scatter = scalar("soft_bifl_scatter", bool, "Soft BIFL scatter.")

    # ── results accessors (AutoForm image_browser) ──
    def _flat_molecules(self) -> list[tuple[int, int]]:
        """Flat ``(result_index, table_row)`` list over every molecule."""
        return [
            (ri, row)
            for ri, result in enumerate(self.results)
            for row in range(row_count(result.dataframe))
        ]

    def _current_molecule(self):
        """Return ``(result, row, row_record)`` for the selected molecule, or None."""
        flat = self._flat_molecules()
        if not flat:
            return None
        idx = int(self.current_molecule) if 0 <= self.current_molecule < len(flat) else 0
        ri, row = flat[idx]
        result = self.results[ri]
        return result, row, rows_from_table(result.dataframe)[row]

    def molecule_entries(self) -> list[dict]:
        """Browsable molecule entries (id = flat index; badge = fitted τ)."""
        entries: list[dict] = []
        idx = 0
        for ri, result in enumerate(self.results):
            file_tag = f"F{ri + 1}·" if len(self.results) > 1 else ""
            for rec in rows_from_table(result.dataframe):
                tau = float(rec.get("tau", float("nan")))
                # Un-fitted (preview) molecules show their area instead of τ.
                badge = f"τ={tau:.2f} ns" if np.isfinite(tau) else f"{int(rec.get('area', 0))} px"
                entries.append({
                    "id": idx,
                    "label": f"{file_tag}Region {int(rec.get('label', idx))}",
                    "badge": badge,
                })
                idx += 1
        return entries

    def segmentation_image(self):
        """Total-intensity image of the current molecule's file (for the canvas)."""
        cur = self._current_molecule()
        if cur is None:
            return None
        return np.asarray(cur[0].intensity_image)

    def current_molecule_marker(self) -> list:
        """Return the selected molecule's centroid as one ``(z, y, x)`` marker."""
        cur = self._current_molecule()
        if cur is None:
            return []
        rec = cur[2]
        return [(0, float(rec.get("centroid_row", 0.0)), float(rec.get("centroid_col", 0.0)))]

    def current_region_curves(self):
        """Return the selected region's fit as a :class:`DecayCurves`.

        The same object the burst-wise tool's panel draws, so a region's decay
        and a burst's decay are one picture with one set of display rules —
        including the ones that only matter when the fit went wrong (a clipped
        runaway model, an area-matched IRF, a range pinned to the data).

        Returns
        -------
        chisurf.core.fluorescence.mle.display.DecayCurves or None
            ``None`` when nothing is selected or the run kept no curves, which
            clears the panel rather than leaving the previous region's decay
            beside a table row it does not belong to.
        """
        from chisurf.core.fluorescence.mle.display import decay_curves

        cur = self._current_molecule()
        if cur is None:
            return None
        result, row, _rec = cur
        if row >= len(result.vv_vh_vectors):
            return None
        data = np.asarray(result.vv_vh_vectors[row], dtype=float)
        if row < len(result.model_curves):
            model = np.asarray(result.model_curves[row], dtype=float)
        else:
            # A batch run fits with `fit_many` and keeps no per-region model, so
            # there is a decay to show and no curve over it. Better than
            # nothing: the data alone, with residuals that are honestly zero.
            model = np.zeros_like(data)
        if model.size != data.size:
            model = np.zeros_like(data)
        return decay_curves(
            data, model,
            irf=self.settings.irf,
            background=self.settings.background,
        )

    def current_molecule_decay(self) -> list[dict]:
        """Return data + fitted-model decay series for the selected molecule."""
        cur = self._current_molecule()
        if cur is None:
            return []
        result, row, _ = cur
        if row >= len(result.vv_vh_vectors):
            return []
        data = np.asarray(result.vv_vh_vectors[row], dtype=float)
        x = np.arange(data.size)
        series = [{"x": x, "y": data, "name": "Data", "color": "#3b82f6"}]
        if row < len(result.model_curves):
            model = np.asarray(result.model_curves[row], dtype=float)
            if model.size == data.size:
                series.append({"x": x, "y": model, "name": "Fit", "color": "#ef4444", "style": "dash"})
        return series

    def current_molecule_info(self) -> str:
        """HTML fit summary for the selected molecule (metadata panel)."""
        cur = self._current_molecule()
        if cur is None:
            return "<i>No region selected.</i>"
        rec = cur[2]

        def g(key, fmt="{:.3f}"):
            try:
                return fmt.format(float(rec.get(key, float("nan"))))
            except (TypeError, ValueError):
                return "—"

        return (
            f"<b>Region {int(rec.get('label', 0))}</b><br>"
            f"τ = {g('tau')} ns &nbsp; γ = {g('gamma')}<br>"
            f"r0 = {g('r0')} &nbsp; ρ = {g('rho')} ns<br>"
            f"photons = {int(rec.get('n_photons_total', 0))} &nbsp; 2I* = {g('2I*')}"
        )

    def info_html(self) -> str:
        """Status / summary text shown above the results."""
        if self.status_text:
            return f"<i>{self.status_text}</i>"
        if not self.results:
            return (
                "<i>Find the regions first with the <b>Spot Finder</b>, then add "
                "the imaging file(s) and an IRF here, set the detector channels "
                "and fit window, and press <b>Run</b>. Each region is fitted with "
                "a single-lifetime Poisson-MLE (Fit23); this tool does not "
                "segment.</i>"
            )
        n_mol = sum(r.n_molecules for r in self.results)
        taus = [float(t) for r in self.results for t in r.dataframe.get("tau", [])]
        median = float(np.median(taus)) if taus else float("nan")
        return (
            f"<b>{n_mol}</b> region(s) in <b>{len(self.results)}</b> file(s); "
            f"median &tau; = <b>{median:.2f}</b> ns."
        )

    # ── the run action ──
    def request_run(self) -> None:
        """Button action: ask the host to start the analysis on a worker thread.

        The actual (blocking) :meth:`run` is launched by the tool in response to
        the ``start_run`` event, so the UI never blocks on the button click.
        """
        self.notify("start_run")

    def request_preview(self) -> None:
        """Button action: ask the host to preview the segmentation on a worker."""
        self.notify("start_preview")

    def request_export(self) -> None:
        """Button action: ask the host for a path and export the molecule table."""
        self.notify("start_export")

    def has_results(self) -> bool:
        """Return True when there is a molecule table to export."""
        return any(row_count(r.dataframe) for r in self.results)

    def export_results(self, path: str) -> str:
        """Write the combined per-molecule table (all files) to *path* (TSV/CSV).

        Returns the written path (empty string when there is nothing to export).
        The separator is inferred from the extension (``.csv`` → comma, else tab).
        """
        from chisurf.core.fio.fluorescence.burst_container import as_table

        # Through the frame boundary: `concat_stores` refuses a frame, and a
        # result computed before the store migration is still one.
        tables = [
            as_table(r.dataframe) for r in self.results if row_count(r.dataframe)
        ]
        if not tables:
            self.status_text = "No regions to export."
            self.notify("done")
            return ""
        sep = "," if str(path).lower().endswith(".csv") else "\t"
        combined = concat_stores(tables)
        write_csv_table(path, combined, delimiter=sep)
        self.status_text = (
            f"Exported {row_count(combined)} region(s) to {pathlib.Path(path).name}")
        self.notify("exported")
        return str(path)

    def can_run(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether a run is possible."""
        if not self.files:
            return False, "No imaging files selected."
        if not self.irf_files:
            return False, "No IRF file selected."
        return True, ""

    def preview_regions(self) -> None:
        """Measure the regions to be fitted, without fitting them.

        Builds an un-fitted, browsable :class:`RegionMleResult` (intensity +
        labels + one row per region), so what is about to be fitted can be
        looked at first. It resolves the regions through the same call the fit
        uses, which is why the preview cannot disagree with the run.
        BLOCKING — call from a worker thread.
        """
        import tttrlib

        from ..core.region_mle import region_preview

        if not self.files:
            self.status_text = "No imaging files selected."
            self.notify("done")
            return

        path = self.files[0]
        try:
            tttr = tttrlib.TTTR(path)
            clsm = tttrlib.CLSMImage(tttr, channels=list(self.settings.detector_chs), fill=True)
            intensity = np.asarray(clsm.intensity).sum(axis=0)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            logger.debug("preview: could not read %s", path, exc_info=True)
            self.status_text = f"{pathlib.Path(path).name}: {exc}"
            self.notify("done")
            return

        result = region_preview(intensity, self.settings)
        self.results = [result]
        self.current_molecule = 0
        background = result.background_rate()
        self.status_text = (
            f"Preview: {result.n_molecules} region(s), background "
            f"{background:.2f} photons/pixel — press Run to fit."
        )
        self.notify("done")

    def run(self) -> None:
        """Analyse every selected file (BLOCKING — call from a worker thread).

        Segments and fits each file, writes a per-file ``molecule_data.tsv`` and a
        merged ``joint_output.tsv``, and keeps the results for display.
        """
        from ..core.region_mle import fit_regions_from_files

        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return

        irf = self.irf_files[0]
        self.results = []
        frames: list = []
        for i, path in enumerate(self.files):
            self.status_text = f"Analysing {pathlib.Path(path).name} ({i + 1}/{len(self.files)})…"
            self.notify("progress")
            try:
                result = fit_regions_from_files(
                    path, irf, dataclasses.replace(self.settings), keep_curves=True
                )
            except Exception as exc:  # noqa: BLE001 - surfaced in the status line
                logger.debug("molecule MLE failed for %s", path, exc_info=True)
                self.status_text = f"{pathlib.Path(path).name}: {exc}"
                continue
            self.results.append(result)
            frames.append(self._save_result(path, result))

        # Merged joint TSV next to the first file.
        frames = [f for f in frames if f is not None and row_count(f)]
        if frames:
            try:
                joint = pathlib.Path(self.files[0]).parent / "joint_output.tsv"
                write_csv_table(joint, concat_stores(frames))
            except Exception:
                logger.debug("joint TSV export failed", exc_info=True)

        self.status_text = ""
        self.notify("done")

    @staticmethod
    def _save_result(path: str, result: RegionMleResult):
        """Persist one file's result next to it (TSV + intensity); return the table.

        Writes ``<stem>_analysis/molecule_data.tsv`` and ``intensity.npy`` so the
        analysis can be reopened later with :meth:`load_analysis`.
        """
        df = result.dataframe
        if df is None or row_count(df) == 0:
            return df
        df = with_source_column(df, path)
        out_dir = pathlib.Path(path).parent / f"{pathlib.Path(path).stem}_analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        write_csv_table(out_dir / "molecule_data.tsv", df)
        try:
            np.save(out_dir / "intensity.npy", np.asarray(result.intensity_image))
        except Exception:
            logger.debug("intensity save failed", exc_info=True)
        return df

    # ── re-load a previous analysis from disk ──
    @property
    def results_tsv(self) -> str:
        """Path of the last-loaded molecule_data.tsv (bound to the file picker)."""
        return getattr(self, "_results_tsv", "")

    @results_tsv.setter
    def results_tsv(self, value) -> None:
        self._results_tsv = str(value or "")
        if self._results_tsv:
            self.load_analysis(self._results_tsv)

    def load_analysis(self, tsv_path: str) -> None:
        """Load a saved ``molecule_data.tsv`` (+ sibling ``intensity.npy``).

        Reconstructs a browsable :class:`RegionMleResult` from disk (the decay
        curves are not persisted, so the per-molecule decay plot is empty for a
        reopened analysis). A ``joint_output.tsv`` with several ``source_ptu``
        files is split back into one result per file.
        """
        p = pathlib.Path(tsv_path)
        if not p.exists():
            self.status_text = f"Not found: {p}"
            self.notify("done")
            return
        try:
            df = read_csv_table(p)
        except Exception as exc:  # noqa: BLE001 - surfaced in the status line
            self.status_text = f"Could not read {p.name}: {exc}"
            self.notify("done")
            return
        if df is None:
            self.status_text = f"Could not read {p.name}: not a delimited table"
            self.notify("done")
            return

        self.results = []
        names = column_names(df)
        if "source_ptu" in names:
            sources = np.asarray(df["source_ptu"]).astype(str)
            groups = [(s, take_where(df, sources == s))
                      for s in dict.fromkeys(sources.tolist())]
        else:
            groups = [(str(p), df)]
        for source, sub in groups:
            intensity = self._load_intensity(p, source)
            centroids = (
                np.column_stack([numeric_column(sub, "centroid_row"),
                                 numeric_column(sub, "centroid_col")])
                if {"centroid_row", "centroid_col"}.issubset(column_names(sub))
                else np.zeros((row_count(sub), 2))
            )
            self.results.append(RegionMleResult(
                dataframe=sub,
                intensity_image=intensity,
                label_image=np.zeros(intensity.shape, dtype=np.int32),
                centroids=centroids,
            ))
        self.current_molecule = 0
        n = sum(r.n_molecules for r in self.results)
        self.status_text = f"Loaded {n} region(s) from {p.name}"
        self.notify("loaded")

    @staticmethod
    def _load_intensity(tsv_path: pathlib.Path, source: str) -> np.ndarray:
        """Load the intensity image saved next to a molecule TSV (else a 1x1 blank)."""
        for candidate in (
            tsv_path.parent / "intensity.npy",
            pathlib.Path(str(source)).parent / f"{pathlib.Path(str(source)).stem}_analysis" / "intensity.npy",
        ):
            try:
                if candidate.exists():
                    return np.asarray(np.load(candidate))
            except Exception:
                logger.debug("intensity load failed for %s", candidate, exc_info=True)
        return np.zeros((1, 1), dtype=float)
