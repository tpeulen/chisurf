"""The Record tool's Survey: image a large area tile by tile, pick and measure the molecules on each.

:class:`SurveyMixin` is mixed into :class:`~chisurf.plugins.core.acq.gui.record_app.RecordModel`.
A survey runs what a user does by hand, again and again: image a tile (the Scan panel's raster at
the tile's corner), *Auto-pick* its molecules, *Measure points*, and on to the next tile -- until
Stop, a stop condition, or the area is done. The tiles come from ``live.survey.plan_tiles``: an
outward spiral from where the user focused (nearest first, as a coverslip is rarely flat) or
serpentine rows. A tile with too few molecules is logged as empty and passed; a tile that fails
is logged and passed. The shutters open once at the start and close once at the end (or Stop);
the laser is never switched. Every tile image and every molecule's recording is a dataset as in a
single run, and one table of all molecules (tile, stage position, results) is stored with the
first tile's image and rewritten after every tile, so a stopped survey keeps its results.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from emtk.i18n import tr

_log = logging.getLogger(__name__)


#: Survey learning choice -> the pi driver's ``learning`` setting.
LEARNING = {"every": 0, "first": 1, "recheck": 2}


class SurveyMixin:
    """Survey options, the tile loop (stepped from ``poll``) and its results."""

    def _init_survey(self) -> None:
        self.survey_area_kind = "piezo"
        self.survey_x0_um, self.survey_y0_um = 10.0, 10.0
        self.survey_w_um, self.survey_h_um = 50.0, 50.0
        self.survey_overlap_um = 0.0
        self.survey_order = "spiral"
        self.survey_centre = "stage"
        self.survey_guard_px = 2
        self.survey_min_molecules = 1
        self.survey_max_tiles = 0
        self.survey_max_molecules = 0
        self.survey_max_minutes = 0.0
        self.survey_max_empty = 0
        self.survey_reimage = False
        #: The scanner's learning during a survey: every tile alike in size, so by default it
        #: learns on the first tile and re-checks the line triggers on the others.
        self.survey_learning = "recheck"
        #: the running survey's state (``None``: no survey)
        self._survey: dict | None = None
        self._survey_sample = None
        self.survey_tiles: list = []
        self.survey_rows: list[dict] = []
        self.survey_log: list[str] = []
        self.survey_fraction: float | None = 0.0
        self.survey_text = tr("Survey: image the area tile by tile, pick and measure each.")
        self.survey_saved = ""

    # -- options ---------------------------------------------------------------------------------
    def survey_area_options(self) -> list:
        return [("piezo", tr("Whole piezo range")), ("custom", tr("Custom area"))]

    def survey_order_options(self) -> list:
        return [("spiral", tr("Spiral out from the start")), ("serpentine", tr("Serpentine rows"))]

    def survey_learning_options(self) -> list:
        return [("every", tr("Every tile (slowest)")), ("first", tr("First tile only")),
                ("recheck", tr("First tile, re-check line triggers"))]

    def _set_scanner_learning(self, mode: int) -> None:
        if self.scanner is not None and hasattr(self.scanner, "learning"):
            self.scanner.learning = int(mode)

    def survey_centre_options(self) -> list:
        return [("stage", tr("Where I focused (the last image)")), ("area", tr("The area's centre"))]

    @property
    def survey_custom_hidden(self) -> bool:
        return self.survey_area_kind != "custom"

    @property
    def survey_active(self) -> bool:
        return self._survey is not None

    def _stage_range(self):
        from chisurf.plugins.core.acq.live.survey import piezo_range

        return piezo_range(self.scanner)

    def survey_area(self) -> tuple[float, float, float, float]:
        """``(x0, y0, width, height)`` of the area to survey, in µm."""
        (x0, x1), (y0, y1) = self._stage_range()
        if self.survey_area_kind == "piezo":
            return x0, y0, x1 - x0, y1 - y0
        return (float(self.survey_x0_um), float(self.survey_y0_um), float(self.survey_w_um),
                float(self.survey_h_um))

    def _start_position(self, ask_stage: bool = True) -> tuple[float, float] | None:
        """Where the user focused: the centre of the last image taken (the scanner parks at the
        stage centre after every raster, so its position says nothing about the focus), else the
        stage's position, else the centre of the Scan panel's raster."""
        if self.survey_centre == "area":
            return None
        if self.image_scan is not None:
            scan = self.image_scan
            return scan.x0_um + scan.area_x_um / 2, scan.y0_um + scan.area_y_um / 2
        if ask_stage and self.scanner is not None:
            try:
                return tuple(float(v) for v in self.scanner.position())  # type: ignore[return-value]
            except Exception:  # noqa: BLE001 - the last image's centre instead
                pass
        scan = self.image_scan or self.scan_settings()
        return scan.x0_um + scan.area_x_um / 2, scan.y0_um + scan.area_y_um / 2

    def survey_plan(self, ask_stage: bool = True) -> list:
        from chisurf.plugins.core.acq.live.survey import plan_tiles

        return plan_tiles(self.survey_area(), (float(self.scan_area_x_um),
                                               float(self.scan_area_y_um)),
                          overlap_um=float(self.survey_overlap_um), stage=self._stage_range(),
                          order=self.survey_order, start_um=self._start_position(ask_stage))

    def _preview_key_now(self) -> tuple:
        return (self.survey_area(), float(self.scan_area_x_um), float(self.scan_area_y_um),
                float(self.survey_overlap_um), self.survey_order, self.survey_centre,
                self._start_position(ask_stage=False))

    def survey_preview(self) -> list:
        """The tiles the overview shows: the running survey's, else the plan of the options now
        (re-planned only when an option changed; the stage is not asked every frame)."""
        if self.survey_active:
            return self.survey_tiles
        key = self._preview_key_now()
        if key != getattr(self, "_preview_key", None):
            self._preview_key = key
            try:
                self.survey_tiles = self.survey_plan(ask_stage=False)
            except ValueError:
                self.survey_tiles = []
        return self.survey_tiles

    # -- the loop ----------------------------------------------------------------------------------
    def survey_start(self) -> bool:
        """Start the survey (see the module notes)."""
        if self.busy or self.survey_active:
            return False
        problem = ""
        if self.mode != "image":
            problem = tr("A survey images: choose Image mode.")
        elif self.source_kind == "replay":
            problem = tr("A survey needs the simulator or the TCSPC device and scanner.")
        elif self.source_kind == "device" and (self.device is None or self.scanner is None):
            problem = tr("Connect the device and the scanner first.")
        try:
            tiles = [] if problem else self.survey_plan()
        except ValueError as exc:
            problem, tiles = str(exc), []
        if problem:
            self.survey_text = self.status_text = problem
            return False
        if self.source_kind == "simulator":
            self._survey_sample = self._surveyed_sample(tiles)
        self.survey_tiles = tiles
        self.survey_rows, self.survey_log, self.survey_saved = [], [], ""
        self.clear_points()
        self._survey = {"next": 0, "phase": "next", "t0": time.monotonic(), "abort": False,
                        "id": time.strftime("survey_%Y%m%d_%H%M%S"),
                        "tile": None, "empty_run": 0, "origin": (self.scan_x0_um,
                                                                 self.scan_y0_um),
                        "container": None, "taken": []}
        self._set_scanner_learning(LEARNING.get(str(self.survey_learning), 2))
        # once for the whole survey (a tile's run leaves them alone while a survey runs)
        self._shutters_at_start()
        self._survey_note(tr("Survey of {n} tile(s) started.").format(n=len(tiles)))
        return True

    def _surveyed_sample(self, tiles):
        """The simulated sample of a survey: fixed on the stage over the surveyed area, as dense
        as one tile of the Scan panel's sample."""
        sample = self.imaging_sample()
        if sample.positions is None and sample.area is None:
            x0, y0, w, h = self.survey_area()
            per_tile = float(self.scan_area_x_um) * float(self.scan_area_y_um)
            sample.n_beads = max(1, int(round(sample.n_beads * w * h / max(per_tile, 1e-9))))
            sample.area = (x0, y0, w, h)
        return sample

    def survey_stop(self) -> None:
        if self._survey is not None:
            self._survey["abort"] = True

    def _survey_note(self, text: str) -> None:
        self.survey_log.append(f"{time.strftime('%H:%M:%S')} {text}")
        _log.info("survey: %s", text)

    def survey_step(self) -> None:
        """Advance the survey by what has finished (called from ``poll``)."""
        sv = self._survey
        if sv is None:
            return
        phase = sv["phase"]
        tile = sv["tile"]
        if phase in ("image", "reimage"):
            if self.session is not None and (self.session.running or not self._registered):
                return
            if phase == "image":
                result = self.session.result if self.session is not None else None
                if sv["container"] is None and result is not None and self.image_uid:
                    sv["container"] = (self.image_ptu, self.image_uid)
                self._record_tile(tile)
                if sv["abort"]:
                    tile.state = "done" if tile.measured else "pending"
                    return self._survey_finish(tr("stopped"))
                sv["phase"] = "pick"
                return self.survey_step()
            sv["phase"] = "next"
        elif phase == "pick":
            self._survey_pick(tile)
        elif phase == "points":
            if self.sequence is None or self.points_running or not self._sequence_finished:
                return
            self._survey_collect(tile)
            if self.survey_reimage and not sv["abort"]:
                self._tag_tile(tile)
                started = self.start()
                self._run_tags = {}
            else:
                started = False
            if started:
                sv["phase"] = "reimage"
            else:
                sv["phase"] = "next"
        if sv["phase"] == "next":
            self._survey_next()
        self._survey_progress()

    def _survey_pick(self, tile) -> None:
        from chisurf.plugins.core.acq.live.survey import keep_picks

        sv = self._survey
        scan = self.image_scan or self.scan_settings()
        pixel = max(scan.pixel_um)
        found, n = self.find_molecules()
        keep, skipped = keep_picks([(x, y) for x, y, _ in found], tile,
                                   guard_um=float(self.survey_guard_px) * pixel,
                                   taken=sv["taken"], same_um=2.0 * pixel,
                                   stage=self._stage_range())
        cap = int(self.autopick_max) if int(self.autopick_max) > 0 else len(keep)
        if int(self.survey_max_molecules) > 0:
            cap = min(cap, int(self.survey_max_molecules) - len(self.survey_rows))
        keep = keep[: max(0, cap)]
        tile.found = n
        why = ", ".join(f"{v} {k}" for k, v in skipped.items() if v)
        if len(keep) < max(1, int(self.survey_min_molecules)):
            tile.state = "empty"
            sv["empty_run"] += 1
            self._survey_note(tr("Tile {i}: {n} spot(s), {k} to measure{why}: empty, passed.")
                              .format(i=tile.index + 1, n=n, k=len(keep),
                                      why=f" ({why} left out)" if why else ""))
            sv["phase"] = "next"
            return
        sv["empty_run"] = 0
        self.clear_points()
        for i in keep:
            x, y, bright = found[i]
            self.add_point(x, y, "auto", bright)
        if not self.measure_points():
            tile.state, tile.note = "failed", self.points_text
            self._survey_note(tr("Tile {i}: the points did not start: {e}").format(
                i=tile.index + 1, e=self.points_text))
            sv["phase"] = "next"
            return
        self._survey_note(tr("Tile {i}: measuring {k} of {n} spot(s).").format(
            i=tile.index + 1, k=len(keep), n=n))
        sv["phase"] = "points"

    def _survey_collect(self, tile) -> None:
        """The tile's measured molecules into the survey's table (stored at once)."""
        sv = self._survey
        measured = 0
        for p in self.points:
            m = self.molecules.get(p["index"])
            sv["taken"].append((p["x_um"], p["y_um"]))
            if m is None:
                continue
            measured += 1
            self.survey_rows.append({"tile": tile.index, "molecule": m, "point": dict(p)})
        tile.measured = measured
        tile.state = "done"
        self._survey_note(tr("Tile {i}: {k} molecule(s) measured.").format(
            i=tile.index + 1, k=measured))
        self._survey_store()

    def _survey_next(self) -> None:
        sv = self._survey
        elapsed = time.monotonic() - sv["t0"]
        done = sum(1 for t in self.survey_tiles if t.state in ("done", "empty", "failed"))
        reason = ""
        if sv["abort"]:
            reason = tr("stopped")
        elif sv["next"] >= len(self.survey_tiles):
            reason = tr("area done")
        elif int(self.survey_max_tiles) > 0 and done >= int(self.survey_max_tiles):
            reason = tr("{n} tiles done").format(n=done)
        elif int(self.survey_max_molecules) > 0 and \
                len(self.survey_rows) >= int(self.survey_max_molecules):
            reason = tr("{n} molecules measured").format(n=len(self.survey_rows))
        elif float(self.survey_max_minutes) > 0 and elapsed >= 60 * float(self.survey_max_minutes):
            reason = tr("time is up")
        elif int(self.survey_max_empty) > 0 and sv["empty_run"] >= int(self.survey_max_empty):
            reason = tr("{n} empty tiles in a row").format(n=sv["empty_run"])
        if reason:
            return self._survey_finish(reason)
        while sv["next"] < len(self.survey_tiles):
            tile = self.survey_tiles[sv["next"]]
            sv["next"] += 1
            sv["tile"] = tile
            tile.state = "current"
            self.scan_x0_um, self.scan_y0_um = tile.x0_um, tile.y0_um
            self._tag_tile(tile)
            started = self.start()
            self._run_tags = {}
            if started:
                sv["phase"] = "image"
                return
            tile.state, tile.note = "failed", self.status_detail
            self._survey_note(tr("Tile {i} failed: {e}").format(i=tile.index + 1,
                                                                 e=self.status_detail))
        return self._survey_finish(tr("area done"))

    def _tile_info(self, tile) -> dict:
        return {"survey_id": self._survey["id"], "tile": tile.index,
                "tile_x0_um": tile.x0_um, "tile_y0_um": tile.y0_um}

    def _learned(self) -> int | None:
        """How many times the scanner has learned a pattern (libphacq pi ``learned``)."""
        try:
            return int(self.scanner.device.get_parameter("learned"))
        except Exception:  # noqa: BLE001 - no scanner, or a driver without the count
            return None

    def _tag_tile(self, tile) -> None:
        """The next recording is this tile's: its header names the survey, the tile, its origin
        and the scanner's learning; the points picked on it name them too."""
        from chisurf.plugins.core.acq.live.provenance import tile_tags

        info = self._tile_info(tile)
        self._point_context = dict(info)
        self._run_tags = tile_tags(info, tiles=len(self.survey_tiles),
                                   learning=str(self.survey_learning) if self.scanner else "",
                                   learned_before=self._learned())

    def _record_tile(self, tile) -> None:
        """The tile's image is a dataset: record it in the survey (its container names the
        survey; the survey's list names the image)."""
        from chisurf.plugins.core.acq.live.provenance import write_survey_tile

        tile.image_uid = str(self.image_uid or "")
        tile.image_name = Path(str(self.image_ptu)).name if self.image_ptu else ""
        try:
            write_survey_tile(self.image_ptu, tile.image_uid, self._tile_info(tile),
                              tiles=len(self.survey_tiles), state="imaged",
                              learned_after=self._learned())
        except Exception:  # noqa: BLE001 - the header carries it anyway
            _log.exception("recording tile %s", tile.index)

    def _survey_finish(self, reason: str) -> None:
        sv = self._survey
        self._survey = None
        self._point_context, self._run_tags = {}, {}
        self._survey_sample = None
        for t in self.survey_tiles:
            if t.state == "current":
                t.state = "done" if t.measured else "pending"
        self._survey_store(sv)
        self._set_scanner_learning(0)   # a single image learns as always
        self._shutters_at_end()
        self._preview_key = self._preview_key_now()  # the overview keeps the survey's tiles
        done = sum(1 for t in self.survey_tiles if t.state in ("done", "empty"))
        elapsed = time.monotonic() - sv["t0"]
        self.survey_text = tr("Survey {why}: {t} tile(s), {m} molecule(s) in {s:.0f} s.").format(
            why=reason, t=done, m=len(self.survey_rows), s=elapsed)
        self._survey_note(self.survey_text)
        self.status_text = self.survey_text
        self.status_detail = self.survey_saved or "\n".join(self.survey_log[-5:])
        self.survey_fraction = 1.0

    def _survey_progress(self) -> None:
        sv = self._survey
        if sv is None:
            return
        n = len(self.survey_tiles)
        done = sum(1 for t in self.survey_tiles if t.state in ("done", "empty", "failed"))
        elapsed = time.monotonic() - sv["t0"]
        eta = elapsed / done * (n - done) if done else float("nan")
        self.survey_fraction = done / max(1, n)
        tile = sv["tile"]
        self.survey_text = tr(
            "Tile {i}/{n} · {m} molecule(s) · {e} elapsed · ETA {r}").format(
            i=(tile.index + 1) if tile is not None else 0, n=n, m=len(self.survey_rows),
            e=_hms(elapsed), r=_hms(eta) if np.isfinite(eta) else "–")
        self.status_text = tr("Survey: tile {i}/{n}").format(
            i=(tile.index + 1) if tile is not None else 0, n=n)
        self.status_detail = self.survey_text

    # -- results -----------------------------------------------------------------------------------
    def survey_table(self) -> dict[str, np.ndarray]:
        """All molecules of the survey: the per-molecule table with the tile of each, its point
        recording and its image (``point_dataset`` / ``image_dataset`` index
        :meth:`survey_lookups`)."""
        from chisurf.plugins.core.acq.live.molecules import molecule_rows
        from chisurf.plugins.core.acq.live.provenance import lookup

        rows = molecule_rows([r["molecule"] for r in self.survey_rows])
        rows["tile"] = np.asarray([r["tile"] for r in self.survey_rows], np.int64)
        refs = self._survey_refs()
        rows["point_dataset"] = lookup(refs, "point")[1]
        rows["image_dataset"] = lookup(refs, "image")[1]
        return rows

    def _survey_refs(self) -> list[dict]:
        out = []
        for r in self.survey_rows:
            p = r.get("point") or {}
            out.append({"point_uid": p.get("dataset_uid"),
                        "point_name": Path(str(p.get("ptu", ""))).name,
                        "image_uid": p.get("image_uid"), "image_name": p.get("image")})
        return out

    def survey_lookups(self) -> dict:
        """The datasets the survey table's ``point_dataset`` / ``image_dataset`` columns index."""
        from chisurf.plugins.core.acq.live.provenance import lookup

        refs = self._survey_refs()
        return {"point_datasets": lookup(refs, "point")[0],
                "image_datasets": lookup(refs, "image")[0]}

    def _survey_store(self, sv: dict | None = None) -> None:
        """The survey with its first tile's image (rewritten after every tile): the table of
        all molecules and the list of all tiles with their images."""
        from chisurf.plugins.core.acq.live import provenance

        sv = sv or self._survey or {}
        container = sv.get("container") or getattr(self, "_survey_container", None)
        if sv.get("container"):
            self._survey_container = sv["container"]
        if container is None:
            return
        source, uid = container
        area = self.survey_area()
        parameters = {"analysis": "survey", "area_um": list(area),
                      "tile_um": [float(self.scan_area_x_um), float(self.scan_area_y_um)],
                      "overlap_um": float(self.survey_overlap_um), "order": self.survey_order}
        try:
            provenance.write_survey_tiles(source, uid, str(sv.get("id", "")), self.survey_tiles,
                                          parameters)
            if not self.survey_rows:
                return
            path = provenance._put(
                str(source), uid, "survey_molecules.table", self.survey_table(),
                artifact_kind="analysis_result", operation_type="survey", row_grain="molecule",
                parameters={**parameters, "survey_id": str(sv.get("id", "")),
                            **self.survey_lookups()},
                units=provenance.MOLECULE_UNITS)
            self.survey_saved = tr("{n} molecule(s) stored with the first tile: {where}").format(
                n=len(self.survey_rows), where=Path(path).name)
        except Exception as exc:  # noqa: BLE001 - shown; the recordings are kept
            _log.exception("storing the survey")
            self.survey_saved = tr("Survey table not stored: {e}").format(e=exc)

    def survey_enabled(self, action: str) -> bool | None:
        if action == "survey_start":
            return not self.running and self.mode == "image" and self.source_kind != "replay" \
                and (self.source_kind != "device" or (self.device is not None
                                                      and self.scanner is not None))
        return None

    def wait_survey(self, timeout: float = 600.0) -> None:
        """Run a survey to its end (scripts and tests): poll until it has finished."""
        end = time.monotonic() + timeout
        while self.survey_active and time.monotonic() < end:
            self.poll(force=True)
            time.sleep(0.01)


