"""Custom AutoForm sections for the Potential-Energy calculator.

Two bespoke Qt widgets are registered here and referenced by ``custom`` sections
in ``calculate_potential.view.json``:

``potential_energy_setup``
    The trajectory and topology pickers (``…`` browse + drag-drop), the
    potential-type combo, the *dynamic* parameter editor (the selected
    :data:`chisurf.gui.widgets.structure.potentialDict` widget, rebuilt on every
    combo change — a direct port of the legacy ``onSelectedPotentialChanged``),
    the weight field and the **Add** button (builds the potential from the current
    editor and calls :meth:`~..view_model.PotentialEnergyViewModel.add_potential`).

``potential_energy_run``
    The **Process** button + progress bar; opens a save dialog for the CSV and
    calls :meth:`~..view_model.PotentialEnergyViewModel.process`.

The widgets own only Qt concerns and drive the Qt-free
:class:`~..view_model.PotentialEnergyViewModel`. Imported (and thus registered)
by ``widget``. Mirrors the TTTR-Splitter ``sections`` pattern.
"""

from __future__ import annotations

import logging
import pathlib

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.autoform.sections.progress_section import InlineProgressWidget
from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.progress import ChiSurfProgress
from chisurf.gui.glyphs import Glyphs
from chisurf.gui import dialogs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# drag-drop helper
# ---------------------------------------------------------------------------


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


def _refresh_host_form(widget: QtWidgets.QWidget) -> None:
    """Walk up to the hosting AutoForm and refresh its widgets (log + table)."""
    parent = widget.parentWidget()
    while parent is not None:
        if hasattr(parent, "sync_fields") and hasattr(parent, "refresh_plots"):
            try:
                parent.sync_fields()
                parent.refresh_plots()
            except Exception:  # pragma: no cover - defensive
                pass
            return
        parent = parent.parentWidget()


# ---------------------------------------------------------------------------
# potential_energy_setup — trajectory picker + potential editor + Add button
# ---------------------------------------------------------------------------


@register_section("potential_energy_setup")
def potential_energy_setup(model, target=None, **options):
    """AutoForm factory for the trajectory picker + potential editor + Add button."""
    return _SetupSection(model)


