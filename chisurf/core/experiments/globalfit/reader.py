from __future__ import annotations

import numpy as np

import chisurf.core.data
from chisurf import typing
from chisurf.core.experiments.core.reader import ExperimentReader


class GlobalFitSetup(ExperimentReader):
    operation_type = "global_fit"
    artifact_kind_derived = "fit_result"

    def __init__(self, *args, **kwargs):
        """Initialize a global-fit setup reader."""
        # This reader creates a UI/data-model placeholder; the actual fit path
        # owns global-fit provenance. Archiving the placeholder would claim a
        # scientific operation that never ran.
        kwargs.setdefault("record_provenance", False)
        super().__init__(*args, **kwargs)

    @staticmethod
    def autofitrange(*args, **kwargs) -> typing.Tuple[int, int]:
        """Return a trivial fit range (not applicable for global-fit setups).

        Returns
        -------
        tuple of int
            Always ``(0, 0)``.
        """
        return 0, 0

    def view_spec(self):
        """Return the declarative settings of this reader (``globalfit_reader.view.json``)."""
        import pathlib

        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(pathlib.Path(__file__).with_name("globalfit_reader.view.json"))

    def read(self, filename: str | None = None, *args, name: str = "Global-fit", **kwargs):
        """Create a placeholder data curve for global fitting.

        Parameters
        ----------
        filename : str, optional
            Unused: a global fit reads no file. Taken so the reader is called
            like every other one.
        name : str
            Name for the placeholder data curve.

        Returns
        -------
        chisurf.core.data.DataCurve
            A singleton data curve with zero-valued x/y.
        """
        return chisurf.core.data.DataCurve(
            x=np.zeros(1), y=np.zeros(1), setup=self, name=name
        )

    def __str__(self):
        """Human-readable string representation."""
        s = "Global-Fit\n"
        s += f"Name: \t{self.name} \n"
        return s
