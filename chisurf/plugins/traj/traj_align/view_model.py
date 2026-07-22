"""Qt-free view-model backing the Align-Trajectory tool.

:class:`AlignTrajectoryViewModel` holds the interactive state (the source
trajectory path, the atom selection used for the superposition, the read
stride, and a running log) and performs the actual work — superposing every
frame of a trajectory onto its first frame through :mod:`mdtraj` and streaming
the result to a new HDF5 trajectory. It is deliberately free of Qt so the logic
can be unit-tested headlessly; the GUI (``sections`` + ``widget``) owns all Qt
concerns and drives this model.

Mirrors :class:`chisurf.plugins.traj.traj_save_topology.view_model.SaveTopologyViewModel`.
"""

from __future__ import annotations

import html
import logging
import pathlib
import time
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "align_trajectory.view.json"


class AlignTrajectoryViewModel:
    """State + logic for the Align-Trajectory tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``align_trajectory.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.trajectory_filename: str = ""
        #: Comma-separated atom ids used as the superposition reference set.
        self.atom_selection: str = ""
        #: Read every ``stride``-th frame of the source trajectory.
        self.stride: int = 1
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
                logger.warning("AlignTrajectory observer failed", exc_info=True)

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

    # ── derived state ───────────────────────────────────────────────────
    def atom_indices(self) -> np.ndarray:
        """Parse :attr:`atom_selection` into an ``int32`` array of atom ids.

        An empty or malformed selection yields an empty array (mdtraj then
        superposes on all atoms).
        """
        return np.fromstring(self.atom_selection, dtype=np.int32, sep=",")

    # ── file wiring ─────────────────────────────────────────────────────
    def set_trajectory(self, filename: str) -> None:
        """Set the source trajectory path and notify observers."""
        self.trajectory_filename = str(filename)
        self.append_log(f"Trajectory: {self.trajectory_filename}")
        self._notify("loaded")

    # ── action ──────────────────────────────────────────────────────────
    def save_aligned(self, target_filename: str) -> None:
        """Superpose every frame on frame 0 and stream the result to *target_filename*.

        The trajectory is read in chunks (so it need not fit in memory), each
        chunk superposed onto the first frame using :meth:`atom_indices`, and the
        aligned coordinates appended to a fresh HDF5 trajectory.

        Parameters
        ----------
        target_filename : str
            Destination ``.h5`` trajectory path.
        """
        import mdtraj as md
        import tables

        filename = self.trajectory_filename
        if not filename:
            self.append_log("No trajectory selected")
            return

        atom_indices = self.atom_indices()
        stride = int(self.stride)
        chunk_size = 1000

        self.append_log(f"Aligning {filename} (stride={stride})")
        frame_0 = md.load_frame(filename, 0)
        target_traj = md.Trajectory(
            xyz=np.empty((0, frame_0.n_atoms, 3)), topology=frame_0.topology
        )
        target_traj.save(target_filename)

        table = tables.open_file(target_filename, "a")
        try:
            for i, chunk in enumerate(md.iterload(filename, chunk=chunk_size, stride=stride)):
                chunk = chunk.superpose(frame_0, frame=0, atom_indices=atom_indices)
                xyz = chunk.xyz.copy()
                table.root.coordinates.append(xyz)
                table.root.time.append(
                    np.arange(i * chunk_size, i * chunk_size + xyz.shape[0], dtype=np.float32)
                )
        finally:
            table.close()
        self.append_log(f"Aligned trajectory saved: {target_filename}")


__all__ = ["AlignTrajectoryViewModel"]
