"""The ALEX Suite's own steps as native emtk apps (no Qt): files with demo data, alternation, titration, CSV export.

Each app reuses the view of :mod:`.app` (``AlexAlternationGui``, ``TitrationGui``, ``LegacyExportGui``) over a
Qt-free model (:mod:`.alternation_model`, :mod:`.titration_view_model`, :mod:`.export_model`), and adds what the
native hub needs: file choosers drawn in the app (``emtk.file_dialog.FileDialog``), the background job's ``running``
flag (Next waits for it), and frames while it runs. The files step is Burst Analysis's data step with the ALEX
Suite's demo measurement under its proceed button.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Callable

from emtk import im

from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import BurstDataSelectionApp

from .alternation_model import AlexAlternationModel
from .app import AlexAlternationApp, LegacyExportApp, TitrationApp
from .export_model import LegacyExportModel
from .titration_view_model import TitrationViewModel

logger = logging.getLogger("chisurf.plugins.burst")

#: Burst tables the titration file chooser offers.
BURST_PATTERNS = ["*.bur", "*.pto", "*.csv", "*.txt"]


class _Dialog:
    """One in-app file chooser at a time: open it, draw it over the app, hand the chosen paths to a callback."""

    def __init__(self) -> None:
        self.dialog = None
        self.window = None
        self.on_done: Callable[[list[str]], None] | None = None

    def open(self, title: str, mode: str, on_done, *, filters=None, filename: str = "") -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        options: dict[str, Any] = {}
        if filters:
            options["filters"] = filters
        if filename:
            options["filename"] = filename
        self.dialog = FileDialog(title, mode=mode, multiselect=mode == "open", **options)
        self.window = DialogWindow(title, size=(640.0, 460.0), key="alex-suite-file")
        self.window.show()
        self.on_done = on_done

    @property
    def open_now(self) -> bool:
        return self.dialog is not None

    def draw(self, frame) -> None:
        if self.dialog is None:
            return
        pressed = self.window.begin(frame)
        result = self.dialog.draw()
        self.window.end()
        if result:
            done, self.dialog = self.on_done, None
            if callable(done):
                done([str(p) for p in (result if isinstance(result, (list, tuple)) else [result])])
        elif result is False or pressed == "close":
            self.dialog = None


# -- 2. Files ----------------------------------------------------------------------------------------------- #
class AlexDataSelectionApp(BurstDataSelectionApp):
    """Burst Analysis's data step, proceeding to the alternation step, with the demo measurement below."""

    PROCEED_LABEL = "Proceed to 3. Alternation"
    PROCEED_TIP = "Go on to 3. Alternation with these files (µs-ALEX data is converted there on arrival)."

    def load_demo(self, folder: Path | None = None) -> Path:
        """Write the simulated µs-ALEX measurement (:mod:`..demo`) into a fresh folder and add it to the files."""
        from ..demo import make_demo

        folder = Path(folder) if folder is not None else Path(tempfile.mkdtemp(prefix="alex_suite_demo_"))
        path = make_demo(folder)
        self.source.add_paths([path])
        self.message = f"Demo µs-ALEX measurement written to {path} (simulated; the answer is known)."
        if self.selected_index is None:
            self.selected_index = 0
        return path

    def _draw_summary_extra(self) -> None:
        im.separator()
        im.text_wrapped("No µs-ALEX measurement at hand?")
        if im.button("Load demo data"):
            self.track("demo")
            try:
                self.load_demo()
            except Exception as exc:  # noqa: BLE001 - shown in the window
                self.message = f"Could not write the demo data: {exc}"
        im.set_item_tooltip(
            "Write a simulated µs-ALEX measurement (100 µs alternation, donor channel 0, acceptor channel 1; low FRET, "
            "high FRET, donor-only and acceptor-only molecules) into a temporary folder and add it."
        )
        self.remember("demo")


