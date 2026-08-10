"""Qt-free view-model for the spot finder.

Holds the file list, the chosen workflow and its settings, runs the Qt-free
detector over the selected files, and exposes the label image, the region
markers and the run table for display. No Qt imports — the heavy
:meth:`SpotFinderViewModel.run` is driven from a background thread by the tool.

The workflow selector is the load-bearing control. Detection settings are a
recipe, not a pile of numbers: picking ``single_molecule`` sets all of them at
once to the pipeline the region MLE has always been fitted on, and the fields
below it are the deviations from that recipe rather than a blank slate a user
must fill in correctly.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
from collections.abc import Callable

import numpy as np

from chisurf.core.datastore import column_names, row_count, rows_from_table, write_csv_table
from chisurf.core.roi import RegionCollection
from chisurf.plugins.microscopy.mle_common.base import MleObserverMixin, scalar

from ..api.models import SpotFinderRequest
from ..core.spots import METHODS, SpotFinderResult, SpotFinderSettings

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "spot_finder.view.json"


class SpotFinderViewModel(MleObserverMixin):
    """State + logic for the spot finder (no Qt)."""

    def __init__(self) -> None:
        self.files: list[str] = []
        #: The analysis region, as the shared named list every ROI GUI edits.
        #: Empty (or all switched off) means the whole frame.
        self.regions = RegionCollection(combine="and", name="analysis region")
        self.settings = SpotFinderSettings()
        self.status_text: str = ""
        #: Detections of the last run, one per file that produced regions.
        self.results: list[SpotFinderResult] = []
        #: Flat index of the region shown in the browser.
        self.current_region: int = 0
        #: The last run's rows — one per input, whatever became of it.
        self.run_rows: list = []
        self.channels: list[int] = []
        self.frame: int = -1
        self.name: str = "spots"
        self.write_results: bool = True
        #: Where the user last clicked on the canvas, as ``(z, y, x)``.
        self.picked_point: tuple = (0, 0, 0)
        #: Spots picked by clicking, each refined by a Gaussian fit.
        self.picked: list = []
        #: Window the pick fit sees, in pixels.
        self.pick_window: int = 9
        self._observers: list[Callable[[str], None]] = []

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored view.json."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    # ── the workflow, which is what the settings below are deviations from ──
    @property
    def workflow(self) -> str:
        """Name of the detection workflow the settings came from."""
        return str(self.settings.workflow)

    @workflow.setter
    def workflow(self, value) -> None:
        """Adopt a workflow wholesale — every setting, not only the method.

        Picking a recipe and then keeping the previous recipe's threshold is how
        a "workflow" becomes decorative, so this replaces the settings object.
        """
        from ..core.workflow import request_from_workflow

        name = str(value or "").strip()
        if not name or name == self.settings.workflow:
            return
        try:
            request = request_from_workflow(name)
        except FileNotFoundError as exc:
            self.status_text = str(exc)
            self.notify("done")
            return
        roi = self.settings.roi
        self.settings = request.settings
        self.settings.roi = roi
        self.status_text = f"Workflow: {name}."
        self.notify("settings")

    def workflow_choices(self) -> list[str]:
        """Names of the shipped workflows, the standard one first."""
        from ..core.workflow import list_workflows

        return list_workflows()

    def method_choices(self) -> list[str]:
        """Detector names."""
        return list(METHODS)

    method = scalar("method", str, "Detector: watershed, threshold, log or dog.")
    sigma = scalar("sigma", float, "Gaussian smoothing applied before thresholding.")
    threshold = scalar("threshold", float, "Intensity level (<0 = Otsu); for log/dog, the minimum response.")
    peak_footprint_size = scalar("peak_footprint_size", int, "Watershed seed footprint side.")
    min_area = scalar("min_area", int, "Smallest region to keep (pixels).")
    max_area = scalar("max_area", int, "Largest region to keep; 0 disables.")
    clear_border = scalar("clear_border", bool, "Drop regions touching the frame edge.")
    min_sigma = scalar("min_sigma", float, "Smallest spot width (log/dog).")
    max_sigma = scalar("max_sigma", float, "Largest spot width (log/dog).")
    num_sigma = scalar("num_sigma", int, "Number of scales between them (log).")
    overlap = scalar("overlap", float, "Blobs overlapping by more than this merge.")

    # ── the drawn analysis region ──
    def apply_regions(self) -> None:
        """Push the drawn region list into the settings."""
        self.settings.roi = self.regions.combined()
        self.notify("regions")

    def region_regions(self) -> RegionCollection:
        """Return the found regions as a collection, for the read-only overlay.

        Each becomes the ellipse with the same second moments as the object —
        centroid, axis lengths, orientation, all numbers already in the table.
        That is what makes the outline worth drawing: it shows what was
        *measured*, so a detection can be checked against the image it came
        from rather than trusted.
        """
        from chisurf.core.roi import regionprops

        collection = RegionCollection(combine="or", name="regions")
        for ri, result in enumerate(self.results):
            tag = f"F{ri + 1}·" if len(self.results) > 1 else ""
            for props in regionprops(result.labels, result.intensity):
                collection.add(props.as_ellipse(f"{tag}Region {props.label}"))
        return collection

    # ── picking: click a spot, and let a Gaussian say where it is ──
    def pick_spot(self) -> None:
        """Fit a Gaussian to the spot under the last click and keep it.

        Bound to the canvas's ``on_pick``. The click seeds the fit and the fit
        decides the answer, so a click two pixels off centre still produces a
        region centred on the spot rather than on the cursor. A fit that does
        not converge is **refused with a reason** rather than dropping an
        ellipse where nothing was found.
        """
        from ..core.picking import fit_gaussian_spot

        image = self.detection_image()
        if image is None:
            self.status_text = "Nothing to pick in yet — detect or preview first."
            self.notify("done")
            return

        _z, y, x = self.picked_point
        spot = fit_gaussian_spot(np.asarray(image), y, x, window=self.pick_window)
        if not spot.success:
            self.status_text = f"No spot picked: {spot.reason}."
            self.notify("done")
            return

        self.picked.append(spot)
        self.status_text = (
            f"Picked spot at ({spot.y:.1f}, {spot.x:.1f}), σ = {spot.sigma:.2f} px "
            f"({len(self.picked)} picked)."
        )
        self.notify("results")

    def pick_help(self) -> str:
        """One line telling the user the gesture, on the panel that offers it."""
        if self.picked:
            return (
                f"<i><b>{len(self.picked)}</b> spot(s) picked. "
                "<b>Add picks</b> makes them regions of this detection.</i>"
            )
        return (
            "<i>Click the image on the <b>Regions</b> tab to pick a spot the "
            "detector missed; a Gaussian fit refines the click.</i>"
        )

    def clear_picked(self) -> None:
        """Forget every picked spot."""
        self.picked = []
        self.status_text = "Picked spots cleared."
        self.notify("results")

    def picked_regions(self) -> RegionCollection:
        """Return the picked spots as regions, for the overlay."""
        collection = RegionCollection(combine="or", name="picked")
        for index, spot in enumerate(self.picked, start=1):
            collection.add(spot.to_roi(f"Picked {index}"))
        return collection

    def picked_markers(self) -> list:
        """Return the fitted centres of the picked spots as ``(z, y, x)`` markers."""
        return [(0, float(s.y), float(s.x)) for s in self.picked]

    def add_picked_to_detection(self) -> None:
        """Add the picked spots to the current detection, as regions of its own.

        A picked spot is a region like any other once it exists — it is written
        through the same contract, fitted by the same tool — so this rasterises
        the fitted ellipses into the label image and re-measures. Picks land
        *after* the detected regions, so their labels are the high ones and a
        table read before and after is still aligned on the rest.
        """
        result = self._current_result()
        if result is None or not self.picked:
            self.status_text = "Nothing to add."
            self.notify("done")
            return

        from chisurf.core.fio.fluorescence.region_container import region_table
        from chisurf.core.roi.segmentation import relabel_sequential

        labels = np.array(result.labels, copy=True)
        next_label = int(labels.max()) + 1
        for spot in self.picked:
            mask = spot.to_roi().to_mask(labels.shape)
            # Only where nothing was found already: a pick is a spot the
            # detector missed, not a claim on pixels it already owns.
            mask &= labels == 0
            if not mask.any():
                continue
            labels[mask] = next_label
            next_label += 1

        labels, _f, _i = relabel_sequential(labels)
        result.labels = labels.astype(np.int32)
        result.table = region_table(result.labels, result.intensity)
        self.picked = []
        self.status_text = f"{result.n_regions} region(s) after adding the picks."
        self.notify("results")

    # ── what the browser shows ──
    def region_entries(self) -> list[dict]:
        """Browsable region entries (id = flat index; badge = area)."""
        entries: list[dict] = []
        idx = 0
        for ri, result in enumerate(self.results):
            file_tag = f"F{ri + 1}·" if len(self.results) > 1 else ""
            for rec in rows_from_table(result.table):
                entries.append({
                    "id": idx,
                    "label": f"{file_tag}Region {int(rec.get('label', idx))}",
                    "badge": f"{int(rec.get('region.area', 0))} px",
                })
                idx += 1
        return entries

    def detection_image(self):
        """Intensity image of the current region's file (for the canvas)."""
        result = self._current_result()
        return None if result is None else np.asarray(result.intensity)

    def current_region_marker(self) -> list:
        """Return the selected region's weighted centroid as one ``(z, y, x)`` marker."""
        cur = self._current_region()
        if cur is None:
            return []
        rec = cur[1]
        return [(0,
                 float(rec.get("region.centroid_weighted_y",
                               rec.get("region.centroid_y", 0.0))),
                 float(rec.get("region.centroid_weighted_x",
                               rec.get("region.centroid_x", 0.0))))]

    def current_region_info(self) -> str:
        """HTML summary for the selected region (metadata panel)."""
        cur = self._current_region()
        if cur is None:
            return "<i>No region selected.</i>"
        rec = cur[1]

        def g(key, fmt="{:.3f}"):
            try:
                return fmt.format(float(rec.get(key, float("nan"))))
            except (TypeError, ValueError):
                return "—"

        out = (
            f"<b>Region {int(rec.get('label', 0))}</b><br>"
            f"area = {g('region.area', '{:.0f}')} px &nbsp; "
            f"perimeter = {g('region.perimeter')}<br>"
            f"circularity = {g('region.circularity')} &nbsp; "
            f"eccentricity = {g('region.eccentricity')}<br>"
        )
        if "region.intensity_mean" in rec:
            out += (f"mean = {g('region.intensity_mean')} &nbsp; "
                    f"max = {g('region.intensity_max')}<br>")
        if "spot.sigma" in rec:
            out += f"σ = {g('spot.sigma')} px<br>"
        return out

    def summary(self) -> str:
        """Status / summary text shown above the results."""
        if self.status_text:
            return f"<i>{self.status_text}</i>"
        if not self.results:
            return (
                "<i>Add imaging file(s), pick a <b>workflow</b> — "
                "<b>single_molecule</b> is the standard one — and press "
                "<b>Detect</b>. What is found is written into each "
                "measurement's own container, and the <b>Region MLE</b> panel "
                "below fits it.</i>"
            )
        total = sum(r.n_regions for r in self.results)
        return (
            f"<b>{total}</b> region(s) in <b>{len(self.results)}</b> file(s); "
            f"workflow <b>{self.settings.workflow}</b>."
        )

    def run_entries(self) -> list[dict]:
        """One row per input, whatever became of it.

        The table the batch rule exists for: a file that raised and a file with
        nothing in it are rows with a status, not files that quietly left the
        list. ``len(run_entries()) == len(files)`` after a run.
        """
        return [
            {
                "input": pathlib.Path(row.input).name,
                "status": row.status,
                "n_regions": row.n_regions,
                "reason": row.reason,
                "container": pathlib.Path(row.container).name if row.container else "",
            }
            for row in self.run_rows
        ]

    # ── actions ──
    def can_run(self) -> tuple[bool, str]:
        """Return ``(ok, reason)`` describing whether a run is possible."""
        if not self.files:
            return False, "No imaging files selected."
        return True, ""

    def preview(self) -> None:
        """Detect in the first file only, writing nothing. BLOCKING."""
        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return
        self._detect(self.files[:1], write=False, label="Preview")

    def run(self) -> None:
        """Detect in every selected file and write each result. BLOCKING."""
        ok, reason = self.can_run()
        if not ok:
            self.status_text = reason
            self.notify("done")
            return
        self._detect(self.files, write=self.write_results, label="Detected")

    def _detect(self, files, *, write: bool, label: str) -> None:
        from ..api.spot_finder import detect_request

        self.settings.roi = self.regions.combined()
        request = SpotFinderRequest(
            files=list(files),
            name=self.name,
            channels=self.channels or None,
            frame=self.frame,
            settings=dataclasses.replace(self.settings),
            write=write,
        )
        result = detect_request(request, progress=self._progress)
        self.run_rows = list(result.rows)

        # The results the browser shows are re-derived per file rather than
        # returned by the batch runner, which deliberately keeps only the row.
        self.results = []
        from ..core.spots import detect, load_intensity

        for row in result.rows:
            if row.status != "ok":
                continue
            try:
                image = load_intensity(row.input, channels=self.channels or None,
                                       frame=self.frame)
                self.results.append(detect(image, dataclasses.replace(self.settings)))
            except Exception:  # noqa: BLE001 - the row already says what happened
                logger.debug("could not re-derive %s for display", row.input, exc_info=True)

        self.current_region = 0
        failed = [r for r in result.rows if r.status not in ("ok",)]
        self.status_text = (
            f"{label}: {result.n_regions} region(s) in {len(result.ok)}/"
            f"{len(result.rows)} file(s)"
            + (f"; {len(failed)} with nothing to show" if failed else "")
        )
        self.notify("results")

    def _progress(self, index: int, total: int, name: str) -> None:
        self.status_text = f"Detecting {name} ({index + 1}/{total})…"
        self.notify("progress")

    # ── button actions: ask the host, so the UI never blocks on a click ──
    def request_run(self) -> None:
        """Button action: start the detection on a worker thread."""
        self.notify("start_run")

    def request_preview(self) -> None:
        """Button action: preview the first file on a worker thread."""
        self.notify("start_preview")

    def request_export(self) -> None:
        """Button action: ask the host for a path and export the region table."""
        self.notify("start_export")

    def request_add_picks(self) -> None:
        """Button action: turn the picked spots into regions of this detection."""
        self.notify("start_add_picks")

    def request_clear_picks(self) -> None:
        """Button action: forget every picked spot."""
        self.notify("start_clear_picks")

    def export_results(self, path: str) -> None:
        """Write the combined region table of every file to *path*."""
        from chisurf.core.datastore import concat_stores

        tables = [r.table for r in self.results if row_count(r.table)]
        if not tables:
            self.status_text = "No regions to export."
            self.notify("done")
            return
        combined = concat_stores(tables)
        write_csv_table(path, combined)
        self.status_text = (
            f"Exported {row_count(combined)} region(s) to {pathlib.Path(path).name}"
        )
        self.notify("done")

    def has_results(self) -> bool:
        """Return True when a run produced regions."""
        return any(r.n_regions for r in self.results)

    # ── shared-setup hooks (Imaging Tools aggregator) ──
    def apply_setup_settings(self, payload: dict) -> None:
        """Adopt the detector channels the shared Setup panel published."""
        from chisurf.core.fluorescence.mle import parse_detector_setup

        if not payload:
            return
        setup = parse_detector_setup(payload)
        channels = list(getattr(setup, "channels", []) or [])
        if channels:
            self.channels = [int(c) for c in channels]
        self.notify("settings")

    def apply_pipeline_context(self, payload: dict) -> None:
        """Adopt the pipeline's source file(s)."""
        files = payload.get("files") or ([payload["file"]] if payload.get("file") else [])
        if files:
            self.files = [str(f) for f in files]
        self.notify("settings")

    def apply_calibration(self, calibration: dict) -> None:
        """Ignore a calibration payload — detection uses none (API uniformity)."""

    # ── internals ──
    def _current_result(self):
        cur = self._current_region()
        return cur[0] if cur else (self.results[0] if self.results else None)

    def _current_region(self):
        idx = 0
        for result in self.results:
            for rec in rows_from_table(result.table):
                if idx == self.current_region:
                    return result, rec
                idx += 1
        return None

    def selection_columns(self) -> list[str]:
        """Column names of the current detection, for the table view."""
        result = self._current_result()
        return [] if result is None else list(column_names(result.table))
