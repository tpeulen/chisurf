"""Native Batch Analysis wizard: the five steps of the Qt wizard in one window, without Qt.

Left window: the step list (a check mark for a completed step) with Back / Next / Finish and Help / Guide. Right window:
the header of the current step and its page. Every page is a panel of the view spec ``batch_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections`; the three tables (loaded datasets, files, results) are ``data_table`` sections. Only
what a spec cannot draw is drawn here: the Markdown texts, the coloured outcome line and the in-app choosers (files,
folder, results CSV, the dataset picker of the database). All state is in :class:`~.model.BatchModel`; the numbers are the
Qt wizard's, from :mod:`..core.runner`. Nothing here imports Qt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import button_row
from chisurf.plugins.emtk_wizard import draw_steps

from .model import BatchModel
from .strings import install_translations, tr

install_translations()

HERE = Path(__file__).parent
#: Colours that carry the outcome of a run (green: it worked, red: it did not).
_OK, _FAILED = (0.18, 0.62, 0.22, 1.0), (0.85, 0.2, 0.2, 1.0)
_CSV = [("CSV files (*.csv)", ["*.csv"]), ("All files (*)", ["*"])]


class BatchAnalysisApp(ImApp):
    """Apply one template fit to many datasets or files and write the results.

    Parameters
    ----------
    model : BatchModel, optional
        The wizard's state (default: one over the process-global ChiSurf session).
    """

    window_title = "Batch Analysis"

    def __init__(self, model: BatchModel | None = None) -> None:
        self.model = model or BatchModel()
        spec = json.loads((HERE / "batch_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["markdown"] = self._draw_markdown
        self.form.custom["notice"] = self._draw_notice
        self.form.custom["run_message"] = self._draw_run_message
        self.form.custom["actions"] = self._draw_actions
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self.dialog_kind = ""
        self.picker = DatasetPicker(on_paths=self._picked)
        self._dialog_window = DialogWindow("File", size=(640.0, 460.0), key="batch_file")
        self._closing = False
        #: Where the file dialogs open next: the folder of the last file added.
        self.last_folder = ""
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
            on_step_change=self._tour_step,
        )
        self.help_window = EmTkHelpWindow(title="Batch analysis - help", resource=HERE / "help.md", owner=self,
                                          on_start_guide=self.tour.start)
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(Split("h", 0.22, Region("steps"), Region("page"), min_size=165.0))
        self.docks.add_window("steps", tr("Steps"), self.draw_steps, dock="steps", closable=False)
        self.docks.add_window("page", tr("Batch Analysis"), self.draw_page, dock="page", closable=False)
        super().__init__(self.render)

    # -- one frame ---------------------------------------------------------------------------------- #
    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (float(vp.pos[0]), float(vp.pos[1]), float(vp.size[0]), float(vp.size[1]))
        self.model.poll()
        self.model.refresh_completion()  # a fit chosen in the list or a run that finished moves the marks
        self.form.rects.clear()
        self.docks.draw(box)
        self._sync_tables()
        self._open_requested_dialog()
        self._draw_dialog(box)
        if self.picker.is_open:
            self.picker.render(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)
        if self.model.finished and not self._closing:
            self._closing = True
            self.request_close()

    def _sync_tables(self) -> None:
        """Keep the file table's selection equal to the model's (a removal or a clear moves it); name the headers."""
        for table, name in (("dataset_rows", "dataset_header"), ("result_rows", "result_header")):
            bound = self.form.tables.get(table)
            box = getattr(getattr(bound, "control", None), "_header_box", None) if bound is not None else None
            if box and table in self.form.rects:
                self.item_rects[name] = tuple(box)
            else:
                self.item_rects.pop(name, None)
        binding = self.form.tables.get("file_rows")
        if binding is None:
            return
        control = binding.control
        wanted = self.model.selected_file or None
        if control.selected_key != wanted:
            if wanted is None:
                control.selected_key = None
                control.also_selected = set()
            else:
                control.select_key(wanted)

    # -- windows ------------------------------------------------------------------------------------ #
    def draw_steps(self, box: Any = None) -> None:
        """The navigation list, the Back / Next / Finish bar and Help / Guide."""
        draw_steps(self.model, self.item_rects, on_pick=self._picked_step)
        im.separator()
        draw_sections(self.panels["navigation"]["sections"], self.model, self.form, titles=False)
        if im.button(tr("Help")):
            self.help_window.show()
        im.set_item_tooltip(tr("Explain the steps of the batch analysis."))
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button(tr("Guide")):
            self.tour.start()
        im.set_item_tooltip(tr("Walk through a batch step by step."))
        self.item_rects["guide"] = im.get_item_rect()

    def _picked_step(self, index: int) -> None:
        """A click on the step list: a tour waiting for it goes on."""
        self.tour.notify_used("nav_list")
        self.tour.notify_used(f"step_{self.model.STEPS[index].id}")

    def _tour_step(self, _index: int, step: dict) -> None:
        """The tour reached a card: open the page that holds the control it points at."""
        page = step.get("page")
        ids = [s.id for s in self.model.STEPS]
        if page in ids:
            self.model.go_to(ids.index(page))

    def draw_page(self, box: Any = None) -> None:
        """The header of the current step and its page."""
        im.text(self.model.title)
        im.begin_disabled(True)
        im.text_wrapped(self.model.subtitle)
        im.end_disabled()
        im.separator()
        draw_sections(self.panels[self.model.step_id]["sections"], self.model, self.form, titles=False)

    # -- custom sections ---------------------------------------------------------------------------- #
    def _draw_markdown(self, section: dict, model: Any, state: FormState, width: float) -> None:
        im.markdown(getattr(model, (section.get("options") or {}).get("source", ""))())

    def _draw_notice(self, section: dict, model: Any, state: FormState, width: float) -> None:
        text = getattr(model, (section.get("options") or {}).get("source", ""))()
        if text:
            im.text_wrapped(text)

    def _draw_actions(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """A row of actions at their natural width (the spec's own button rows stretch to the window)."""
        buttons = [{"label": b["label"], "key": b["action"], "tip": b.get("description", ""),
                    "enabled": model.enabled(b["action"])} for b in (section.get("options") or {}).get("buttons", [])]
        pressed = button_row(buttons, width, remember=lambda name: state.rects.__setitem__(name, im.get_item_rect()))
        if pressed:
            state.used(pressed)
            getattr(model, pressed)()

    def _draw_run_message(self, section: dict, model: Any, state: FormState, width: float) -> None:
        if model.message:
            im.text_colored(_OK if model.message_ok else _FAILED, model.message)
        elif model.step_id == "results" and model._results is None:
            im.text_wrapped(model.results_text)
        for line in model.outputs:
            im.text_wrapped(line)

    # -- choosers ----------------------------------------------------------------------------------- #
    def _open_requested_dialog(self) -> None:
        """Turn the model's ``dialog_request`` into a file dialog or the database picker."""
        kind, self.model.dialog_request = self.model.dialog_request, ""
        if not kind or self.dialog is not None or self.picker.is_open:
            return
        if kind == "database":
            self.picker.open()
            return
        self.dialog_kind = kind
        start = self.last_folder or None
        if kind == "files":
            self.dialog = FileDialog("Add files", multiselect=True, filters=[("All files (*)", ["*"])], directory=start)
        elif kind == "folder":
            self.dialog = FileDialog("Add a folder", mode="folder", directory=start)
        else:
            current = Path(self.model.save_path).parent if self.model.save_path else None
            self.dialog = FileDialog("Save results", mode="save", filters=_CSV,
                                     directory=str(current) if current and current.is_dir() else start)
        self._dialog_window.title = self.dialog.title
        self._dialog_window.show()

    def _draw_dialog(self, box: tuple) -> None:
        if self.dialog is None:
            return
        pressed = self._dialog_window.begin(box)
        result = self.dialog.draw()
        self._dialog_window.end()
        if result:
            kind, self.dialog = self.dialog_kind, None
            self._dialog_window.hide()
            if kind == "results":
                path = str(result[0])
                if not Path(path).suffix:
                    path += ".csv"
                self.model.choose_results(path)
            else:
                self.last_folder = str(Path(result[0]) if kind == "folder" else Path(result[0]).parent)
                self.model.add_paths([str(p) for p in result])
        elif result is False or pressed == "close":
            self.dialog = None
            self._dialog_window.hide()
            self.model.cancel_dialog()

    def _picked(self, paths: list) -> None:
        self.model.add_paths([str(p) for p in paths])

    # -- host hooks --------------------------------------------------------------------------------- #
    def files_dropped(self, paths: Any) -> bool:
        """Host hook (native, web and Qt hosts): queue the dropped files and folders (a drop adds to the list)."""
        return self.model.add_paths([str(p) for p in paths or []]) > 0

    on_files_dropped = files_dropped
    on_paths_dropped = files_dropped

    # -- frames only while something moves ---------------------------------------------------------- #
    def animating(self) -> bool:
        return self.model.running or not self.model._events.empty() or super().animating()

    # -- persistence -------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered: the step, the template fit, the CSV path and the window layout."""
        return {**self.model.export_settings(), "docks": self.docks.state()}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        self.model.restore_settings(settings)
        self.docks.restore(settings.get("docks"))

    def close(self) -> None:
        self.picker.close()
        self.model.close()


def make_app() -> BatchAnalysisApp:
    """Build the wizard (the manifest's ``entrypoints.emtk``)."""
    from chisurf.emtk.i18n import install

    install()
    return BatchAnalysisApp()


__all__ = ["BatchAnalysisApp", "make_app"]
