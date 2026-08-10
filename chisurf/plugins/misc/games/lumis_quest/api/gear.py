"""Optical gear: the equipment layer, read from real filters and detectors.

The same database that holds the creatures also holds **668 filters with
measured transmission spectra**, plus dichroics and detectors. So gear is not
invented either -- an emission filter in the game is a real Chroma or Thorlabs
part, and what it does in a fight is what it does on a bench: it passes some
wavelengths and blocks others.

That gives the loot loop its teeth. A filter is not "+3 damage": it decides
**what you can even see**. Equip a 525/50 and the green creatures come through
bright while the far-red ones go dark -- both in combat, where your shot is
multiplied by what the filter passes, and on the map, where a creature the
filter blocks is not rendered. Swapping gear and walking back through ground you
have already cleared shows you things that were always there.
"""

from __future__ import annotations

import dataclasses
import functools
import pathlib
import random
import sqlite3

import numpy as np

from .roster import _blob, database_path

#: Probe types that are equipment rather than creatures, by slot.
GEAR_TYPES: dict[str, tuple[str, ...]] = {
    "emission": (
        "Chroma Emission Filter",
        "Chroma Bandpass Filter",
        "Thorlabs Bandpass Filter",
        "3Doptix Bandpass Filter",
    ),
    "excitation": ("Chroma Excitation Filter",),
    "dichroic": ("Chroma Dichroic Beamsplitter", "3Doptix Dichroic Beamsplitter"),
    "detector": ("Fpbase Detector", "Thorlabs APD Detector"),
}

#: Wavelength grid every transmission curve is resampled onto, in nm.
GRID = np.arange(350.0, 800.0, 1.0)


@dataclasses.dataclass
class Gear:
    """One piece of optical hardware.

    Attributes
    ----------
    probe_id : int
        Row id in the spectra database.
    name : str
        The part's own catalogue name, e.g. ``ET525/50m``.
    slot : str
        ``emission``, ``excitation``, ``dichroic`` or ``detector``.
    curve : numpy.ndarray
        Transmission on :data:`GRID`, in 0..1.
    """

    probe_id: int
    name: str
    slot: str
    curve: np.ndarray

    @property
    def center_nm(self) -> float:
        """Middle of the passband.

        Returns
        -------
        float
            Wavelength in nm, weighted by transmission.
        """
        total = float(self.curve.sum())
        if total <= 0:
            return 0.0
        return float((GRID * self.curve).sum() / total)

    @property
    def bandwidth_nm(self) -> float:
        """Full width of the passband at half its maximum.

        Returns
        -------
        float
            Width in nm; 0 for a curve that never opens.
        """
        peak = float(self.curve.max())
        if peak <= 0:
            return 0.0
        open_ = GRID[self.curve >= peak * 0.5]
        return float(open_[-1] - open_[0]) if open_.size else 0.0

    def passes(self, nanometres: float) -> float:
        """How much of a wavelength this part lets through.

        Parameters
        ----------
        nanometres : float
            Wavelength in nm.

        Returns
        -------
        float
            0 blocked, 1 fully passed.
        """
        return float(np.interp(nanometres, GRID, self.curve, left=0.0, right=0.0))

    @property
    def summary(self) -> str:
        """One line for the inventory.

        Returns
        -------
        str
            Name, passband centre and width.
        """
        return f"{self.name}  {self.center_nm:.0f}/{self.bandwidth_nm:.0f} nm"


@functools.lru_cache(maxsize=1)
def load_gear(db_path: str | None = None) -> tuple[Gear, ...]:
    """Read every usable piece of gear from the database.

    Only parts with a stored transmission curve are loaded: a filter whose
    passband is unknown cannot do the one thing gear exists to do.

    Parameters
    ----------
    db_path : str, optional
        Database file. Defaults to the shipped one.

    Returns
    -------
    tuple of Gear
        Sorted by passband centre, so the inventory reads as a spectrum.
    """
    path = pathlib.Path(db_path) if db_path else database_path()
    if not path.is_file():
        return ()

    by_type = {name: slot for slot, names in GEAR_TYPES.items() for name in names}
    placeholders = ",".join("?" * len(by_type))
    query = f"""
        SELECT p.probe_id, p.chromophore_name, pt.display_name,
               s.wavelengths, s.intensity_values
        FROM probes p
        JOIN probe_types pt ON pt.type_id = p.type_id
        JOIN spectra s ON s.probe_id = p.probe_id
        WHERE pt.display_name IN ({placeholders})
          AND s.spectrum_type IN ('transmission', 'quantum_efficiency')
          AND p.deleted_at IS NULL
    """
    found: dict[int, Gear] = {}
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        for probe_id, name, type_name, wavelengths, values in connection.execute(
            query, tuple(by_type)
        ):
            if probe_id in found:
                continue
            grid = _blob(wavelengths)
            curve = _blob(values)
            if grid.size < 4 or grid.size != curve.size:
                continue
            resampled = np.interp(GRID, grid, curve, left=0.0, right=0.0)
            peak = float(resampled.max())
            if peak <= 0:
                continue
            # Catalogues store transmission as either a fraction or a
            # percentage; normalising by the peak makes both read the same and
            # keeps "how much gets through" comparable across vendors.
            found[probe_id] = Gear(
                probe_id=int(probe_id),
                name=str(name or f"part {probe_id}"),
                slot=by_type[type_name],
                curve=np.clip(resampled / peak, 0.0, 1.0),
            )
    return tuple(sorted(found.values(), key=lambda part: part.center_nm))


