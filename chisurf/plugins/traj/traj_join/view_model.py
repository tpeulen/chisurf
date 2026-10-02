"""Qt-free view-model backing the Join-Trajectories tool.

:class:`JoinTrajectoriesViewModel` holds the interactive state (the two source
trajectory paths, the join mode, the per-trajectory time-reversal flags, the
read chunk size, and a running log) and performs the actual work — joining two
trajectories either along the time axis (append frames, ``traj_1.join(traj_2)``)
or along the atom axis (stack, ``traj_1.stack(traj_2)``) through :mod:`mdtraj`
and streaming the result to a new HDF5 trajectory. It is deliberately free of Qt
so the logic can be unit-tested headlessly; the GUI (``sections`` + ``widget``)
owns all Qt concerns and drives this model.

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

_VIEW_JSON = pathlib.Path(__file__).parent / "join_trajectories.view.json"


class JoinTrajectoriesViewModel:
    """State + logic for the Join-Trajectories tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``join_trajectories.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.trajectory_filename_1: str = ""
        # DCD stores coordinates only, so the atom names have to come
        # from somewhere. Empty is fine for a self-describing file.
        self.topology_filename: str = ""
        self.trajectory_filename_2: str = ""
        #: Join along the time axis (``"time"``) or the atom axis (``"atoms"``).
        self.join_mode: str = "time"
        #: Reverse each read chunk of trajectory 1/2 in time before concatenation.
        self.reverse_traj_1: bool = False
        self.reverse_traj_2: bool = False
        #: Trajectories are read piecewise to save memory; the chunk size sets the
        #: number of frames per read.
        self.chunk_size: int = 1000
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
                logger.warning("JoinTrajectories observer failed", exc_info=True)

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

    def log_text(self) -> list[str]:
        """Return the raw log lines (bound by the native app; no HTML)."""
        return list(self._log)

    # ── file wiring ─────────────────────────────────────────────────────
    def set_topology(self, filename: str) -> None:
        """Set the topology (PDB) that names the atoms, and notify observers."""
        self.topology_filename = str(filename)
        self.append_log(f"Topology: {self.topology_filename}")
        self._notify("loaded")

    def set_trajectory_1(self, filename: str) -> None:
        """Set the first source trajectory path and notify observers."""
        self.trajectory_filename_1 = str(filename)
        self.append_log(f"Trajectory 1: {self.trajectory_filename_1}")
        self._notify("loaded")

    def set_trajectory_2(self, filename: str) -> None:
        """Set the second source trajectory path and notify observers."""
        self.trajectory_filename_2 = str(filename)
        self.append_log(f"Trajectory 2: {self.trajectory_filename_2}")
        self._notify("loaded")

    # ── action ──────────────────────────────────────────────────────────
    def save_joined(self, target_filename: str) -> None:
        """Join the two trajectories and write the result to *target_filename*.

        In ``"time"`` mode every frame of trajectory 1 is followed by every
        frame of trajectory 2 (the two must have the same atoms); in
        ``"atoms"`` mode frame *i* of both is placed side by side as one system
        (the two must have the same number of frames). :attr:`reverse_traj_1`
        / :attr:`reverse_traj_2` reverse a whole trajectory in time before the
        join. The result is written in blocks of :attr:`chunk_size` frames.

        Both inputs are read whole, as the loader decodes a file in one pass
        anyway. The join used to pair the two in read chunks, which in time
        mode interleaved them (A0-99, B0-99, A100-199, ...), truncated the
        longer one, and reversed each chunk instead of the trajectory.

        Parameters
        ----------
        target_filename : str
            Destination ``.dcd`` path.

        Raises
        ------
        ValueError
            If the atom counts (time mode) or frame counts (atoms mode) differ.
        """
        from chisurf.core.fio.trajectory import DCDWriter
        from chisurf.core.structure import trajectory_data as md

        topology = self.topology_filename or None

        fn1 = self.trajectory_filename_1
        fn2 = self.trajectory_filename_2
        if not fn1 or not fn2:
            self.append_log("Two trajectories are required")
            return
        if self.join_mode not in ("time", "atoms"):  # pragma: no cover - guarded by the choice section
            raise ValueError(f"unknown join_mode {self.join_mode!r}")

        self.append_log(f"Join mode: {self.join_mode}")
        self.append_log(f"Trajectory 1: {fn1}")
        self.append_log(f"Trajectory 2: {fn2}")

        traj_1 = md.load(fn1, top=topology)
        traj_2 = md.load(fn2, top=topology)
        xyz_1 = traj_1.xyz[::-1] if self.reverse_traj_1 else traj_1.xyz
        xyz_2 = traj_2.xyz[::-1] if self.reverse_traj_2 else traj_2.xyz
        block = self._block()
        if self.join_mode == "time":
            if traj_1.n_atoms != traj_2.n_atoms:
                raise ValueError(f"Joining in time needs the same atoms: trajectory 1 has {traj_1.n_atoms}, "
                                 f"trajectory 2 has {traj_2.n_atoms}")
            n_atoms, n_frames = traj_1.n_atoms, traj_1.n_frames + traj_2.n_frames
            pieces = (xyz[start:start + block] for xyz in (xyz_1, xyz_2) for start in range(0, len(xyz), block))
        else:
            if traj_1.n_frames != traj_2.n_frames:
                raise ValueError(f"Joining by atoms needs the same number of frames: trajectory 1 has "
                                 f"{traj_1.n_frames}, trajectory 2 has {traj_2.n_frames}")
            n_atoms, n_frames = traj_1.n_atoms + traj_2.n_atoms, traj_1.n_frames
            pieces = (np.concatenate((xyz_1[start:start + block], xyz_2[start:start + block]), axis=1)
                      for start in range(0, n_frames, block))

        with DCDWriter(target_filename, n_atoms=n_atoms) as writer:
            for piece in pieces:
                writer.write(piece)
        self.append_log(f"Wrote {n_frames} frames of {n_atoms} atoms")
        self.append_log(f"Joined trajectory saved: {target_filename}")

    def _block(self) -> int:
        """Frames per written block (at least one)."""
        return max(1, int(self.chunk_size))


__all__ = ["JoinTrajectoriesViewModel"]
