"""EMTK app for the MFD preparation plugin.

One window: pick a burst run of the workspace in the Input section, prepare it, read what was found as three tables
(detectors, photon sources, summary) and the report text. The spec ``mfd_prepare.view.json`` is drawn by
``emtk.view_form``; the state and the numbers are in :class:`~.model.MfdPrepareModel` (Qt-free). The Qt tool in ``tool.py``
only hosts this app.
"""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.view_form import FormState, draw_form

from chisurf.core.plugin.workspace_input import (
    WorkspaceInputMixin,
    input_section,
    read_address,
    spec_for,
)
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import (
    action_caption,
    action_tooltip,
    button_row,
    layout_spec,
    window_size,
)

from .model import MfdPrepareModel

HERE = Path(__file__).parent
SPEC = json.loads((HERE / "mfd_prepare.view.json").read_text(encoding="utf-8"))
#: Widest the window's content is drawn: the tables and the report stay readable on a wide screen.
MAX_WIDTH = 980.0
REPORT_HINT = (
    "Pick a burst run in the Input section and press Prepare to see the MFD preparation report."
)


class _Input(WorkspaceInputMixin):
    """The Input section's model: the workspace's burst runs, a pick handed to :func:`receive_bursts`."""

    workspace_input_plugin = "mfd_prepare"


def _input_spec() -> dict:
    """The generated Input section of the manifest's ``accepts[].from_workspace``."""
    found = spec_for(json.loads((HERE.parent / "manifest.json").read_text(encoding="utf-8")))
    if not found:
        return {"sections": []}
    section = input_section(found[1])
    # A few rows (the table scrolls): the result tables and the report below must stay on screen.
    for part in section.get("sections", []):
        if (part.get("options") or {}).get("source") == "workspace_input_rows":
            part["options"]["height"] = 72
    return {"sections": [section]}


class MfdPreparePanel:
    """What the spec reads (fields, rows) and calls (actions); a thin layer over the model and the app."""

    def __init__(self, app: MfdPrepareApp) -> None:
        self.app = app

    @property
    def m(self) -> MfdPrepareModel:
        return self.app.model

    # fields
    @property
    def folder_line(self) -> str:
        return ("Burst run:  " + self.m.folder) if self.m.folder else "No burst run picked"

    @property
    def status_line(self) -> str:
        if self.app.job.busy:
            return self.app.job.progress or "Preparing..."
        return self.m.status_text

    @property
    def has_result(self) -> bool:
        return bool(self.m.result)

    # tables
    def detector_columns(self):
        return [
            {
                "key": "detector",
                "label": "Detector",
                "width": 90,
                "editable": False,
                "description": "Detector name from the burst table's Number of Photons columns.",
            },
            {
                "key": "channels",
                "label": "Channels",
                "width": 90,
                "editable": False,
                "description": "Routing channels that define the detector (from the manifest, or inferred from the photons).",
            },
            {
                "key": "window",
                "label": "Micro-time window",
                "width": 140,
                "editable": False,
                "description": "Micro-time window of the detector in channels; an acceptor-excitation detector is a window on the acceptor channels.",
            },
            {
                "key": "empty",
                "label": "Bursts without photons",
                "width": 170,
                "editable": False,
                "description": "Bursts in which this detector registered no photon.",
            },
            {
                "key": "agreement",
                "label": "Count agreement",
                "width": 130,
                "format": "%.4f",
                "editable": False,
                "description": "Fraction of bursts whose count, recomputed from the photons, equals the burst table's column.",
            },
            {
                "key": "verdict",
                "label": "Verdict",
                "editable": False,
                "description": "ok needs a count agreement of 0.98; an UNVERIFIED detector would put photons under the wrong colour and the MFD fit refuses it.",
            },
        ]

    def detector_rows(self):
        return self.m.detector_rows()

    def source_columns(self):
        return [
            {
                "key": "file",
                "label": "File",
                "width": 110,
                "editable": False,
                "description": "Photon file named by the burst table.",
            },
            {
                "key": "path",
                "label": "Resolved path",
                "editable": False,
                "description": "Where the file was found.",
            },
            {
                "key": "origin",
                "label": "Found by",
                "width": 100,
                "editable": False,
                "description": "manifest, legacy .mti sidecar, or a file beside the folder.",
            },
            {
                "key": "photons",
                "label": "Photons",
                "width": 90,
                "editable": False,
                "description": "Photons read from the file.",
            },
        ]

    def source_rows(self):
        return self.m.source_rows()

    def summary_columns(self):
        return [
            {
                "key": "quantity",
                "label": "Quantity",
                "width": 190,
                "editable": False,
                "description": "What the report states about the folder as a whole.",
            },
            {"key": "value", "label": "Value", "editable": False, "description": "Its value."},
        ]

    def summary_rows(self):
        return self.m.summary_rows()

    # actions
    def enabled(self, name: str) -> bool:
        if name in ("guide", "help"):
            return True
        if self.app.job.busy:
            return False
        if name == "prepare":
            return bool(self.m.folder)
        return True

    def prepare(self):
        self.app.start_prepare()

    def guide(self):
        self.app.tour.start()

    def help(self):
        self.app.help_window.show()


