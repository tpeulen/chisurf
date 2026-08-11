"""Qt-free view-model backing the Save-Topology tool.

:class:`SaveTopologyViewModel` holds the interactive state (the loaded
trajectory path and a running log) and performs the actual work — loading the
first frame of a trajectory through ChiSurf's trajectory readers and writing it out as a
topology/structure file. It is deliberately free of Qt so the logic can be
unit-tested headlessly; the GUI (``sections`` + ``widget``) owns all Qt concerns
and drives this model.

Mirrors :class:`chisurf.plugins.tttr.tttr_splitter.gui.view_model.SplitterViewModel`.
"""

from __future__ import annotations

import html
import logging
import pathlib
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "save_topology.view.json"


class SaveTopologyViewModel:
    """State + logic for the Save-Topology tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``save_topology.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.trajectory_filename: str = ""
        # DCD stores coordinates only, so the atom names have to come
        # from somewhere. Empty is fine for a self-describing file.
        self.topology_filename: str = ""
        self._log: list[str] = []
        self._observers: list[Callable[[str], None]] = []
        self.append_log("Ready")

    # ── observer plumbing ───────────────────────────────────────────────
    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a ``callback(event)`` fired on state changes."""
        self._observers.append(callback)

    def _notify(self, event: str) -> None:
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover - observers are best-effort
                logger.warning("SaveTopology observer failed", exc_info=True)

    # ── log ─────────────────────────────────────────────────────────────
    def append_log(self, message: str) -> None:
        """Append a timestamped line to the log and notify observers."""
        timestamp = time.strftime("%H:%M:%S")
        self._log.append(f"[{timestamp}] {message}")
        self._notify("log")

    def log_html(self) -> str:
        """Render the log as a monospace HTML block (bound by the ``info`` section)."""
        lines = "<br>".join(html.escape(line) for line in self._log)
        return f"<pre style='margin:0;font-family:monospace'>{lines}</pre>"

    # ── file wiring ─────────────────────────────────────────────────────
    def set_topology(self, filename: str) -> None:
        """Set the topology (PDB) that names the atoms, and notify observers."""
        self.topology_filename = str(filename)
        self.append_log(f"Topology: {self.topology_filename}")
        self._notify("loaded")

    def set_trajectory(self, filename: str) -> None:
        """Set the source trajectory path and notify observers."""
        self.trajectory_filename = str(filename)
        self.append_log(f"Trajectory: {self.trajectory_filename}")
        self._notify("loaded")

    # ── action ──────────────────────────────────────────────────────────
    def save_topology(self, target_filename: str) -> None:
        """Load the first frame of the trajectory and write it to *target_filename*.

        Parameters
        ----------
        target_filename : str
            Destination structure file (e.g. a ``.pdb`` path).
        """
        from chisurf.core.structure import trajectory_data as md

        filename = self.trajectory_filename
        if not filename:
            self.append_log("No trajectory selected")
            return
        try:
            self.append_log(f"Loading first frame: {filename}")
            frame_0 = md.load_frame(filename, 0, top=self.topology_filename or None)
            self.append_log(f"Saving topology to: {target_filename}")
            frame_0.save(target_filename)
            self.append_log("Topology saved")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Save failed: {exc}")
            raise


__all__ = ["SaveTopologyViewModel"]