@dataclasses.dataclass
class Loadout:
    """What is currently fitted.

    Attributes
    ----------
    emission : Gear or None
        The emission filter. With none fitted everything is visible and nothing
        is amplified -- a bare eye rather than a blind one.
    detector : Gear or None
        The detector.
    """

    emission: Gear | None = None
    detector: Gear | None = None

    def response(self, nanometres: float) -> float:
        """Overall sensitivity at a wavelength.

        Parameters
        ----------
        nanometres : float
            Wavelength in nm.

        Returns
        -------
        float
            Near zero when blocked, up to about 1.5 for a well-matched pair.
            Unfitted slots contribute a neutral 1.
        """
        response = 1.0
        if self.emission is not None:
            # A matched filter is worth more than nothing fitted; a mismatched
            # one is worth much less. That asymmetry is what makes choosing
            # gear a decision rather than a formality.
            # The floor has to sit *below* the visibility threshold, or a
            # blocked wavelength still registers and the whole "wrong filter
            # blinds you" mechanic never fires. It was 0.25 against a 0.22
            # threshold, so nothing was ever invisible.
            response *= 0.08 + 1.45 * self.emission.passes(nanometres)
        if self.detector is not None:
            response *= 0.55 + 0.65 * self.detector.passes(nanometres)
        return response

    def sees(self, nanometres: float, threshold: float = 0.25) -> bool:
        """Whether a creature at this wavelength is visible at all.

        Parameters
        ----------
        nanometres : float
            Wavelength in nm.
        threshold : float, optional
            Response below which nothing registers.

        Returns
        -------
        bool
            False when the fitted filter blocks it.
        """
        return self.response(nanometres) >= threshold

    @property
    def summary(self) -> str:
        """One line for the HUD.

        Returns
        -------
        str
            What is fitted, or that nothing is.
        """
        parts = [part.summary for part in (self.emission, self.detector) if part is not None]
        return "   ".join(parts) if parts else "no filter fitted"


def loot_for(seed_text: str, difficulty: float, pool=None) -> Gear | None:
    """The gear a cleared room yields.

    Seeded by the room's address, so the same page always yields the same part
    and a player cannot farm one building for rerolls.

    Parameters
    ----------
    seed_text : str
        Usually the page address.
    difficulty : float
        0..1. A remoter room yields a narrower, more selective filter -- which
        is better in the band it passes and worse everywhere else.
    pool : sequence of Gear, optional
        Gear to choose from. Defaults to everything loaded.

    Returns
    -------
    Gear or None
        ``None`` when no gear is available at all.
    """
    available = list(pool if pool is not None else load_gear())
    filters = [part for part in available if part.slot in ("emission", "detector")]
    if not filters:
        return None
    level = max(0.0, min(difficulty, 1.0))

    # Narrow filters are the prize: selective, and useless outside their band.
    ranked = sorted(filters, key=lambda part: -part.bandwidth_nm)
    span = max(1, len(ranked) // 4)
    top = int(round(level * (len(ranked) - 1)))
    window = ranked[max(0, top - span // 2): max(1, top + span // 2 + 1)] or ranked
    return random.Random(seed_text).choice(window)


def starting_loadout(pool=None) -> Loadout:
    """A broad, forgiving filter to begin with.

    Parameters
    ----------
    pool : sequence of Gear, optional
        Gear to choose from.

    Returns
    -------
    Loadout
        The widest emission filter available, so a new player is not blinded
        to most of the roster before they understand why.
    """
    available = list(pool if pool is not None else load_gear())
    emission = [part for part in available if part.slot == "emission"]
    if not emission:
        return Loadout()
    return Loadout(emission=max(emission, key=lambda part: part.bandwidth_nm))
