"""Qt-free view-model backing the Batch-Analysis wizard.

Holds the wizard's state (selected files, template fit, save path, loaded-dataset
selection) and exposes the ``source`` methods (HTML info panels), the
``options_source`` for the fit combo, the zero-arg ``action`` methods (button-row
callbacks) and the ``complete_when`` booleans that drive the step ✓ marks. All
layout lives in ``batch.view.json``; the numeric work is :mod:`...core.runner`, and the run itself (worker thread,
progress bar, result lines) is :class:`~.model.BatchModel`'s, the model the emtk app draws.

Mirrors :class:`chisurf.plugins.core.boarding.view_model.BoardingViewModel`.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Callable

from ..core import runner

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent.parent / "batch.view.json"

_WELCOME_HTML = """
<h3>Batch Analysis</h3>
<p>Apply one <b>template fit</b> to many datasets or files in one pass. Each item
starts from the template's parameters, so the results are directly comparable.</p>
<p>Before you start:</p>
<ol>
<li>Load some data in ChiSurf and create a fit for one representative dataset.</li>
<li><b>Manually optimise</b> that template fit — its parameter values seed every run.</li>
<li>Pick already-loaded datasets and/or drop files below, choose the template fit,
then run.</li>
</ol>
<p>Results are written to a CSV (plus an optional DOCX report and a ZIP of the
per-run exports).</p>
"""


class BatchViewModel:
    """State + view wiring for the batch-analysis wizard."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``batch.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self._observers: list[Callable[[str], None]] = []
        #: file paths bound to the ``path_list`` section
        self.files: list[str] = []
        #: indices (into ``chisurf.imported_datasets``) chosen in the loaded-data step
        self.selected_dataset_indices: list[int] = []
        #: display name of the template fit chosen in the combo
        self.selected_fit_name: str = ""
        #: destination CSV path (``value`` file field)
        self.save_path: str = ""
        self._results: runner.BatchResults | None = None
        self._status_html = ""

    # ── observer hook ──────────────────────────────────────────────────
    def add_observer(self, cb: Callable[[str], None]) -> None:
        """Register *cb* to be called with an event name on every change."""
        self._observers.append(cb)

    def notify(self, event: str = "changed") -> None:
        """Notify observers (the host refreshes info panels / ✓ marks)."""
        for cb in list(self._observers):
            try:
                cb(event)
            except Exception:
                logger.debug("batch observer failed", exc_info=True)

    def update(self) -> None:
        """Refresh after the ``path_list`` section edits ``files``."""
        self.notify("refresh")

    def refresh(self) -> None:
        """Button/host hook: re-read the info panels and ✓ marks."""
        self.notify("refresh")

    # ── fit / dataset resolution ────────────────────────────────────────
    def _fit_client(self):
        from chisurf.core.api.fitting_client import get_fitting_client

        return get_fitting_client()

    def fit_names(self) -> list[str]:
        """Return the display names of the available fits (``options_source``)."""
        try:
            return [f.name for f in self._fit_client().get_fit_objects()]
        except Exception:
            logger.debug("batch: could not list fits", exc_info=True)
            return []

    def fit_index(self) -> int:
        """Return the index of the selected fit, or ``-1`` when none matches."""
        names = self.fit_names()
        if self.selected_fit_name in names:
            return names.index(self.selected_fit_name)
        return 0 if names and not self.selected_fit_name else -1

    def imported_datasets(self) -> list:
        """Return the process-global imported datasets (excluding the global one)."""
        from chisurf.core.api import dataset_objects

        out = []
        for ds in dataset_objects():
            if getattr(ds, "name", None) == "Global Dataset":
                continue
            out.append(ds)
        return out

    def selected_datasets(self) -> list:
        """Return the dataset objects chosen in the loaded-data step."""
        available = self.imported_datasets()
        return [available[i] for i in self.selected_dataset_indices if 0 <= i < len(available)]

    def build_items(self) -> list[runner.BatchItem]:
        """Return the processing queue from the current selection."""
        return runner.build_queue(self.selected_datasets(), self.files)

    # ── info sources (HTML) ─────────────────────────────────────────────
    def welcome_html(self) -> str:
        """Return the welcome-step introduction (HTML)."""
        return _WELCOME_HTML

    def selection_html(self) -> str:
        """Return a live summary of the current selection (HTML)."""
        n_ds = len(self.selected_datasets())
        n_files = len(self.files)
        fit = self.selected_fit_name or "<i>none</i>"
        return (
            "<h4>Ready to run</h4>"
            f"<ul><li>Loaded datasets: <b>{n_ds}</b></li>"
            f"<li>Files: <b>{n_files}</b></li>"
            f"<li>Template fit: <b>{fit}</b></li></ul>"
        )

    def results_html(self) -> str:
        """Return the results table of the last run (HTML), or a hint."""
        if self._results is None:
            return "<p>No results yet — run the batch on the previous step.</p>"
        rows = self._results.rows
        head = "".join(f"<th>{c}</th>" for c in runner.FIELDNAMES)
        body = []
        for r in rows:
            cells = "".join(f"<td>{r.get(c, '')}</td>" for c in runner.FIELDNAMES)
            body.append(f"<tr>{cells}</tr>")
        return (
            f"{self._status_html}"
            f"<table border='1' cellspacing='0' cellpadding='3'>"
            f"<tr>{head}</tr>{''.join(body)}</table>"
        )

    def status_html(self) -> str:
        """Return the outcome message of the last run (HTML)."""
        return self._status_html or "<p>Choose a save location, then click <b>Run batch</b>.</p>"

    # ── completion booleans (complete_when) ─────────────────────────────
    @property
    def has_data(self) -> bool:
        """Whether at least one dataset or file is selected."""
        return bool(self.files or self.selected_dataset_indices)

    @property
    def fit_selected(self) -> bool:
        """Whether a template fit is chosen (or exactly one fit is available)."""
        return self.fit_index() >= 0

    @property
    def ready(self) -> bool:
        """Whether the batch can run (data + fit selected)."""
        return self.has_data and self.fit_selected

    @property
    def has_results(self) -> bool:
        """Whether a batch run has produced results."""
        return self._results is not None and bool(self._results.rows)

    # ── actions (button-row callbacks) ──────────────────────────────────
    def set_save_path(self, value: str) -> None:
        """Bind the CSV destination (``value`` file field ``call``)."""
        self.save_path = str(value or "")

    def run(self) -> None:
        """Run the batch (the *Run batch* button of ``batch.view.json``).

        The run belongs to :class:`~.model.BatchModel`, which drives :func:`...core.runner.run_batch` on a worker
        thread and reports progress, results and failures as lines in its window.
        """
        raise NotImplementedError("the batch runs in BatchModel (gui/model.py)")


__all__ = ["BatchViewModel"]
