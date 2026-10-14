"""The Förster radius calculator: R0 of a donor–acceptor pair from MMFDB spectra.

What the *calc R0* button of the FRET models' κ² row opens, without a toolkit:
the MMFDB queries (probes that carry an emission or an absorption spectrum,
their spectra, their quantum yield and extinction coefficient, a tabulated R0
of the pair), and the computation -- both spectra interpolated onto 1000 points
of the range they share, the peak-normalised absorption scaled to ε_max, and
:func:`~chisurf.core.fluorescence.fret.forster.forster_radius_from_spectra`
with κ² = 2/3 (orientation is the FRET model's κ² controls' business).

:class:`ForsterCalculatorModel` is the form: its attributes are the fields
(``donor``, ``acceptor``, ``donor_qy``, ``acceptor_emax``,
``refractive_index``) and the outputs (``r0``, ``overlap``, ``cached``,
``status``). The Qt widget and the emtk dialog both draw it. The database is
injectable: ``open_database`` is a callable that returns an opened
``MFDatabase``-like object (``conn`` with ``sqlite3.Row`` rows,
``get_optical_properties``, ``close``); by default MMFDB is opened read-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra
from chisurf.core.support.i18n import tr

if TYPE_CHECKING:
    from mmfdb.repository import MFDatabase

#: Optical-property names an MMFDB probe stores its peak extinction coefficient under.
EXT_COEFF_ALIASES = frozenset(
    {
        "ext_coeff",
        "molar_extinction",
        "molar_ec",
        "epsilon",
        "extinction coefficient",
        "ext_coeff_max",
        "ec_max",
    }
)

#: Optical-property names an MMFDB probe stores its fluorescence quantum yield under.
QY_ALIASES = frozenset(
    {
        "qy",
        "quantum yield",
        "phi",
        "phi_d",
        "qy_d",
        "quantum_yield",
        "fluorescence quantum yield",
        "q_fluor",
    }
)

#: Points of the common wavelength grid the overlap integral is evaluated on.
GRID_POINTS = 1000

#: The orientation factor of the calculator (dynamic isotropic averaging).
KAPPA2 = 2.0 / 3.0

MMFDB_UNAVAILABLE = "MMFDB is unavailable; spectra selection requires MMFDB."
MMFDB_UNREADABLE = "Could not open MMFDB database."


def open_spectra_database() -> MFDatabase:
    """Open the MMFDB read-only, importing it only when the calculator needs it.

    Returns
    -------
    MFDatabase
        The resolved MMFDB, opened read-only.

    Raises
    ------
    RuntimeError
        If the optional ``mmfdb`` package is not installed.
    """
    try:
        from mmfdb.repository import MFDatabase
        from mmfdb.store.database_resolver import resolve_database_path
    except ModuleNotFoundError as exc:
        if exc.name != "mmfdb" and not (exc.name or "").startswith("mmfdb."):
            raise
        raise RuntimeError(MMFDB_UNAVAILABLE) from exc
    return MFDatabase(str(resolve_database_path()), readonly=True)


def query_probes_with_spectrum(db: Any, spectrum_type: str) -> list[dict[str, Any]]:
    """The probes that carry a spectrum of *spectrum_type*, by name.

    Parameters
    ----------
    db : MFDatabase
        An opened database.
    spectrum_type : str
        ``"emission"`` or ``"absorption"``.

    Returns
    -------
    list of dict
        ``{"probe_id", "chromophore_name"}`` per probe, sorted by name.
    """
    rows = db.conn.execute(
        """SELECT DISTINCT p.probe_id, p.chromophore_name
           FROM probes p
           JOIN spectra s ON s.probe_id = p.probe_id
           WHERE s.spectrum_type = ?
             AND p.deleted_at IS NULL
             AND s.deleted_at IS NULL
           ORDER BY p.chromophore_name""",
        (spectrum_type,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_spectra_for_probe(db: Any, probe_id: int) -> dict[str, dict[str, np.ndarray]]:
    """Every live spectrum of a probe.

    Parameters
    ----------
    db : MFDatabase
        An opened database.
    probe_id : int
        The probe.

    Returns
    -------
    dict
        ``spectrum_type -> {"wavelengths", "intensity"}`` (float64 arrays).
    """
    rows = db.conn.execute(
        """SELECT spectrum_type, wavelengths, intensity_values
           FROM spectra
           WHERE probe_id = ?
             AND deleted_at IS NULL""",
        (probe_id,),
    ).fetchall()
    result: dict[str, dict[str, np.ndarray]] = {}
    for r in rows:
        result[r["spectrum_type"]] = {
            "wavelengths": np.frombuffer(r["wavelengths"], dtype=np.float64),
            "intensity": np.frombuffer(r["intensity_values"], dtype=np.float64),
        }
    return result


def lookup_optical_property(db: Any, probe_id: int, name_aliases: frozenset[str]) -> float | None:
    """The first positive optical property of a probe stored under one of *name_aliases*.

    Parameters
    ----------
    db : MFDatabase
        An opened database.
    probe_id : int
        The probe.
    name_aliases : frozenset of str
        Accepted ``property_name`` spellings (:data:`QY_ALIASES`, :data:`EXT_COEFF_ALIASES`).

    Returns
    -------
    float or None
        The value, or ``None`` when the probe has no usable one.
    """
    for prop in db.get_optical_properties(probe_id):
        if prop["property_name"] in name_aliases:
            try:
                val = float(prop["property_value"])
            except (ValueError, TypeError):
                continue
            if val > 0:
                return val
    return None


def lookup_cached_r0(db: Any, donor_name: str, acceptor_name: str) -> float | None:
    """A tabulated R0 of the pair (``flr_fret_forster_radius``), in Å.

    Parameters
    ----------
    db : MFDatabase
        An opened database.
    donor_name, acceptor_name : str
        Chromophore names of the pair.

    Returns
    -------
    float or None
        The tabulated value, or ``None`` when the pair has none.
    """
    row = db.conn.execute(
        """SELECT fr.forster_radius
           FROM flr_fret_forster_radius fr
           JOIN probes d ON d.probe_id = fr.donor_probe_id
           JOIN probes a ON a.probe_id = fr.acceptor_probe_id
           WHERE d.chromophore_name = ?
             AND a.chromophore_name = ?
             AND d.deleted_at IS NULL
             AND a.deleted_at IS NULL
           LIMIT 1""",
        (donor_name, acceptor_name),
    ).fetchone()
    return float(row[0]) if row else None


def spectrum_summary(kind: str, data: dict[str, np.ndarray]) -> str:
    """One line describing a spectrum: kind, number of points and range.

    Parameters
    ----------
    kind : str
        ``"emission"`` or ``"absorption"``.
    data : dict
        ``{"wavelengths", "intensity"}``.

    Returns
    -------
    str
    """
    wl = data["wavelengths"]
    return f"{tr(kind)} · {len(wl)} pts · {wl[0]:.0f}–{wl[-1]:.0f} nm"


def _interp_fill0(xp: np.ndarray, fp: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Linear interpolation that is zero outside ``[xp[0], xp[-1]]``."""
    inside = (x >= xp[0]) & (x <= xp[-1])
    out = np.zeros_like(x, dtype=float)
    out[inside] = np.interp(x[inside], xp, fp)
    return out


