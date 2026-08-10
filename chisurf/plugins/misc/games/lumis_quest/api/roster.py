"""The creature roster, read from the shipped spectra database.

Nothing here is invented. `chisurf/plugins/spectra_downloader/spectra.db` already
holds around a thousand real fluorophores with their measured extinction
coefficients, quantum yields and emission maxima, and the emission and
absorption *spectra* for most of them. That is a bestiary with stat blocks, and
using it means every hour played teaches real spectroscopy rather than a table
someone made up.

The mapping is deliberate:

===================  ==========================================================
Game stat            Where it comes from
===================  ==========================================================
Attack               brightness, extinction coefficient times quantum yield
Max HP               photostability, from the dye's class and brightness
Type                 emission maximum, which is also the creature's colour
Effectiveness        the **real spectral overlap integral** of your emission
                     with the target's absorption
===================  ==========================================================

**Degrade, never fabricate.** Only 383 of the ~1030 fluorophores carry a
complete stat set. A creature missing one shows it as estimated and takes a
class default; it does not get an invented quantum yield, because a game that
teaches a false number is worse than a game that admits it does not know.
"""

from __future__ import annotations

import dataclasses
import functools
import math
import pathlib
import sqlite3

import numpy as np

#: Probe types that are creatures rather than optical hardware.
FLUOROPHORE_TYPES = (
    "Fpbase Fluorescent Protein",
    "Fpbase Organic Dye",
    "Atto Organic Dye",
    "Photochemcad Organic Dye",
    "Chroma Fluorochrome",
)

#: Class defaults for a missing stat, by whether the creature is a protein.
DEFAULT_EXT_COEFF = {True: 40_000.0, False: 70_000.0}
DEFAULT_QY = {True: 0.45, False: 0.60}

#: Brightness that counts as a full-strength attack, in units of ec*qy/1000.
REFERENCE_BRIGHTNESS = 60.0


def database_path() -> pathlib.Path:
    """Where the shipped spectra database lives.

    Returns
    -------
    pathlib.Path
        The database file. It may not exist in a stripped install; callers
        degrade to an empty roster.
    """
    here = pathlib.Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "spectra_downloader" / "spectra.db"
        if candidate.is_file():
            return candidate
    return here.parents[3] / "spectra_downloader" / "spectra.db"


@dataclasses.dataclass
class Creature:
    """One fluorophore, as something you can field in a fight.

    Attributes
    ----------
    probe_id : int
        Row id in the spectra database.
    name : str
        The fluorophore's own name.
    is_protein : bool
        Whether it is a fluorescent protein rather than an organic dye.
    emission_nm : float
        Emission maximum. Also the creature's colour and its type.
    absorption_nm : float
        Absorption maximum.
    ext_coeff : float
        Molar extinction coefficient.
    quantum_yield : float
        Fluorescence quantum yield.
    estimated : frozenset of str
        Which stats are class defaults rather than measured values.
    """

    probe_id: int
    name: str
    is_protein: bool
    emission_nm: float
    absorption_nm: float
    ext_coeff: float
    quantum_yield: float
    estimated: frozenset[str] = frozenset()

    @property
    def brightness(self) -> float:
        """Molecular brightness, in the usual ec*qy/1000 units.

        Returns
        -------
        float
            Higher is brighter.
        """
        return self.ext_coeff * self.quantum_yield / 1000.0

    @property
    def attack(self) -> int:
        """Damage per clean hit.

        Brightness is how much signal a dye puts out, so it is what a hit is
        worth.

        Returns
        -------
        int
            Roughly 10..60 across the roster.
        """
        return max(6, int(round(10 + 50 * min(self.brightness / REFERENCE_BRIGHTNESS, 1.6))))

    @property
    def max_hp(self) -> int:
        """How long the creature lasts before it bleaches.

        The trade every fluorophore makes: a high quantum yield cycles harder
        and bleaches sooner, so the brightest creatures hit hardest and burn out
        fastest. Proteins are shielded by their barrel and last longer.

        Returns
        -------
        int
            Roughly 30..120.
        """
        base = 120.0 if self.is_protein else 90.0
        return max(24, int(round(base - 45.0 * min(self.quantum_yield, 1.0))))

    @property
    def stokes_shift_nm(self) -> float:
        """Gap between absorption and emission maxima.

        Returns
        -------
        float
            Nanometres. A large shift is easier to filter cleanly.
        """
        return self.emission_nm - self.absorption_nm

    @property
    def summary(self) -> str:
        """One line for the battle UI.

        Returns
        -------
        str
            Name, colour and the two headline stats.
        """
        mark = "~" if self.estimated else ""
        return (
            f"{self.name}  {self.emission_nm:.0f} nm  "
            f"atk {self.attack}{mark}  hp {self.max_hp}{mark}"
        )


