from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.structure.av import ACV
from chisurf.core.structure import Structure
import chisurf.core.models.tcspc.fret as fret


class FRETStructure(fret.FRETModel):
    """FRET model that fits fractions of multiple PDB structures.

    This model computes distance distributions using accessible volumes (AV)
    calculated for each PDB structure in the ensemble and fits their fractions
    (amplitudes) to match observed fluorescence decays.
    """

    name = "FRET: Structure fit"
    view_spec_file = "fret_structure.view.json"

    x = fret.rda_axis

    @property
    def distance_distribution(self) -> np.ndarray:
        """Weighted distance distribution from the ensemble of structures.

        Returns
        -------
        np.ndarray
            3D array with shape (1, 2, n_bins) containing probability and rDA axis.
        """
        self.p = np.zeros_like(self.x)
        for i, amplitude in enumerate(self.amplitudes):
            p = self.ps[i] * amplitude
            self.p[1:] += p
        total_p = sum(self.p)
        if total_p > 0:
            self.p /= total_p

        d = list()
        threshold_fraction = cs.core.settings.cs_settings.get('tcspc', {}).get('threshold', 0.001)
        threshold = max(self.p) * threshold_fraction
        self.p = np.where(self.p >= threshold, self.p, 0)
        d.append([self.p, self.x])
        d = np.array(d)
        return d

    @property
    def amplitudes(self) -> np.ndarray:
        """Normalized amplitudes (fractions) for the structures.

        Returns
        -------
        np.ndarray
            1D array of normalized amplitudes summing to 1.
        """
        ampls = np.sqrt(np.array([a.value**2 for a in self._amplitudes]))
        ampls /= sum(ampls)
        return ampls

    def append(self, structure: Structure, **kwargs) -> None:
        """Append a new structure to the ensemble.

        Parameters
        ----------
        structure : Structure
            The PDB Structure object to add.
        """
        amplitude = kwargs.get('amplitude', 0.5)
        res_1 = kwargs.get('res_1', self.res_1)
        res_2 = kwargs.get('res_2', self.res_2)
        atom_name_1 = kwargs.get('atom_name_1', self.atom_name_1)
        atom_name_2 = kwargs.get('atom_name_2', self.atom_name_2)
        linker_length_1 = kwargs.get('linker_length_1', self.linker_length_1)
        linker_length_2 = kwargs.get('linker_length_2', self.linker_length_2)
        radius1_1 = kwargs.get('radius1_1', self.radius1_1)
        radius1_2 = kwargs.get('radius1_2', self.radius1_2)
        linker_width_1 = kwargs.get('linker_width_1', self.linker_width_1)
        linker_width_2 = kwargs.get('linker_width_2', self.linker_width_2)

        av1 = ACV(
            structure=structure,
            residue_seq_number=res_1,
            atom_name=atom_name_1,
            linker_length=linker_length_1,
            linker_width=linker_width_1,
            radius1=radius1_1,
            radius2=kwargs.get('radius2_1', self.radius2_1),
            radius3=kwargs.get('radius3_1', self.radius3_1),
            simulation_grid_resolution=kwargs.get(
                'simulation_grid_resolution', self.simulation_grid_resolution
            ),
        )
        av2 = ACV(
            structure=structure,
            residue_seq_number=res_2,
            atom_name=atom_name_2,
            linker_length=linker_length_2,
            linker_width=linker_width_2,
            radius1=radius1_2,
            radius2=kwargs.get('radius2_2', self.radius2_2),
            radius3=kwargs.get('radius3_2', self.radius3_2),
            simulation_grid_resolution=kwargs.get(
                'simulation_grid_resolution', self.simulation_grid_resolution
            ),
        )
        
        p, _ = av1.pRDA(av2, rda_axis=self.x, same_size=False)
        p = p * amplitude
        
        self.ps.append(p)
        self.names.append(structure.name)
        self.filenames.append(getattr(structure, 'filename', None))
        amplitude_param = FittingParameter(
            value=amplitude, 
            name="x_" + str(len(self.names)), 
            lb=0.0, 
            ub=1.0, 
            bounds_on=True,
            description='Amplitude (population weight) of this structural ensemble in the mixture.'
        )
        self._amplitudes.append(amplitude_param)
        if getattr(self, "_parameters", None) is not None:
            self.append_parameter(amplitude_param)

    def clear(self) -> None:
        """Clear all structures and amplitudes from the model."""
        old_amplitudes = self._amplitudes
        self._amplitudes = list()
        self.ps = list()
        self.names = list()
        self.filenames = list()
        self.p = np.zeros_like(self.x)
        if getattr(self, "_parameters", None) is not None:
            self._parameters = [p for p in self._parameters if p not in old_amplitudes]

    def pop(self) -> None:
        """Remove the last appended structure from the model."""
        if self._amplitudes:
            amplitude = self._amplitudes.pop()
            self.ps.pop()
            self.names.pop()
            self.filenames.pop()
            if getattr(self, "_parameters", None) is not None:
                self._parameters = [p for p in self._parameters if p is not amplitude]

    @property
    def structure_files(self) -> list:
        """PDB files whose accessible volumes make up the ensemble.

        Assigning to this rebuilds the ensemble, which is what makes the
        structure list authorable as a declarative ``path_list`` section: that
        section writes the attribute and calls ``update()``, so loading needs no
        GUI code of its own.

        Returns
        -------
        list of str
            The currently loaded PDB paths, in load order.
        """
        return list(self._structure_files)

    @structure_files.setter
    def structure_files(self, paths) -> None:
        """Replace the ensemble with the accessible volumes of `paths`."""
        wanted = [str(p) for p in (paths or [])]
        if wanted == list(self._structure_files):
            return
        self.load_structures(wanted)

    def load_structures(self, paths) -> None:
        """Clear the ensemble and rebuild it from `paths`.

        A file that cannot be read is skipped and logged rather than aborting the
        load: one unreadable PDB in a folder of twenty should not lose the other
        nineteen.

        Parameters
        ----------
        paths : iterable of str
            PDB files to load.
        """
        self.clear()
        self._structure_files = []
        for path in (paths or []):
            path = str(path)
            try:
                self.append(Structure(path))
            except Exception as exc:
                cs.logging.warning(
                    f"FRETStructure: could not load {path!r} ({exc}); skipped"
                )
                continue
            self._structure_files.append(path)

    def _fraction_parameter_rows(self) -> list:
        """Return the per-structure fraction parameters, one per row.

        The ensemble's structures define how many there are, so this group has no
        add/remove of its own -- the row count follows the loaded file list.

        Returns
        -------
        list
            The amplitude parameters, in structure order.
        """
        return list(self._amplitudes)

    def get_state(self) -> dict:
        """Return a JSON-serializable state snapshot of the model, including ensemble structures."""
        state = fret.FRETModel.get_state(self)
        if not isinstance(state, dict):
            state = {}
        extra = state.setdefault("extra", {})

        # Save label settings
        extra["res_1"] = self.res_1
        extra["res_2"] = self.res_2
        extra["atom_name_1"] = self.atom_name_1
        extra["atom_name_2"] = self.atom_name_2
        extra["linker_length_1"] = self.linker_length_1
        extra["linker_length_2"] = self.linker_length_2
        extra["radius1_1"] = self.radius1_1
        extra["radius1_2"] = self.radius1_2
        extra["linker_width_1"] = self.linker_width_1
        extra["linker_width_2"] = self.linker_width_2

        # Save structures info
        structures_info = []
        for i, name in enumerate(self.names):
            filename = self.filenames[i] if i < len(self.filenames) else None
            # Get current amplitude parameter value if available
            amp_val = self._amplitudes[i].value if i < len(self._amplitudes) else 0.5
            structures_info.append({
                "name": name,
                "filename": filename,
                "amplitude": amp_val
            })
        extra["structures"] = structures_info

        return state

    def set_state(self, state: dict) -> None:
        """Restore state from a JSON-serializable snapshot, reloading ensemble structures."""
        if not isinstance(state, dict):
            return
        extra = state.get("extra") or {}

        # Restore label settings
        self.res_1 = extra.get("res_1", self.res_1)
        self.res_2 = extra.get("res_2", self.res_2)
        self.atom_name_1 = extra.get("atom_name_1", self.atom_name_1)
        self.atom_name_2 = extra.get("atom_name_2", self.atom_name_2)
        self.linker_length_1 = extra.get("linker_length_1", self.linker_length_1)
        self.linker_length_2 = extra.get("linker_length_2", self.linker_length_2)
        self.radius1_1 = extra.get("radius1_1", self.radius1_1)
        self.radius1_2 = extra.get("radius1_2", self.radius1_2)
        self.linker_width_1 = extra.get("linker_width_1", self.linker_width_1)
        self.linker_width_2 = extra.get("linker_width_2", self.linker_width_2)

        # Clear existing structures
        self.clear()

        # Restore structures
        structures_info = extra.get("structures", [])
        for s_info in structures_info:
            filename = s_info.get("filename")
            if filename:
                try:
                    s = Structure(filename)
                    self.append(
                        s,
                        amplitude=s_info.get("amplitude", 0.5),
                        res_1=self.res_1,
                        res_2=self.res_2,
                        atom_name_1=self.atom_name_1,
                        atom_name_2=self.atom_name_2,
                        linker_length_1=self.linker_length_1,
                        linker_length_2=self.linker_length_2,
                        radius1_1=self.radius1_1,
                        radius1_2=self.radius1_2,
                        linker_width_1=self.linker_width_1,
                        linker_width_2=self.linker_width_2
                    )
                except Exception as e:
                    import logging
                    logging.warning(f"FRETStructure: Failed to reload structure {filename}: {e}")

        fret.FRETModel.set_state(self, state)

    def __init__(self, fit: cs.core.fitting.fit.FitGroup, **kwargs):
        """Initialize FRETStructure model.

        Parameters
        ----------
        fit : FitGroup
            The fit group this model belongs to.
        """
        fret.FRETModel.__init__(self, fit, **kwargs)
        self.names = list()
        self.filenames = list()
        self.ps = list()
        self._amplitudes = list()
        self._structure_files = list()
        self.p = np.zeros_like(self.x)

        self.res_1 = kwargs.get('res_1', 0)
        self.res_2 = kwargs.get('res_2', 0)

        self.atom_name_1 = kwargs.get('atom_name_1', 'CA')
        self.atom_name_2 = kwargs.get('atom_name_2', 'CA')

        self.linker_length_1 = kwargs.get('linker_length_1', 20.0)
        self.linker_length_2 = kwargs.get('linker_length_2', 20.0)

        self.radius1_1 = kwargs.get('radius1_1', 4.0)
        self.radius1_2 = kwargs.get('radius1_2', 4.0)

        # AV3 outer radii and the simulation grid. The hand-written editor
        # exposed all three and ``append`` never passed them on, so setting them
        # did nothing -- they now reach the accessible-volume calculation.
        self.radius2_1 = kwargs.get('radius2_1', 4.5)
        self.radius2_2 = kwargs.get('radius2_2', 4.5)
        self.radius3_1 = kwargs.get('radius3_1', 3.5)
        self.radius3_2 = kwargs.get('radius3_2', 3.5)
        self.simulation_grid_resolution = kwargs.get('simulation_grid_resolution', 0.5)

        self.linker_width_1 = kwargs.get('linker_width_1', 4.5)
        self.linker_width_2 = kwargs.get('linker_width_2', 4.5)