def overlap_curves(
    donor_emission: dict[str, np.ndarray],
    acceptor_absorption: dict[str, np.ndarray],
    acceptor_emax: float,
) -> dict[str, np.ndarray] | None:
    """Both spectra on the common grid the overlap integral is evaluated on.

    Parameters
    ----------
    donor_emission, acceptor_absorption : dict
        ``{"wavelengths", "intensity"}`` of the donor's emission and the
        acceptor's absorption spectrum.
    acceptor_emax : float
        Peak molar extinction coefficient the absorption is scaled to [M⁻¹ cm⁻¹].

    Returns
    -------
    dict or None
        ``wavelengths`` (:data:`GRID_POINTS` points over the shared range),
        ``donor`` (emission as stored) and ``acceptor`` (extinction, peak
        ``acceptor_emax``); ``None`` when the spectra share no range.
    """
    acceptor_ext = np.asarray(acceptor_absorption["intensity"], dtype=float)
    peak = float(acceptor_ext.max())
    if peak > 0:
        acceptor_ext = acceptor_ext / peak * acceptor_emax
    wl_min = max(
        float(np.min(donor_emission["wavelengths"])),
        float(np.min(acceptor_absorption["wavelengths"])),
    )
    wl_max = min(
        float(np.max(donor_emission["wavelengths"])),
        float(np.max(acceptor_absorption["wavelengths"])),
    )
    if wl_min >= wl_max:
        return None
    grid = np.linspace(wl_min, wl_max, GRID_POINTS)
    return {
        "wavelengths": grid,
        "donor": _interp_fill0(donor_emission["wavelengths"], donor_emission["intensity"], grid),
        "acceptor": _interp_fill0(acceptor_absorption["wavelengths"], acceptor_ext, grid),
    }


