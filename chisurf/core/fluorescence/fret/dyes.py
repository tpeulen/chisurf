"""Dye properties and spectra from MMFDB, turned into calibration parameters.

Three of the numbers an accurate-FRET calibration needs are properties of the
*dyes*, not of the data: the donor and acceptor quantum yields, and the Förster
radius. They are usually typed in from a catalogue or a paper. MMFDB already
holds the underlying measurements — absorption and emission spectra, quantum
yields, extinction coefficients — so selecting the two dyes should be enough.

That is what this module does. Given a donor and an acceptor it reads what the
database knows and computes what follows:

    R0 = f( ∫ F_D(λ)·ε_A(λ)·λ⁴ dλ , Φ_D, κ², n )

using :func:`~chisurf.core.fluorescence.fret.forster.forster_radius_from_spectra`
— the acceptor's normalized absorption scaled by its molar extinction
coefficient, the donor's emission area-normalized. Computed this way for real
database entries it reproduces the literature (EGFP→mCherry 52 Å, ATTO 550→ATTO
643 65 Å).

**Provenance is part of the answer.** MMFDB is a curated but incomplete
catalogue: some probes carry spectra and no quantum yield, some the reverse. So
every returned quantity says where it came from — a measured spectrum, a stored
property, a stored pair value, or nothing at all — and a quantity the database
cannot supply is left alone rather than defaulted to something plausible. A
calibration built on a guessed quantum yield is worse than one that admits it
does not know.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra

__all__ = [
    "DyeProperties",
    "FretPair",
    "open_database",
    "list_dyes",
    "list_absorbing_dyes",
    "dye_properties",
    "absorption_spectrum",
    "extinction_at",
    "fret_pair",
    "apply_to_calibration",
]

#: MMFDB property names carrying each quantity (the repository normalizes
#: catalogue spellings onto these keys).
_PROPERTY_KEYS = {
    "quantum_yield": ("qy", "quantum_yield"),
    "extinction_coefficient": ("ext_coeff", "extinction_coefficient"),
    "lifetime": ("lifetime", "tau"),
    "absorption_maximum": ("abs_max",),
    "emission_maximum": ("em_max",),
}


@dataclass
class DyeProperties:
    """What MMFDB holds about one dye.

    Attributes
    ----------
    probe_id : int
        MMFDB probe identifier.
    name : str
        Chromophore name as curated in the database.
    quantum_yield, extinction_coefficient, lifetime : float or None
        Fluorescence quantum yield, molar extinction coefficient (M⁻¹cm⁻¹) and
        fluorescence lifetime (ns); ``None`` when the database has no value.
    absorption_maximum, emission_maximum : float or None
        Spectral maxima (nm), when curated.
    has_absorption, has_emission : bool
        Whether a usable spectrum of that kind is stored.
    category : str
        MMFDB category (``organic_dye``, ``protein``, …).
    """

    probe_id: int
    name: str
    quantum_yield: float | None = None
    extinction_coefficient: float | None = None
    lifetime: float | None = None
    absorption_maximum: float | None = None
    emission_maximum: float | None = None
    has_absorption: bool = False
    has_emission: bool = False
    category: str = ""

    @property
    def usable_as_donor(self) -> bool:
        """Whether an emission spectrum and a quantum yield are available."""
        return bool(self.has_emission and self.quantum_yield)

    @property
    def usable_as_acceptor(self) -> bool:
        """Whether an absorption spectrum and an extinction coefficient are available."""
        return bool(self.has_absorption and self.extinction_coefficient)


@dataclass
class FretPair:
    """What MMFDB implies for a donor/acceptor pair.

    Attributes
    ----------
    donor, acceptor : DyeProperties
        The two dyes as the database describes them.
    forster_radius : float or None
        R0 in Å — computed from the spectra when possible, otherwise a stored
        pair value, otherwise ``None``.
    overlap_integral : float or None
        The spectral overlap J (M⁻¹cm⁻¹nm⁴) behind a computed R0.
    kappa2, refractive_index : float
        Assumptions the Förster radius was computed with.
    provenance : dict
        Per quantity, where the number came from: ``"mmfdb:spectra"``,
        ``"mmfdb:property"``, ``"mmfdb:pair"`` or ``"missing"``.
    """

    donor: DyeProperties
    acceptor: DyeProperties
    forster_radius: float | None = None
    overlap_integral: float | None = None
    kappa2: float = 2.0 / 3.0
    refractive_index: float = 1.33
    provenance: dict = field(default_factory=dict)

    def summary(self) -> str:
        """One line per quantity, with the value and where it came from."""
        lines = [f"{self.donor.name} → {self.acceptor.name}"]
        rows = [
            ("R0", self.forster_radius, "Å", "forster_radius"),
            ("Phi_D", self.donor.quantum_yield, "", "quantum_yield_donor"),
            ("Phi_A", self.acceptor.quantum_yield, "", "quantum_yield_acceptor"),
            ("tau_D(0)", self.donor.lifetime, "ns", "donor_lifetime"),
        ]
        for label, value, unit, key in rows:
            origin = self.provenance.get(key, "missing")
            shown = "—" if value is None else f"{float(value):.4g}{(' ' + unit) if unit else ''}"
            lines.append(f"  {label:<9s} {shown:<12s} [{origin}]")
        return "\n".join(lines)


@contextlib.contextmanager
def open_database(db_path: str | None = None, db=None):
    """Open MMFDB read-only, or pass an already-open handle through.

    Parameters
    ----------
    db_path : str, optional
        Database path; the configured default is resolved when omitted.
    db : object, optional
        An already-open database, which is then yielded unchanged (and not
        closed).

    Yields
    ------
    object or None
        The database handle, or ``None`` when MMFDB is unavailable.
    """
    if db is not None:
        yield db
        return
    try:
        from mmfdb.repository import MFDatabase
        from mmfdb.store.database_resolver import resolve_database_path

        handle = MFDatabase(db_path or resolve_database_path(), readonly=True)
    except Exception:
        yield None
        return
    try:
        yield handle
    finally:
        with contextlib.suppress(Exception):
            handle.close()


def _properties(db, probe_id: int) -> dict:
    """Read one probe's optical properties under canonical keys."""
    values: dict[str, float] = {}
    try:
        rows = db.get_optical_properties(probe_id)
    except Exception:
        return values
    raw = {}
    for row in rows:
        entry = dict(row)
        name = entry.get("property_name")
        if name is None:
            continue
        raw[str(name)] = entry.get("property_value")
    for key, names in _PROPERTY_KEYS.items():
        for name in names:
            value = raw.get(name)
            if value is None:
                continue
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(number):
                values[key] = number
                break
    return values