def _hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def survey_tile_colour(state: str) -> tuple[int, int, int, int]:
    """The overview's fill of a tile in *state*."""
    return {"pending": (60, 60, 66, 255), "current": (230, 160, 40, 255),
            "done": (60, 170, 80, 255), "empty": (95, 95, 110, 255),
            "failed": (200, 60, 60, 255)}.get(state, (60, 60, 66, 255))


def draw_survey_map(model: Any, width: float, height: float) -> None:
    """The survey's overview: the area, its tiles coloured by state with the visiting path, and
    every measured molecule as a dot (hand-drawn: a spec has no canvas)."""
    from emtk import im

    tiles = model.survey_tiles
    x0, y0, w, h = model.survey_area()
    origin = im.get_cursor_screen_pos()
    scale = min(width / max(w, 1e-9), height / max(h, 1e-9))
    box_w, box_h = w * scale, h * scale
    draw = im.get_window_draw_list()
    ox, oy = origin[0], origin[1]

    def at(x, y):
        return ox + (x - x0) * scale, oy + (y - y0) * scale

    draw.add_rect_filled((ox, oy), (ox + box_w, oy + box_h), (25, 25, 30, 255))
    for t in tiles:
        a = at(t.x0_um, t.y0_um)
        b = at(t.x0_um + t.width_um, t.y0_um + t.height_um)
        draw.add_rect_filled((a[0] + 0.5, a[1] + 0.5), (b[0] - 0.5, b[1] - 0.5),
                             survey_tile_colour(t.state))
    if len(tiles) > 1:
        centres = [at(t.x0_um + t.width_um / 2, t.y0_um + t.height_um / 2) for t in tiles]
        for p, q in zip(centres[:-1], centres[1:]):
            draw.add_line(p, q, (240, 240, 240, 140), 1.0)
        if tiles[0].width_um * scale > 16:
            for t, c in zip(tiles, centres):
                draw.add_text((c[0] - 4.0, c[1] - 7.0), (255, 255, 255, 230), str(t.index + 1))
    for row in model.survey_rows:
        m = row["molecule"]
        draw.add_circle_filled(at(*m.point), 1.8, (120, 230, 255, 255))
    draw.add_rect((ox, oy), (ox + box_w, oy + box_h), (180, 180, 190, 255))
    im.dummy(width, box_h + 4.0)
