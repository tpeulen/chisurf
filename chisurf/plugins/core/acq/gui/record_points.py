"""The Record tool's scanner, picking and point measurements: the model half of the *Points* panel.

:class:`ScanPointsMixin` is mixed into :class:`~chisurf.plugins.core.acq.gui.record_app.RecordModel`.

* **Scanner** -- the sample scanner a settings file's ``scanner`` section names (the MT200's PI
  E-725 through libphacq's ``pi`` driver; ``"sim:"`` its simulator), connected when the settings
  are loaded, its own settings (learning, turnaround, the stage position) in a form generated from
  the driver's schema. The raster comes from the Scan panel. With a TCSPC device and a scanner the
  Image mode records a real scan (``live.scanning.ScannedSource``).
* **Picking** -- a click on the image adds a point (stage µm); *Auto-pick* runs the spot finder's
  ``single_molecule`` workflow on the intensity image and adds its molecules, brightest first.
* **Point measurements** -- *Measure points* parks the focus on each point in turn and records it
  (``live.points.PointSequence``): one recording per point, for a set time or until the molecule
  has bleached. Each finished point is put into Datasets and analysed
  (``live.molecules.analyse_point``: the intensity-trace tool's binning and the shared HMM); the
  results fill the point's row, and the table of every molecule is written into the image's
  container when the sequence ends.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from emtk.i18n import tr

_log = logging.getLogger(__name__)

#: The spot finder workflow auto-pick runs.
AUTOPICK_WORKFLOW = "single_molecule"


class ScanPointsMixin:
    """Scanner connection, picked points and point measurements for the Record model."""

    def _init_scan_points(self) -> None:
        # -- the scanner ---------------------------------------------------------------------
        self.scanner = None
        #: the settings file's ``scanner`` section (what Connect opens)
        self.scanner_section: dict | None = None
        #: Advanced: the address Connect opens without a settings file
        self.scanner_address = ""
        self.scanner_text = tr("No scanner")
        self.scanner_form = None
        self._scanner_sent: dict = {}
        # -- the picked points -----------------------------------------------------------------
        #: ``{"index", "x_um", "y_um", "origin", "brightness", "status"}`` plus a molecule's results
        self.points: list[dict] = []
        self._next_point = 0
        self.pick_on_click = True
        self.autopick_max = 20
        self.autopick_min = 0.0
        self.autopick_max_brightness = 0.0
        self.selected_point: int | None = None
        # -- point measurements ----------------------------------------------------------------
        self.point_time_s = 5.0
        self.until_bleached = True
        self.bleach_background_kcps = 0.0
        self.sequence = None
        self.points_fraction: float | None = 0.0
        self.points_text = tr("Click the image to pick a point, or Auto-pick.")
        #: analysed molecules by point index (``live.molecules.MoleculeResult``)
        self.molecules: dict[int, Any] = {}
        self._analysis_threads: list[threading.Thread] = []
        self._handled_points = 0
        self._sequence_finished = True
        self.molecules_saved = ""
        #: the spot finder run the last Auto-pick used (``workflow``, ``settings_hash``)
        self._last_pick: dict = {}
        #: what a point picked now belongs to in a survey (``survey_id``, ``tile``, its origin)
        self._point_context: dict = {}
        #: extra header tags of the next recording (a survey tile's)
        self._run_tags: dict = {}
        # -- the image the points are picked on ---------------------------------------------------
        #: the last scan's snapshot (its maps stay while points are measured)
        self.image_snapshot: dict | None = None
        #: the scan it was recorded with (pixel -> stage)
        self.image_scan = None
        #: the image recording (its dataset holds the per-molecule table)
        self.image_ptu: Path | None = None
        self.image_uid = ""

    # -- the scanner ---------------------------------------------------------------------------
    @property
    def scanner_connected(self) -> bool:
        return self.scanner is not None

    def connect_scanner(self, section: dict | None = None) -> bool:
        """Open the scanner *section* names (default: the loaded settings' section, else the
        Advanced address). Nothing moves until a scan or a point measurement."""
        from chisurf.plugins.core.acq.live.scanning import open_scanner

        if self.scanner is not None:
            return False
        section = dict(section or self.scanner_section
                       or {"driver": "pi", "address": str(self.scanner_address)})
        try:
            self.scanner = open_scanner(section)
        except Exception as exc:  # noqa: BLE001 - shown; imaging needs the scanner
            self.scanner, self.scanner_text = None, tr("Scanner not connected: {e}").format(e=exc)
            return False
        self.scanner_section = section
        self.scanner_address = str(section.get("address", ""))
        info = self.scanner.device.information()
        where = tr("simulator") if self.scanner_address.startswith("sim:") else \
            (self.scanner_address or tr("first on USB"))
        self.scanner_text = tr("Scanner: {model} ({where})").format(
            model=f"{info.vendor} {info.model}".strip(), where=where)
        self._scanner_form_from_device()
        return True

    def disconnect_scanner(self) -> bool:
        if self.scanner is None or self.running:
            return False
        try:
            self.scanner.close()
        finally:
            self.scanner = None
            self.scanner_form = None
            self.scanner_text = tr("No scanner")
        return True

    def _scanner_form_from_device(self) -> None:
        from chisurf.plugins.core.acq.live import devices
        from chisurf.plugins.core.acq.live.scanning import SCAN_PANEL_KEYS

        dev = self.scanner.device
        self._scanner_sent = dict(dev.settings())
        self.scanner_form = devices.settings_form(
            dev, self._scanner_sent, on_change=self.scanner_settings_edited, folded=False,
            advanced=self.advanced, exclude=SCAN_PANEL_KEYS)

    def scanner_settings_edited(self) -> None:
        """An edit in the scanner's form (learning, turnaround, the stage position): sent now."""
        if self.scanner is None or self.scanner_form is None:
            return
        from chisurf.plugins.core.acq.live import devices

        values = self.scanner_form.params()
        changed = {k: v for k, v in values.items() if self._scanner_sent.get(k) != v}
        if not changed or self.running:
            return
        notes = devices.apply_settings(self.scanner.device, changed)
        if notes:
            self.scanner_text = tr("Scanner: {e}").format(e="; ".join(notes))
        self._scanner_form_from_device()

    @property
    def scanner_hidden(self) -> bool:
        """The scanner line is for a recording of a real scan (a device source)."""
        return self.source_kind != "device"

    # -- the image the points are picked on ----------------------------------------------------
    def image_pixel_to_um(self, px: float, py: float) -> tuple[float, float]:
        """Plot coordinates of the image (pixels, y down) to stage coordinates (µm)."""
        scan = self.image_scan or self.scan_settings()
        sx, sy = scan.pixel_um
        return float(scan.x0_um + px * sx), float(scan.y0_um + py * sy)

    def image_um_to_pixel(self, x_um: float, y_um: float) -> tuple[float, float]:
        scan = self.image_scan or self.scan_settings()
        sx, sy = scan.pixel_um
        return float((x_um - scan.x0_um) / sx), float((y_um - scan.y0_um) / sy)

    # -- picking ---------------------------------------------------------------------------------
    def add_point(self, x_um: float, y_um: float, origin: str = "click",
                  brightness: float | None = None) -> dict:
        """A point at stage *(x_um, y_um)*, with what traces it back: the image it was picked on
        (file, dataset uid, raster, pixel), how it was picked, the survey and tile."""
        scan = self.image_scan or self.scan_settings()
        px, py = self.image_um_to_pixel(x_um, y_um)
        row = {"index": self._next_point, "x_um": float(x_um), "y_um": float(y_um),
               "origin": origin, "brightness": brightness, "status": "",
               "pixel_x": px, "pixel_y": py, "image_x0_um": float(scan.x0_um),
               "image_y0_um": float(scan.y0_um), "image_pixel_um": float(scan.pixel_um[0]),
               "image": Path(str(self.image_ptu)).name if self.image_ptu else "",
               "image_uid": str(self.image_uid or "")}
        if origin == "auto":
            row.update(self._last_pick)
        row.update(self._point_context)
        self._next_point += 1
        self.points.append(row)
        self._points_summary()
        return row

    def pick_at_pixel(self, px: float, py: float) -> dict | None:
        """A click on the image at pixel *(px, py)* (plot coordinates)."""
        if not self.pick_on_click or self.running:
            return None
        image = ((self.image_snapshot or {}).get("images") or {}).get("Intensity")
        if image is not None:
            ny, nx = np.asarray(image).shape
            if not (0 <= px < nx and 0 <= py < ny):
                return None
            value = float(np.asarray(image)[int(py), int(px)])
        else:
            value = None
        x, y = self.image_pixel_to_um(px, py)
        row = self.add_point(x, y, "click", value)
        self.selected_point = row["index"]
        return row

    def remove_point(self, record: dict) -> None:
        if self.busy:
            return
        index = int(record.get("index", -1))
        self.points = [p for p in self.points if p["index"] != index]
        self.molecules.pop(index, None)
        if self.selected_point == index:
            self.selected_point = None
        self._points_summary()

    def clear_points(self) -> None:
        if self.busy:
            return
        self.points, self.molecules, self.selected_point = [], {}, None
        self._next_point = 0
        self._points_summary()

    def point_edited(self, record: dict, key: str, value: Any) -> None:
        for p in self.points:
            if p["index"] == record.get("index") and key in ("x_um", "y_um"):
                p[key] = float(value)

    def point_selected(self, record: dict | None) -> None:
        self.selected_point = None if record is None else int(record.get("index", -1))

    def _points_summary(self) -> None:
        if self.running:
            return
        n = len(self.points)
        done = sum(1 for p in self.points if p["index"] in self.molecules)
        self.points_text = (
            tr("Click the image to pick a point, or Auto-pick.") if n == 0 else
            tr("{n} point(s), {d} measured.").format(n=n, d=done))

    def point_rows(self) -> list[dict]:
        """The points table: one row per point, a measured molecule's results in it."""
        from chisurf.plugins.core.acq.live.molecules import summary

        rows = []
        for p in self.points:
            m = self.molecules.get(p["index"])
            row = {
                "index": p["index"] + 1,
                "x_um": p["x_um"],
                "y_um": p["y_um"],
                "status": p.get("status", ""),
                "kphotons": m.photons / 1e3 if m is not None else None,
                "bleach_s": m.bleach_s if m is not None else None,
                "steps": int(m.steps) if m is not None else None,
                "efficiency": m.efficiency if m is not None else None,
                "stoichiometry": m.stoichiometry if m is not None else None,
                "lifetime_ns": m.lifetime_ns if m is not None else None,
                "remove": "" if self.running else "✕",
                "_index": p["index"],
            }
            detail = [f"{p['origin']} pick"]
            if p.get("brightness") is not None:
                detail.append(tr("{v:.0f} photons in the image").format(v=p["brightness"]))
            if m is not None:
                s = summary(m)
                detail += [s["states"], s["on"]]
                if m.message:
                    detail.append(m.message)
            row["detail"] = "; ".join(detail)
            rows.append(row)
        return rows

    def remove_point_row(self, record: dict) -> None:
        """The ✕ button of a row."""
        self.remove_point({"index": record.get("_index", -1)})

    @property
    def selected_point_row(self) -> dict | None:
        """The table's selected row (``_index`` is the point's index): the image rings the point
        and the Trace dock shows its molecule."""
        if self.selected_point is None:
            return None
        if getattr(self, "_selected_row", {}).get("_index") != self.selected_point:
            self._selected_row = {"_index": self.selected_point}
        return self._selected_row

    @selected_point_row.setter
    def selected_point_row(self, record: dict | None) -> None:
        self.selected_point = None if not record else int(record.get("_index", -1))

    def delete_point_row(self, record: dict) -> None:
        self.remove_point_row(record)

    # -- auto-pick: the spot finder's single-molecule workflow ---------------------------------------
    def find_molecules(self) -> tuple[list[tuple[float, float, float]], int]:
        """The molecules the spot finder's ``single_molecule`` workflow finds in the intensity
        image: ``(x_um, y_um, photons)`` within the brightness limits, brightest first, and how
        many spots it found in all."""
        from chisurf.core.datastore import column_names, numeric_column
        from chisurf.plugins.microscopy.spot_finder.core.spots import (
            SpotFinderSettings,
            detect,
        )
        from chisurf.plugins.microscopy.spot_finder.core.workflow import builtin_workflow

        image = ((self.image_snapshot or {}).get("images") or {}).get("Intensity")
        if image is None or not np.asarray(image).any():
            return [], 0
        flow = builtin_workflow(AUTOPICK_WORKFLOW)
        known = SpotFinderSettings.__dataclass_fields__
        settings = SpotFinderSettings(**{k: v for k, v in flow["settings"].items() if k in known},
                                      workflow=AUTOPICK_WORKFLOW)
        from chisurf.plugins.core.acq.live.provenance import settings_hash

        self._last_pick = {"workflow": AUTOPICK_WORKFLOW,
                           "settings_hash": settings_hash(flow["settings"])}
        result = detect(np.asarray(image, float), settings)
        if not result.n_regions:
            return [], 0
        table = result.table
        names = column_names(table)
        ys = numeric_column(table, "region.centroid_weighted_y" if
                            "region.centroid_weighted_y" in names else "region.centroid_y")
        xs = numeric_column(table, "region.centroid_weighted_x" if
                            "region.centroid_weighted_x" in names else "region.centroid_x")
        bright = numeric_column(table, "region.intensity_sum")
        keep = bright >= float(self.autopick_min)
        if float(self.autopick_max_brightness) > 0:
            keep &= bright <= float(self.autopick_max_brightness)
        out = []
        for i in np.argsort(-bright):
            if keep[i]:
                # a label's centroid is a pixel index; the pixel's centre is half a pixel further
                x, y = self.image_pixel_to_um(float(xs[i]) + 0.5, float(ys[i]) + 0.5)
                out.append((x, y, float(bright[i])))
        return out, int(result.n_regions)

    def autopick(self) -> int:
        """Find molecules in the intensity image with the spot finder's ``single_molecule``
        workflow and add them as points, brightest first (within the brightness limits, at most
        *Max molecules*). Returns how many were added."""
        if ((self.image_snapshot or {}).get("images") or {}).get("Intensity") is None:
            self.points_text = tr("Record or replay an image first: Auto-pick looks at it.")
            return 0
        found, n = self.find_molecules()
        if not found:
            self.points_text = tr("Auto-pick found no molecule in the image.")
            return 0
        taken = [(p["x_um"], p["y_um"]) for p in self.points]
        scan = self.image_scan or self.scan_settings()
        near = 0.5 * max(scan.pixel_um)
        added = 0
        for x, y, bright in found:
            if int(self.autopick_max) > 0 and added >= int(self.autopick_max):
                break
            if any((x - a) ** 2 + (y - b) ** 2 < near**2 for a, b in taken):
                continue
            self.add_point(x, y, "auto", bright)
            taken.append((x, y))
            added += 1
        self.points_text = tr(
            "Auto-pick ({flow}): {n} molecule(s) added of {found} found.").format(
            flow=AUTOPICK_WORKFLOW.replace("_", " "), n=added, found=n)
        return added

    # -- point measurements ------------------------------------------------------------------------
    @property
    def points_running(self) -> bool:
        return self.sequence is not None and self.sequence.running

    def _point_scanner(self):
        """What parks the focus: the connected scanner, else (simulator) a simulated one."""
        if self.scanner is not None:
            return self.scanner
        if self.source_kind == "simulator":
            from chisurf.plugins.core.acq.live.scanner import SimScanner

            return SimScanner()
        return None

    def _point_source(self, scanner):
        if self.source_kind == "device":
            from chisurf.plugins.core.acq.live import devices

            if self.device is None:
                raise RuntimeError(tr("Connect the device first."))
            return devices.DeviceSource(self.device)
        if self.source_kind == "simulator":
            from chisurf.plugins.core.acq.live.scanner import PointSimSource

            return PointSimSource(scanner, self.image_scan or self.scan_settings(),
                                  self.imaging_sample(), self.realism(),
                                  bleach_s=float(self.img_bleach_s), speed=float(self.speed),
                                  realtime=self.realtime)
        raise RuntimeError(tr("Point measurements need the simulator or a TCSPC device."))

    def measure_points(self) -> bool:
        """Measure the picked points in turn (see the module notes)."""
        from chisurf.plugins.core.acq.live.points import BleachDetector, PointSequence
        from chisurf.plugins.core.acq.live.project import recording_dir
        from chisurf.plugins.core.acq.live.scanner import ScanSettings

        if self.busy or not self.points:
            return False
        try:
            scanner = self._point_scanner()
            if scanner is None or not hasattr(scanner, "move_to"):
                raise RuntimeError(tr("Connect the scanner first: it parks the focus on each "
                                      "point."))
            source = self._point_source(scanner)
            experiment = self.make_experiment(source.info.n_micro)
        except Exception as exc:  # noqa: BLE001 - shown; nothing moved
            self.status_text = tr("Cannot measure points")
            self.status_detail = self.points_text = str(exc)
            return False
        name = self.run_name.strip().replace("{date}", time.strftime("%Y%m%d_%H%M%S"))
        name = self.unique_name(name or time.strftime("points_%Y%m%d_%H%M%S"))
        scan = ScanSettings(points=[(p["x_um"], p["y_um"]) for p in self.points],
                            point_ms=float(self.point_time_s) * 1e3)
        background = float(self.bleach_background_kcps)
        if not background and self.source_kind == "simulator":
            real = self.realism()
            background = float(real.background_donor_khz + real.background_acceptor_khz)
        for p in self.points:
            p["status"] = tr("waiting")
            self.molecules.pop(p["index"], None)
        from chisurf.plugins.core.acq.live.provenance import point_tags

        self.sequence = PointSequence(
            scanner, source, scan, out_dir=recording_dir(self.output_dir), name=name,
            point_tags=[point_tags(p) for p in self.points],
            until_bleached=bool(self.until_bleached),
            bleach=lambda: BleachDetector(background_kcps=background),
            session_kwargs={"experiment": experiment, "settings": self._run_settings(),
                            "embed": self.recording_store == "embed",
                            "header_tags": self.run_header_tags()})
        self._handled_points = 0
        self._sequence_finished = False
        self._run_shutters(True)
        self.sequence.start()
        self.snapshot = None
        self.points_fraction = 0.0
        self.status_text = tr("Measuring points…")
        self.status_detail = str(recording_dir(self.output_dir) / f"{name}_p000.ptu")
        return True

    def poll_points(self) -> None:
        """Follow a point sequence: the current point's live snapshot, finished points into
        Datasets and their analysis, the end of the sequence (main thread)."""
        seq = self.sequence
        if seq is None:
            return
        current = seq.current
        if current is not None:
            self.snapshot = current.snapshot()
            index = self.points[current.index]["index"] if current.index < len(self.points) else -1
            for p in self.points:
                if p["index"] == index:
                    p["status"] = tr("running")
        results = list(seq.results)
        for result in results[self._handled_points:]:
            self._point_done(result)
        self._handled_points = len(results)
        n = max(1, len(seq.scan.points))
        elapsed = (time.monotonic() - current.started_at) if current is not None and \
            current.started_at else 0.0
        part = min(1.0, elapsed / max(1e-3, seq.scan.point_ms * 1e-3)) if current else 0.0
        self.points_fraction = min(1.0, (len(results) + part) / n)
        if seq.running:
            self.points_text = tr("Point {k} of {n}…").format(k=min(len(results) + 1, n), n=n)
            return
        if not self._sequence_finished and all(not t.is_alive()
                                               for t in self._analysis_threads):
            self._sequence_finished = True
            self._run_shutters(False)
            self._record_points()
            if not self.survey_active:  # a survey stores one table for all its tiles
                self._store_molecules()
            stopped = len(results) < n
            for p in self.points:
                if p["status"] in (tr("waiting"), tr("running")):
                    p["status"] = tr("not measured")
            self.status_text = (tr("Stopped: {k} of {n} points") if stopped
                                else tr("Points done: {k} of {n}")).format(k=len(results), n=n)
            self.status_detail = seq.error or self.molecules_saved
            self.points_text = self.status_text
            self.points_fraction = 1.0

    def _point_done(self, result) -> None:
        """One point finished: into Datasets, then analysed in a thread of its own."""
        row = next((p for i, p in enumerate(self.points) if i == result.index), None)
        if row is None:
            return
        reason = result.run.stop_reason if result.run is not None else "error"
        row["status"] = {"bleached": tr("bleached"), "duration reached": tr("done"),
                         "stopped": tr("stopped")}.get(reason, reason)
        session = result.session
        if session is not None:
            try:
                session.register()
            except Exception:  # noqa: BLE001 - the file is on disk either way
                _log.exception("registering point %s", result.index)
        ptu = result.run.ptu if result.run is not None else None
        row["ptu"] = str(ptu) if ptu else ""
        row["dataset_uid"] = str(getattr(result.run, "dataset_uid", "") or "")
        row["reached_x_um"], row["reached_y_um"] = (float(v) for v in result.position)
        if ptu is None or not Path(ptu).exists():
            return
        from chisurf.plugins.core.acq.live.molecules import analyse_point

        index = row["index"]

        def work():
            try:
                self.molecules[index] = analyse_point(ptu, index, result.target)
            except Exception as exc:  # noqa: BLE001 - shown in the row
                _log.exception("analysing point %s", index)
                row["status"] = tr("analysis failed: {e}").format(e=exc)

        thread = threading.Thread(target=work, name=f"molecule-{index}", daemon=True)
        self._analysis_threads.append(thread)
        thread.start()

    def _record_points(self) -> None:
        """Into the project: each measured point's record (and its molecule) in its own
        container, the image's list of its points (``live.provenance``)."""
        from chisurf.plugins.core.acq.live import provenance

        measured = [p for p in self.points if p.get("dataset_uid")]
        try:
            for p in measured:
                provenance.write_point_record(p, self.molecules.get(p["index"]))
            if measured:
                provenance.write_image_points(self.image_ptu, self.image_uid, measured)
        except Exception:  # noqa: BLE001 - the recordings and their headers carry it anyway
            _log.exception("recording the points' provenance")

    def wait_points(self, timeout: float = 120.0) -> None:
        """Wait for a point sequence and its analyses (scripts and tests); poll once at the end."""
        end = time.monotonic() + timeout
        while self.sequence is not None and (self.sequence.running or not self._sequence_finished):
            self.poll_points()
            if time.monotonic() > end:
                break
            time.sleep(0.02)

    def molecule_table(self, points: list[dict]) -> tuple[dict, dict]:
        """The per-molecule table of *points* (measured ones), each row naming its point
        recording and its image (``point_dataset`` / ``image_dataset`` index the lookup lists
        returned as the second item, which go into the record's settings)."""
        from chisurf.plugins.core.acq.live.molecules import molecule_rows
        from chisurf.plugins.core.acq.live.provenance import lookup

        table = molecule_rows([self.molecules[p["index"]] for p in points])
        refs = [{"point_uid": p.get("dataset_uid"), "point_name": Path(str(p.get("ptu", ""))).name,
                 "image_uid": p.get("image_uid"), "image_name": p.get("image")} for p in points]
        point_sets, table["point_dataset"] = lookup(refs, "point")
        image_sets, table["image_dataset"] = lookup(refs, "image")
        return table, {"point_datasets": point_sets, "image_datasets": image_sets}

    def _store_molecules(self) -> None:
        """The per-molecule table into the image's container (beside its other imaging results),
        when the image is a dataset of the project."""
        from chisurf.plugins.core.acq.live.provenance import MOLECULE_UNITS, _put

        points = [p for p in self.points if p["index"] in self.molecules]
        self.molecules_saved = ""
        if not points:
            return
        source, uid = self.image_ptu, self.image_uid
        if source is None or not uid:
            self.molecules_saved = tr("Molecules not stored: the image is not a dataset of the "
                                      "project.")
            return
        try:
            table, lookups = self.molecule_table(points)
            container = _put(
                str(source), uid, "molecules.table", table, artifact_kind="analysis_result",
                operation_type="trace_segmentation", row_grain="molecule",
                parameters={"analysis": "point_traces", "autopick": AUTOPICK_WORKFLOW,
                            "point_time_s": float(self.point_time_s),
                            "until_bleached": bool(self.until_bleached), **lookups},
                units=MOLECULE_UNITS)
            self.molecules_saved = tr("{n} molecule(s) stored with the image: {where}").format(
                n=len(points), where=Path(container).name)
        except Exception as exc:  # noqa: BLE001 - shown; the recordings are kept
            _log.exception("storing the molecules")
            self.molecules_saved = tr("Molecules not stored: {e}").format(e=exc)

    def points_enabled(self, action: str) -> bool | None:
        """``enabled()`` for this panel's actions; ``None`` for actions it does not own."""
        if action == "measure_points":
            return bool(self.points) and not self.running and self.source_kind != "replay"
        if action in ("clear_points",):
            return bool(self.points) and not self.running
        if action == "autopick":
            return not self.running and bool((self.image_snapshot or {}).get("images"))
        if action == "connect_scanner":
            return self.scanner is None and not self.connecting
        if action == "disconnect_scanner":
            return self.scanner is not None and not self.running
        return None
