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
import re
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
        # DCD and XTC store coordinates only, so the atom names have to come
        # from somewhere. Empty is fine for a self-describing file.
        self.topology_filename: str = ""
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
    def atom_indices(self) -> np.ndarray | None:
        """Parse :attr:`atom_selection` into an ``int32`` array of atom ids.

        Returns
        -------
        numpy.ndarray or None
            The selected atom ids, or ``None`` when the selection is empty.
            ``None`` is what :meth:`mdtraj.Trajectory.superpose` reads as "use
            every atom"; an empty *array* instead superposes on **no** atoms,
            which leaves the Theobald solver unconverged and every rotated
            coordinate ``NaN``.

        Raises
        ------
        ValueError
            If the selection holds a token that is not an atom id. Silently
            dropping such a token would superpose on fewer atoms than asked
            for — or, for a wholly non-numeric selection, on none at all.
        """
        tokens = [t for t in re.split(r"[,;\s]+", self.atom_selection.strip()) if t]
        if not tokens:
            return None
        indices: list[int] = []
        bad: list[str] = []
        for token in tokens:
            try:
                indices.append(int(token))
            except ValueError:
                bad.append(token)
        if bad:
            raise ValueError(
                "Atom selection must be a comma-separated list of atom ids; "
                f"cannot parse {', '.join(repr(t) for t in bad)}"
            )
        return np.asarray(indices, dtype=np.int32)

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
    def save_aligned(self, target_filename: str) -> None:
        """Superpose every frame on frame 0 and stream the result to *target_filename*.

        The trajectory is read in chunks (so it need not fit in memory), each
        chunk superposed onto the first frame using :meth:`atom_indices`, and the
        aligned coordinates appended to a fresh DCD.

        Aligning changes coordinates, not time: each chunk's own ``time`` array
        is carried through unchanged, so a strided read keeps the source frame
        times (``0, 32, 64, …`` at ``stride=32``) instead of a write-index
        counter that would claim unit frame spacing (RF-708).

        Parameters
        ----------
        target_filename : str
            Destination ``.dcd`` path.
        """
        from chisurf.core.fio.trajectory import DCDWriter
        from chisurf.core.structure import trajectory_data as md

        topology = self.topology_filename or None

        filename = self.trajectory_filename
        if not filename:
            self.append_log("No trajectory selected")
            return

        try:
            atom_indices = self.atom_indices()
        except ValueError as error:
            self.append_log(str(error))
            return
        stride = int(self.stride)
        chunk_size = 1000

        self.append_log(f"Aligning {filename} (stride={stride})")
        frame_0 = md.load_frame(filename, 0, top=topology)
        # Stream straight into the DCD rather than writing an empty container
        # and appending to it: the frame count in the header is patched on
        # close, so nothing has to be reserved up front.
        writer = None
        try:
            for chunk in md.iterload(filename, chunk=chunk_size, stride=stride,
                                     top=topology):
                chunk = chunk.superpose(frame_0, frame=0, atom_indices=atom_indices)
                if writer is None:
                    # Open on the first chunk so the frame spacing can be taken
                    # from the source rather than assumed: a strided read must
                    # keep the real spacing, not count frames (RF-708). DCD
                    # stores that as the timestep between saved frames.
                    spacing = (float(chunk.time[1] - chunk.time[0])
                               if chunk.n_frames > 1 else 1.0)
                    writer = DCDWriter(target_filename, n_atoms=frame_0.n_atoms,
                                       delta=spacing or 1.0)
                writer.write(chunk.xyz * 10.0)     # nm in memory, Angstrom on disk
        finally:
            if writer is not None:
                writer.close()
        self.append_log(f"Aligned trajectory saved: {target_filename}")


__all__ = ["AlignTrajectoryViewModel"]
