"""The legacy-export window: one explicit way out of the ``.pto`` world.

Drop a container, see the plan (which run becomes which companion, what is
skipped), press Export. The ALEX-Suite CSVs are the second, optional part.
The workflow plugins themselves read and write ``.pto`` only -- this window is
where the old formats are reached.
"""

from __future__ import annotations

import pathlib
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.i18n import tr

from chisurf.plugins.emtk_layout import action_button

from .. import core

_FILTERS = [("Photon containers", ["*.pto"]), ("All files", ["*"])]
#: Room kept right of a text field or combo for its label.
_LABEL_ROOM = 130.0
_PARTS = ("meta", "hist_E", "hist_S", "hist_2D", "original_bursts")


class LegacyExportModel:
    """Qt-free state: the container, its plan, and what the last export wrote."""

    def __init__(self) -> None:
        self.filename: str = ""
        self.out_folder: str = ""
        self.plan: list[dict[str, Any]] = []
        self.status: str = ""
        self.written: list[str] = []
        #: ALEX part: the chosen run ("" = none) and the free-text meta fields.
        self.alex_run: str = ""
        self.sample: str = ""
        self.buffer: str = ""
        #: Which CSV parts to write; original_bursts needs the burst table.
        self.parts: set[str] = set(_PARTS[:4])

    # -- inputs ---------------------------------------------------------------- #
    def alex_runs(self) -> list[str]:
        """The runs the ALEX-Suite CSVs can be written from: those holding a burst table.

        The CSVs are histograms over a burst table, and ``<container>/<run>`` opens a
        run, not a table inside it -- so this lists run names (``container_run``),
        one per burst-table row of the plan, in plan order.
        """
        runs: list[str] = []
        for row in self.plan:
            run = row.get("container_run", "")
            if row["ending"] == "bur" and run and run not in runs:
                runs.append(run)
        return runs

    def set_file(self, path: str) -> None:
        self.filename = str(path)
        self.plan = core.export_plan(self.filename)
        runs = self.alex_runs()
        self.alex_run = runs[0] if runs else ""
        if not self.out_folder:
            self.out_folder = str(pathlib.Path(self.filename).parent)
        self.status = (
            tr("{} run(s); the endings above are what the export writes.").format(len(self.plan))
            if self.plan
            else tr("No analysis runs in this container -- nothing to export.")
        )
        self.written = []

    def load_example(self) -> str:
        """Open the plugin's demonstration container (written once, then cached)."""
        from .. import demo

        try:
            path = demo.make_demo()
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.status = tr("Could not write the example: {}").format(exc)
            return self.status
        self.out_folder = str(path.parent / "legacy")
        self.set_file(str(path))
        return self.status

    # -- actions ---------------------------------------------------------------- #
    def export_burst_folder(self, folder: str | None = None) -> str:
        if not self.filename:
            return tr("Open a .pto container first.")
        target = folder or self.out_folder
        if not target:
            return tr("Choose the output folder first.")
        self.out_folder = str(target)
        try:
            written = core.export_burst_folder(self.filename, target)
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.status = tr("Export failed: {}").format(exc)
            return self.status
        self.written = [str(p) for p in written]
        self.status = tr("Wrote {} file(s) into {}.").format(
            len(written), pathlib.Path(self.out_folder).name
        )
        return self.status

    def export_alex_csvs(self) -> str:
        if not self.filename or not self.alex_run:
            self.status = tr("Open a container with a burst-search run first.")
            return self.status
        stem = pathlib.Path(self.out_folder or pathlib.Path(self.filename).parent) / (
            pathlib.Path(self.filename).stem + "_alex"
        )
        try:
            written = core.export_alex_csvs(
                f"{self.filename}/{self.alex_run}",
                stem,
                sample=self.sample,
                buffer=self.buffer,
                parts=tuple(self.parts),
            )
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.status = tr("ALEX export failed: {}").format(exc)
            return self.status
        self.written = [str(p) for p in written]
        self.status = tr("Wrote {} ALEX-Suite CSV(s) beside {}.").format(
            len(written), stem.name
        )
        return self.status


def _labelled_width() -> None:
    """Size the next field so its label, drawn to its right, stays inside the window."""
    im.set_next_item_width(max(160.0, im.get_content_region_avail()[0] - _LABEL_ROOM))


