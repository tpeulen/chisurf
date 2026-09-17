"""Qt-free view-model backing the Potential-Energy calculator.

:class:`PotentialEnergyViewModel` holds the interactive state (the source DCD
trajectory and its topology, the read stride, the selected potential type and weight, and a
:class:`~chisurf.core.structure.Universe` collecting the configured potentials)
and performs the actual work — iterating a trajectory frame by frame, scoring
every configured potential for each frame and writing the per-potential energies
to a CSV file. It is deliberately free of Qt so the logic can be unit-tested
headlessly; the GUI (``sections`` + ``widget``) owns all Qt concerns and drives
this model.

The concrete potential *objects* added through :meth:`add_potential` originate
from the Qt :data:`chisurf.gui.widgets.structure.potentialDict` registry (the
parameter editors double as the potentials), but this model only ever calls
their Qt-free ``getEnergy`` / ``name`` / ``structure`` interface, so the compute
path stays Qt-free. Mirrors
:class:`chisurf.plugins.traj.traj_align.view_model.AlignTrajectoryViewModel`.
"""

from __future__ import annotations

import html
import logging
import pathlib
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "calculate_potential.view.json"


class PotentialEnergyViewModel:
    """State + logic for the Potential-Energy calculator (no Qt)."""

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``calculate_potential.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        import chisurf.core.structure

        #: Source DCD trajectory path.
        self.trajectory_file: str = ""
        #: Structure (PDB/mmCIF) naming the atoms; DCD stores coordinates only.
        self.topology_filename: str = ""
        #: Read every ``stride``-th frame; also seeds the emitted frame numbers.
        self.stride: int = 1
        #: Index of the currently selected potential type (into :meth:`potential_names`).
        self.selected_potential_index: int = 0
        #: Weight applied to the next potential added to the universe.
        self.potential_weight: float = 1.0
        #: Structure scored during :meth:`process` (kept for the ``energy`` readout).
        self.structure = None
        #: Collects the configured potentials and their weights.
        self.universe = chisurf.core.structure.Universe()
        #: Table records mirroring :attr:`universe` (``{"name", "weight"}``).
        self._potentials: list[dict] = []
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
                logger.warning("PotentialEnergy observer failed", exc_info=True)

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

    # ── potential registry ──────────────────────────────────────────────
    def potential_names(self) -> list[str]:
        """Return the available potential-type names.

        The only registry is the Qt :data:`chisurf.gui.widgets.structure.potentialDict`
        (its editor widgets double as the potentials), so this imports Qt lazily;
        the compute path (:meth:`process`) stays Qt-free.
        """
        from chisurf.gui.widgets.structure import potentialDict

        return list(potentialDict)

    # ── file wiring ─────────────────────────────────────────────────────
    def set_trajectory(self, filename: str) -> None:
        """Set the source trajectory path and notify observers."""
        self.trajectory_file = str(filename)
        self.append_log(f"Trajectory: {self.trajectory_file}")
        self._notify("loaded")

    def set_topology(self, filename: str) -> None:
        """Set the topology (PDB) that names the atoms, and notify observers."""
        self.topology_filename = str(filename)
        self.append_log(f"Topology: {self.topology_filename}")
        self._notify("loaded")

    # ── potentials ──────────────────────────────────────────────────────
    def add_potential(self, potential_obj, weight: float, name: str | None = None) -> None:
        """Add *potential_obj* (weight *weight*) to the universe and the table.

        Parameters
        ----------
        potential_obj : object
            Any object exposing the potential interface (a ``getEnergy()`` method
            and a settable ``structure`` attribute); in the GUI this is the
            selected ``potentialDict`` editor widget.
        weight : float
            Scaling factor applied to this potential's energy.
        name : str, optional
            Display name for the table row; defaults to ``potential_obj.name``.
        """
        weight = float(weight)
        self.universe.addPotential(potential_obj, weight)
        display = name if name is not None else str(getattr(potential_obj, "name", "potential"))
        self._potentials.append({"name": display, "weight": weight})
        self.append_log(f"Added potential '{display}' (weight={weight:g})")
        self._notify("potentials")

    def remove_potential(self, idx: int) -> None:
        """Remove the potential at *idx* from both the universe and the table."""
        if not 0 <= idx < len(self._potentials):
            return
        record = self._potentials.pop(idx)
        self.universe.removePotential(idx)
        self.append_log(f"Removed potential '{record['name']}'")
        self._notify("potentials")

    def remove_potential_activated(self, row: dict) -> None:
        """Remove the double-clicked table *row* (dispatched by the table section)."""
        try:
            idx = int(row.get("idx"))
        except (TypeError, ValueError):
            return
        self.remove_potential(idx)

    def added_potentials(self) -> list[dict]:
        """Return the table rows (``{"name", "weight", "idx"}``) for the ``table`` section."""
        return [
            {"name": record["name"], "weight": record["weight"], "idx": index}
            for index, record in enumerate(self._potentials)
        ]

    # ── derived readout ─────────────────────────────────────────────────
    def energy(self) -> float:
        """Total (scaled) energy of all potentials for the current structure."""
        return float(self.universe.getEnergy(self.structure))

    # ── action ──────────────────────────────────────────────────────────
    def process(self, energy_file, progress_cb: Callable[[int], None] | None = None) -> int:
        """Score every frame of the trajectory and write the energies to *energy_file*.

        Iterates the trajectory frame by frame (ports ``onProcessTrajectory``),
        setting the structure coordinates to the frame's ``xyz`` (Å), updating
        the C-alpha distance matrix when the structure supports it, and writing one
        CSV row per frame (``FrameNbr`` followed by one column per configured
        potential of :meth:`Universe.getEnergies`).

        Parameters
        ----------
        energy_file : str or pathlib.Path
            Destination CSV path (tab-separated).
        progress_cb : callable, optional
            Called ``progress_cb(n_frames_done)`` after every processed frame.

        Returns
        -------
        int
            The number of frames processed.
        """
        import chisurf.core.fio as io
        import chisurf.core.structure
        from chisurf.core.structure import trajectory_data as mdtraj

        if not self.trajectory_file:
            self.append_log("No trajectory selected")
            return 0

        header = "FrameNbr\t"
        for potential in self.universe.potentials:
            header += f"{getattr(potential, 'name', 'E')}\t"
        header += "\n"
        with io.zipped.open_maybe_zipped(filename=energy_file, mode="w") as handle:
            handle.write(header)

        topology = self.topology_filename or None
        self.structure = chisurf.core.structure.TrajectoryFile(
            mdtraj.load_frame(self.trajectory_file, 0, top=topology)
        )[0]

        i = 0
        with open(energy_file, "a") as handle:
            # The stride was used to number the rows but never to read, so a
            # strided run labelled every frame as if it had been skipped.
            for chunk in mdtraj.iterload(
                self.trajectory_file, stride=int(self.stride), top=topology
            ):
                for frame in chunk:
                    # A single-frame trajectory's xyz is (1, n_atoms, 3). Ångström
                    # already, like the structure's: the ×10 here was a nm → Å
                    # conversion left behind when trajectories moved to Å.
                    self.structure.xyz = frame.xyz[0]
                    update_dist = getattr(self.structure, "update_dist", None)
                    if callable(update_dist):
                        update_dist()
                    row = f"{i * self.stride + 1}\t"
                    for energy in self.universe.getEnergies(self.structure):
                        row += f"{energy:.3f}\t"
                    row += "\n"
                    handle.write(row)
                    i += 1
                    if progress_cb is not None:
                        progress_cb(i)

        self.append_log(f"Processed {i} frame(s) → {energy_file}")
        self._notify("processed")
        return i


__all__ = ["PotentialEnergyViewModel"]
