"""Qt-free view-model backing the Remove-Clashed-Frames tool.

:class:`RemoveClashesViewModel` holds the interactive state (the source
trajectory path, an atom-selection expression, the read stride, the
minimum clash distance and a running log) and performs the actual work —
streaming a trajectory in chunks, dropping every frame that contains an
atom-atom distance below the minimum, and writing the surviving frames to a
fresh HDF5 trajectory. It is deliberately free of Qt so the logic can be
unit-tested headlessly; the GUI (``sections`` + ``widget``) owns all Qt concerns
and drives this model.

The module-level :func:`below_min_distance` numba kernel is kept verbatim from
the former hand-built widget and does the per-frame clash test.

Mirrors :class:`chisurf.plugins.traj.traj_align.view_model.AlignTrajectoryViewModel`.
"""

# The ``below_min_distance`` kernel below is kept verbatim from the former
# hand-built widget, including its legacy Sphinx-style docstring; exempt the two
# pydocstyle rules it trips (summary/description split and imperative mood).
# ruff: noqa: D205, D401
from __future__ import annotations

import html
import logging
import pathlib
import time
from collections.abc import Callable

import numba as nb
import numpy as np

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "remove_clashes.view.json"


@nb.jit(nopython=True)
def below_min_distance(
    xyz: np.ndarray,
    min_distance: float,
    atom_list: np.ndarray = np.empty(0, dtype=np.int32),
) -> np.ndarray:
    """Takes the xyz-coordinates (frame, atom, xyz) of a trajectory as an argument an returns a vector of booleans
    of length of the number of frames. The bool is False if the frame contains a atomic distance smaller than the
    min distance.

    :param xyz: numpy array
        The coordinates (frame fit_index, atom fit_index, coord)

    :param min_distance: float
        Minimum distance if a distance

    :return: numpy-array
        If a atom-atom distance within a frame is smaller than min_distance the value within the array is True otherwise
        it is False.

    """
    n_frames = xyz.shape[0]
    re = np.zeros(n_frames, dtype=np.uint8)

    atoms = np.arange(xyz.shape[1]) if atom_list.shape[0] == 0 else atom_list
    n_atoms = atoms.shape[0]
    min_distance2 = min_distance**2.0

    for i_frame in range(n_frames):
        for i in range(n_atoms):
            i_atom = atoms[i]
            x1 = xyz[i_frame, i_atom, 0]
            y1 = xyz[i_frame, i_atom, 1]
            z1 = xyz[i_frame, i_atom, 2]

            for j in range(i + 1, n_atoms):
                j_atom = atoms[j]

                x2 = xyz[i_frame, j_atom, 0]
                y2 = xyz[i_frame, j_atom, 1]
                z2 = xyz[i_frame, j_atom, 2]

                dx = (x1 - x2) ** 2
                dy = (y1 - y2) ** 2
                dz = (z1 - z2) ** 2

                if dx + dy + dz < min_distance2:
                    re[i_frame] += 1
                    break

            if re[i_frame] > 0:
                break
    return re


class RemoveClashesViewModel:
    """State + logic for the Remove-Clashed-Frames tool (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``remove_clashes.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        self.trajectory_filename: str = ""
        # DCD and XTC store coordinates only, so the atom names have to come
        # from somewhere. Empty is fine for a self-describing file.
        self.topology_filename: str = ""
        #: atom-selection expression (e.g. ``"name CA"``) selecting the
        #: atoms whose pairwise distances are tested for clashes.
        self.atom_selection: str = "name CA and resSeq 1 to 256"
        #: Read every ``stride``-th frame of the source trajectory.
        self.stride: int = 1
        #: Raw minimum-distance spin value; the consumed threshold (in the
        #: trajectory's length unit, nm) is this value divided by ten — see
        #: :meth:`min_distance_nm`.
        self.min_distance: float = 2.85
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
                logger.warning("RemoveClashes observer failed", exc_info=True)

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
    def min_distance_nm(self) -> float:
        """Return the consumed clash threshold: the raw spin value divided by ten.

        The GUI shows the raw spin value (historically labelled in Ångström);
        the kernel consumes it after a ``/ 10.0`` conversion, matching the
        former widget's ``min_distance`` getter.
        """
        return float(self.min_distance) / 10.0

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
    def save_clash_free(self, target_filename: str) -> None:
        """Stream the trajectory and write only the clash-free frames to *target_filename*.

        The trajectory is read in chunks (so it need not fit in memory). For each
        chunk, :func:`below_min_distance` flags frames whose selected atoms come
        closer than :meth:`min_distance_nm`; frames with a flag ``< 1`` are kept
        and appended to a fresh HDF5 trajectory.

        The kept frames carry their **own** source times rather than a running
        write counter, so the gaps left by the discarded frames — and the read
        stride — stay visible on the time axis (RF-708).

        Parameters
        ----------
        target_filename : str
            Destination ``.h5`` trajectory path.
        """
        from chisurf.core.fio.trajectory import DCDWriter
        from chisurf.core.structure import trajectory_data as md

        topology = self.topology_filename or None

        filename = self.trajectory_filename
        if not filename:
            self.append_log("No trajectory selected")
            return

        stride = int(self.stride)
        min_distance = self.min_distance_nm()
        chunk_size = 1000

        self.append_log(f"Removing clashes: {filename} (stride={stride})")
        frame_0 = md.load_frame(filename, 0, top=topology)
        atom_list = frame_0.top.select(self.atom_selection)

        writer = None
        kept_times: list[float] = []
        try:
            for chunk in md.iterload(filename, chunk=chunk_size, stride=stride,
                                     top=topology):
                xyz = chunk.xyz.copy()
                frames_below = below_min_distance(
                    xyz=xyz, min_distance=min_distance, atom_list=atom_list
                )
                selection = np.where(frames_below < 1)[0]
                xyz_clash_free = np.take(xyz, selection, axis=0)
                if writer is None:
                    # Frames are dropped here, so the surviving ones are no
                    # longer evenly spaced; the header can only record one
                    # interval, so it records the source's.
                    spacing = (float(chunk.time[1] - chunk.time[0])
                               if chunk.n_frames > 1 else 1.0)
                    writer = DCDWriter(target_filename, n_atoms=frame_0.n_atoms,
                                       delta=spacing or 1.0)
                if len(xyz_clash_free):
                    writer.write(xyz_clash_free * 10.0)
                    kept_times.extend(
                        np.asarray(chunk.time, dtype=np.float64)[selection].tolist())
        finally:
            if writer is not None:
                # Dropping frames leaves gaps, and a DCD header can only carry
                # one uniform interval -- so the real axis goes beside the
                # file. Renumbering the survivors 0, 1, ... would hide both the
                # removals and the read stride from every later reader
                # (RF-708).
                writer.write_times(kept_times)
                writer.close()
        self.append_log(f"Clash-free trajectory saved: {target_filename}")


__all__ = ["RemoveClashesViewModel", "below_min_distance"]
