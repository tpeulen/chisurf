"""The smFRET page: sticky, docked windows in a simple and an advanced mode.

``make_app()`` is the factory every emtk host mounts::

    python -m emtk.native --app smfretweb.app.frame:make_app    # desktop
    python -m smfretweb.app.web                                 # browser tab

Layout (emtk's :class:`~emtk.docking.DockManager`, the docking chimol and ndX
use): a column on the left for the measurement and its settings, the results
in the middle as tabs. Windows can be dragged out, snapped together and
docked back; in one region they are tabs.

* **Simple** -- Measurement | Quality, E / S, Bursts.
* **Advanced** -- adds Channels (with the micro-time histograms), Burst
  search and Corrections on the left, and Time trace and ndX (the burst
  table, hosted as a child app: :mod:`.ndx_view`) in the middle.

Help (``help.md``) and the guided tour (``guide.json``) are emtk's help
window and tour (:mod:`emtk.help_guide`).
"""
from __future__ import annotations

import json
import pathlib

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form, find_section

from . import plots
from .ndx_view import NdxView
from .session import Session

__all__ = ["SmFretApp", "make_app", "WINDOWS"]

HERE = pathlib.Path(__file__).parent
VIEW = json.loads((HERE / "view.json").read_text(encoding="utf-8"))

#: ``key: (title, region, modes)`` -- what each mode shows.
WINDOWS = {
    "measurement": ("Measurement", "left", ("simple", "advanced")),
    "channels": ("Channels", "left", ("advanced",)),
    "search": ("Burst search", "left", ("advanced",)),
    "corrections": ("Corrections", "left", ("advanced",)),
    "quality": ("Quality", "main", ("simple", "advanced")),
    "es": ("E / S", "main", ("simple", "advanced")),
    "bursts": ("Bursts", "main", ("simple", "advanced")),
    "trace": ("Time trace", "main", ("advanced",)),
    "ndx": ("ndX", "main", ("advanced",)),
}
#: The view.json panel each settings window draws.
PANELS = {"measurement": "Measurement", "channels": "Channels", "search": "Burst search",
          "corrections": "Corrections", "trace": "Time trace"}

WELCOME = (
    "Confocal single-molecule FRET, analysed entirely in your browser.\n\n"
    "Your data stays on this computer: the file is read and processed here, by tttrlib compiled "
    "to WebAssembly. Nothing is uploaded, and no data ends up on any server.\n\n"
    "Drop a TTTR file on the window (PicoQuant PTU/HT3/T3R, Becker & Hickl SPC, SM, PTO, ...), "
    "or simulate an example under Measurement > Try it without a file. The experiment -- cw, PIE "
    "or µsALEX, which detector is donor or acceptor, polarization -- is detected from the photons.\n\n"
    "New here? Press Guide.")


def _help_guide():
    try:
        from emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - an older emtk without it
        return None, None
    return EmTkHelpWindow, EmTkGuidedTour


