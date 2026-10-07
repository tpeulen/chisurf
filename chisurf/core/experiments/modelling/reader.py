""" """

from __future__ import annotations

import json
from pathlib import Path

import chisurf.core.base
import chisurf.core.fio
import chisurf.core.structure
import chisurf.core.support.decorators
from chisurf import typing
from chisurf.core.experiments.core.reader import ExperimentReader
from chisurf.core.support.i18n import tr


class StructureReader(ExperimentReader):
    operation_type = "import"
    artifact_kind_source = "external_file"
    artifact_kind_derived = "processed_data"

    def __init__(self, compute_internal_coordinates: bool = False, *args, **kwargs):
        """Initialize a structure reader.

        Parameters
        ----------
        compute_internal_coordinates : bool
            Whether to compute internal coordinates (dihedral angles etc.)
            when loading a structure.
        """
        super().__init__(*args, **kwargs)
        self.compute_internal_coordinates = compute_internal_coordinates
        self._filename = ""
        self.n_atoms = 0
        self.n_residues = 0

    @property
    def filename(self) -> str:
        """Return the single PDB source selected for the next import."""
        return self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        """Select a source and clear counts belonging to a previous import."""
        value = str(value)
        if value != self._filename:
            self.n_atoms = 0
            self.n_residues = 0
        self._filename = value

    def view_spec(self) -> dict:
        """Return the native single-file structure settings declaration."""
        spec = json.loads(Path(__file__).with_name("structure.view.json").read_text())
        spec["title"] = tr(spec["title"])
        for section in spec["sections"]:
            for declaration in (section, section.get("options", {})):
                for key in ("label", "description", "text"):
                    if key in declaration:
                        declaration[key] = tr(declaration[key])
        return spec

    @staticmethod
    def autofitrange(data: chisurf.core.base.Data, **kwargs) -> typing.Tuple[int, int]:
        """Return a trivial fit range (not applicable for structure data).

        Parameters
        ----------
        data : chisurf.core.base.Data
            The experimental data (unused).

        Returns
        -------
        tuple of int
            Always ``(0, 0)``.
        """
        return 0, 0

    def read(self, filename: str | None = None, *args, **kwargs) -> chisurf.core.data.ExperimentDataGroup:
        """Load a molecular structure from a file.

        Parameters
        ----------
        filename : str, optional
            Path to the structure file (e.g. PDB). Uses the selected source
            when omitted.

        Returns
        -------
        chisurf.core.data.ExperimentDataGroup
            Group containing the loaded :class:`Structure`.
        """
        filename = filename if filename is not None else self.filename or None
        structure = chisurf.core.structure.Structure(
            p_object=filename, make_coarse=self.compute_internal_coordinates
        )
        data_group = chisurf.core.data.ExperimentDataGroup(seq=[structure])
        data_group.data_reader = self
        self.filename = str(filename) if filename is not None else ""
        self.n_atoms = structure.n_atoms
        self.n_residues = structure.n_residues
        return data_group
