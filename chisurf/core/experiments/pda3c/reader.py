"""Three-colour PDA experiment readers (PRD-65).

A tcPDA dataset is a **burst table**, not a curve: five photon counts per burst,
``F_BB``/``F_BG``/``F_BR`` under blue excitation and ``F_GG``/``F_GR`` under
green. Two readers produce one:

- :class:`Pda3cBurstTableReader` loads a table that upstream burst selection
  already produced (CSV or ``.npz``);
- :class:`Pda3cSimulatorReader` generates one from a known model, so the model
  and its editor can be exercised — and a fit validated against ground truth —
  without a three-colour measurement to hand.

Both wrap the table in a :class:`~chisurf.core.data.DataCurve` whose
``meta_data['pda3c']`` carries the counts. The curve's ``y`` is the measured
proximity-ratio histograms the model plots against, so the standard plotting
machinery works unchanged; the fit objective is the burst likelihood and does
not read ``y``.
"""

from __future__ import annotations

import pathlib

import numpy as np

import chisurf.core.data
from chisurf.core.experiments.core.reader import ExperimentReader

#: Column names accepted in a burst table, in canonical order.
COLUMNS = ("F_BB", "F_BG", "F_BR", "F_GG", "F_GR")


def _wrap(blue, green, name: str) -> chisurf.core.data.DataCurve:
    """Wrap blue/green count tables into a DataCurve carrying ``pda3c`` metadata."""
    from chisurf.core.fluorescence.pda3c import BurstCounts
    from chisurf.core.models.pda3c.tcpda import observed_ratio_histograms

    blue = np.atleast_2d(np.asarray(blue, dtype=float))
    green = np.atleast_2d(np.asarray(green, dtype=float))
    counts = BurstCounts(blue=blue, green=green)

    histogram = observed_ratio_histograms(counts.collapsed()) * float(blue.shape[0])
    x = np.arange(histogram.size, dtype=float)
    curve = chisurf.core.data.DataCurve(
        name=name,
        load_filename_on_init=False,
        x=x,
        y=histogram,
        ey=np.sqrt(np.maximum(histogram, 1.0)),
    )
    payload = {
        "blue": blue,
        "green": green,
        "n_bursts": int(blue.shape[0]),
        "columns": list(COLUMNS),
    }
    try:
        curve.meta_data["pda3c"] = payload
    except Exception:
        pass
    # Also as a plain attribute, mirroring how the two-colour reader exposes
    # its payload, so consumers can reach it either way.
    curve.pda3c = payload
    return curve


def load_burst_table(filename) -> tuple:
    """Load a five-column burst table from ``.npz``, ``.npy`` or a text file.

    Parameters
    ----------
    filename : str or pathlib.Path
        Path to the table. ``.npz`` files are read by the column names in
        :data:`COLUMNS` (or by a ``blue``/``green`` pair); text files are read
        as five whitespace/comma-separated columns in canonical order, with an
        optional header line.

    Returns
    -------
    blue : numpy.ndarray
        ``(n_bursts, 3)`` counts under blue excitation.
    green : numpy.ndarray
        ``(n_bursts, 2)`` counts under green excitation.
    """
    path = pathlib.Path(filename)
    if path.suffix == ".npz":
        with np.load(path) as handle:
            if "blue" in handle and "green" in handle:
                return np.asarray(handle["blue"]), np.asarray(handle["green"])
            table = np.stack([np.asarray(handle[c]) for c in COLUMNS], axis=1)
    elif path.suffix == ".npy":
        table = np.asarray(np.load(path))
    else:
        table = np.genfromtxt(path, delimiter=None, names=None, comments="#")
        if table.ndim == 1:
            table = table.reshape(1, -1)
        if np.isnan(table).all(axis=1)[0]:  # a header line survived
            table = table[1:]
    table = np.asarray(table, dtype=float)
    if table.ndim != 2 or table.shape[1] < 5:
        raise ValueError(f"expected a 5-column burst table, got shape {table.shape}")
    return table[:, :3], table[:, 3:5]