class SmFretApp(ImApp):
    def __init__(self, runner: str | None = None) -> None:
        super().__init__(self._gui)
        self.session = Session(runner=runner)
        s = self.session
        s.download = self._download
        s.on_help = self.show_help
        s.on_guide = self.start_guide
        self.forms = {key: FormState() for key in PANELS}
        self.forms["channels"].custom["micro_histograms"] = lambda sec, m, st, w: plots.draw_micro(m, w)
        self.forms["trace"].custom["trace_plot"] = lambda sec, m, st, w: plots.draw_trace(m, w)
        self.item_rects: dict = {}
        self._painter = None
        self._plots: plots.Plots | None = None
        self._plots_version = -1
        self._pending = None
        self._pending_frames = 0
        self._mode = None
        self._outcome = (None, None)
        self.ndx = NdxView(self.request_frame)
        self._ndx_drawn = False
        root = Split("h", 0.27, Region("left"), Region("main"), min_size=220.0)
        self.docks = DockManager(root)
        for key, (title, region, _modes) in WINDOWS.items():
            self.docks.add_window(key, title, self._drawer(key), dock=region, closable=False)
        help_cls, tour_cls = _help_guide()
        self.help = help_cls(title="smFRET help", resource=HERE / "help.md",
                             on_start_guide=self.start_guide) if help_cls else None
        self.tour = tour_cls(HERE / "guide.json", get_target_rect=self._target_rect,
                             on_step_change=self._tour_step, wait_for_controls=True) if tour_cls else None
        for form in self.forms.values():
            form.on_used = self._used
        self._apply_mode()
        if self.session.runner == "jobs":
            # In a page: boot the compute worker now, while the user picks a
            # file, so the first analysis does not wait for it.
            try:
                from emtk import jobs as emtk_jobs  # noqa: PLC0415

                if hasattr(emtk_jobs, "configure"):
                    # The analysis needs numpy and tttrlib only, not ndX's scipy
                    # and matplotlib: a lighter worker boots sooner.
                    emtk_jobs.configure(packages=["numpy"])
                emtk_jobs.warm()
            except Exception:  # noqa: BLE001 - the first job starts it anyway
                pass

    # -- modes ---------------------------------------------------------------- #
    def _apply_mode(self) -> None:
        mode = self.session.mode
        if mode == self._mode:
            return
        for key, (_t, _r, modes) in WINDOWS.items():
            (self.docks.show if mode in modes else self.docks.hide)(key)
        self._mode = mode
        self.docks.focus("quality")
        self.docks.focus("measurement")

    # -- help and guide ------------------------------------------------------- #
    def show_help(self) -> None:
        if self.help is not None:
            self.help.show()
        else:
            self.session.status = "Help needs emtk.help_guide (emtk too old)."

    def start_guide(self) -> None:
        if self.tour is not None:
            if self.help is not None:
                self.help.hide()
            self.tour.start()
        else:
            self.session.status = "The guide needs emtk.help_guide (emtk too old)."

    def _used(self, name: str) -> None:
        if self.tour is not None:
            self.tour.notify_used(name)

    def _tour_step(self, index: int, step: dict) -> None:
        """A step can ask for a mode and a window in front."""
        if step.get("mode") and self.session.mode != step["mode"]:
            self.session.mode = step["mode"]
            self._apply_mode()
        if step.get("window") in self.docks.windows:
            self.docks.focus(step["window"])

    def _target_rect(self, name: str):
        for form in self.forms.values():
            if name in form.rects:
                return form.rects[name]
        if name in self.item_rects:
            return self.item_rects[name]
        win = self.docks.windows.get(name)
        return getattr(win, "frame", None) if win is not None else None

    def _tour_outcomes(self) -> None:
        """The tour waits for outcomes, not button presses: data loaded, analysed."""
        s = self.session
        now = (s.path, s.version if s.bursts is not None else None)
        for key, before, current in zip(("data_loaded", "analysed"), self._outcome, now):
            if current is not None and current != before:
                self._used(key)
        self._outcome = now
        # The outcome steps point at the window that shows it.
        self.item_rects["data_loaded"] = getattr(self.docks.windows["measurement"], "frame", None)
        self.item_rects["analysed"] = getattr(self.docks.windows["quality"], "frame", None)

    # -- host hooks ----------------------------------------------------------- #
    def draw(self, painter, x, y, w, h) -> None:
        self._painter = painter
        busy = self.session.poll()      # the analysis runs as a job: take its results in
        try:
            super().draw(painter, x, y, w, h)
        finally:
            self._painter = None
        if busy:
            self.request_frame()        # keep the progress moving
        if self._pending is not None:
            # Show "loading" for one frame, then do the work.
            self._pending_frames += 1
            if self._pending_frames >= 2:
                job, self._pending = self._pending, None
                try:
                    job()
                except Exception as exc:  # noqa: BLE001 - shown in the panel
                    self.session.status = f"Could not load: {exc}"
            self.request_frame()

    def files_dropped(self, paths) -> bool:
        paths = [str(p) for p in paths or ()]
        if not paths:
            return False
        if self._ndx_drawn and self.ndx.focus:
            return bool(self.ndx.app.files_dropped(paths))
        self.open(paths[0])
        return True

    on_files_dropped = files_dropped

    def open(self, path: str) -> None:
        if self.session.runner == "sync":
            # Inline: show "loading" for a frame before the work blocks.
            self._later(f"Loading {pathlib.Path(path).name} ...", lambda: self.session.open(path))
        else:
            self.session.open(path)
            self.request_frame()

    def _later(self, status: str, job) -> None:
        self._pending = job
        self._pending_frames = 0
        self.session.status = status
        self.request_frame()

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        if self._ndx_drawn:
            self.ndx.pointer_press(x, y, button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self._ndx_drawn:
            self.ndx.pointer_release(x, y, button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self._ndx_drawn:
            self.ndx.pointer_move(x, y, buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        if self._ndx_drawn and self.ndx.wheel(x, y, steps, modifiers):
            return
        super().wheel(x, y, steps, modifiers)

    def key(self, key, text="", modifiers=0):
        if self._ndx_drawn and self.ndx.key(key, text, modifiers):
            return True
        return super().key(key, text, modifiers)

    def animating(self) -> bool:
        return super().animating() or self.ndx.animating() or self.session.busy

    def _download(self, name: str, data: bytes, mime: str) -> None:
        from emtk.web.page import download, in_browser  # noqa: PLC0415

        if in_browser():
            download(name, data, mime)
            self.session.status = f"Downloaded {name}"
        else:
            out = pathlib.Path.home() / "Downloads" / name
            out.write_bytes(data)
            self.session.status = f"Saved {out}"

    # -- the frame ------------------------------------------------------------ #
    def _gui(self) -> None:
        s = self.session
        self._apply_mode()
        if s.bursts is not None and s.qc is not None and self._plots_version != s.version:
            self._plots = plots.Plots(s)
            self._plots_version = s.version
        self._ndx_drawn = False
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        for form in self.forms.values():
            form.rects.clear()
        self.docks.draw(box)
        self._tour_outcomes()
        if self.help is not None:
            self.help.draw(box)
        if self.tour is not None:
            self.tour.draw(*vp.size)

    def _drawer(self, key: str):
        def draw(win_box) -> None:
            if key in PANELS:
                if key == "measurement" and self._plots is None and self._pending is None:
                    im.text_wrapped(WELCOME)
                    im.separator()
                draw_form(find_section(VIEW, PANELS[key]), self.session, self.forms[key], titles=False)
                return
            if self._plots is None:
                plots.empty("Open a file or simulate an example (Measurement window) to see results here.")
                return
            if key == "quality":
                plots.draw_quality(self.session, self._plots)
            elif key == "es":
                plots.draw_es(self.session, self._plots)
            elif key == "bursts":
                plots.draw_bursts(self.session, self._plots)
            elif key == "ndx":
                self._draw_ndx(win_box)
        return draw

    def _draw_ndx(self, win_box) -> None:
        s = self.session
        if not self.ndx.ensure():
            plots.empty(self.ndx.error or "ndX is not available here.")
            return
        self.ndx.show(s.table(), (s.version, s.drop_flagged))
        x, y = im.get_cursor_screen_pos()
        w, h = im.get_content_region_avail()
        self.ndx.draw(self, self._painter, (x, y, max(w, 1.0), max(h, 1.0)))
        im.dummy(max(w, 1.0), max(h, 1.0))
        self._ndx_drawn = True


def make_app(path: str | None = None, runner: str | None = None) -> SmFretApp:
    """The app; ``runner="sync"`` runs the analysis inline (tests, scripts)."""
    app = SmFretApp(runner=runner)
    if path:
        app.open(path)
    return app