def _spectrum_types(db, probe_id: int) -> set[str]:
    """Which spectrum types are stored for a probe."""
    types: set[str] = set()
    for kind in ("absorption", "emission", "excitation"):
        try:
            if db.get_spectrum_record(probe_id, kind) is not None:
                types.add(kind)
        except Exception:
            continue
    return types


def _spectrum(db, probe_id: int, kind: str):
    """Return one spectrum as ``(wavelength_nm, values)``, or ``None``.

    ``absorption`` falls back to ``excitation``: for a dye the two have the same
    shape, and many catalogue entries carry only the excitation curve.
    """
    order = ("absorption", "excitation") if kind == "absorption" else (kind,)
    for name in order:
        try:
            record = db.get_spectrum_record(probe_id, name)
        except Exception:
            record = None
        if record is None:
            continue
        wavelength = np.asarray(record["wavelengths"], dtype=float)
        values = np.asarray(record["intensity_values"], dtype=float)
        if wavelength.size > 1 and wavelength.size == values.size:
            return wavelength, values
    return None


def _dye_from_row(db, row) -> DyeProperties:
    """Build :class:`DyeProperties` from a probe row."""
    entry = dict(row)
    probe_id = int(entry["probe_id"])
    properties = _properties(db, probe_id)
    types = _spectrum_types(db, probe_id)
    return DyeProperties(
        probe_id=probe_id,
        name=str(entry.get("chromophore_name") or entry.get("name") or f"Probe {probe_id}"),
        quantum_yield=properties.get("quantum_yield"),
        extinction_coefficient=properties.get("extinction_coefficient"),
        lifetime=properties.get("lifetime"),
        absorption_maximum=properties.get("absorption_maximum"),
        emission_maximum=properties.get("emission_maximum"),
        has_absorption=bool({"absorption", "excitation"} & types),
        has_emission="emission" in types,
        category=str(entry.get("category") or ""),
    )


def list_dyes(
    *, db=None, db_path: str | None = None, usable_only: bool = True, limit: int | None = None
) -> list[DyeProperties]:
    """List the dyes MMFDB can describe.

    Parameters
    ----------
    db : object, optional
        Open MMFDB handle; one is opened and closed when omitted.
    db_path : str, optional
        Database path.
    usable_only : bool, optional
        Keep only probes that can serve as a donor *or* an acceptor (i.e. carry
        the spectrum and property a Förster radius needs). This is what makes the
        list short enough to pick from: most catalogue entries are filters,
        detectors and unmeasured probes.
    limit : int, optional
        Maximum number of entries.

    Returns
    -------
    list of DyeProperties
        Sorted by name.
    """
    out: list[DyeProperties] = []
    with open_database(db_path, db) as handle:
        if handle is None:
            return out
        try:
            rows = handle.get_probes()
        except Exception:
            return out
        for row in rows:
            dye = _dye_from_row(handle, row)
            if usable_only and not (dye.usable_as_donor or dye.usable_as_acceptor):
                continue
            out.append(dye)
            if limit is not None and len(out) >= int(limit):
                break
    return sorted(out, key=lambda d: d.name.lower())