class Pda3cBurstTableReader(ExperimentReader):
    """Read a three-colour burst table produced by upstream burst selection."""

    name = "tcPDA burst table"

    def __init__(self, *args, **kwargs):
        """Initialize the burst-table reader.

        Parameters
        ----------
        *args, **kwargs
            Forwarded to :class:`~chisurf.core.experiments.core.reader.ExperimentReader`.
        """
        super().__init__(*args, **kwargs)

    @staticmethod
    def autofitrange(data, **kwargs) -> tuple:
        """Return the full index range; there is no windowing on a burst table."""
        try:
            return 0, int(np.asarray(data.y).size)
        except Exception:
            return 0, 0

    def read(self, filename=None, *args, **kwargs):
        """Read one or more burst tables into an experiment data group."""
        group = chisurf.core.data.ExperimentDataCurveGroup([])
        if filename is None:
            return group
        names = filename if isinstance(filename, (list, tuple)) else [filename]
        for entry in names:
            path = pathlib.Path(entry)
            if not path.is_file():
                continue
            blue, green = load_burst_table(path)
            curve = _wrap(blue, green, name=path.name)
            curve.experiment = getattr(self, "experiment", None)
            group.append(curve)
        return group


class Pda3cSimulatorReader(ExperimentReader):
    """Generate a synthetic three-colour burst table from a known model.

    Three-colour data is scarce, and a model nobody can open is a model nobody
    checks. This makes the tcPDA model immediately usable — and lets a fit be
    validated against a truth the reader itself set.
    """

    name = "tcPDA simulator"

    def __init__(
            self,
            n_bursts: int = 4000,
            r_gr: float = 52.0,
            r_bg: float = 46.0,
            r_br: float = 68.0,
            sigma: float = 6.0,
            correlation: float = 0.0,
            photons_blue: float = 40.0,
            photons_green: float = 35.0,
            r0_bg: float = 49.0,
            r0_br: float = 52.0,
            r0_gr: float = 51.0,
            seed: int = 1,
            *args,
            **kwargs,
    ):
        """Initialize the simulator with the ground truth it will generate.

        Parameters
        ----------
        n_bursts : int
            Number of bursts to draw.
        r_gr, r_bg, r_br : float
            True mean distances, in Angstrom.
        sigma : float
            True width of all three distance distributions.
        correlation : float
            True correlation between the GR and BG distances.
        photons_blue, photons_green : float
            Mean signal photons per burst in each excitation period.
        r0_bg, r0_br, r0_gr : float
            Förster radii.
        seed : int
            Random seed, so a simulated dataset is reproducible.
        *args, **kwargs
            Forwarded to :class:`~chisurf.core.experiments.core.reader.ExperimentReader`.
        """
        super().__init__(*args, **kwargs)
        self.n_bursts = int(n_bursts)
        self.r_gr = float(r_gr)
        self.r_bg = float(r_bg)
        self.r_br = float(r_br)
        self.sigma = float(sigma)
        self.correlation = float(correlation)
        self.photons_blue = float(photons_blue)
        self.photons_green = float(photons_green)
        self.r0_bg = float(r0_bg)
        self.r0_br = float(r0_br)
        self.r0_gr = float(r0_gr)
        self.seed = int(seed)

    @staticmethod
    def autofitrange(data, **kwargs) -> tuple:
        """Return the full index range."""
        try:
            return 0, int(np.asarray(data.y).size)
        except Exception:
            return 0, 0

    def read(self, filename=None, *args, **kwargs):
        """Generate one simulated burst table."""
        from chisurf.core.fluorescence.pda3c import (
            ThreeColorSetup,
            ThreeColorSpecies,
            covariance_from_statistics,
            simulate_bursts,
        )

        setup = ThreeColorSetup.from_scalars(
            r0_bg=self.r0_bg, r0_br=self.r0_br, r0_gr=self.r0_gr
        )
        covariance = covariance_from_statistics(
            np.full(3, self.sigma), [self.correlation, 0.0, 0.0]
        )
        species = [
            ThreeColorSpecies(
                amplitude=1.0,
                means=np.array([self.r_gr, self.r_bg, self.r_br]),
                covariance=covariance,
            )
        ]
        counts = simulate_bursts(
            self.n_bursts, species, setup,
            photons_blue=self.photons_blue, photons_green=self.photons_green,
            seed=self.seed,
        )
        curve = _wrap(counts.blue, counts.green, name=f"tcPDA-sim-{self.seed}")
        curve.experiment = getattr(self, "experiment", None)
        group = chisurf.core.data.ExperimentDataCurveGroup([curve])
        return group
