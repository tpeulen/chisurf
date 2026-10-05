"""The native FCS correlator steps: Files & Steps, Photon / Burst Filter and Correlator, as emtk apps.

Each step draws its Qt-free model (:mod:`..filter_model`, :mod:`..correlator_model`) from the same ``view.json`` the Qt
AutoForm panel draws; the Qt-only custom sections are drawn here. The hand-over between the steps is
:class:`..workflow.FcsWorkflow`'s, called by the hub when a step is opened (:mod:`chisurf.plugins.fcs.fcs_toolbox.gui.app`).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from ..correlator_model import CorrelatorSettingsModel, apply_channel_key, preset_names
from ..filter_model import FilterSettingsModel
from ..workflow import FILE_EXTENSIONS, filter_step_allowed

HERE = Path(__file__).resolve().parents[1]
TTTR_FILTER = "TTTR files (" + " ".join(f"*{e}" for e in FILE_EXTENSIONS) + ");;All files (*)"
LIFETIME_FILTER = "Lifetime filters (*.json *.npy *.npz);;All files (*)"
#: Correlation curve colours (one per chunk / species), RGBA.
CURVES = [(228, 26, 28, 255), (255, 221, 0, 255), (55, 126, 184, 255), (77, 175, 74, 255),
          (152, 78, 163, 255), (255, 127, 0, 255), (166, 86, 40, 255), (247, 129, 191, 255)]
SELECTED, REMOVED = (0, 220, 220, 255), (230, 200, 0, 255)


def _body(name: str, pad: float = 6.0) -> None:
    """Open a padded, scrolling region filling the window (emtk windows do not scroll, a child region does)."""
    x, y = im.get_cursor_screen_pos()
    w, h = im.get_content_region_avail()
    im.set_cursor_screen_pos((x + pad, y + pad))
    im.begin_child(name, (max(1.0, w - 2 * pad), max(1.0, h - 2 * pad)))


def _same_line_if_fits(label: str, used: float) -> float:
    """Put the next button on this line if it fits, else on the next; the width used on the line after it."""
    width = im.calc_text_size(label)[0] + 2 * im.get_style().frame_padding[0]
    room = im.get_content_region_avail()[0]
    if used > 0 and used + im.get_style().item_spacing[0] + width <= room:
        im.same_line()
        return used + im.get_style().item_spacing[0] + width
    return width


class _Dialogs:
    """A file dialog drawn over the step, and the callback that takes its choice."""

    def __init__(self) -> None:
        self.dialog: FileDialog | None = None
        self.window: DialogWindow | None = None
        self._on_pick: Callable[[list[str]], Any] | None = None

    def ask(self, title: str, mode: str, filters: str, on_pick, multiselect: bool = False) -> None:
        kwargs = {"multiselect": True} if multiselect else {}
        self.dialog = FileDialog(title, mode=mode, filters=filters, **kwargs)
        self.window = DialogWindow(title, size=(720, 520))
        self._on_pick = on_pick

    def draw(self, frame) -> None:
        if self.dialog is None:
            return
        pressed = self.window.begin(frame)
        result = self.dialog.draw()
        self.window.end()
        if result:
            self.dialog, pick = None, self._on_pick
            pick([str(p) for p in result])
        elif result is False or pressed == "close":
            self.dialog = None


# ── 2. Files & Steps ─────────────────────────────────────────────────────────


class FilesStepApp(ImApp):
    """The checked file list (Files..., Folder..., Database, All, None, Remove, Clear) and the optional steps."""

    def __init__(self, on_change: Callable[[], Any] | None = None, client: Any = None,
                 on_used: Callable[[str], Any] | None = None) -> None:
        self.on_used = on_used or (lambda _name: None)
        self.paths: list[str] = []
        self.checked: set[str] = set()
        self.current = -1
        self.use_filter = False
        self.use_merger = True
        self.on_change = on_change
        self.client = client
        self.dialogs = _Dialogs()
        self.picker = None
        self.item_rects: dict[str, tuple] = {}
        super().__init__(gui=self.render, continuous=False)

    # what the workflow reads
    @property
    def checked_files(self) -> list[str]:
        return [p for p in self.paths if p in self.checked]

    @property
    def filter_allowed(self) -> bool:
        return filter_step_allowed(self.checked_files)

    def changed(self) -> None:
        if not self.filter_allowed:
            self.use_filter = False
        if self.on_change is not None:
            self.on_change()
        self.request_frame()

    # actions
    def add_paths(self, paths) -> int:
        added = 0
        for p in paths:
            p = str(Path(str(p)).resolve())
            if p not in self.paths and (Path(p).is_dir() or Path(p).suffix.lower() in FILE_EXTENSIONS):
                self.paths.append(p)
                self.checked.add(p)
                added += 1
        if added:
            self.changed()
        return added

    def remove_current(self) -> None:
        if 0 <= self.current < len(self.paths):
            self.checked.discard(self.paths.pop(self.current))
            self.current = min(self.current, len(self.paths) - 1)
            self.changed()

    def clear(self) -> None:
        self.paths, self.checked, self.current = [], set(), -1
        self.changed()

    def set_all(self, on: bool) -> None:
        self.checked = set(self.paths) if on else set()
        self.changed()

    def add_example(self) -> None:
        """The demonstration photon stream (:mod:`..demo`), written once into the settings cache, added and ticked."""
        from ..demo import demo_folder, make_demo

        self.add_paths([make_demo(demo_folder())])

    def open_database(self) -> None:
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.picker = DatasetPicker(client=self.client, kinds=["tttr"], on_paths=self.add_paths)
        self.picker.open()

    def on_paths_dropped(self, paths) -> bool:
        return self.add_paths(paths) > 0

    def export_settings(self) -> dict:
        return {"paths": list(self.paths), "checked": self.checked_files, "use_filter": self.use_filter,
                "use_merger": self.use_merger}

    def restore_settings(self, state: dict) -> None:
        self.paths = [p for p in state.get("paths", []) if Path(p).exists()]
        self.checked = {p for p in state.get("checked", []) if p in self.paths}
        self.use_filter = bool(state.get("use_filter", False))
        self.use_merger = bool(state.get("use_merger", True))
        self.changed()

    def _button(self, label: str, key: str, tip: str, enabled: bool = True) -> bool:
        im.begin_disabled(not enabled)
        pressed = im.button(label)
        im.end_disabled()
        im.set_item_tooltip(tip)
        self.item_rects[key] = im.get_item_rect()
        if pressed and enabled:
            self.on_used(key)
        return pressed and enabled

    def render(self) -> None:
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, w, h)
        blocked = self.dialogs.dialog is not None or bool(self.picker and self.picker.is_open)
        if im.begin("Files & Steps", frame, flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            _body("files_body")
            im.begin_disabled(blocked)
            im.text("Files:")
            im.set_item_tooltip("TTTR files (or folders of them) to correlate; only the ticked ones are used.")
            x, y = im.get_cursor_screen_pos()
            list_h = max(80.0, im.get_content_region_avail()[1] - 90.0)
            im.begin_child("files_list", (im.get_content_region_avail()[0], list_h))
            if not self.paths:
                im.text_disabled("No file. Add files or a folder, or drop them here.")
            for i, path in enumerate(list(self.paths)):
                on = path in self.checked
                changed, on = im.checkbox(f"##check{i}", on)
                if changed:
                    (self.checked.add if on else self.checked.discard)(path)
                    self.changed()
                im.set_item_tooltip("Use this file.")
                self.item_rects[f"check.{i}"] = im.get_item_rect()
                im.same_line()
                if im.selectable(f"{path}##row{i}", i == self.current):
                    self.current = i
                im.set_item_tooltip(path)
                self.item_rects[f"row.{i}"] = im.get_item_rect()
            im.end_child()
            self.item_rects["files"] = (x, y, im.get_content_region_avail()[0], list_h)
            used = 0.0
            for label, key, tip, enabled, act in (
                ("Files...", "add_files", "Add TTTR files.", True,
                 lambda: self.dialogs.ask("Add TTTR files", "open", TTTR_FILTER, self.add_paths, multiselect=True)),
                ("Folder...", "add_folder", "Add a folder: its TTTR files are correlated.", True,
                 lambda: self.dialogs.ask("Add a folder", "folder", "All files (*)", self.add_paths)),
                ("Database", "database", "Add a TTTR dataset registered in the database.", True, self.open_database),
                ("Example", "example", "Add a simulated FCS measurement (molecules crossing the focus in about "
                 "0.25 ms) to try the workflow on data whose answer is known.", True, self.add_example),
                ("All", "all", "Tick every file.", bool(self.paths), lambda: self.set_all(True)),
                ("None", "none", "Untick every file.", bool(self.paths), lambda: self.set_all(False)),
                ("Remove", "remove", "Remove the highlighted file from the list (the file is kept).",
                 0 <= self.current < len(self.paths), self.remove_current),
                ("Clear", "clear", "Empty the list (no file is deleted).", bool(self.paths), self.clear),
            ):
                used = _same_line_if_fits(label, used)
                if self._button(label, key, tip, enabled):
                    act()
            im.text("Steps:")
            im.same_line()
            im.begin_disabled(not self.filter_allowed)
            changed, value = im.checkbox("Count rate/burst filter", self.use_filter)
            im.end_disabled()
            if changed and self.filter_allowed:
                self.use_filter = value
                self.on_used("use_filter")
                self.changed()
            im.set_item_tooltip("Correlate only the photons a count-rate or burst filter keeps (step 3)."
                                if self.filter_allowed else "Disabled when Burst-ID (.bst) files are selected.")
            self.item_rects["use_filter"] = im.get_item_rect()
            im.same_line()
            changed, value = im.checkbox("FCS merger", self.use_merger)
            if changed:
                self.use_merger = value
                self.on_used("use_merger")
                self.changed()
            im.set_item_tooltip("Screen and merge the correlation curves after correlating (step 5).")
            self.item_rects["use_merger"] = im.get_item_rect()
            im.end_disabled()
            im.end_child()
        im.end()
        self.dialogs.draw(frame)
        if self.picker is not None:
            self.picker.render(frame)


# ── 3. Photon / Burst Filter ─────────────────────────────────────────────────


class FilterStepApp(ImApp):
    """The filter parameters (mode-pruned spec), the kept-photon count and the dT / count-rate plots."""

    def __init__(self, model: FilterSettingsModel | None = None,
                 on_used: Callable[[str], Any] | None = None) -> None:
        self.model = model or FilterSettingsModel()
        self.form = FormState(on_used=on_used)
        self.form.custom["filter_info"] = self._draw_info
        self.form.custom["filter_dt_plot"] = self._draw_dt
        self.form.custom["filter_cr_plot"] = self._draw_cr
        self.item_rects: dict[str, tuple] = {}
        self._spec_mode = None
        self._spec = None
        super().__init__(gui=self.render, continuous=False)

    def spec(self) -> dict:
        if self._spec is None or self._spec_mode != self.model.filter_mode:
            self._spec, self._spec_mode = self.model.view_spec_dict(), self.model.filter_mode
            for section in _walk(self._spec["sections"]):
                if section.get("type") == "panel":
                    section.setdefault("collapsible", True)
        return self._spec

    def _draw_info(self, section, model, state, width) -> None:
        im.text(self.model.info_text())
        self.item_rects["filter_info"] = im.get_item_rect()

    def _draw_dt(self, section, model, state, width) -> None:
        series = self.model.dt_scatter_series()
        if implot.begin_plot("Delta macro-time##fcsdt", (-1, 220)):
            implot.setup_axes("Photon index", "dT (ms)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for s in series:
                colour = SELECTED if s["name"] == "selected" else REMOVED
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 1.5, colour, 0.0, colour)
                x, y = np.asarray(s["x"], float), np.asarray(s["y"], float)
                keep = y > 0
                implot.plot_scatter(s["name"], x[keep], y[keep])
            lo, hi = float(self.model.min_dmt), float(self.model.max_dmt)
            a = implot.drag_line_y(1, lo, (80, 180, 255, 255), 1.0)
            b = implot.drag_line_y(2, hi, (80, 180, 255, 255), 1.0)
            if a.modified or b.modified:
                lo, hi = a.value, b.value
                self.model.min_dmt, self.model.max_dmt = float(min(lo, hi)), float(max(lo, hi))
                self.model.use_min = self.model.use_max = True
                self.model.on_param_changed()
            implot.end_plot()
        im.set_item_tooltip("dT between consecutive photons; drag the blue lines to set min / max dMT.")
        self.item_rects["filter_dt_plot"] = im.get_item_rect()

    def _draw_cr(self, section, model, state, width) -> None:
        series = self.model.count_rate_series()
        if implot.begin_plot("Count rate##fcscr", (-1, 200)):
            implot.setup_axes("Time (s)", "Intensity (kHz)")
            for s in series:
                implot.set_next_line_style(SELECTED if s["name"] == "selected" else REMOVED, 1.0)
                implot.plot_line(s["name"], np.asarray(s["x"], float), np.asarray(s["y"], float))
            implot.end_plot()
        im.set_item_tooltip("Count rate of all photons and of the photons the filter keeps.")
        self.item_rects["filter_cr_plot"] = im.get_item_rect()

    def render(self) -> None:
        w, h = im.get_main_viewport().size
        if im.begin("Photon / Burst Filter", (0.0, 0.0, w, h),
                    flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            _body("filter_body")
            if self.model._tttr is None:
                im.text_wrapped("No photons: tick files in Files & Steps first.")
            self.form.rects.clear()
            draw_form(self.spec(), self.model, self.form)
            self.item_rects.update(self.form.rects)
            im.end_child()
        im.end()


# ── 4. Correlator ────────────────────────────────────────────────────────────


class CorrelatorStepApp(ImApp):
    """Correlation channels and settings (left), the correlation curves (right); Correlate runs on a worker."""

    def __init__(self, model: CorrelatorSettingsModel | None = None,
                 open_tool: Callable[[str], Any] | None = None,
                 on_used: Callable[[str], Any] | None = None) -> None:
        self.on_used = on_used or (lambda _name: None)
        self.model = model or CorrelatorSettingsModel()
        self.open_tool = open_tool
        self.dialogs = _Dialogs()
        self.status = "No data loaded."
        self.filter_status = ""
        self.preset = ""
        self.item_rects: dict[str, tuple] = {}
        self._worker: threading.Thread | None = None
        self._stop = False
        self._done = 0
        spec = json.loads((HERE / "correlator.view.json").read_text(encoding="utf-8"))
        dock = spec["sections"][0]
        controls = next(s for s in dock["sections"] if s.get("title") == "Controls")
        self.controls_spec = {"sections": controls["sections"]}
        self.plot_section = next(s for s in _walk(dock["sections"]) if s.get("type") == "plot")
        self.form = FormState(on_used=self.on_used)
        self.form.custom.update({
            "fcs_presets": self._draw_presets,
            "lifetime_filter_controls": self._draw_filter_controls,
            "channel_combos": self._draw_channel_combos,
            "correlate_controls": self._draw_correlate,
        })
        self.docks = DockManager(Split("h", 0.42, Region("controls"), Region("plot")))
        self.docks.add_window("controls", "Controls", self._draw_controls, dock="controls", closable=False)
        self.docks.add_window("plot", "FCS Correlation", self._draw_plot, dock="plot", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(gui=self.render, continuous=False)

    # worker
    @property
    def running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def correlate(self, wait: bool = False) -> None:
        if self.running:
            return
        self._stop, self._done = False, 0

        def progress(done, total):
            self._done = done
            self.status = f"Correlating chunk {done} of {total}..."
            self.request_frame()
            return not self._stop

        def run():
            self.status = self.model.correlate_data(progress=progress)
            self.request_frame()

        self.status = "Computing correlations..."
        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()
        if wait:
            self._worker.join()

    def stop(self) -> None:
        self._stop = True

    def run_step(self) -> bool:
        """The step's run for the hub's Next / fast-forward: Correlate (only when there are photons)."""
        if self.model._tttr is None or len(self.model._tttr) == 0:
            return False
        self.correlate()
        return True

    def animating(self) -> bool:
        return self.running or super().animating()

    def close(self) -> None:
        self._stop = True

    # filters
    def load_filters(self, path: str) -> None:
        try:
            n = self.model.load_lifetime_filter_file(path)
        except Exception as exc:  # noqa: BLE001 - shown beside the buttons
            self.filter_status = f"Filter load failed: {exc}"
            return
        self.filter_status = f"{n} species loaded."

    # custom sections
    def _draw_presets(self, section, model, state, width) -> None:
        names = ["", *preset_names(self.model)]
        idx = names.index(self.preset) if self.preset in names else 0
        im.text("FCS Preset:")
        im.same_line()
        im.set_next_item_width(-1)
        changed, new = im.combo("##fcs_preset", idx, names)
        if changed:
            self.preset = names[new]
            self.model.apply_preset(new)
        im.set_item_tooltip("A correlation pair of the detector setup's FCS presets (step 1): fills the channels, "
                            "micro-time ranges and correlator settings.")
        self.item_rects["fcs_preset"] = im.get_item_rect()

    def _draw_filter_controls(self, section, model, state, width) -> None:
        if im.button("Load filters..."):
            self.dialogs.ask("Load lifetime filters", "open", LIFETIME_FILTER, lambda p: self.load_filters(p[0]))
        im.set_item_tooltip("Load lifetime (FLCS) filters from a Filter-Calculator JSON, or a .npy/.npz filter "
                            "matrix. Correlation then gives species auto-/cross-correlations; A/B pick species.")
        self.item_rects["load_filters"] = im.get_item_rect()
        used = _same_line_if_fits("Unload", im.calc_text_size("Load filters...")[0] + 2 * im.get_style().frame_padding[0])
        im.begin_disabled(not self.model.filter_mode)
        if im.button("Unload"):
            self.model.clear_lifetime_filter()
            self.filter_status = ""
        im.end_disabled()
        im.set_item_tooltip("Remove the lifetime filters and return to detector-channel correlation.")
        self.item_rects["unload_filters"] = im.get_item_rect()
        _same_line_if_fits("Filter Calc...", used)
        im.begin_disabled(self.open_tool is None)
        if im.button("Filter Calc..."):
            self.open_tool("filter_calc")
        im.end_disabled()
        im.set_item_tooltip("Open the fFCS Filter Calculator to compute lifetime filters from decay patterns.")
        self.item_rects["filter_calc"] = im.get_item_rect()
        if self.model.filter_mode:
            src = self.model._filter_source or "filters"
            im.text_wrapped(f"Species mode: {src} ({len(self.model._filter_labels or [])} species).")
        elif self.filter_status:
            im.text_wrapped(self.filter_status)

    def _draw_channel_combos(self, section, model, state, width) -> None:
        m = self.model
        species = m.filter_mode
        names = list(m._filter_labels or []) if species else sorted(m._channel_defs)
        for side in ("a", "b"):
            label = f"Species {side.upper()}:" if species else f"{side.upper()}:"
            if species:
                idx = int(getattr(m, f"_species_{side}", 0))
            else:
                idx = getattr(self, f"_combo_{side}", 0)
            idx = idx if 0 <= idx < len(names) else 0
            im.text(label)
            im.same_line()
            im.set_next_item_width(-1)
            changed, new = im.combo(f"##combo_{side}", idx, names or [""])
            if changed and names:
                if species:
                    setattr(m, f"_species_{side}", new)
                else:
                    setattr(self, f"_combo_{side}", new)
                    apply_channel_key(m, side, names[new])
            im.set_item_tooltip("The species (filter row) to correlate." if species else
                                "A logical channel of the detector setup: fills the routing channels and "
                                "micro-time ranges below.")
            self.item_rects[f"combo_{side}"] = im.get_item_rect()

    def _draw_correlate(self, section, model, state, width) -> None:
        if self.running:
            if im.button("Stop"):
                self.stop()
            im.set_item_tooltip("Stop after the current chunk (the chunks done are kept).")
            self.item_rects["stop"] = im.get_item_rect()
        else:
            im.push_style_color(im.Col.BUTTON, (31, 122, 31, 255))
            pressed = im.button("Correlate")
            im.pop_style_color(1)
            im.set_item_tooltip("Correlate the photons of the ticked files (or the filtered photons).")
            self.item_rects["correlate"] = im.get_item_rect()
            if pressed:
                self.on_used("correlate")
                self.correlate()
        im.same_line()
        im.text_wrapped(self.status)
        self.item_rects["correlate_status"] = im.get_item_rect()

    # docks
    def _draw_controls(self, box) -> None:
        self.form.rects.clear()
        draw_form(self.controls_spec, self.model, self.form)
        self.item_rects.update(self.form.rects)

    def _draw_plot(self, box) -> None:
        s = self.plot_section
        if implot.begin_plot("FCS Correlation##fcscorr", (-1, -1)):
            implot.setup_axes(s.get("x_label", ""), s.get("y_label", ""))
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            for i, c in enumerate(self.model.correlation_series()):
                implot.set_next_line_style(CURVES[i % len(CURVES)], 1.5)
                implot.plot_line(f"{c['name']}##{i}", np.asarray(c["x"], float), np.asarray(c["y"], float))
            implot.end_plot()
        im.set_item_tooltip(s.get("description", ""))
        self.item_rects["plot"] = tuple(box)

    def render(self) -> None:
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, w, h)
        im.begin_disabled(self.dialogs.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        self.dialogs.draw(frame)


def _walk(sections):
    for s in sections:
        yield s
        yield from _walk(s.get("sections", []))


__all__ = ["CorrelatorStepApp", "FilesStepApp", "FilterStepApp"]
