"""Qt-free state of the batch-analysis wizard drawn by :mod:`.app`.

The Qt wizard is an AutoForm ``wizard`` section over :class:`~.view_model.BatchViewModel`: five steps (Welcome, Loaded
data, Files & fit, Run, Results), a check mark for every completed step and a Back / Next / Finish bar. This model is that
wizard without a toolkit. It extends :class:`BatchViewModel`, which holds the selection (datasets, files, template fit, the
CSV path), the completion booleans and the fit / dataset resolution, so the two wizards cannot drift apart, and it drives
the same :mod:`..core.runner` for the numbers.

What differs from the Qt model is what a Qt-free app must do differently:

* the run goes through a worker thread and reports ``i/total: name`` in a progress bar instead of a modal progress dialog,
  and every message the Qt run showed in a message box (no data, no fit, batch complete, failure) is a line in the window;
* the file choosers (add files, add folder, the results CSV, the database) are requests the app answers with its in-app
  dialogs;
* the session (datasets, fit client, action dispatcher, a per-run screenshot) is injectable, so a test runs a whole batch
  against fakes; without one the process-global ChiSurf session is used exactly as the Qt tool uses it.
"""

from __future__ import annotations

import logging
import os
import pathlib
import queue
import tempfile
import threading
from collections.abc import Callable
from typing import Any

from chisurf.plugins.emtk_wizard import Step, Stepper

from ..core import runner
from .view_model import BatchViewModel

logger = logging.getLogger(__name__)

#: The steps, with the titles, subtitles and completion conditions of ``batch.view.json``.
STEPS: tuple[Step, ...] = (
    Step("welcome", "Welcome", "Apply one template fit to many datasets or files."),
    Step("datasets", "Loaded data", "Optionally pick datasets already loaded in ChiSurf."),
    Step(
        "files", "Files & fit", "Drop files to process and choose the template fit.", "fit_selected"
    ),
    Step("run", "Run", "Choose where to save results, then run the batch.", "has_results"),
    Step("results", "Results", "Per-parameter results of the last run."),
)

_WELCOME_MD = """\
# Batch Analysis

Apply one **template fit** to many datasets or files in one pass. Each item starts from the template's parameters, so the \
results are directly comparable.

Before you start:

1. Load some data in ChiSurf and create a fit for one representative dataset.
2. **Manually optimise** that template fit — its parameter values seed every run.
3. Pick already-loaded datasets and/or drop files below, choose the template fit, then run.

Results are written to a CSV (plus an optional DOCX report and a ZIP of the per-run exports).
"""

#: Columns of the results table: the CSV's, with the width and tooltip each gets.
RESULT_COLUMNS = runner.FIELDNAMES