def _blob(raw) -> np.ndarray:
    """Decode a stored spectrum column.

    Parameters
    ----------
    raw : bytes or None
        A float64 blob.

    Returns
    -------
    numpy.ndarray
        The values, or an empty array when absent.
    """
    if not raw:
        return np.zeros(0)
    return np.frombuffer(raw, dtype="<f8")


@functools.lru_cache(maxsize=1)
def load_roster(db_path: str | None = None) -> tuple[Creature, ...]:
    """Read every fielded fluorophore from the database.

    Parameters
    ----------
    db_path : str, optional
        Database file. Defaults to the shipped one.

    Returns
    -------
    tuple of Creature
        Sorted by emission wavelength, so the roster reads as a spectrum. Empty
        when the database is missing.
    """
    path = pathlib.Path(db_path) if db_path else database_path()
    if not path.is_file():
        return ()

    placeholders = ",".join("?" * len(FLUOROPHORE_TYPES))
    query = f"""
        SELECT p.probe_id, p.chromophore_name, pt.display_name,
               MAX(CASE WHEN o.property_name='ext_coeff' THEN o.property_value END),
               MAX(CASE WHEN o.property_name='qy'        THEN o.property_value END),
               MAX(CASE WHEN o.property_name='em_max'    THEN o.property_value END),
               MAX(CASE WHEN o.property_name='abs_max'   THEN o.property_value END)
        FROM probes p
        JOIN probe_types pt ON pt.type_id = p.type_id
        LEFT JOIN optical_properties o ON o.probe_id = p.probe_id
        WHERE pt.display_name IN ({placeholders}) AND p.deleted_at IS NULL
        GROUP BY p.probe_id
    """
    creatures: list[Creature] = []
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        for probe_id, name, type_name, ec, qy, em, ab in connection.execute(
            query, FLUOROPHORE_TYPES
        ):
            emission = _number(em)
            if emission is None or not 350.0 <= emission <= 800.0:
                # No emission maximum means no colour and no type. Such a row is
                # a database entry, not a creature.
                continue
            is_protein = "Protein" in (type_name or "")
            estimated = set()
            ext = _number(ec)
            if ext is None or ext <= 0:
                ext = DEFAULT_EXT_COEFF[is_protein]
                estimated.add("ext_coeff")
            yield_ = _number(qy)
            if yield_ is None or not 0.0 < yield_ <= 1.0:
                yield_ = DEFAULT_QY[is_protein]
                estimated.add("quantum_yield")
            absorption = _number(ab)
            if absorption is None or not 300.0 <= absorption <= 800.0:
                # A typical Stokes shift, flagged as the guess it is.
                absorption = emission - 25.0
                estimated.add("absorption_nm")
            creatures.append(
                Creature(
                    probe_id=int(probe_id),
                    name=str(name or f"probe {probe_id}"),
                    is_protein=is_protein,
                    emission_nm=emission,
                    absorption_nm=absorption,
                    ext_coeff=ext,
                    quantum_yield=yield_,
                    estimated=frozenset(estimated),
                )
            )
    creatures.sort(key=lambda creature: (creature.emission_nm, creature.name))
    return tuple(creatures)


def _number(value) -> float | None:
    """Parse one EAV value.

    The property table stores everything as text, and it holds non-numeric
    properties (``Origin``, ``Material Name``) alongside the numeric ones -- so
    a cast over the whole column raises. Every read goes through here.

    Parameters
    ----------
    value : object
        Whatever the database returned.

    Returns
    -------
    float or None
        ``None`` when the value is absent or not a number.
    """
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


