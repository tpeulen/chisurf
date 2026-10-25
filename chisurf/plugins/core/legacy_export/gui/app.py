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
    def set_file(self, path: str) -> None:
        self.filename = str(path)
        self.plan = core.export_plan(self.filename)
        self.alex_run = ""
        runs = [r["run"] for r in self.plan if r["operation"] == "burst_search"]
        if not runs and self.plan:
            runs = [self.plan[0]["run"]]
        if runs:
            self.alex_run = runs[0]
        if not self.out_folder:
            self.out_folder = str(pathlib.Path(self.filename).parent)
        self.status = (
            tr("{} run(s); the endings above are what the export writes.").format(len(self.plan))
            if self.plan
            else tr("No analysis runs in this container -- nothing to export.")
        )
        self.written = []

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
            return tr("Open a container and pick a run first.")
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


class LegacyExportApp(ImApp):
    """The EMTK window over :class:`LegacyExportModel`."""

    def __init__(self, model: LegacyExportModel | None = None) -> None:
        self.model = model if model is not None else LegacyExportModel()
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
            get_target_rect=lambda key: None,
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

    # -- drawing ------------------------------------------------------------------ #
    def _render(self) -> None:
        m = self.model
        im.text_wrapped(
            tr(
                "The dedicated way out: workflows read and write .pto only; the legacy "
                "burst folder and the ALEX-Suite CSVs are written from here."
            )
        )
        im.separator()
        im.text(m.filename or tr("no container"))
        im.same_line()
        if action_button("open", tooltip=tr("Choose a .pto container to export from.")):
            self.choose_file()
        im.same_line()
        pressed = im.button(tr("Refresh"))
        im.set_item_tooltip(tr("Re-read the container from disk."))
        if pressed:
            if m.filename:
                m.set_file(m.filename)
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
            if im.begin_table("##plan", 3):
                im.table_setup_column(tr("Run"))
                im.table_setup_column(tr("Operation"))
                im.table_setup_column(tr("Companion"))
                im.table_headers_row()
                for row in m.plan:
                    im.table_next_row()
                    for value in (row["run"], row["operation"], row["ending"] or "—"):
                        im.table_next_column()
                        im.text(str(value))
                im.end_table()
            im.text_disabled(
                tr("A dash means no registered companion: that analysis is skipped, never guessed.")
            )
            im.spacing()

        _, m.out_folder = im.input_text_with_hint(
            tr("Output folder"), m.out_folder, str(pathlib.Path.home())
        )
        pressed = im.button(tr("📤 Export burst folder"), role="primary")
        im.set_item_tooltip(tr("Unpack the container into the Seidel/Margarita burst folder (.bur/.bg4)."))
        if pressed:
            m.export_burst_folder()
        im.spacing()
        im.separator()

        im.text_wrapped(tr("ALEX-Suite CSVs (optional)"))
        runs = [r["run"] for r in m.plan]
        if runs:
            current = m.alex_run if m.alex_run in runs else runs[0]
            changed, value = im.combo(tr("Run"), runs.index(current) if current in runs else 0, runs)
            im.set_item_tooltip(tr("Which run's CSVs to write."))
            if changed:
                m.alex_run = runs[int(value)]
            _, m.sample = im.input_text_with_hint(tr("Sample"), m.sample, tr("free text"))
            _, m.buffer = im.input_text_with_hint(tr("Buffer"), m.buffer, tr("free text"))
            for part in _PARTS:
                _, on = im.checkbox(tr(part), part in m.parts)
                im.set_item_tooltip(tr("Include this table in the export."))
                if on:
                    m.parts.add(part)
                else:
                    m.parts.discard(part)
            pressed = im.button(tr("Write ALEX-Suite CSVs"))
            im.set_item_tooltip(tr("Write the ALEX-Suite CSV tables of the selected run."))
            if pressed:
                m.export_alex_csvs()
        else:
            im.text_disabled(tr("Open a container with runs to write the ALEX CSVs."))

        vp = im.get_main_viewport()
        self.help_window.draw((*vp.pos, *vp.size))
        self.tour.draw(*vp.size)

        if m.status:
            im.spacing()
            im.separator()
            im.text_wrapped(m.status)
            for path in m.written[-8:]:
                im.text_disabled(path)


def make_app() -> LegacyExportApp:
    return LegacyExportApp()


__all__ = ["LegacyExportApp", "LegacyExportModel", "make_app"]