def dye_properties(dye, *, db=None, db_path: str | None = None) -> DyeProperties | None:
    """Return one dye's properties by name or probe id.

    Parameters
    ----------
    dye : str or int
        Chromophore name (exact, then case-insensitive) or probe id.
    db : object, optional
        Open MMFDB handle.
    db_path : str, optional
        Database path.

    Returns
    -------
    DyeProperties or None
        ``None`` when the dye or the database is not available.
    """
    with open_database(db_path, db) as handle:
        if handle is None:
            return None
        try:
            if isinstance(dye, (int, np.integer)):
                row = handle.get_probe(int(dye))
                return _dye_from_row(handle, row) if row is not None else None
            wanted = str(dye).strip().lower()
            for row in handle.get_probes():
                entry = dict(row)
                name = str(entry.get("chromophore_name") or entry.get("name") or "")
                if name.strip().lower() == wanted:
                    return _dye_from_row(handle, row)
        except Exception:
            return None
    return None


def list_absorbing_dyes(*, db=None, db_path: str | None = None) -> list[str]:
    """Names of the dyes that carry both an absorption spectrum and an epsilon.

    That is the pair :func:`extinction_at` needs, so this is the list worth
    offering in a chooser.

    Parameters
    ----------
    db : object, optional
        Open MMFDB handle.
    db_path : str, optional
        Database path.

    Returns
    -------
    list of str
        Dye names, sorted case-insensitively.
    """
    return [
        dye.name
        for dye in list_dyes(db=db, db_path=db_path, usable_only=False)
        if dye.has_absorption and dye.extinction_coefficient
    ]


def absorption_spectrum(dye, *, db=None, db_path: str | None = None):
    """Return a dye's absorption spectrum scaled to epsilon(lambda).

    The stored curve is a peak-normalized shape; it is multiplied by the
    catalogued molar extinction coefficient so the result is in M⁻¹cm⁻¹.

    Parameters
    ----------
    dye : str, int or DyeProperties
        Chromophore name, probe id, or already-resolved properties.
    db : object, optional
        Open MMFDB handle.
    db_path : str, optional
        Database path.

    Returns
    -------
    tuple of np.ndarray or None
        ``(wavelength_nm, epsilon)``, or ``None`` when the database has no
        usable spectrum or no extinction coefficient for the dye.
    """
    with open_database(db_path, db) as handle:
        if handle is None:
            return None
        resolved = dye if isinstance(dye, DyeProperties) else dye_properties(dye, db=handle)
        if resolved is None or not resolved.extinction_coefficient:
            return None
        spectrum = _spectrum(handle, resolved.probe_id, "absorption")
        if spectrum is None:
            return None
        wavelength, shape = spectrum
        peak = float(np.max(shape))
        if not np.isfinite(peak) or peak <= 0.0:
            return None
        return wavelength, shape / peak * float(resolved.extinction_coefficient)


def extinction_at(
    dye, wavelength_nm: float, *, db=None, db_path: str | None = None
) -> float | None:
    """Molar extinction coefficient of a dye *at a given wavelength*.

    Excitation rarely happens at the absorption maximum, and the catalogued
    epsilon is the peak value: exciting a 650 nm dye at 488 nm delivers a small
    fraction of it. Reading epsilon off the spectrum is the difference between a
    correct excitation rate and one that is wrong by a large factor.

    Parameters
    ----------
    dye : str, int or DyeProperties
        Chromophore name, probe id, or already-resolved properties.
    wavelength_nm : float
        Excitation wavelength (nm).
    db : object, optional
        Open MMFDB handle.
    db_path : str, optional
        Database path.

    Returns
    -------
    float or None
        ``epsilon(lambda)`` in M⁻¹cm⁻¹, ``0.0`` outside the stored range, or
        ``None`` when the dye or its spectrum is unavailable.
    """
    spectrum = absorption_spectrum(dye, db=db, db_path=db_path)
    if spectrum is None:
        return None
    grid, epsilon = spectrum
    return float(np.interp(float(wavelength_nm), grid, epsilon, left=0.0, right=0.0))


