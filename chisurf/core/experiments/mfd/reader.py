"""Load a burst-analysis folder as a fittable 2D MFD dataset.

The reader calls :mod:`chisurf.core.fluorescence.mfd.prepare` **directly**, not
through the preparation plugin. It is data-loading infrastructure on the path for
every burst dataset, and routing it through plugin discovery would let a disabled
or broken plugin present as a data-loading failure — a diagnosis nobody would make
from the symptom.

The dataset it produces is the 2D histogram *flattened* row-major, with
``meta_data['grid']`` recording the shape so the generic 2D machinery (the fit-range
controller, the residual image) works without knowing anything about MFD. The 2D
objects themselves ride on ``data.mfd``, which is what the model reads and what
``supports_data`` keys on.

The axes are **raw**: the proximity ratio and the raw mean micro time. Every
correction lives in the forward model, so the histogram this reader builds is
correct for every parameter value the fit will ever try — which is what lets a
correction factor be fitted at all.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import numpy as np

import chisurf.core.data
from chisurf.core.experiments.core.reader import ExperimentReader

_VIEW_JSON = pathlib.Path(__file__).parent / "mfd.view.json"


class MfdReader(ExperimentReader):
    """Read a burst-analysis folder into a 2D MFD histogram dataset."""

    operation_type = "mfd_histogram_computation"
    artifact_kind_source = "burst_analysis"
    artifact_kind_derived = "mfd_histogram"
    derived_data_format = "json"
    derived_mime_type = "application/json"

    name: str = "MFD (burst folder)"

    def __init__(
        self,
        name: str = "MFD (burst folder)",
        green: str = "green",
        red: str = "red",
        n_ratio_bins: int = 41,
        n_micro_time_bins: int = 41,
        micro_time_min: float = 0.0,
        micro_time_max: float = 8.0,
        min_green_photons: int = 20,
        n_signal_bins: int = 24,
        n_span_bins: int = 6,
        *args,
        **kwargs,
    ) -> None:
        """Initialise the reader.

        Parameters
        ----------
        name : str
            Human-readable reader name.
        green, red : str
            Detector names in the burst tables.
        n_ratio_bins, n_micro_time_bins : int
            Histogram resolution on the proximity-ratio and mean-micro-time axes.
        micro_time_min, micro_time_max : float
            Mean-micro-time range, nanoseconds.
        min_green_photons : int
            Bursts with fewer green photons are excluded, because the Gaussian
            ``⟨t⟩`` kernel the model uses is not valid there. The model applies the
            same cut, and the excluded fraction is reported on the dataset.
        n_signal_bins, n_span_bins : int
            Grid the nuisance measure is compressed onto. Checked to cost no width
            (see :mod:`chisurf.core.fluorescence.mfd.histogram`).
        *args, **kwargs
            Forwarded to :class:`ExperimentReader`.
        """
        super().__init__(*args, **kwargs)
        self.name = name
        self.green = green
        self.red = red
        self.n_ratio_bins = int(n_ratio_bins)
        self.n_micro_time_bins = int(n_micro_time_bins)
        self.micro_time_min = float(micro_time_min)
        self.micro_time_max = float(micro_time_max)
        self.min_green_photons = int(min_green_photons)
        self.n_signal_bins = int(n_signal_bins)
        self.n_span_bins = int(n_span_bins)

    def view_spec(self):
        """Return the declarative editor spec for the reader's settings."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def autofitrange(self, data, **kwargs) -> tuple[int, int]:
        """Return the default fit window: the whole flattened histogram.

        Parameters
        ----------
        data : chisurf.core.data.DataCurve
            The dataset.
        **kwargs
            Ignored; present for the base-class signature.

        Returns
        -------
        tuple of int
        """
        return 0, int(np.asarray(data.y).size)

    def read(
        self,
        filename: str | Sequence[str] | None = None,
        *args,
        **kwargs,
    ) -> chisurf.core.data.ExperimentDataCurveGroup:
        """Load one burst-analysis folder.

        Parameters
        ----------
        filename : path-like or sequence of path-like
            The analysis folder, its ``bi4_bur`` directory, or a ``.bur`` inside it.
        *args, **kwargs
            Ignored; present for the base-class signature.

        Returns
        -------
        chisurf.core.data.ExperimentDataCurveGroup
            Holding one :class:`~chisurf.core.data.DataCurve` — the flattened 2D
            histogram — with the MFD objects on its ``mfd`` attribute.
        """
        from chisurf.core.fluorescence.mfd.fit import load_mfd_data
        from chisurf.core.fluorescence.mfd.histogram import HistogramAxes

        group = chisurf.core.data.ExperimentDataCurveGroup([])
        if filename is None:
            return group
        if isinstance(filename, (list, tuple)):
            if not filename:
                return group
            filename = filename[0]
        folder = pathlib.Path(str(filename))
        if not folder.exists():
            return group

        axes = HistogramAxes.default(
            n_ratio=self.n_ratio_bins,
            n_micro_time=self.n_micro_time_bins,
            micro_time_range=(self.micro_time_min, self.micro_time_max),
        )
        mfd = load_mfd_data(
            folder,
            green=self.green,
            red=self.red,
            axes=axes,
            min_green_photons=self.min_green_photons,
            n_signal_bins=self.n_signal_bins,
            n_span_bins=self.n_span_bins,
        )

        counts = np.asarray(mfd.observed.counts, dtype=float)
        y = counts.ravel(order="C")
        x = np.arange(y.size, dtype=float)
        # Counting statistics, with the empty bins given unit weight rather than
        # zero — a bin the data left empty is information, and a zero error would
        # make it either infinitely important or (after a guard) silently dropped.
        ey = np.where(y > 0.0, np.sqrt(y), 1.0)

        curve = chisurf.core.data.DataCurve(
            x=x,
            y=y,
            ey=ey,
            filename=str(folder),
            name=folder.name,
            data_reader=self,
            experiment=self.experiment,
            load_filename_on_init=False,
            mfd=mfd,
            meta_data={
                "grid": {
                    "ndim": 2,
                    "shape": tuple(counts.shape),
                    "order": "C",
                    "size": int(y.size),
                },
                "mfd": {
                    "green": self.green,
                    "red": self.red,
                    "ratio_edges": axes.ratio_edges,
                    "micro_time_edges": axes.micro_time_edges,
                    "min_green_photons": self.min_green_photons,
                    "n_bursts": int(len(mfd.preparation)),
                    "n_used": int(mfd.observed.n_used),
                    "excluded_fraction": float(
                        mfd.observed.summary["excluded_fraction"]
                    ),
                    "background_rates": {
                        name: float(response.background_rate)
                        for name, response in mfd.responses.items()
                    },
                    "report": mfd.report(),
                },
            },
        )
        group.append(curve)
        group.data_reader = self
        return group
