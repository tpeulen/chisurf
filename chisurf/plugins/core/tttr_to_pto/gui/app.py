"""Standalone EMTK drop tool for lossless vendor ⇄ PTO conversion."""

from __future__ import annotations

import json
from collections import deque
from copy import deepcopy
from pathlib import Path

from emtk import i18n, im
from emtk.app import ImApp
from emtk.docking import DockManager, Region

from chisurf.core.fio import staging
from chisurf.core.fio.pto import SIDECAR_ONLY_EXTENSIONS, Measurement, is_measurement
from chisurf.core.fio.pto import SUFFIX as PTO_SUFFIX
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.core.tttr_to_pto import api
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

_CONTEXT = "TttrToPtoNative"
_CATALOG = json.loads(Path(__file__).with_name("strings.json").read_text())
for _locale, _translations in _CATALOG.items():
    i18n.add_translations(_locale, _translations, context=_CONTEXT)


def tr(text):
    return i18n.tr(text, context=_CONTEXT)


class TttrToPtoApp(ImApp):
    """Serialize drops while publishing worker outcomes on the frame thread.

    No cancellation is offered during a write: closing leaves the current
    operation finishing safely and prevents later queued jobs from starting.
    A saved history is documentary and is never replayed on restore.
    """

    def __init__(self, converter=None, extractor=None):
        self.converter = converter or api.convert
        self.extractor = extractor or api.extract
        self.rows = []
        self.pending = deque()
        self.job = BackgroundJob()
        self.closed = False
        self.item_rects = {}
        self.help_locale = None
        self.help = None
        self.tour = None
        self.docks = DockManager(Region("conversion"))
        self.docks.add_window("conversion", "TTTR ⇄ .pto", self.draw_conversion, dock="conversion")
        self.refresh_help()
        super().__init__(gui=self.render, continuous=True)

    @staticmethod
    def accepts(path):
        path = Path(path)
        return path.is_file() and (
            path.suffix.lower() == PTO_SUFFIX
            or (path.suffix.lower() not in SIDECAR_ONLY_EXTENSIONS
                and (path.suffix.lower() in staging.VENDOR_EXTENSIONS or is_measurement(path)))
        )

    def add_paths(self, paths):
        """Unpack each container; pack all vendor files from one drop together."""
        if self.closed:
            return False
        vendors = []
        accepted = False
        for value in dict.fromkeys(str(Path(p).expanduser().resolve()) for p in paths):
            path = Path(value)
            if not self.accepts(path):
                self.rows.append({"paths": [value], "action": "reject", "status": "rejected",
                                  "outputs": [], "error": "Sidecars need their .spc file."
                                  if path.suffix.lower() in SIDECAR_ONLY_EXTENSIONS
                                  else "Choose existing vendor photon files or PTO containers."})
                continue
            accepted = True
            if path.suffix.lower() == PTO_SUFFIX or is_measurement(path):
                self.enqueue("unpack", [value])
            else:
                vendors.append(value)
        if vendors:
            self.enqueue("pack", sorted(vendors, key=lambda p: Path(p).name))
        self.start_next()
        return accepted

    on_paths_dropped = add_paths

    def enqueue(self, action, paths):
        row = {"paths": paths, "action": action, "status": "queued", "outputs": [], "error": ""}
        self.rows.append(row)
        self.pending.append(row)

    def start_next(self):
        if self.closed or self.job.running or not self.pending:
            return
        row = self.pending.popleft()
        row["status"] = "running"

        def work():
            if row["action"] == "pack":
                target = self.converter(row["paths"], keep_original=True)
                # The explicit tool verifies every write, even when keeping sources.
                with Measurement.open(target, writable=False) as check:
                    problems = check.verify()
                if problems:
                    raise ValueError("; ".join(problems))
                return [str(target)]
            return [str(p) for p in self.extractor(row["paths"][0])]

        def publish(outputs):
            row.update(status="verified", outputs=outputs)

        def error(exc):
            row.update(status="error", error=str(exc))

        self.job.start(work, publish, error)

    def poll(self):
        self.job.poll()
        self.start_next()

    def clear_history(self):
        self.rows[:] = [row for row in self.rows if row["status"] in {"queued", "running"}]

    def refresh_help(self):
        locale = i18n.get_locale()
        if locale == self.help_locale:
            return
        was_open = bool(self.help and self.help.open)
        self.help_locale = locale
        steps = [
            {"title": tr("The drop decides the direction"), "text": tr("Drop vendor photon files to pack one PTO, or drop a PTO to recover its original files and analysis results."), "target": "drop"},
            {"title": tr("Originals stay untouched"), "text": tr("Outputs are written beside the dropped files. Packing verifies the container; unpacking verifies the recovered instrument bytes. Originals are never deleted."), "target": "drop"},
            {"title": tr("One recording, one container"), "text": tr("Vendor files dropped together are packed into one PTO in filename order. The first filename names the container."), "target": "drop"},
            {"title": tr("Sidecars travel with their SPC"), "text": tr("A matching SET sidecar is embedded automatically with its SPC file. A SET file alone is rejected."), "target": "drop"},
        ]
        self.tour = EmTkGuidedTour(steps=steps, get_target_rect=self.item_rects.get)
        self.help = EmTkHelpWindow(
            title=tr("TTTR ⇄ PTO — Help"), text="\n\n".join(
                "## " + step["title"] + "\n" + step["text"] for step in steps
            ), on_start_guide=self.tour.start,
        )
        if was_open:
            self.help.show()

    def button(self, source, tip, callback):
        if im.button(tr(source)):
            callback()
        im.set_item_tooltip(tr(tip))
        self.item_rects[source] = im.get_item_rect()

    def draw_conversion(self, box):
        im.text_wrapped(tr("Drop vendor photon files to pack one PTO, or drop a PTO to recover its original files and analysis results."))
        im.text_disabled(tr("Originals stay untouched"))
        im.spacing()
        self.button("Guide", "Walk through packing, unpacking and sidecar handling.", self.tour.start)
        im.same_line()
        self.button("Help", "Read the conversion rules and verification guarantees.", self.help.show)
        im.same_line()
        self.button("Clear history", "Remove completed status rows; files on disk stay untouched.", self.clear_history)
        im.separator()
        im.text_colored(tr("Drop photon files or PTO containers here"), (0.45, 0.75, 1.0, 1.0))
        im.set_item_tooltip(tr("Drop multiple vendor files together to pack one measurement. Matching SET sidecars are included automatically."))
        self.item_rects["drop"] = im.get_item_rect()
        if self.job.running:
            im.text_colored(tr("Converting…"), (1.0, 0.8, 0.35, 1.0))
        if im.begin_child("conversion_history"):
            if not self.rows:
                im.text_disabled(tr("No conversions yet."))
            for index, row in enumerate(self.rows):
                names = ", ".join(Path(p).name for p in row["paths"])
                status = {"queued": "Queued", "running": "Converting…", "verified": "Verified", "error": "Failed", "rejected": "Rejected", "interrupted": "Not completed"}[row["status"]]
                colour = (0.45, 0.85, 0.55, 1.0) if row["status"] == "verified" else (1.0, 0.65, 0.4, 1.0) if row["status"] in {"error", "rejected"} else (0.8, 0.8, 0.8, 1.0)
                im.text_colored(tr(status) + " · " + names, colour)
                im.set_item_tooltip("\n".join(row["paths"]))
                if row["outputs"]:
                    im.text_wrapped("→ " + ", ".join(Path(p).name for p in row["outputs"]))
                    im.set_item_tooltip("\n".join(row["outputs"]))
                if row["error"]:
                    im.text_wrapped(tr(row["error"]))
                if index < len(self.rows) - 1:
                    im.separator()
        im.end_child()

    def render(self):
        self.poll()
        self.refresh_help()
        viewport = im.get_main_viewport()
        frame = (0.0, 0.0, *viewport.size)
        self.docks.draw(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.tour.active:
            self.tour.draw(*viewport.size)

    def export_state(self):
        return {"history": deepcopy(self.rows), "docks": self.docks.state()}

    def restore_state(self, state):
        if self.job.running:
            raise RuntimeError("Cannot restore conversion history while a write is active.")
        self.pending.clear()
        self.rows = deepcopy(state.get("history", []))
        for row in self.rows:
            if row.get("status") in {"queued", "running"}:
                row["status"] = "interrupted"
        self.docks.restore(state.get("docks"))

    def close(self):
        self.closed = True
        for row in self.pending:
            row["status"] = "interrupted"
        self.pending.clear()
        self.job.close()


def create_app():
    return TttrToPtoApp()
