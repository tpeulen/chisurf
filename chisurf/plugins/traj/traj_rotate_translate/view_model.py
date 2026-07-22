"""Qt-free view-model backing the Rotate/Translate-Trajectory tool.

:class:`RotateTranslateViewModel` holds the interactive state (the source
trajectory path, a 3x3 rotation matrix, a 3-vector translation, the read stride,
and a running log) and performs the actual work — applying a rigid-body rotation
and translation to every frame of a trajectory through :mod:`mdtraj` and
streaming the result to a new HDF5 trajectory. It is deliberately free of Qt so
the logic can be unit-tested headlessly; the GUI (``sections`` + ``widget``) owns
all Qt concerns and drives this model.

Mirrors :class:`chisurf.plugins.traj.traj_align.view_model.AlignTrajectoryViewModel`.
"""

from __future__ import annotations

import html
import logging
import pathlib
import time
from collections.abc import Callable

import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "rotate_translate.view.json"


class RotateTranslateViewModel:
    """State + logic for the Rotate/Translate-Trajectory tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``rotate_translate.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.trajectory_filename: str = ""
        #: 3x3 rotation matrix multiplied onto every frame's coordinates.
        self.rotation_matrix: np.ndarray = np.eye(3, dtype=np.float32)
        #: Raw 3-vector translation as entered by the user (see :meth:`save_rotated_translated`).
        self.translation_vector: np.ndarray = np.zeros(3, dtype=np.float32)
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
                logger.warning("RotateTranslate observer failed", exc_info=True)

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
    def set_trajectory(self, filename: str) -> None:
        """Set the source trajectory path and notify observers."""
        self.trajectory_filename = str(filename)
        self.append_log(f"Trajectory: {self.trajectory_filename}")
        self._notify("loaded")

    def set_rotation_matrix(self, matrix) -> None:
        """Set the 3x3 rotation matrix and notify observers (re-syncs the editors)."""
        self.rotation_matrix = np.asarray(matrix, dtype=np.float32)
        self._notify("fields")

    def set_translation_vector(self, vector) -> None:
        """Set the raw 3-vector translation and notify observers (re-syncs the editors)."""
        self.translation_vector = np.asarray(vector, dtype=np.float32)
        self._notify("fields")

    # ── action ──────────────────────────────────────────────────────────
    def save_rotated_translated(self, target_filename: str) -> None:
        """Rotate + translate every frame and stream the result to *target_filename*.

        The trajectory is read in chunks (so it need not fit in memory); each
        chunk is rotated by :attr:`rotation_matrix` and translated by
        :attr:`translation_vector` divided by ``10.0`` (matching the historic
        Angstrom-to-nanometre convention of this tool), and the transformed
        coordinates are appended to a fresh HDF5 trajectory.

        Parameters
        ----------
        target_filename : str
            Destination ``.h5`` trajectory path.
        """
        import mdtraj as md
        import tables

        from chisurf.core.structure import rotate, translate

        filename = self.trajectory_filename
        if not filename:
            self.append_log("No trajectory selected")
            return

        rotation_matrix = np.asarray(self.rotation_matrix, dtype=np.float32)
        translation_vector = np.asarray(self.translation_vector, dtype=np.float32) / 10.0
        stride = int(self.stride)
        chunk_size = 1000

        try:
            self.append_log(f"Rotating/translating {filename} (stride={stride})")
            frame_0 = md.load_frame(filename, 0)
            self.append_log(f"Loaded first frame with {frame_0.n_atoms} atoms")
            target_traj = md.Trajectory(
                xyz=np.empty((0, frame_0.n_atoms, 3)), topology=frame_0.topology
            )
            target_traj.save(target_filename)

            table = tables.open_file(target_filename, "a")
            try:
                for i, chunk in enumerate(md.iterload(filename, chunk=chunk_size, stride=stride)):
                    xyz = chunk.xyz.copy()
                    rotate(xyz, rotation_matrix)
                    translate(xyz, translation_vector)
                    table.root.coordinates.append(xyz)
                    table.root.time.append(
                        np.arange(i * chunk_size, i * chunk_size + xyz.shape[0], dtype=np.float32)
                    )
                    if (i + 1) % 10 == 0:
                        self.append_log(f"Processed {i + 1} chunks")
            finally:
                table.close()
            self.append_log(f"Rotated/translated trajectory saved: {target_filename}")
        except Exception as exc:  # noqa: BLE001
            self.append_log(f"Save failed: {exc}")
            raise


__all__ = ["RotateTranslateViewModel"]
