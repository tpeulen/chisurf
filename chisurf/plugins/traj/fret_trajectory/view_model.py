"""Qt-free view-model backing the Structure-to-Transfer (Trajectory→FRET) tool.

:class:`FretTrajectoryViewModel` holds the interactive state — the source
trajectory file(s), the donor / acceptor dipole atom-index pairs, the frame
time-step and the dye parameters (Förster radius, donor lifetime, dipole
averaging, read stride) — plus a running log, and performs the actual work by
driving a :class:`~.traj2fret.CalculateTransfer` engine over the trajectory to
produce the FRET/transfer time-series and write the CSV output.

It is deliberately free of Qt so the compute can be unit-tested headlessly; the
GUI (``sections`` + ``gui``) owns all Qt concerns (the trajectory picker, the
four :class:`~chisurf.gui.widgets.pdb.PDBSelector` atom pickers and the Process
button) and drives this model. Mirrors
:class:`chisurf.plugins.traj.traj_align.view_model.AlignTrajectoryViewModel`.
"""

from __future__ import annotations

import html
import logging
import pathlib
import tempfile
import time
from collections.abc import Callable

import numpy as np

from .traj2fret import CalculateTransfer

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "structure2transfer.view.json"


class FretTrajectoryViewModel:
    """State + logic for the Trajectory→FRET tool (no Qt).

    The heavy compute lives in an owned :class:`~.traj2fret.CalculateTransfer`
    engine that is fed plain values (donor/acceptor atom indices, time-step,
    paths); the model never touches Qt widgets or dialogs.
    """

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``structure2transfer.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self, verbose: bool = False) -> None:
        #: Compute engine (Qt-free); the model proxies its parameters.
        self._engine = CalculateTransfer(verbose=verbose)
        self._engine.donor = (0, 1)
        self._engine.acceptor = (2, 3)
        #: List of trajectory files to process (first is the "current" one).
        self.filenames: list[str] = []
        #: Structured coordinate array of the first frame (drives the atom pickers).
        self.pdb: np.ndarray | None = None
        #: Path of the temporary PDB holding the trajectory topology.
        self.topology_file: str = ""
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
                logger.warning("FretTrajectory observer failed", exc_info=True)

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

    # ── proxied engine parameters ───────────────────────────────────────
    @property
    def trajectory_file(self) -> str:
        """Path of the current (first) trajectory file."""
        return self._engine.trajectory_file or ""

    @trajectory_file.setter
    def trajectory_file(self, value: str) -> None:
        self._engine.trajectory_file = str(value)

    @property
    def donor(self) -> tuple:
        """Donor dipole atom-index pair ``(i, j)``."""
        return self._engine.donor

    @donor.setter
    def donor(self, value) -> None:
        self._engine.donor = tuple(value)

    @property
    def acceptor(self) -> tuple:
        """Acceptor dipole atom-index pair ``(i, j)``."""
        return self._engine.acceptor

    @acceptor.setter
    def acceptor(self, value) -> None:
        self._engine.acceptor = tuple(value)

    @property
    def t_step(self) -> float:
        """Time between successive trajectory frames in nanoseconds."""
        return self._engine.t_step

    @t_step.setter
    def t_step(self, value: float) -> None:
        self._engine.t_step = float(value)

    @property
    def stride(self) -> int:
        """Read every ``stride``-th frame of the source trajectory."""
        return int(self._engine.stride)

    @stride.setter
    def stride(self, value: int) -> None:
        self._engine.stride = int(value)

    @property
    def forster_radius(self) -> float:
        """Förster radius R0 of the dye pair in Ångström."""
        return float(self._engine.forster_radius)

    @forster_radius.setter
    def forster_radius(self, value: float) -> None:
        self._engine.forster_radius = float(value)

    @property
    def tau0(self) -> float:
        """Donor fluorescence lifetime (in absence of FRET) in nanoseconds."""
        return float(self._engine.tau0)

    @tau0.setter
    def tau0(self, value: float) -> None:
        self._engine.tau0 = float(value)

    @property
    def dipoles(self) -> bool:
        """If True use two atoms per dye and compute the orientation factor kappa2."""
        return bool(self._engine.dipoles)

    @dipoles.setter
    def dipoles(self, value: bool) -> None:
        self._engine.dipoles = bool(value)

    # ── trajectory / topology wiring ────────────────────────────────────
    def set_trajectory_files(self, filenames) -> None:
        """Set the trajectory file list, load the topology and notify observers.

        The first frame of the first file is written to a temporary PDB and read
        back into a structured coordinate array (:attr:`pdb`) that drives the
        donor/acceptor atom pickers.

        Parameters
        ----------
        filenames : list of str
            One or more ``.h5`` trajectory paths.
        """
        filenames = [str(f) for f in filenames if str(f)]
        if not filenames:
            return
        self.filenames = filenames
        self.trajectory_file = filenames[0]
        self.append_log(f"Loaded {len(filenames)} trajectory file(s)")
        self._load_topology(self.trajectory_file)
        self._notify("loaded")

    def set_trajectory(self, filename: str) -> None:
        """Set a single trajectory file (convenience wrapper)."""
        self.set_trajectory_files([filename])

    def _load_topology(self, trajectory_file: str) -> None:
        """Extract the first frame of *trajectory_file* into :attr:`pdb`."""
        from chisurf.core.structure import trajectory_data as md

        from chisurf.core.fio.structure import coordinates

        frame0 = md.load_frame(trajectory_file, 0)
        _, tmp = tempfile.mkstemp(suffix=".pdb")
        frame0.save(tmp)
        self.topology_file = tmp
        self.pdb = coordinates.read(tmp, verbose=False)

    # ── action ──────────────────────────────────────────────────────────
    def calc(self, output_file: str, **kwargs) -> np.ndarray:
        """Compute the FRET/transfer time-series for every trajectory file.

        A single trajectory writes its table to *output_file*; several
        trajectories write to ``<output_file>.<index>.csv``. The stacked result
        of the last processed file is returned.

        Parameters
        ----------
        output_file : str
            Destination CSV path.
        **kwargs
            Forwarded to the :class:`~.traj2fret.CalculateTransfer` engine (e.g.
            ``verbose``).

        Returns
        -------
        np.ndarray
            Array of shape ``(n_frames, 6)`` with columns
            ``[frame, time[ns], RDA[Ang], kappa, kappa2, FRETrate[1/ns]]`` for the
            last processed trajectory (empty array if nothing was processed).
        """
        filenames = self.filenames or ([self.trajectory_file] if self.trajectory_file else [])
        if not filenames:
            self.append_log("No trajectory selected")
            return np.empty((0, 6), dtype=np.float64)

        result = np.empty((0, 6), dtype=np.float64)
        for index, filename in enumerate(filenames, start=1):
            self.append_log(f"Processing {index}/{len(filenames)}: {filename}")
            target = output_file if len(filenames) == 1 else f"{output_file}.{index}.csv"
            result = self._engine.calc(
                output_file=target,
                trajectory_file=filename,
                verbose=kwargs.get("verbose", self._engine.verbose),
            )
            self.append_log(f"Finished {filename} ({result.shape[0]} frames)")
        return result

    # convenience alias
    process = calc


__all__ = ["FretTrajectoryViewModel"]
