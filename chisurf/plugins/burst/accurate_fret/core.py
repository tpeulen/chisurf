"""Accurate-FRET calibration on a burst table — loading, calibration, export.

Qt-free layer of the plugin. It turns a burst table (any delimited text file, or
the columns of a live ndX window) into the arrays the accurate-FRET core
needs, runs the automatic calibration
(:func:`chisurf.core.fluorescence.fret.accurate.auto_calibrate`), and hands back
the factors, the population summary and ready-to-plot series.

Two prior sources are supported and both are optional:

* a **light path** saved by the light-path simulator — its excitation/emission
  probabilities become the Gaussian priors of ``gamma``/``alpha``/``delta``;
* the donor **lifetime** column plus a static FRET line, which identifies
  ``gamma`` even for a single-population sample.
"""

from __future__ import annotations

import logging
import pathlib
from dataclasses import dataclass, field

import numpy as np
import tttrlib

from chisurf.core.fluorescence.burst.table import columns_from_data, read_burst_table
from chisurf.core.fluorescence.fret.accurate import AutoCalibration, auto_calibrate
from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
from chisurf.core.fluorescence.fret.lines import dynamic_fret_line, static_fret_line

logger = logging.getLogger(__name__)

# Which column is which channel is tttrlib.guess_burst_columns, shared with ndX.
__all__ = [
    "CalibrationResult",
    "read_burst_table",
    "columns_from_data",
    "calibrate",
    "list_lightpaths",
    "lightpath_prior",
    "export_csv",
]


@dataclass
class CalibrationResult:
    """Everything one calibration run produced.

    Attributes
    ----------
    calibration : AutoCalibration
        The automatic-calibration result (factors, uncertainties, populations).
    efficiency, stoichiometry : numpy.ndarray
        Per-burst accurate ``E`` and ``S``.
    tau_f : numpy.ndarray or None
        Per-burst donor lifetime, when a lifetime column was mapped.
    labels : numpy.ndarray
        Population label per burst (``-2`` acceptor-only, ``-1`` donor-only,
        ``0…`` FRET sub-populations).
    line, dynamic_line : FretLine or None
        Static and dynamic FRET lines matching the calibration.
    distance : numpy.ndarray
        Per-burst donor–acceptor distance.
    """

    calibration: AutoCalibration
    efficiency: np.ndarray
    stoichiometry: np.ndarray | None
    tau_f: np.ndarray | None
    labels: np.ndarray
    line: object | None = None
    dynamic_line: object | None = None
    distance: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    @property
    def factors(self) -> dict:
        """The posterior correction factors."""
        return self.calibration.factors

    def factor_rows(self) -> list[dict]:
        """Table rows: one per factor with value, uncertainty and its origin."""
        origin = {
            "alpha": "donor-only bursts",
            "delta": "acceptor-only bursts",
            "gamma": "E-S fit / FRET line",
            "beta": "E-S fit",
            "bg_dd": "given",
            "bg_da": "given",
            "bg_aa": "given",
            "r0": "given",
        }
        for message in self.calibration.messages:
            for key in ("alpha", "delta", "gamma"):
                if message.startswith(f"{key} not identifiable"):
                    origin[key] = "light path (optics prior)"
                elif message.startswith(f"{key}: data"):
                    origin[key] = "data × light-path prior"
        # A table cell renders one flat string, so the symbols come from
        # Unicode rather than markup. ``r0`` is spelled ``R_0`` only to be
        # typeset; the row keys stay the plain factor names.
        from chisurf.core.support.labels import to_unicode

        symbol = {key: to_unicode(key) for key in ("alpha", "beta", "gamma", "delta")}
        symbol["r0"] = to_unicode("R_0")

        rows = []
        for key in ("alpha", "beta", "gamma", "delta", "r0"):
            sigma = self.calibration.uncertainties.get(key, float("nan"))
            rows.append(
                {
                    "factor": symbol.get(key, key),
                    "value": f"{self.factors.get(key, float('nan')):.4f}",
                    "uncertainty": "—" if not np.isfinite(sigma) else f"{sigma:.4f}",
                    "origin": origin.get(key, ""),
                }
            )
        return rows

    def population_rows(self) -> list[dict]:
        """Table rows: one per FRET population (E, S, lifetime, distance, off-line)."""
        rows = []
        for p in self.calibration.populations:
            rows.append(
                {
                    "population": str(p["label"]),
                    "n": str(p["n"]),
                    "E": f"{p['E']:.4f} ± {p['sigma_E']:.4f}",
                    "S": f"{p['S']:.3f}",
                    "tau_f": f"{p['tau_f']:.3f}"
                    if "tau_f" in p and np.isfinite(p["tau_f"])
                    else "—",
                    "distance": f"{p['distance']:.1f} ± {p['sigma_distance']:.1f}",
                    "off_line": f"{p['deviation']:+.4f}" if "deviation" in p else "—",
                }
            )
        return rows