class LegacyExportApp(ImApp):
    """The EMTK window over :class:`LegacyExportModel`."""

    def __init__(self, model: LegacyExportModel | None = None) -> None:
        self.model = model if model is not None else LegacyExportModel()
        #: Control rectangles by id: the tour's targets and the driver's click names.
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.dialog: FileDialog | None = None
        self.file_window = DialogWindow(
            "Legacy export — choose container", size=(640.0, 460.0), key="legacy-export-file"
        )
        from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

        here = pathlib.Path(__file__).resolve().parent
        self.help_window = EmTkHelpWindow(
            title="Legacy export — Help", resource=here / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=here / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        super().__init__(gui=self._render, continuous=False)

    # -- host hooks -------------------------------------------------------------- #
    def files_dropped(self, paths) -> bool:
        for p in paths or ():
            if str(p).lower().endswith(".pto"):
                self.model.set_file(str(p))
                return True
        return False

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    def choose_file(self) -> None:
        self.dialog = FileDialog(
            tr("Open photon container"), mode="open", multiselect=False, filters=_FILTERS
        )
        self.file_window.show()

    def load_example(self) -> None:
        """Open the demonstration container and tell the tour the button was used."""
        self.model.load_example()
        self.tour.notify_used("load_example")

    # -- drawing ------------------------------------------------------------------ #
    def _render(self) -> None:
        m = self.model
        im.text_wrapped(
            tr(
                "The dedicated way out: workflows read and write .pto only; the legacy "
                "burst folder and the ALEX-Suite CSVs are written from here."
            )
        )
        if action_button("guide"):
            self.tour.start()
        self.remember("guide")
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.remember("help")
        im.separator()
        im.text(m.filename or tr("no container"))
        if action_button("open", tooltip=tr("Choose a .pto container to export from.")):
            self.choose_file()
        self.remember("open")
        im.same_line()
        if action_button(
            "example",
            tooltip=tr("Open a demo container: 12 planted bursts, a burst search and a BVA run."),
        ):
            self.load_example()
        self.item_rects["load_example"] = im.get_item_rect()
        im.same_line()
        pressed = im.button(tr("Refresh") + "###refresh")
        im.set_item_tooltip(tr("Re-read the container from disk."))
        if pressed:
            if m.filename:
                m.set_file(m.filename)
        self.remember("refresh")
        im.spacing()

        if self.dialog is not None:
            close = self.file_window.begin((0, 58, 640, 460))
            selected = self.dialog.draw()
            self.file_window.end()
            if close or selected is False:
                self.dialog = None
            elif selected:
                self.dialog = None
                m.set_file(selected[0])

        if m.plan:
            # The tour points at the whole table: after end_table the "last item" is
            # only its last cell, so the frame is measured from the cursor instead.
            top_x, top_y = im.get_cursor_screen_pos()
            table_w = im.get_content_region_avail()[0]
            if im.begin_table("##plan", 4):
                im.table_setup_column(tr("Run"))
                im.table_setup_column(tr("Table"))
                im.table_setup_column(tr("Operation"))
                im.table_setup_column(tr("Companion"))
                im.table_headers_row()
                for row in m.plan:
                    im.table_next_row()
                    for value in (
                        row.get("container_run") or "—",
                        row["run"],
                        row["operation"],
                        row["ending"] or "—",
                    ):
                        im.table_next_column()
                        im.text(str(value))
                im.end_table()
            self.remember("plan", (top_x, top_y, table_w, im.get_cursor_screen_pos()[1] - top_y))
            im.text_disabled(
                tr("A dash means no registered companion: that analysis is skipped, never guessed.")
            )
            im.spacing()

        _labelled_width()
        _, m.out_folder = im.input_text_with_hint(
            tr("Output folder"), m.out_folder, str(pathlib.Path.home())
        )
        im.set_item_tooltip(tr("Where the burst folder and the CSVs are written."))
        self.remember("out_folder")
        pressed = im.button(tr("📤 Export burst folder"), role="primary")
        im.set_item_tooltip(tr("Unpack the container into the Seidel/Margarita burst folder (.bur/.bg4)."))
        if pressed:
            m.export_burst_folder()
            self.tour.notify_used("export")
        self.remember("export")
        im.spacing()
        im.separator()

        im.text_wrapped(tr("ALEX-Suite CSVs (optional)"))
        runs = m.alex_runs()
        if runs:
            current = m.alex_run if m.alex_run in runs else runs[0]
            _labelled_width()
            changed, value = im.combo(tr("Run") + "###alex_run", runs.index(current), runs)
            im.set_item_tooltip(tr("The burst-search run whose bursts the CSVs histogram."))
            if changed:
                m.alex_run = runs[int(value)]
            self.remember("alex_run")
            _labelled_width()
            _, m.sample = im.input_text_with_hint(tr("Sample"), m.sample, tr("free text"))
            im.set_item_tooltip(tr("Sample description written into the _meta file."))
            self.remember("sample")
            _labelled_width()
            _, m.buffer = im.input_text_with_hint(tr("Buffer"), m.buffer, tr("free text"))
            im.set_item_tooltip(tr("Buffer description written into the _meta file."))
            self.remember("buffer")
            for part in _PARTS:
                _, on = im.checkbox(tr(part) + f"###part_{part}", part in m.parts)
                im.set_item_tooltip(tr("Include this table in the export."))
                if on:
                    m.parts.add(part)
                else:
                    m.parts.discard(part)
                self.remember(f"part_{part}")
            pressed = im.button(tr("Write ALEX-Suite CSVs") + "###write_alex")
            im.set_item_tooltip(tr("Write the ALEX-Suite CSV tables of the selected run."))
            if pressed:
                m.export_alex_csvs()
                self.tour.notify_used("write_alex")
            self.remember("write_alex")
        else:
            im.text_disabled(
                tr("Open a container with a burst-search run to write the ALEX CSVs.")
            )

        if m.status:
            im.spacing()
            im.separator()
            im.text_wrapped(m.status)
            for path in m.written[-8:]:
                im.text_disabled(path)

        vp = im.get_main_viewport()
        self.help_window.draw((*vp.pos, *vp.size))
        self.tour.draw(*vp.size)


def make_app() -> LegacyExportApp:
    return LegacyExportApp()


__all__ = ["LegacyExportApp", "LegacyExportModel", "make_app"]
