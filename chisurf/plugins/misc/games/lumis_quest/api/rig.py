"""Crafting: assembling a light path out of the parts you have found.

Fitting one filter is equipment. A **rig** is the crafting layer: an excitation
filter, a dichroic, an emission filter and a detector, wired into a path. Its
statistics are not invented and they are not computed here either -- they come
from the application's existing light-path simulator, which already knows how to
propagate a spectrum through optics and what a Förster radius is.

That reuse is the point. A crafted rig in the game and a real instrument
described in the Light Path Simulator are the same object, evaluated by the same
code, so a player who learns which parts go together has learned something that
transfers to a bench.

Three numbers come out of a rig, and each is a real quantity:

* **response** -- how much of a given wavelength survives the whole path;
* **collection** -- what fraction of a creature's emission the path actually
  collects, which read against the *other* member of a pair is the **crosstalk**
  a two-colour experiment must correct for;
* **Förster radius** -- the reach of a FRET pair, from the simulator's own
  ``calculate_r0``.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from .gear import GRID, Gear
from .roster import Creature, _spectrum

#: Slots a rig fills, in the order light passes through them.
SLOTS = ("excitation", "dichroic", "emission", "detector")


def _simulator():
    """The application's light-path simulator, imported lazily.

    Returns
    -------
    module or None
        The crosstalk backend, or ``None`` when the plugin is not installed --
        in which case the rig falls back to its own arithmetic rather than
        failing to build.
    """
    try:
        from chisurf.plugins.core.lightpath_simulator.backend import crosstalk

        return crosstalk
    except Exception:
        return None


@dataclasses.dataclass
class Rig:
    """A crafted optical path.

    Attributes
    ----------
    excitation, dichroic, emission, detector : Gear or None
        The fitted parts. An empty slot is transparent, not opaque: a partial
        rig is a working rig with less selectivity, which is what a player
        assembling one piece at a time actually has.
    """

    excitation: Gear | None = None
    dichroic: Gear | None = None
    emission: Gear | None = None
    detector: Gear | None = None

    @property
    def parts(self) -> list[Gear]:
        """Every fitted part, in path order.

        Returns
        -------
        list of Gear
            May be empty.
        """
        return [
            part
            for part in (self.excitation, self.dichroic, self.emission, self.detector)
            if part is not None
        ]

    @property
    def complete(self) -> bool:
        """Whether every slot is filled.

        Returns
        -------
        bool
            True for a full path.
        """
        return len(self.parts) == len(SLOTS)

    def fit(self, part: Gear) -> None:
        """Put a part in its own slot.

        Parameters
        ----------
        part : Gear
            What to fit. Its ``slot`` decides where it goes.
        """
        if part.slot in SLOTS:
            setattr(self, part.slot, part)

    def curve(self) -> np.ndarray:
        """Transmission of the whole path, on :data:`GRID`.

        Returns
        -------
        numpy.ndarray
            The product of the fitted parts. An empty rig passes everything.

        Notes
        -----
        A dichroic is taken as ``max(T, 1 - T)``. It does not absorb what it
        fails to transmit -- it **reflects** it, and a real path collects one arm
        or the other. Multiplying its transmission in blindly made every
        assembled rig blind at exactly the wavelengths its beamsplitter was
        chosen to steer, which looked like a balance problem and was a modelling
        error.
        """
        total = np.ones_like(GRID)
        for part in self.parts:
            curve = part.curve
            if part.slot == "dichroic":
                curve = np.maximum(curve, 1.0 - curve)
            total = total * curve
        return total

    def response(self, nanometres: float) -> float:
        """How much of a wavelength survives the path.

        Parameters
        ----------
        nanometres : float
            Wavelength in nm.

        Returns
        -------
        float
            Scaled so a well-matched full path beats a bare eye, and a badly
            matched one is much worse -- the same asymmetry a single filter has,
            which is what makes assembling a path a decision.
        """
        if not self.parts:
            return 1.0
        curve = self.curve()
        peak = float(curve.max())
        if peak <= 0:
            return 0.08
        # Normalised by the path's own peak: a longer path is more *selective*,
        # not dimmer. Without this every extra element multiplied the whole
        # curve down and a complete rig scored worse than a bare eye everywhere.
        passed = float(np.interp(nanometres, GRID, curve / peak, left=0.0, right=0.0))
        return 0.08 + (1.0 + 0.18 * len(self.parts)) * passed

    def sees(self, nanometres: float, threshold: float = 0.25) -> bool:
        """Whether anything at this wavelength registers.

        Parameters
        ----------
        nanometres : float
            Wavelength in nm.
        threshold : float, optional
            Response below which nothing is detected.

        Returns
        -------
        bool
            False when the path blocks it.
        """
        return self.response(nanometres) >= threshold

    def collection(self, creature: Creature, db_path: str | None = None) -> float:
        """Fraction of a creature's emission this path actually collects.

        The same number reads two ways, which is why it is named for what it
        measures rather than for one of its uses. Applied to the creature the
        path was tuned for it is **collection efficiency**; applied to the other
        member of a pair it is **crosstalk** -- the leakage a two-colour
        experiment has to correct for. Calling it "crosstalk" outright was
        wrong: a rig tuned for a 560 nm emitter collects it at 1.0, which is
        excellent, not leakage.

        Parameters
        ----------
        creature : Creature
            The emitter.
        db_path : str, optional
            Spectra database.

        Returns
        -------
        float
            0..1.
        """
        emission = _spectrum(creature.probe_id, "emission", db_path)
        if emission is None:
            return float(np.clip(self.response(creature.emission_nm) / 1.5, 0.0, 1.0))
        curve = np.interp(GRID, emission[0], emission[1], left=0.0, right=0.0)
        total = float(curve.sum())
        if total <= 0:
            return 0.0
        return float(np.clip((curve * self.curve()).sum() / total, 0.0, 1.0))

    def crosstalk(self, donor: Creature, acceptor: Creature,
                  db_path: str | None = None) -> float:
        """Leakage of the donor into a path tuned for the acceptor.

        Parameters
        ----------
        donor, acceptor : Creature
            The pair. ``acceptor`` is what this path is meant to collect.
        db_path : str, optional
            Spectra database.

        Returns
        -------
        float
            0..1. Zero when the path collects nothing of the acceptor either,
            because leakage relative to nothing is not a meaningful number.
        """
        wanted = self.collection(acceptor, db_path)
        if wanted <= 0.0:
            return 0.0
        return float(np.clip(self.collection(donor, db_path) / (wanted + 1e-9), 0.0, 1.0))

    def forster_radius(
        self, donor: Creature, acceptor: Creature, db_path: str | None = None
    ) -> float:
        """Reach of a FRET pair through this rig, in ångström.

        Computed by the light-path simulator's own ``calculate_r0`` rather than
        re-derived here: a crafted rig and a real instrument description are the
        same object, and they should not disagree about the physics.

        Parameters
        ----------
        donor, acceptor : Creature
            The pair.
        db_path : str, optional
            Spectra database.

        Returns
        -------
        float
            R0 in ångström, or 0 when the spectra needed are not stored.
        """
        simulator = _simulator()
        emission = _spectrum(donor.probe_id, "emission", db_path)
        absorption = _spectrum(acceptor.probe_id, "absorption", db_path)
        if simulator is None or emission is None or absorption is None:
            return 0.0

        grid = simulator.WAVELENGTHS
        donor_em = np.interp(grid, emission[0], emission[1], left=0.0, right=0.0)
        acceptor_abs = np.interp(grid, absorption[0], absorption[1], left=0.0, right=0.0)
        peak = float(acceptor_abs.max())
        if peak <= 0:
            return 0.0
        acceptor_abs = acceptor_abs / peak
        return float(
            simulator.calculate_r0(
                donor_em, donor.quantum_yield, acceptor_abs, acceptor.ext_coeff
            )
        )

    @property
    def summary(self) -> str:
        """One line for the HUD.

        Returns
        -------
        str
            The fitted parts, or that the path is empty.
        """
        if not self.parts:
            return "bare path"
        return "  ".join(f"{part.name}" for part in self.parts)