class ForsterCalculatorModel:
    """The calculator's form: pick a donor and an acceptor, get R0 in Å.

    Parameters
    ----------
    open_database : callable, optional
        ``open_database() -> MFDatabase``; :func:`open_spectra_database` by
        default. Called once on :meth:`load` (probes, spectra, optical
        properties) and once per :meth:`compute` (the tabulated R0); every
        database it returns is closed after use.
    load : bool, optional
        Read the probes now (default). ``False`` leaves the lists empty until
        :meth:`load` is called.

    Attributes
    ----------
    donor, acceptor : int or None
        The chosen probes (``probe_id``).
    donor_qy, acceptor_emax, refractive_index : float
        Inputs of the R0 formula.
    r0 : float or None
        The result in Å; ``None`` until a pair is chosen.
    overlap : float or None
        The overlap integral J [M⁻¹ cm⁻¹ nm⁴] (``None`` for a tabulated R0).
    cached : bool
        Whether ``r0`` is the database's tabulated value.
    curves : dict or None
        :func:`overlap_curves` of the last computation, for a plot.
    status : str
        One line for the user: the result, or why there is none.
    detail : str
        :attr:`status` without the R0 -- J, *cached*, or why there is no
        result -- for a form that shows ``r0`` in a field of its own.
    available : bool
        Whether the database could be read.
    """

    def __init__(self, open_database: Callable[[], Any] | None = None, load: bool = True) -> None:
        self._open_database = open_database or open_spectra_database
        self.donor: int | None = None
        self.acceptor: int | None = None
        self.donor_qy = 0.9
        self.acceptor_emax = 100_000.0
        self.refractive_index = 1.33
        self.r0: float | None = None
        self.overlap: float | None = None
        self.cached = False
        self.curves: dict[str, np.ndarray] | None = None
        self.status = ""
        self.detail = ""
        self.available = False
        self.probe_names: dict[int, str] = {}
        self.probe_spectra: dict[int, dict[str, dict[str, np.ndarray]]] = {}
        #: Stored quantum yield / ε_max per probe, ``None`` where MMFDB has none.
        self.probe_properties: dict[int, dict[str, float | None]] = {}
        self.donors: list[int] = []
        self.acceptors: list[int] = []
        if load:
            self.load()

    # ---- database -------------------------------------------------------

    def load(self) -> bool:
        """Read the probes with an emission or absorption spectrum, their spectra and properties.

        Returns
        -------
        bool
            Whether the database could be read; :attr:`status` says why not.
        """
        try:
            db = self._open_database()
        except RuntimeError as exc:
            self.status = self.detail = tr(str(exc))
            self.available = False
            return False
        except Exception:
            self.status = self.detail = tr(MMFDB_UNREADABLE)
            self.available = False
            return False
        try:
            donors = query_probes_with_spectrum(db, "emission")
            acceptors = query_probes_with_spectrum(db, "absorption")
            for p in donors + acceptors:
                self.probe_names[p["probe_id"]] = p["chromophore_name"]
            for pid in self.probe_names:
                spectra = get_spectra_for_probe(db, pid)
                if spectra:
                    self.probe_spectra[pid] = spectra
                self.probe_properties[pid] = {
                    "qy": lookup_optical_property(db, pid, QY_ALIASES),
                    "emax": lookup_optical_property(db, pid, EXT_COEFF_ALIASES),
                }
            self.donors = [
                p["probe_id"]
                for p in donors
                if "emission" in self.probe_spectra.get(p["probe_id"], {})
            ]
            self.acceptors = [
                p["probe_id"]
                for p in acceptors
                if "absorption" in self.probe_spectra.get(p["probe_id"], {})
            ]
        finally:
            db.close()
        self.available = True
        self.status = self.detail = ""
        return True

    # ---- choices --------------------------------------------------------

    def probe_name(self, pid: int | None) -> str:
        """The chromophore name of *pid* (``"?"`` when unknown)."""
        if pid is None:
            return "?"
        return self.probe_names.get(pid, "?")

    def donor_options(self) -> list[tuple[Any, str]]:
        """``(probe_id, name)`` of every donor with an emission spectrum, after the empty entry."""
        return [("", "")] + [(pid, self.probe_names[pid]) for pid in self.donors]

    def acceptor_options(self) -> list[tuple[Any, str]]:
        """``(probe_id, name)`` of every acceptor with an absorption spectrum, after the empty entry."""
        return [("", "")] + [(pid, self.probe_names[pid]) for pid in self.acceptors]

    def _spectrum(self, pid: int | None, kind: str) -> dict[str, np.ndarray] | None:
        """The stored *kind* spectrum of probe *pid*; ``None`` when there is none."""
        return None if pid is None else self.probe_spectra.get(pid, {}).get(kind)

    def _property(self, pid: int | None, key: str) -> float | None:
        """The stored optical property *key* of probe *pid*; ``None`` when there is none."""
        return None if pid is None else self.probe_properties.get(pid, {}).get(key)

    def spectra_text(self) -> str:
        """The chosen donor's emission and acceptor's absorption spectrum, one line each."""
        lines = []
        for label, pid, kind in (
            ("Donor", self.donor, "emission"),
            ("Acceptor", self.acceptor, "absorption"),
        ):
            spectrum = self._spectrum(pid, kind)
            if spectrum is not None:
                lines.append(f"{tr(label)}: {spectrum_summary(kind, spectrum)}")
        return "\n".join(lines)

    @staticmethod
    def _probe_id(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def set_donor(self, value: Any) -> None:
        """Choose the donor; its stored quantum yield fills :attr:`donor_qy`, then R0 is recomputed."""
        self.donor = self._probe_id(value)
        qy = self._property(self.donor, "qy")
        if qy is not None:
            self.donor_qy = qy
        self.compute()

    def set_acceptor(self, value: Any) -> None:
        """Choose the acceptor; its stored ε_max fills :attr:`acceptor_emax`, then R0 is recomputed."""
        self.acceptor = self._probe_id(value)
        emax = self._property(self.acceptor, "emax")
        if emax is not None:
            self.acceptor_emax = emax
        self.compute()

    def changed(self, _value: Any = None) -> None:
        """An input changed: recompute R0."""
        self.compute()

    # ---- computation ----------------------------------------------------

    def _clear(self, status: str = "", detail: str | None = None) -> None:
        self.r0 = None
        self.overlap = None
        self.cached = False
        self.curves = None
        self.status = status
        self.detail = status if detail is None else detail

    def _cached_r0(self) -> float | None:
        # The database was readable at load; if it is not now, compute from the spectra.
        try:
            db = self._open_database()
        except Exception:
            return None
        try:
            return lookup_cached_r0(db, self.probe_name(self.donor), self.probe_name(self.acceptor))
        finally:
            db.close()

    def compute(self) -> float | None:
        """R0 of the chosen pair, in Å: tabulated in MMFDB if it is, else from the spectra.

        Returns
        -------
        float or None
            :attr:`r0`; ``None`` while a probe or its spectrum is missing or the
            computation fails (:attr:`status` says why).
        """
        donor_em = self._spectrum(self.donor, "emission")
        acceptor_abs = self._spectrum(self.acceptor, "absorption")
        if donor_em is None or acceptor_abs is None:
            if self.available:
                self._clear()
            return None

        curves = overlap_curves(donor_em, acceptor_abs, float(self.acceptor_emax))
        cached = self._cached_r0()
        if cached is not None and cached > 0:
            self._clear(
                tr("R₀ = {r0:.1f} Å  (cached)").format(r0=cached),
                tr("tabulated in MMFDB for this pair (cached)"),
            )
            self.r0 = cached
            self.cached = True
            self.curves = curves
            return self.r0

        if curves is None:
            self._clear(tr("R₀ = 0.0 Å  (no spectral overlap)"), tr("no spectral overlap"))
            self.r0 = 0.0
            return self.r0

        try:
            r0, overlap = forster_radius_from_spectra(
                curves["wavelengths"],
                curves["donor"],
                curves["acceptor"],
                donor_quantum_yield=float(self.donor_qy),
                kappa2=KAPPA2,
                refractive_index=float(self.refractive_index),
            )
        except (ValueError, ZeroDivisionError) as exc:
            self._clear(tr("Error: {error}").format(error=exc))
            return None
        self._clear(
            tr("R₀ = {r0:.1f} Å    J = {j:.3e} M⁻¹ cm⁻¹ nm⁴").format(r0=r0, j=overlap),
            tr("J = {j:.3e} M⁻¹ cm⁻¹ nm⁴").format(j=overlap),
        )
        self.r0 = float(r0)
        self.overlap = float(overlap)
        self.curves = curves
        return self.r0

    def enabled(self, name: str) -> bool:
        """Whether a field or action is usable now (the form's ``enabled`` hook)."""
        if name in ("donor", "acceptor"):
            return self.available
        if name == "apply":
            return self.r0 is not None
        return True


__all__ = [
    "EXT_COEFF_ALIASES",
    "ForsterCalculatorModel",
    "GRID_POINTS",
    "KAPPA2",
    "QY_ALIASES",
    "get_spectra_for_probe",
    "lookup_cached_r0",
    "lookup_optical_property",
    "open_spectra_database",
    "overlap_curves",
    "query_probes_with_spectrum",
    "spectrum_summary",
]