@functools.lru_cache(maxsize=4096)
def _spectrum(probe_id: int, kind: str, db_path: str | None = None):
    """Read one spectrum, as wavelengths and intensities.

    Parameters
    ----------
    probe_id : int
        Probe row id.
    kind : {'emission', 'absorption'}
        Which spectrum.
    db_path : str, optional
        Database file.

    Returns
    -------
    tuple of numpy.ndarray or None
        ``(wavelengths, intensities)``, or ``None`` when not stored.
    """
    path = pathlib.Path(db_path) if db_path else database_path()
    if not path.is_file():
        return None
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT wavelengths, intensity_values FROM spectra "
            "WHERE probe_id=? AND spectrum_type=? LIMIT 1",
            (probe_id, kind),
        ).fetchone()
    if not row:
        return None
    wavelengths, intensities = _blob(row[0]), _blob(row[1])
    if wavelengths.size < 4 or wavelengths.size != intensities.size:
        return None
    return wavelengths, intensities


def overlap(donor: Creature, acceptor: Creature, db_path: str | None = None) -> float:
    """Spectral overlap of a donor's emission with an acceptor's absorption.

    This is the type chart, and it is measured rather than designed: the
    integral of the donor's normalised emission against the acceptor's
    absorption. Where a spectrum is not stored, it falls back to overlapping
    Gaussians at the two maxima -- an approximation, but one that still answers
    "do these two talk to each other" from the real numbers.

    Parameters
    ----------
    donor, acceptor : Creature
        The attacker and the target.
    db_path : str, optional
        Database file.

    Returns
    -------
    float
        0 for no overlap, 1 for a strong match.
    """
    emission = _spectrum(donor.probe_id, "emission", db_path)
    absorption = _spectrum(acceptor.probe_id, "absorption", db_path)
    if emission is None or absorption is None:
        return _gaussian_overlap(donor.emission_nm, acceptor.absorption_nm)

    grid = np.arange(350.0, 800.0, 1.0)
    donor_curve = np.interp(grid, emission[0], emission[1], left=0.0, right=0.0)
    acceptor_curve = np.interp(grid, absorption[0], absorption[1], left=0.0, right=0.0)
    donor_area = float(donor_curve.sum())
    acceptor_peak = float(acceptor_curve.max())
    if donor_area <= 0 or acceptor_peak <= 0:
        return _gaussian_overlap(donor.emission_nm, acceptor.absorption_nm)
    donor_curve = donor_curve / donor_area
    acceptor_curve = acceptor_curve / acceptor_peak
    return float(np.clip((donor_curve * acceptor_curve).sum() * 2.2, 0.0, 1.0))


def _gaussian_overlap(donor_nm: float, acceptor_nm: float, width: float = 34.0) -> float:
    """Overlap of two bands when the real spectra are not stored.

    Parameters
    ----------
    donor_nm, acceptor_nm : float
        Band centres.
    width : float, optional
        Typical band half-width in nm.

    Returns
    -------
    float
        0..1.
    """
    gap = donor_nm - acceptor_nm
    return float(math.exp(-(gap * gap) / (4.0 * width * width)))


def effectiveness(donor: Creature, acceptor: Creature, db_path: str | None = None) -> float:
    """Damage multiplier for attacking one creature with another.

    Parameters
    ----------
    donor, acceptor : Creature
        Attacker and target.
    db_path : str, optional
        Database file.

    Returns
    -------
    float
        0.5 for a poor match up to 2.0 for a strong one. The floor is not zero:
        a badly matched pair still transfers a little, and a move that can do
        nothing at all is a move a player simply never picks.
    """
    return 0.5 + 1.5 * overlap(donor, acceptor, db_path)


def starters(count: int = 3, db_path: str | None = None) -> tuple[Creature, ...]:
    """A spread of well-characterised creatures to begin with.

    Parameters
    ----------
    count : int, optional
        How many.
    db_path : str, optional
        Database file.

    Returns
    -------
    tuple of Creature
        Fully measured creatures spread across the visible range, so a starting
        team can answer more than one colour.
    """
    measured = [creature for creature in load_roster(db_path) if not creature.estimated]
    if not measured:
        return ()
    lo = measured[0].emission_nm
    hi = measured[-1].emission_nm
    chosen: list[Creature] = []
    for index in range(count):
        target = lo + (hi - lo) * (index + 0.5) / count
        chosen.append(min(measured, key=lambda c: abs(c.emission_nm - target)))
    return tuple(chosen)