# ---------------------------------------------------------------------------
# the light-path (optics) prior
# ---------------------------------------------------------------------------


def list_lightpaths(db_path: str | None = None) -> list[dict]:
    """List the saved light-path simulations usable as an optics prior.

    Parameters
    ----------
    db_path : str, optional
        MMFDB path; the configured default is used when omitted.

    Returns
    -------
    list of dict
        ``{"operation_id", "name"}`` per saved light path (empty when the
        light-path simulator or its database is unavailable).
    """
    try:
        from chisurf.plugins.core.lightpath_simulator.core.workflow import (
            list_lightpaths as _list,
        )

        return list(_list(db_path).get("simulations", []))
    except Exception:
        logger.debug("no light-path simulations available", exc_info=True)
        return []


def lightpath_prior(
    operation_id: str,
    *,
    donor: str | None = None,
    acceptor: str | None = None,
    green_detector: str | None = None,
    red_detector: str | None = None,
    green_laser: str | None = None,
    red_laser: str | None = None,
    quantum_yields: dict | None = None,
    detection_efficiencies: dict | None = None,
    db_path: str | None = None,
) -> dict:
    """Build the ``lightpath`` argument of ``auto_calibrate`` from a saved light path.

    Reads the stored excitation/emission crosstalk matrices and resolves the dye
    and detector labels, defaulting to the first two of each (donor before
    acceptor, green detector before red) when they are not given explicitly.

    Parameters
    ----------
    operation_id : str
        Identifier of the saved light-path simulation.
    donor, acceptor : str, optional
        Dye labels; default to the first two columns of the excitation matrix.
    green_detector, red_detector : str, optional
        Detector labels; default to the first two columns of the emission matrix.
    green_laser : str, optional
        Donor-excitation laser; defaults to the first excitation row.
    red_laser : str, optional
        Acceptor-excitation laser (``delta`` is referenced to it); defaults to
        the second excitation row.
    quantum_yields : dict, optional
        ``{dye: QY}`` — the donor and acceptor quantum yields entering ``gamma``.
    detection_efficiencies : dict, optional
        ``{detector: g}`` — the detection efficiencies entering ``gamma``.
    db_path : str, optional
        MMFDB path.

    Returns
    -------
    dict
        Keyword arguments for
        :func:`chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`,
        ready to be passed as ``auto_calibrate(..., lightpath=...)``.

    Raises
    ------
    ValueError
        If the light path holds no crosstalk matrices.
    """
    from chisurf.plugins.core.lightpath_simulator.core.workflow import get_lightpath

    payload = get_lightpath(operation_id, db_path)
    matrices = payload.get("crosstalk_matrices")
    if not matrices:
        raise ValueError(f"light path {operation_id} carries no crosstalk matrices")
    dyes = list((matrices.get("excitation") or {}).get("columns", []))
    detectors = list((matrices.get("emission") or {}).get("columns", []))
    lasers = list((matrices.get("excitation") or {}).get("rows", []))
    donor = donor or (dyes[0] if dyes else None)
    acceptor = acceptor or (dyes[1] if len(dyes) > 1 else None)
    green_detector = green_detector or (detectors[0] if detectors else None)
    red_detector = red_detector or (detectors[1] if len(detectors) > 1 else None)
    qy = quantum_yields or {}
    det = detection_efficiencies or {}
    return {
        "matrices": matrices,
        "donor": donor,
        "acceptor": acceptor,
        "green_detector": green_detector,
        "red_detector": red_detector,
        "green_laser": green_laser or (lasers[0] if lasers else None),
        "red_laser": red_laser or (lasers[1] if len(lasers) > 1 else None),
        "qy_d": float(qy.get(donor, 1.0)),
        "qy_a": float(qy.get(acceptor, 1.0)),
        "gG": float(det.get(green_detector, 1.0)),
        "gR": float(det.get(red_detector, 1.0)),
    }