class _SetupSection(QtWidgets.QWidget):
    """Trajectory picker, potential-type combo, dynamic editor, weight and Add."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._editor = None  # the current potentialDict parameter widget

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)

        # -- trajectory row --------------------------------------------------
        traj_row = QtWidgets.QHBoxLayout()
        traj_row.setContentsMargins(0, 0, 0, 0)
        traj_row.setSpacing(2)
        traj_row.addWidget(QtWidgets.QLabel("Trajectory"))
        self._traj_edit = QtWidgets.QLineEdit()
        self._traj_edit.setReadOnly(True)
        self._traj_edit.setPlaceholderText("Drop a DCD trajectory here or browse…")
        self._traj_edit.setText(self._model.trajectory_file)
        traj_row.addWidget(self._traj_edit, 1)
        browse = QtWidgets.QToolButton()
        browse.setText("…")
        browse.setToolTip("Open a DCD trajectory.")
        browse.clicked.connect(self._browse_trajectory)
        traj_row.addWidget(browse)
        layout.addLayout(traj_row)

        # DCD holds coordinates and nothing else, so the atom names -- which
        # every potential scores by -- have to come from a structure file.
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(2)
        top_row.addWidget(QtWidgets.QLabel("Topology"))
        self._top_edit = QtWidgets.QLineEdit()
        self._top_edit.setReadOnly(True)
        self._top_edit.setPlaceholderText("PDB naming the atoms — required for DCD")
        self._top_edit.setText(self._model.topology_filename)
        top_row.addWidget(self._top_edit, 1)
        top_browse = QtWidgets.QToolButton()
        top_browse.setText("…")
        top_browse.setToolTip(
            "Open the PDB that names the atoms. DCD stores coordinates "
            "only, so this is required for them."
        )
        top_browse.clicked.connect(self._browse_topology)
        top_row.addWidget(top_browse)
        layout.addLayout(top_row)

        # -- potential-type combo + Add -------------------------------------
        combo_row = QtWidgets.QHBoxLayout()
        combo_row.setContentsMargins(0, 0, 0, 0)
        combo_row.setSpacing(2)
        self._combo = QtWidgets.QComboBox()
        self._combo.addItems(self._model.potential_names())
        self._combo.setCurrentIndex(int(self._model.selected_potential_index))
        self._combo.currentIndexChanged.connect(self._on_potential_changed)
        combo_row.addWidget(self._combo, 1)
        self._add_btn = QtWidgets.QToolButton()
        self._add_btn.setText(f"{Glyphs.ADD} Add")
        self._add_btn.setToolTip("Add the configured potential to the list of used potentials.")
        self._add_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._add_btn.clicked.connect(self._add_potential)
        combo_row.addWidget(self._add_btn)
        layout.addWidget(_wrap(combo_row))

        # -- dynamic parameter editor ---------------------------------------
        self._editor_box = QtWidgets.QGroupBox("Parameters")
        self._editor_layout = QtWidgets.QVBoxLayout(self._editor_box)
        self._editor_layout.setContentsMargins(4, 4, 4, 4)
        self._editor_layout.setSpacing(2)
        layout.addWidget(self._editor_box)

        # -- weight ----------------------------------------------------------
        weight_row = QtWidgets.QHBoxLayout()
        weight_row.setContentsMargins(0, 0, 0, 0)
        weight_row.setSpacing(2)
        weight_row.addWidget(QtWidgets.QLabel("Weight"))
        self._weight = QtWidgets.QDoubleSpinBox()
        self._weight.setDecimals(3)
        self._weight.setMinimum(-1e6)
        self._weight.setMaximum(1e6)
        self._weight.setValue(float(self._model.potential_weight))
        self._weight.valueChanged.connect(self._on_weight_changed)
        weight_row.addWidget(self._weight, 1)
        layout.addWidget(_wrap(weight_row))

        self._rebuild_editor()

        _enable_file_drop(self._traj_edit, self._load_trajectory)
        _enable_file_drop(self._top_edit, self._load_topology)
        self._model.add_observer(self._on_model_event)

    # ── model wiring ────────────────────────────────────────────────────
    def _on_model_event(self, event: str) -> None:
        if event != "loaded":
            return
        if self._traj_edit.text() != self._model.trajectory_file:
            self._traj_edit.setText(self._model.trajectory_file)
        if self._top_edit.text() != self._model.topology_filename:
            self._top_edit.setText(self._model.topology_filename)

    # ── trajectory ──────────────────────────────────────────────────────
    def _browse_trajectory(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename(
            "Open trajectory", "Trajectories (*.dcd)"
        )
        if filename:
            self._load_trajectory(str(filename))

    def _browse_topology(self) -> None:
        import chisurf.gui.widgets

        filename = chisurf.gui.widgets.get_filename(
            "Open topology", "Structures (*.pdb *.cif *.ent)"
        )
        if filename:
            self._load_topology(str(filename))

    def _load_topology(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_topology(path)
        _refresh_host_form(self)

    def _load_trajectory(self, path: str) -> None:
        if not path or not pathlib.Path(path).is_file():
            return
        self._model.set_trajectory(path)
        _refresh_host_form(self)

    # ── dynamic potential editor ────────────────────────────────────────
    def _on_potential_changed(self, index: int) -> None:
        self._model.selected_potential_index = int(index)
        self._rebuild_editor()

    def _rebuild_editor(self) -> None:
        """Rebuild the parameter editor for the selected potential (port of legacy slot)."""
        import chisurf.gui.widgets

        while self._editor_layout.count():
            item = self._editor_layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()

        name = self._current_potential_name()
        factory = chisurf.gui.widgets.structure.potentialDict.get(name)
        if factory is None:
            self._editor = None
            return
        self._editor = factory(structure=self._model.structure, parent=self)
        self._editor.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._editor.setMaximumHeight(160)
        self._editor_layout.addWidget(self._editor)

    def _current_potential_name(self) -> str:
        names = self._model.potential_names()
        index = self._combo.currentIndex()
        if 0 <= index < len(names):
            return names[index]
        return names[0] if names else ""

    # ── weight ──────────────────────────────────────────────────────────
    def _on_weight_changed(self, value: float) -> None:
        self._model.potential_weight = float(value)

    # ── add ─────────────────────────────────────────────────────────────
    def _add_potential(self) -> None:
        if self._editor is None:
            self._rebuild_editor()
        if self._editor is None:
            dialogs.warning(self, "No potential", "No potential type is available.")
            return
        self._model.add_potential(
            self._editor,
            float(self._weight.value()),
            name=self._current_potential_name(),
        )
        # The added editor now belongs to the universe; give the combo a fresh one.
        self._rebuild_editor()
        _refresh_host_form(self)


# ---------------------------------------------------------------------------
# potential_energy_run — Process button + progress bar
# ---------------------------------------------------------------------------


@register_section("potential_energy_run")
def potential_energy_run(model, target=None, **options):
    """AutoForm factory for the Process button and progress bar."""
    return _RunSection(model)


class _RunSection(QtWidgets.QWidget):
    """The Process action button and its progress bar."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self._running = False

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(6)

        self._btn = QtWidgets.QToolButton()
        self._btn.setText(f"{Glyphs.SETTINGS} Process")
        self._btn.setToolTip("Score every frame of the trajectory and write the energies to a CSV.")
        self._btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._btn.clicked.connect(self._run)
        layout.addWidget(self._btn)

        self._progress = InlineProgressWidget()
        layout.addWidget(self._progress, 1)
        self._task = None

    def _run(self) -> None:
        if self._running:
            return
        if not self._model.trajectory_file:
            dialogs.information(self, "No trajectory", "Open a trajectory first.")
            return
        if not self._model.universe.potentials:
            dialogs.information(self, "No potentials", "Add at least one potential.")
            return
        energy_file, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save energies", "", "CSV-name file (*.txt)"
        )
        if not energy_file:
            self._model.append_log("Process cancelled")
            _refresh_host_form(self)
            return
        self._running = True
        self._btn.setEnabled(False)
        # The frame count is not known up front, so this starts as a busy
        # indicator; ChiSurfProgress renders it in the bar beside the button.
        with ChiSurfProgress(self._btn, "Scoring frames…", 0, cancellable=False) as self._task:
            try:
                count = self._model.process(energy_file, progress_cb=self._on_progress)
                dialogs.information(
                    self, "Processing complete", f"Processed {count} frame(s)."
                )
            except Exception as exc:  # noqa: BLE001
                dialogs.error(self, "Processing failed", str(exc))
            finally:
                self._running = False
                self._btn.setEnabled(True)
        self._task = None
        _refresh_host_form(self)

    def _on_progress(self, frames_done: int) -> None:
        if self._task is not None:
            self._task.set_text(f"Scoring frames… ({frames_done} done)")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _wrap(inner_layout: QtWidgets.QLayout) -> QtWidgets.QWidget:
    """Wrap a layout in a margin-free container widget."""
    box = QtWidgets.QWidget()
    box.setLayout(inner_layout)
    return box


__all__ = ["potential_energy_setup", "potential_energy_run"]