# -- 3. Alternation ----------------------------------------------------------------------------------------- #
class AlternationStepApp(AlexAlternationApp):
    """The alternation step over :class:`AlexAlternationModel`; the detection runs in the background."""

    def __init__(self, model: AlexAlternationModel | None = None) -> None:
        self.model = model if model is not None else AlexAlternationModel()
        super().__init__(self.model)
        # In the hub the step has less height than in its own window: give the controls (period and gates under
        # the detection report) the room they need, the phase plot keeps the rest.
        for split in self.alternation_gui.docks.splits.values():
            split.ratio = 0.56

    @property
    def running(self) -> bool:
        return self.model.running

    def animating(self) -> bool:
        return self.model.running or self.model._gate_edit_at is not None or super().animating()

    def _render(self) -> None:
        self.model.poll()
        super()._render()

    def files_dropped(self, paths) -> bool:
        paths = [Path(p) for p in paths or ()]
        if not paths:
            return False
        self.model.set_files(paths)
        return True

    on_files_dropped = files_dropped


# -- Titration ---------------------------------------------------------------------------------------------- #
class TitrationStep:
    """What the titration view reads beside its model: the file choosers and the workflow hand-off (no Qt)."""

    def __init__(self, model: TitrationViewModel | None = None) -> None:
        self.model = model if model is not None else TitrationViewModel()
        self.dialog = _Dialog()
        self.model.request_files = self._choose_files
        self.message = ""

    def _choose_files(self) -> list[str]:
        """Open the burst-file chooser; the chosen files are added when it closes (nothing to return now)."""
        self.dialog.open(
            "Add burst files (one per concentration)",
            "open",
            self.model.add_files,
            filters=[("Burst tables", BURST_PATTERNS), ("All files", ["*"])],
        )
        return []

    def export_csv(self, path: str | None = None) -> Path | None:
        """Write the result to *path*; without one, ask where (the file chooser in save mode)."""
        if path is None:
            self.dialog.open("Export titration", "save", lambda p: self.export_csv(p[0]),
                             filters=[("CSV", ["*.csv"])], filename="titration.csv")
            return None
        try:
            written = self.model.export_csv(path)
        except Exception as exc:  # noqa: BLE001 - shown in the result block
            self.model.summary = f"Export failed: {exc}"
            logger.warning(f"ALEX Suite: titration export failed - {exc}")
            return None
        self.model.summary = (self.model.summary or "") + f"\n\nExported to {written}"
        return Path(written)

    def set_burst_files(self, files) -> None:
        """Seed the series from the pipeline's burst files, only while the table is empty (typed concentrations
        are never replaced by a context refresh)."""
        if self.model.rows or not files:
            return
        self.model.add_files([str(p) for p in files])

    def set_corrections(self, *, gamma: float | None = None, beta: float | None = None) -> None:
        """Adopt γ / β from the Accurate FRET step."""
        if gamma is not None:
            self.model.gamma = float(gamma)
        if beta is not None:
            self.model.beta = float(beta)
        self.model.notify("changed")


class TitrationStepApp(TitrationApp):
    """The titration step over :class:`TitrationStep`."""

    def __init__(self, step: TitrationStep | None = None) -> None:
        self.step = step if step is not None else TitrationStep()
        super().__init__(self.step)

    @property
    def model(self) -> TitrationViewModel:
        return self.step.model

    def _render(self) -> None:
        super()._render()
        w, h = im.get_main_viewport().size
        self.step.dialog.draw((0.0, 0.0, float(w), float(h)))

    def files_dropped(self, paths) -> bool:
        paths = [str(p) for p in paths or ()]
        if paths:
            self.model.add_files(paths)
        return bool(paths)

    on_files_dropped = files_dropped


# -- Export (ALEX-Suite CSV) -------------------------------------------------------------------------------- #
class ExportStepApp(LegacyExportApp):
    """The ALEX-Suite CSV export over :class:`LegacyExportModel`."""

    def __init__(self, model: LegacyExportModel | None = None) -> None:
        self.model = model if model is not None else LegacyExportModel()
        super().__init__(self.model)

    def set_burst_files(self, files) -> None:
        self.model.set_burst_files(files)
        gui = self.export_gui
        gui.selected_index = min(gui.selected_index, max(0, len(self.model.bur_files) - 1))

    def files_dropped(self, paths) -> bool:
        paths = [str(p) for p in paths or ()]
        if paths:
            self.set_burst_files(paths)
        return bool(paths)

    on_files_dropped = files_dropped


__all__ = [
    "AlexDataSelectionApp",
    "AlternationStepApp",
    "ExportStepApp",
    "TitrationStep",
    "TitrationStepApp",
]