class BatchModel(Stepper, BatchViewModel):
    """The batch-analysis wizard: steps, the three tables, dialog requests and the threaded run.

    Parameters
    ----------
    session : object, optional
        Stands in for the ChiSurf session: ``datasets`` (list), ``client`` (the fitting client) and ``dispatch(name,
        payload)``. Without one the process-global session is read, as the Qt tool does.
    capture : callable, optional
        ``capture(out_dir, name, run_index) -> path`` grabs a picture of the fit after each run for the DOCX report (the
        Qt tool grabs the current fit sub-window); without one the report has the table only.
    """

    STEPS = STEPS

    def __init__(
        self, session: Any = None, capture: Callable[[str, str, int], str] | None = None
    ) -> None:
        BatchViewModel.__init__(self)
        self.session = session
        self.capture = capture
        self.init_steps()
        #: Whether a run is in progress (its worker thread is alive).
        self.running = False
        self.progress: tuple[int, int] = (0, 0)
        self.progress_name = ""
        #: A line under the Run button: what the Qt tool said in a message box or a status panel.
        self.message = ""
        self.message_ok = True
        #: Output files of the last run (CSV, DOCX, ZIP).
        self.outputs: list[str] = []
        #: ``""`` or the chooser the app should open: ``files``, ``folder``, ``results``, ``database``.
        self.dialog_request = ""
        self._run_after_dialog = False
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._fit_names: list[str] = []
        self._dataset_rows: list[dict] = []
        self._file_rows: list[dict] = []
        self._result_rows: list[dict] = []
        #: Path of the selected row in the files table.
        self.selected_file = ""
        self.reload_fits()
        self.reload_datasets()
        self.reload_files()

    # -- the session ------------------------------------------------------------------------------------------------- #
    def _fit_client(self):
        if self.session is not None:
            return self.session.client
        return super()._fit_client()

    def _all_datasets(self) -> list:
        if self.session is not None:
            return list(self.session.datasets)
        import chisurf as cs

        return list(getattr(cs, "imported_datasets", []))

    def imported_datasets(self) -> list:
        """The loaded datasets (the global one excluded), of the injected session or the process."""
        return [d for d in self._all_datasets() if getattr(d, "name", None) != "Global Dataset"]

    def _dispatch(self):
        if self.session is not None:
            return lambda name, payload: self.session.dispatch(name, payload)
        import chisurf.core.actions

        return chisurf.core.actions.dispatch

    # -- fits -------------------------------------------------------------------------------------------------------- #
    def reload_fits(self) -> None:
        """Read the fit names again; an empty selection takes the first fit (the one a run would use)."""
        self._fit_names = super().fit_names()
        if self._fit_names and not self.selected_fit_name:
            self.selected_fit_name = self._fit_names[0]
        self.refresh_completion()

    def fit_names(self) -> list[str]:
        """The names of the fits (read when the step is entered, on Refresh and before a run)."""
        return list(self._fit_names)

    def on_step(self, index: int) -> None:
        if self.STEPS[index].id in ("files", "run"):
            self.reload_fits()
        if self.STEPS[index].id == "datasets":
            self.reload_datasets()

    def refresh_fits(self) -> None:
        """Refresh fits button: list the fits of the session again."""
        self.reload_fits()
        self.message = ""

    # -- loaded datasets --------------------------------------------------------------------------------------------- #
    def reload_datasets(self) -> None:
        """Re-scan the loaded datasets, keeping the ticks of the ones still there (the Qt Refresh button)."""
        available = self.imported_datasets()
        self.selected_dataset_indices = [
            i for i in self.selected_dataset_indices if 0 <= i < len(available)
        ]
        chosen = set(self.selected_dataset_indices)
        rows = []
        for idx, ds in enumerate(available):
            name = (
                getattr(ds, "name", None) or getattr(ds, "filename", None) or f"Dataset {idx + 1}"
            )
            rows.append(
                {
                    "index": idx,
                    "label": f"{idx + 1}. {name}",
                    "name": str(name),
                    "use": idx in chosen,
                    "tip": str(getattr(ds, "filename", "") or name),
                }
            )
        self._dataset_rows = rows
        self.refresh_completion()

    def refresh_datasets(self) -> None:
        """Refresh button of the Loaded data step."""
        self.reload_datasets()

    def dataset_rows(self) -> list[dict]:
        """Rows of the dataset table: ``use`` (a check box), ``label`` (``"1. name"``) and ``tip``."""
        return self._dataset_rows

    def set_dataset_use(self, record: dict, key: str, value: Any) -> None:
        """A tick in the dataset table: write it to ``selected_dataset_indices`` (the Qt list's ``_commit``)."""
        if key != "use":
            return
        chosen = set(self.selected_dataset_indices)
        (chosen.add if value else chosen.discard)(int(record["index"]))
        record["use"] = bool(value)
        self.selected_dataset_indices = sorted(chosen)
        self.update()

    def datasets_hint(self) -> str:
        """The line under the dataset table: how many are ticked, or why the list is empty."""
        total = len(self._dataset_rows)
        if not total:
            return "No dataset is loaded in ChiSurf. Load data there, then press Refresh."
        return f"{len(self.selected_dataset_indices)} of {total} datasets ticked. Hover a row for its file."

    # -- files ------------------------------------------------------------------------------------------------------- #
    def reload_files(self) -> None:
        """Rebuild the file table from ``files``."""
        self._file_rows = [
            {"name": pathlib.Path(p).name, "folder": str(pathlib.Path(p).parent), "path": p}
            for p in self.files
        ]
        if self.selected_file not in self.files:
            self.selected_file = ""
        self.refresh_completion()

    def update(self) -> None:
        """After the file list or a tick changed (the Qt section calls ``model.update()``)."""
        self.reload_files()
        super().update()

    def file_rows(self) -> list[dict]:
        """Rows of the file table: ``name``, ``folder``, ``path``."""
        return self._file_rows

    def select_file(self, record: dict | None) -> None:
        """Selection of the file table."""
        self.selected_file = str((record or {}).get("path", ""))

    @staticmethod
    def expand(paths: list[str]) -> list[str]:
        """Files stay, a folder becomes every file below it (sorted): the Qt section's ``_expand`` without a filter."""
        out: list[str] = []
        for item in paths:
            p = pathlib.Path(item)
            if p.is_file():
                out.append(str(p))
            elif p.is_dir():
                out.extend(str(f) for f in sorted(p.rglob("*")) if f.is_file())
        return out

    def add_paths(self, paths: list) -> int:
        """Add files and folders (a folder is expanded, a repeated path ignored). Returns how many were new."""
        before = len(self.files)
        seen: set[str] = set()
        merged = [
            p
            for p in list(self.files) + self.expand([str(p) for p in paths])
            if not (p in seen or seen.add(p))
        ]
        self.files = merged
        self.update()
        return len(self.files) - before

    def remove_selected(self) -> None:
        """Remove button: drop the selected file from the list (the file stays on disk)."""
        if self.selected_file in self.files:
            self.files = [p for p in self.files if p != self.selected_file]
            self.selected_file = ""
            self.update()

    def remove_file(self, record: dict | None) -> None:
        """Delete key in the table."""
        if record:
            self.selected_file = str(record.get("path", ""))
            self.remove_selected()

    def clear_files(self) -> None:
        """Clear button."""
        self.files = []
        self.selected_file = ""
        self.update()

    def request_dialog(self, kind: str) -> None:
        """Ask the app to open a chooser (``files``, ``folder``, ``results`` or ``database``)."""
        if not self.running:
            self.dialog_request = kind

    def add_files(self) -> None:
        """Files button."""
        self.request_dialog("files")

    def add_folder(self) -> None:
        """Folder button."""
        self.request_dialog("folder")

    def add_database(self) -> None:
        """Database button."""
        self.request_dialog("database")

    def browse_results(self) -> None:
        """The ``...`` button of the CSV field."""
        self.request_dialog("results")

    def choose_results(self, path: str) -> None:
        """The CSV path chosen in the save dialog; a pending Run goes on with it."""
        self.set_save_path(path)
        if self._run_after_dialog:
            self._run_after_dialog = False
            self.run()

    def cancel_dialog(self) -> None:
        """A chooser was cancelled: a pending Run is dropped (the Qt tool returned without running)."""
        self._run_after_dialog = False

    # -- texts ------------------------------------------------------------------------------------------------------- #
    def welcome_md(self) -> str:
        """The introduction of the first step (Markdown; the Qt step shows the same text as HTML)."""
        return _WELCOME_MD

    def selection_md(self) -> str:
        """A live summary of the selection (the Qt ``selection_html`` as Markdown)."""
        fit = self.selected_fit_name or "*none*"
        return (
            "#### Ready to run\n\n"
            f"- Loaded datasets: **{len(self.selected_datasets())}**\n"
            f"- Files: **{len(self.files)}**\n"
            f"- Template fit: **{fit}**\n"
        )

    def enabled(self, action: str) -> bool:
        """Whether the button *action* may be pressed now (the form greys it otherwise)."""
        if action == "go_back":
            return not self.is_first
        if action in ("remove_selected",):
            return bool(self.selected_file) and not self.running
        if action in ("clear_files",):
            return bool(self.files) and not self.running
        if action in ("add_files", "add_folder", "add_database", "browse_results", "run"):
            return not self.running
        return True

    # -- the results table ------------------------------------------------------------------------------------------- #
    def result_rows(self) -> list[dict]:
        """Rows of the results table: the CSV's columns, one row per item and parameter of the last run."""
        return self._result_rows

    @property
    def results_text(self) -> str:
        """What the Results step says above the table: the outcome of the run, or a hint."""
        if self._results is None:
            return "No results yet — run the batch on the previous step."
        return "\n".join(self.outputs)

    @property
    def progress_fraction(self) -> float:
        done, total = self.progress
        return (done / total) if total else 0.0

    def progress_text(self) -> str:
        """The text over the progress bar: ``i/total: name`` while running, ``Idle`` before."""
        done, total = self.progress
        if not total:
            return "Idle"
        return (
            f"{done}/{total}: {os.path.basename(self.progress_name)}"
            if self.progress_name
            else f"{done}/{total}"
        )

    # -- the run ----------------------------------------------------------------------------------------------------- #
    def run(self) -> None:
        """Run button: validate, ask for the CSV when there is none, then fit every item on a worker thread."""
        if self.running:
            return
        self.message_ok = False
        items = self.build_items()
        self.reload_fits()
        if not items:
            self.message = "No data: Select datasets or add files first."
            return
        if self.fit_index() < 0:
            self.message = "No fit: Select a template fit first."
            return
        if not (self.save_path or "").strip():
            self._run_after_dialog = True
            self.request_dialog("results")
            return
        self.message = ""
        self.message_ok = True
        self.outputs = []
        self.running = True
        self.progress = (0, len(items))
        self.progress_name = ""
        fit_index = self.fit_index()
        save_path = self.save_path.strip()
        self._thread = threading.Thread(
            target=self._work, args=(fit_index, items, save_path), daemon=True
        )
        self._thread.start()

    def _work(self, fit_index: int, items: list, save_path: str) -> None:
        """The worker: restore, fit and collect every item, then write the CSV, the DOCX and the ZIP."""
        try:
            exports_dir = tempfile.mkdtemp(prefix="chisurf_batch_fit_exports_")
            shots_dir = tempfile.mkdtemp(prefix="chisurf_batch_")

            def on_progress(i: int, total: int, name: str) -> None:
                self._events.put(("progress", i, total, name))

            on_complete = None
            if self.capture is not None:

                def on_complete(item, run_index, key):
                    return self.capture(shots_dir, item.name, run_index)

            results = runner.run_batch(
                fit_index,
                items,
                fit_client=self._fit_client(),
                dispatch=self._dispatch(),
                imported_datasets=self._all_datasets(),
                on_progress=on_progress,
                on_run_complete=on_complete,
                fit_export_dir=exports_dir,
            )
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            results.write_csv(save_path)
            docx_path = os.path.splitext(save_path)[0] + ".docx"
            docx_ok, docx_note = runner.write_docx(
                results.rows,
                docx_path,
                results.file_order,
                results.screenshot_map,
                csv_name=os.path.basename(save_path),
            )
            zip_out = runner.zip_directory(
                exports_dir, os.path.splitext(save_path)[0] + "_fit_results"
            )
            lines = [f"CSV: {save_path}"]
            lines.append(
                f"DOCX: {docx_path}" if docx_ok else "DOCX report not written: " + str(docx_note)
            )
            if zip_out:
                lines.append(f"Per-run exports (ZIP): {zip_out}")
            self._events.put(("done", results, lines))
        except Exception as exc:  # noqa: BLE001 - the Qt tool showed "Batch failed" with the text
            logger.warning("batch run failed", exc_info=True)
            self._events.put(("failed", f"Batch failed: {exc}"))

    def poll(self) -> bool:
        """Take the worker's messages (progress, done, failed); True when something changed."""
        changed = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if event[0] == "progress":
                _, done, total, name = event
                self.progress, self.progress_name = (done, total), name
            elif event[0] == "done":
                _, results, lines = event
                self._results = results
                self.outputs = lines
                self._result_rows = [
                    {c: r.get(c, "") for c in runner.FIELDNAMES} for r in results.rows
                ]
                self.message, self.message_ok = "Batch complete", True
                self.running = False
                self.refresh_completion()
            elif event[0] == "failed":
                self.message, self.message_ok = event[1], False
                self.running = False
        return changed

    def wait(self, timeout: float = 30.0) -> None:
        """Block until the run ends (tests and scripts)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self.poll()

    # -- persistence ------------------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """What is remembered: the step, the template fit and the CSV path (the file list is not: paths go stale)."""
        return {
            **self.export_step(),
            "selected_fit_name": self.selected_fit_name,
            "save_path": self.save_path,
        }

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; an unusable value is ignored."""
        self.restore_step(settings)
        self.selected_fit_name = str(settings.get("selected_fit_name", "") or "")
        self.save_path = str(settings.get("save_path", "") or "")
        self.reload_fits()

    def close(self) -> None:
        """Drop the observers (the worker is a daemon and ends with the process)."""
        self._observers.clear()


__all__ = ["BatchModel", "STEPS", "RESULT_COLUMNS"]