# ---------------------------------------------------------------------------
# the calibration run
# ---------------------------------------------------------------------------


def calibrate(
    i_dd,
    i_da,
    i_aa=None,
    tau_f=None,
    *,
    donor_lifetime: float = 4.0,
    forster_radius: float = 52.0,
    linker_sigma: float = 6.0,
    background=(0.0, 0.0, 0.0),
    gamma_source: str = "auto",
    n_bootstrap: int = 50,
    lightpath: dict | None = None,
    use_priors: bool = True,
    max_fret_populations: int = 3,
    min_population: int = 20,
    dynamic_distances=None,
    calibration: CalibrationParameters | None = None,
) -> CalibrationResult:
    """Run the automatic calibration and package everything the GUI/CLI shows.

    Parameters
    ----------
    i_dd, i_da : array_like
        Donor and acceptor signal under donor excitation, per burst.
    i_aa : array_like, optional
        Acceptor signal under acceptor excitation (ALEX/PIE).
    tau_f : array_like, optional
        Fluorescence-averaged donor lifetime per burst (ns).
    donor_lifetime : float, optional
        Donor-only lifetime tau_D(0) (ns) anchoring the FRET lines.
    forster_radius : float, optional
        Förster radius R0 (Å).
    linker_sigma : float, optional
        Width of the linker distance distribution (Å) used for the static line.
    background : tuple of float, optional
        ``(Bg_DD, Bg_DA, Bg_AA)`` per burst, in the units of the channels.
    gamma_source : str, optional
        ``"auto"``, ``"es"``, ``"lifetime"`` or ``"combined"``.
    n_bootstrap : int, optional
        Bootstrap resamples for the factor uncertainties.
    lightpath : dict, optional
        Optics prior (see :func:`lightpath_prior`).
    use_priors : bool, optional
        Combine the data estimates with the optics priors.
    max_fret_populations : int, optional
        Largest number of FRET sub-populations searched.
    min_population : int, optional
        Smallest population accepted for a factor estimate.
    dynamic_distances : tuple of float, optional
        ``(R1, R2)`` limiting distances of a dynamic FRET line to draw; the
        efficiency extremes of the found populations are used when omitted.
    calibration : CalibrationParameters, optional
        Group to refine in place (e.g. the session calibration).

    Returns
    -------
    CalibrationResult
        Factors, per-burst accurate values, populations and FRET lines.
    """
    calib = calibration if calibration is not None else CalibrationParameters()
    calib.bg_dd, calib.bg_da, calib.bg_aa = (float(b) for b in background)
    calib.r0 = float(forster_radius)

    line = None
    if tau_f is not None:
        line = static_fret_line(
            float(donor_lifetime), r0=float(forster_radius), sigma=float(linker_sigma)
        )

    result = auto_calibrate(
        i_dd,
        i_da,
        i_aa,
        calibration=calib,
        lightpath=lightpath,
        tau_f=tau_f,
        line=line,
        donor_lifetime=float(donor_lifetime),
        linker_sigma=float(linker_sigma),
        gamma_source=gamma_source,
        n_bootstrap=int(n_bootstrap),
        use_priors=use_priors,
        max_fret_populations=int(max_fret_populations),
        min_population=int(min_population),
    )

    split = result.split
    labels = np.zeros(np.asarray(i_dd).shape, dtype=int)
    if split is not None:
        labels = np.where(split.fret, split.fret_labels, -1)
        labels = np.where(split.acceptor_only, -2, labels)

    final = tttrlib.accurate_fret(
        i_dd,
        i_da,
        i_aa,
        factors=calib.as_dict(),
        tau_f=tau_f,
        line=line,
        uncertainties=result.uncertainties,
        labels=labels,
    )

    dynamic = None
    if line is not None:
        distances = dynamic_distances
        if distances is None and len(result.populations) >= 2:
            e_values = [p["E"] for p in result.populations]
            distances = tuple(
                float(forster_radius) * (1.0 / min(max(e, 1e-3), 1 - 1e-3) - 1.0) ** (1 / 6)
                for e in (max(e_values), min(e_values))
            )
        if distances is not None:
            dynamic = dynamic_fret_line(
                float(donor_lifetime),
                r0=float(forster_radius),
                sigma=float(linker_sigma),
                distance_1=float(distances[0]),
                distance_2=float(distances[1]),
            )

    return CalibrationResult(
        calibration=result,
        efficiency=np.asarray(final["E"], dtype=float),
        stoichiometry=None if final["S"] is None else np.asarray(final["S"], dtype=float),
        tau_f=None if tau_f is None else np.asarray(tau_f, dtype=float),
        labels=labels,
        line=line,
        dynamic_line=dynamic,
        distance=np.asarray(final["distance"], dtype=float),
        meta={
            "donor_lifetime": float(donor_lifetime),
            "r0": float(forster_radius),
            "linker_sigma": float(linker_sigma),
            "gamma_source": gamma_source,
        },
    )


