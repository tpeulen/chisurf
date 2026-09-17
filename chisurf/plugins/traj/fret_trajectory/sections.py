"""Custom AutoForm sections for the Structure-to-Transfer (Trajectory→FRET) tool.

Three bespoke Qt widgets are registered here and drive the Qt-free
:class:`~.view_model.FretTrajectoryViewModel`:

* ``fret_traj_io`` — the trajectory picker (``…`` browse + drag-drop, H5 filter).
* ``fret_atom_pairs`` — the donor / acceptor atom selection hosting the four
  :class:`~chisurf.gui.widgets.pdb.PDBSelector` widgets (``d1``/``d2`` donor
  pair, ``a1``/``a2`` acceptor pair; the second of each is created with
  ``show_labels=False``). It loads the model's trajectory topology into the
  selectors and writes the chosen atom indices back to the model.
* ``fret_run`` — the Process button (save-file dialog → ``model.calc``) and a
  progress bar.

The declarative numeric settings (t_step, R0, tau0, stride, dipole toggle) and
the live log are plain built-in sections in ``structure2transfer.view.json``.
Imported (and thus registered) by ``gui``.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui import dialogs
from chisurf.gui.autoform.sections.progress_section import InlineProgressWidget
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.widgets.pdb import PDBSelector

logger = logging.getLogger(__name__)


def _enable_file_drop(line_edit: QtWidgets.QLineEdit, on_file) -> None:
    """Enable dropping a single existing file onto *line_edit* → ``on_file(path)``."""
    line_edit.setAcceptDrops(True)

    def dragEnterEvent(event: QtGui.QDragEnterEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and pathlib.Path(urls[0].toLocalFile()).is_file():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(event: QtGui.QDropEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1:
            path = urls[0].toLocalFile()
            if pathlib.Path(path).is_file():
                event.acceptProposedAction()
                on_file(path)
                return
        event.ignore()

    line_edit.dragEnterEvent = dragEnterEvent
    line_edit.dropEvent = dropEvent


# ---------------------------------------------------------------------------
# fret_traj_io — trajectory picker
# ---------------------------------------------------------------------------


@register_section("fret_traj_io")
def fret_traj_io(model, target=None, **options):
    """AutoForm factory for the trajectory picker row."""
    return _TrajectoryIoSection(model)


class _TrajectoryIoSection(QtWidgets.QWidget):
    """Trajectory row (browse + drag-drop, H5 filter) driving the view-model."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model

        row = QtWidgets.QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(2)
        row.addWidget(QtWidgets.QLabel("Trajectory"))
        self._edit = QtWidgets.QLineEdit()
        self._edit.setReadOnly(True)
        self._edit.setPlaceholderText("Drop an H5 trajectory here or browse…")
        self._edit.setText(self._model.trajectory_file)
        row.addWidget(self._edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open an H5 trajectory file.")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)

        _enable_file_drop(self._edit, self._load)
        self._model.add_observer(self._on_model_event)

    def _on_model_event(self, event: str) -> None:
        if event == "loaded" and self._edit.text() != self._model.trajectory_file:
            self._edit.setText(self._model.trajectory_file)

    def _browse(self) -> None:
        import chisurf.gui.widgets

        filenames = chisurf.gui.widgets.open_files(
            "Open Trajectory-File", "H5-Trajectory-Files (*.h5)"
        )
        if filenames:
            self._model.set_trajectory_files(filenames)

    def _load(self, path: str) -> None:
        if path and pathlib.Path(path).is_file():
            self._model.set_trajectory_files([path])


# ---------------------------------------------------------------------------
# fret_atom_pairs — donor / acceptor dipole atom selection
# ---------------------------------------------------------------------------


@register_section("fret_atom_pairs")
def fret_atom_pairs(model, target=None, **options):
    """AutoForm factory for the donor/acceptor atom-pair selectors."""
    return _AtomPairSection(model)


class _AtomPairSection(QtWidgets.QWidget):
    """Hosts the four :class:`PDBSelector` widgets and writes indices to the model.

    ``d1``/``d2`` define the donor dipole, ``a1``/``a2`` the acceptor dipole. The
    structure loaded into the model (:attr:`FretTrajectoryViewModel.pdb`) is
    pushed into every selector on the ``loaded`` event, and any selection change
    writes the chosen atom indices back to ``model.donor`` / ``model.acceptor``.

    The section deliberately does **not** opt into ``AUTOFORM_REFRESH``: a generic
    form refresh (e.g. triggered by a log line emitted while processing) must not
    reload the structure and reset the atom combos, which would clobber the user's
    donor/acceptor selection mid-compute. The selectors are (re)loaded only when
    the trajectory actually changes, via the ``loaded`` observer event.
    """

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        # Back-reference so the hosting widget / tests can reach the selectors.
        model.atom_pair_section = self

        self.d1 = PDBSelector()
        self.d2 = PDBSelector(show_labels=False)
        self.a1 = PDBSelector()
        self.a2 = PDBSelector(show_labels=False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        layout.addWidget(self._group("Donor", self.d1, self.d2), 1)
        layout.addWidget(self._group("Acceptor", self.a1, self.a2), 1)

        for selector in (self.d1, self.d2, self.a1, self.a2):
            selector.atom_combo.currentIndexChanged.connect(self._on_changed)

        self._model.add_observer(self._on_model_event)
        if self._model.pdb is not None:
            self.load_structure()

    @staticmethod
    def _group(title, *selectors) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        lay = QtWidgets.QVBoxLayout(box)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        for selector in selectors:
            lay.addWidget(selector)
        return box

    # ── model wiring ────────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event == "loaded":
            self.load_structure()

    def load_structure(self) -> None:
        """Push the model's topology into every selector and sync the defaults."""
        pdb = self._model.pdb
        if pdb is None:
            return
        for selector in (self.d1, self.d2, self.a1, self.a2):
            selector.atoms = pdb
        self._on_changed()

    def _on_changed(self, *_) -> None:
        """Write the current selector atom indices back to the model."""
        try:
            self._model.donor = (self.d1.atom_number, self.d2.atom_number)
            self._model.acceptor = (self.a1.atom_number, self.a2.atom_number)
        except Exception:  # pragma: no cover - defensive (empty selectors)
            logger.debug("FretTrajectory: could not read atom selection", exc_info=True)

    # ── programmatic API (used by tests / macros) ───────────────────────
    def set_donor(self, i: int, j: int) -> None:
        """Select the donor dipole atoms at indices *i*, *j* and push to the model."""
        self.d1.set_atom_index(int(i))
        self.d2.set_atom_index(int(j))
        self._on_changed()

    def set_acceptor(self, i: int, j: int) -> None:
        """Select the acceptor dipole atoms at indices *i*, *j* and push to the model."""
        self.a1.set_atom_index(int(i))
        self.a2.set_atom_index(int(j))
        self._on_changed()


# ---------------------------------------------------------------------------
# fret_run — Process button + progress bar
# ---------------------------------------------------------------------------


@register_section("fret_run")
def fret_run(model, target=None, **options):
    """AutoForm factory for the Process button and progress bar."""
    return _RunSection(model)


class _RunSection(QtWidgets.QWidget):
    """The Process action button (save-file dialog → ``model.calc``) + progress bar."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._running = False
        model.run_section = self

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        self._btn = QtWidgets.QToolButton()
        self._btn.setText("▶ Process trajectory")
        self._btn.setToolTip("Compute the FRET observables and save them to a CSV file.")
        self._btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._btn.clicked.connect(self.run)
        layout.addWidget(self._btn)

        self._progress = InlineProgressWidget()
        layout.addWidget(self._progress, 1)

    def run(self, output_file: str | None = None):
        """Run the transfer computation, prompting for an output file if needed.

        Parameters
        ----------
        output_file : str, optional
            Destination CSV path. When ``None`` a save-file dialog is shown; this
            argument lets tests drive the action headlessly.

        Returns
        -------
        np.ndarray or None
            The computed transfer array, or ``None`` if cancelled / already busy.
        """
        if self._running:
            return None
        if not (self._model.filenames or self._model.trajectory_file):
            dialogs.information(self, "No trajectory", "Open a trajectory first.")
            return None
        if output_file is None:
            import chisurf.gui.widgets

            output_file = chisurf.gui.widgets.save_file(
                description="Output-file", file_type="All files (*.csv)"
            )
        if not output_file:
            self._model.append_log("Process cancelled")
            self._refresh_host_form()
            return None

        self._running = True
        self._btn.setEnabled(False)
        result = None
        # The frame count is not known up front, so the bar beside the button
        # runs as a busy indicator until the computation returns.
        with ChiSurfProgress(self._btn, "Computing FRET observables…", 0, cancellable=False):
            try:
                result = self._model.calc(output_file=output_file)
            except Exception as exc:  # noqa: BLE001
                self._model.append_log(f"Processing failed: {exc}")
                dialogs.error(self, "Processing failed", str(exc))
            finally:
                self._running = False
                self._btn.setEnabled(True)
                self._refresh_host_form()
        return result

    def _refresh_host_form(self) -> None:
        """Walk up to the hosting AutoForm and refresh its widgets (log panel)."""
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "sync_fields") and hasattr(widget, "refresh_plots"):
                try:
                    widget.sync_fields()
                    widget.refresh_plots()
                except Exception:  # pragma: no cover - defensive
                    pass
                return
            widget = widget.parentWidget()


__all__ = ["fret_traj_io", "fret_atom_pairs", "fret_run"]