def fret_pair(
    donor,
    acceptor,
    *,
    kappa2: float = 2.0 / 3.0,
    refractive_index: float = 1.33,
    db=None,
    db_path: str | None = None,
) -> FretPair | None:
    """Resolve a donor/acceptor pair and everything MMFDB implies for it.

    Parameters
    ----------
    donor, acceptor : str, int or DyeProperties
        The two dyes (name, probe id, or already-resolved properties).
    kappa2 : float, optional
        Orientation factor; ``2/3`` is the isotropic average and the usual
        assumption, and it enters R0 as ``kappa2^(1/6)``.
    refractive_index : float, optional
        Refractive index of the medium (1.33 water, ~1.4 for a protein
        environment); R0 scales as ``n^(-2/3)``.
    db : object, optional
        Open MMFDB handle.
    db_path : str, optional
        Database path.

    Returns
    -------
    FretPair or None
        ``None`` when either dye cannot be resolved.
    """
    with open_database(db_path, db) as handle:
        if handle is None:
            return None
        donor_dye = donor if isinstance(donor, DyeProperties) else dye_properties(donor, db=handle)
        acceptor_dye = (
            acceptor if isinstance(acceptor, DyeProperties) else dye_properties(acceptor, db=handle)
        )
        if donor_dye is None or acceptor_dye is None:
            return None

        provenance = {
            "quantum_yield_donor": ("mmfdb:property" if donor_dye.quantum_yield else "missing"),
            "quantum_yield_acceptor": (
                "mmfdb:property" if acceptor_dye.quantum_yield else "missing"
            ),
            "donor_lifetime": "mmfdb:property" if donor_dye.lifetime else "missing",
        }
        r0 = overlap = None

        emission = _spectrum(handle, donor_dye.probe_id, "emission")
        absorption = _spectrum(handle, acceptor_dye.probe_id, "absorption")
        if (
            emission is not None
            and absorption is not None
            and donor_dye.quantum_yield
            and acceptor_dye.extinction_coefficient
        ):
            wl_d, f_d = emission
            wl_a, eps_a = absorption
            low = max(wl_d.min(), wl_a.min())
            high = min(wl_d.max(), wl_a.max())
            if high - low > 1.0:
                grid = np.arange(low, high + 1.0, 1.0)
                donor_emission = np.interp(grid, wl_d, f_d, left=0.0, right=0.0)
                shape = np.interp(grid, wl_a, eps_a, left=0.0, right=0.0)
                peak = float(np.max(shape))
                if peak > 0 and float(np.max(donor_emission)) > 0:
                    # The stored curve is a normalized shape; scale it to epsilon(lambda).
                    epsilon = shape / peak * float(acceptor_dye.extinction_coefficient)
                    try:
                        r0, overlap = forster_radius_from_spectra(
                            grid,
                            donor_emission,
                            epsilon,
                            donor_quantum_yield=float(donor_dye.quantum_yield),
                            kappa2=float(kappa2),
                            refractive_index=float(refractive_index),
                        )
                        provenance["forster_radius"] = "mmfdb:spectra"
                    except ValueError:
                        r0 = overlap = None

        if r0 is None:
            try:
                stored = handle.lookup_forster_radius(donor_dye.name, acceptor_dye.name)
            except Exception:
                stored = None
            if stored:
                r0 = float(stored)
                provenance["forster_radius"] = "mmfdb:pair"
        provenance.setdefault("forster_radius", "missing")

        return FretPair(
            donor=donor_dye,
            acceptor=acceptor_dye,
            forster_radius=r0,
            overlap_integral=overlap,
            kappa2=float(kappa2),
            refractive_index=float(refractive_index),
            provenance=provenance,
        )


def apply_to_calibration(pair: FretPair, calibration=None) -> tuple:
    """Write what the dyes imply into a calibration group.

    Only quantities the database actually supplied are written; anything it
    could not answer keeps the calibration's current value, so a curated gap
    never silently overwrites a number the user set.

    Parameters
    ----------
    pair : FretPair
        The resolved dye pair.
    calibration : CalibrationParameters, optional
        Group to fill in place; a fresh one is created when omitted.

    Returns
    -------
    tuple
        ``(calibration, applied)`` where ``applied`` maps each written quantity
        to its provenance string.
    """
    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters

    calibration = calibration if calibration is not None else CalibrationParameters()
    applied: dict[str, str] = {}
    if pair is None:
        return calibration, applied
    if pair.donor.quantum_yield:
        calibration.phi_d = float(pair.donor.quantum_yield)
        applied["PhiD"] = pair.provenance.get("quantum_yield_donor", "mmfdb:property")
    if pair.acceptor.quantum_yield:
        calibration.phi_a = float(pair.acceptor.quantum_yield)
        applied["PhiA"] = pair.provenance.get("quantum_yield_acceptor", "mmfdb:property")
    if pair.forster_radius:
        calibration.r0 = float(pair.forster_radius)
        applied["R0"] = pair.provenance.get("forster_radius", "mmfdb:spectra")
    return calibration, applied