class MfdPrepareApp(TourTarget, ImApp):
    """The window."""

    tour: EmTkGuidedTour

    def __init__(self, model: MfdPrepareModel | None = None) -> None:
        self.window_size = window_size(SPEC, (1100, 720))
        self.model = model or MfdPrepareModel()
        self.job = SnapshotJob(self.model)
        self.panel = MfdPreparePanel(self)
        self.spec = layout_spec(json.loads(json.dumps(SPEC)))
        self.form_state = FormState(on_used=lambda name: self.tour.notify_used(name))
        self.item_rects: dict = {}
        #: The Input section: which burst run of the workspace is prepared.
        self.input = _Input()
        self.input.workspace_input_app = self  # a pick goes to receive_bursts(self, ...)
        self.input.workspace_input_on_used = lambda name: self.tour.notify_used(name)
        self.input_spec = _input_spec()
        self.input_form = FormState(on_used=lambda name: self.tour.notify_used(name))
        self.help_window = EmTkHelpWindow(
            title="MFD Prepare - Help & Reference",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=lambda: self.tour.start(),
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        super().__init__(self._render, continuous=False)

    # -- actions -------------------------------------------------------------------------------------- #
    def start_prepare(self) -> None:
        if not self.model.folder:
            self.model.prepare()  # "Select a folder first." (the button is greyed, this is for scripts)
            return
        self.job.start("prepare")

    # -- drawing --
    def draw_toolbar(self, width: float) -> None:
        """The Input section (the workspace's burst runs), the run picked, and one wrapping row of
        buttons (natural widths, greyed while they cannot act)."""
        self.input_form.rects.clear()
        im.begin_disabled(self.job.busy)
        draw_form(self.input_spec, self.input, self.input_form)
        im.end_disabled()
        self.item_rects.update(self.input_form.rects)
        im.text_wrapped(self.panel.folder_line)
        busy = self.job.busy
        pressed = button_row(
            [
                {
                    "label": "Prepare",
                    "key": "prepare",
                    "enabled": bool(self.model.folder) and not busy,
                    "colours": ((46, 160, 67, 255), (56, 180, 77, 255), (36, 140, 57, 255)),
                    "tip": "Read the folder the way the MFD fit does: resolve the photon files, detect the photon-index convention and "
                    "recompute each detector's counts. Nothing is moved or rewritten. Pick a burst run first.",
                },
                {"label": action_caption("guide"), "key": "guide", "tip": action_tooltip("guide")},
                {"label": action_caption("help"), "key": "help", "tip": action_tooltip("help")},
            ],
            remember=self.remember,
        )
        if pressed:
            self.tour.notify_used(pressed)
            getattr(self.panel, pressed)()

    def draw_report(self) -> None:
        """The report text in a scrolling region that takes the room left (the mouse wheel scrolls it)."""
        im.text_unformatted("Report")
        avail = im.get_content_region_avail()
        box_h = max(avail[1] - 4.0, 1.0)
        x, y = im.get_cursor_screen_pos()
        im.begin_child("##mfd_report", (0.0, box_h))
        for line in (self.model.report or REPORT_HINT).splitlines():
            im.text_wrapped(line) if line else im.spacing()
        im.end_child()
        self.item_rects["report"] = (float(x), float(y), float(avail[0]), float(box_h))

    def _render(self) -> None:
        self.job.poll()
        vp = im.get_main_viewport()
        width, height = float(vp.size[0]), float(vp.size[1])
        im.set_next_window_pos((0.0, 0.0), im.Cond.ALWAYS)
        im.set_next_window_size((width, height), im.Cond.ALWAYS)
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE
        if im.begin("##mfd_prepare", (0.0, 0.0, width, height), flags):
            self.form_state.rects.clear()
            self.draw_toolbar(width)
            draw_form(self.spec, self.panel, self.form_state, titles=True)
            self.item_rects.update(self.form_state.rects)
            self.draw_report()
        im.end()
        frame = (0.0, 0.0, width, height)
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            # The card is a bounded window of its own, so it takes its own presses and the highlighted control stays
            # clickable; a full-frame overlay would sit on top of the card once a step stops awaiting.
            self.tour.draw(width, height)
        if self.job.busy:
            self.request_frame()  # poll the job again

    def close(self) -> None:
        pass


def make_app(**kwargs) -> MfdPrepareApp:
    from chisurf.emtk.i18n import install

    install()
    return MfdPrepareApp(**kwargs)


def receive_bursts(app: MfdPrepareApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``bursts``): prepare the burst run ``payload["folder"]``.

    ``folder`` is an address -- a run of a measurement container (``m000.pto/<run>``) -- as the
    Input section, *Open in…* or a drag from the Datasets view hands it.
    """
    address = read_address(str(payload["folder"]))
    if not app.model.set_folder(address):
        raise ValueError(f"{address} is not a burst run")
    app.request_frame()


__all__ = ["MfdPrepareApp", "MfdPreparePanel", "make_app", "receive_bursts"]