def export_csv(path: str | pathlib.Path, result: CalibrationResult) -> None:
    """Write the per-burst accurate values and the calibration header to a CSV file.

    The correction factors are written as ``#`` comment lines so the file
    documents the calibration it was produced with.

    Parameters
    ----------
    path : str or pathlib.Path
        Destination file.
    result : CalibrationResult
        The run to export.
    """
    columns = {"E": result.efficiency, "label": result.labels}
    if result.stoichiometry is not None:
        columns["S"] = result.stoichiometry
    if result.tau_f is not None:
        columns["tau_f"] = result.tau_f
    if result.distance is not None:
        columns["R_DA"] = result.distance
    header_lines = [f"# {line}" for line in result.calibration.report().splitlines()]
    data = np.column_stack([np.asarray(v, dtype=float) for v in columns.values()])
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header_lines) + "\n")
        fh.write(",".join(columns) + "\n")
        np.savetxt(fh, data, delimiter=",", fmt="%.6g")


def write_container(
    source: str | pathlib.Path,
    result: CalibrationResult,
    *,
    parameters: dict | None = None,
    out_dir: str | pathlib.Path | None = None,
) -> str:
    """Write the corrected per-burst values into the measurement's container.

    Two objects, because there are two grains. The corrected ``E``, ``S``,
    lifetime and distance are per *burst*; the correction factors and the
    populations they were fitted from are per *population*, and a table with
    one row per population cannot be a companion — which is why
    :func:`export_csv` puts the calibration in ``#`` comment lines, where it is
    readable and not queryable.

    The factors are the reason to keep them: an accurate ``E`` means nothing
    without the α, β, γ, δ and R₀ it was computed with, and a file that carries
    the values and not the calibration is a file whose numbers cannot be
    checked or recomputed.

    Parameters
    ----------
    source : str or pathlib.Path
        The instrument file the bursts came from, or the container itself.
    result : CalibrationResult
        The run to record.
    parameters : dict, optional
        The settings. Their hash is the identity of the run.
    out_dir : str or pathlib.Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    columns: dict[str, np.ndarray] = {
        "Burst Index": np.arange(len(result.efficiency), dtype=np.int64),
        "E": np.asarray(result.efficiency, dtype=float),
        # -2 acceptor-only, -1 donor-only, 0… a FRET sub-population. An integer
        # column, so the sentinels stay exact.
        "Population": np.asarray(result.labels, dtype=np.int32),
    }
    units = {
        "Burst Index": "dimensionless",
        "E": "dimensionless",
        "Population": "dimensionless",
    }
    for name, values, unit in (
        ("S", result.stoichiometry, "dimensionless"),
        ("Tau (donor)", result.tau_f, "nanoseconds"),
        ("R_DA", result.distance, "angstroms"),
    ):
        if values is not None:
            columns[name] = np.asarray(values, dtype=float)
            units[name] = unit

    written = write_burst_artifact(
        source,
        store_from_arrays(columns),
        name="accurate fret",
        artifact_kind="analysis_result",
        operation_type="calibration",
        row_grain="burst",
        parameters=parameters,
        derived_from="bursts",
        source_row_column="Burst Index",
        target_row_column="Burst Index",
        units=units,
        out_dir=out_dir,
    )

    populations = result.calibration.populations
    if populations:
        keys = (
            "label",
            "n",
            "E",
            "sigma_E",
            "S",
            "tau_f",
            "distance",
            "sigma_distance",
            "deviation",
        )
        rows = {
            key: np.asarray([p.get(key, float("nan")) for p in populations], dtype=float)
            for key in keys
            if any(key in p for p in populations)
        }
        # The factors are constant over the populations, and that is the point:
        # they describe the calibration all of them share, so every row can be
        # read on its own without a header comment to go and find.
        #
        # Under the names flrCIF gives them, from the declaration beside this
        # file -- these factors are not a chisurf invention and
        # `_flr_fret_calibration_parameters` has carried them all along.
        from .calibration_columns import calibration_columns

        # From the calibration *object*, falling back to the factor dict. The
        # dict holds only what the calibration determined -- alpha, beta, gamma,
        # delta, r0 -- while the quantum yields are inputs it was determined
        # *with*, and gG/gR is a function of all three. Writing only the
        # determined half stored a calibration nobody could reproduce: gamma
        # without the yields it was measured against is not a number that can be
        # applied to another instrument.
        source_calibration = getattr(result, "calibration", None)
        for spec in calibration_columns():
            factor = spec["factor"]
            value = getattr(source_calibration, factor, None)
            if value is None:
                value = result.factors.get(factor, float("nan"))
            rows[spec["column"]] = np.full(len(populations), float(value))

        # The derived one, written for whoever reads the file rather than
        # recomputed by them.
        phi_a = float(rows["phi_acceptor"][0])
        phi_d = float(rows["phi_donor"][0])
        gamma = float(rows["gamma"][0])
        rows["gG_gR_ratio"] = np.full(
            len(populations),
            (phi_a / phi_d) / gamma if phi_d and gamma else float("nan"),
        )
        write_burst_artifact(
            source,
            store_from_arrays(rows),
            name="accurate fret calibration",
            artifact_kind="parameter_table",
            operation_type="calibration",
            row_grain="species",
            parameters=parameters,
            derived_from="accurate fret",
            source_row_column="Population",
            target_row_column="label",
            units={
                **{spec["column"]: spec["units"] for spec in calibration_columns()},
                "distance": "angstroms",
                "sigma_distance": "angstroms",
                "tau_f": "nanoseconds",
                "E": "dimensionless",
                "sigma_E": "dimensionless",
                "S": "dimensionless",
                "deviation": "dimensionless",
                "alpha": "dimensionless",
                "beta": "dimensionless",
                "gamma": "dimensionless",
                "delta": "dimensionless",
                "label": "dimensionless",
                "n": "counts",
            },
            out_dir=out_dir,
        )
    return written
