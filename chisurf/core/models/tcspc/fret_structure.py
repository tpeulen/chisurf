"""FRET against an ensemble of structures: one fraction per PDB.

Each structure contributes the donor-acceptor distance distribution of its two
labels' accessible volumes; the fit mixes those distributions by fitted
fractions. The model is IMP.bff's ``tcspc_fret_tabulated`` family -- given
distance distributions quenching a donor through the TCSPC instrument -- and
this module is only the part that is not a fit: reading the PDB files and
computing each structure's distribution with the accessible-volume code, once
per load, which is Python by design (nothing here runs per iteration).
"""
from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.models.description import for_family

#: The label settings a structure's accessible volumes are computed with.
LABEL_DEFAULTS = {
    "res_1": 0, "res_2": 0, "atom_name_1": "CA", "atom_name_2": "CA",
    "linker_length_1": 20.0, "linker_length_2": 20.0,
    "linker_width_1": 4.5, "linker_width_2": 4.5,
    "radius1_1": 4.0, "radius1_2": 4.0, "radius2_1": 4.5, "radius2_2": 4.5,
    "radius3_1": 3.5, "radius3_2": 3.5, "simulation_grid_resolution": 0.5,
}


def av_distance_distribution(structure, axis, **labels) -> np.ndarray:
    """The distance distribution of a structure's two labels, on ``axis``.

    The histogram has one value per axis interval; it is placed on the upper
    edge of each interval (index 1 onward), as ChiSurf's structure model
    placed it, so the array is as long as the axis.
    """
    from chisurf.core.structure.av import ACV

    labels = {**LABEL_DEFAULTS, **labels}

    def volume(k):
        return ACV(structure=structure, residue_seq_number=labels[f"res_{k}"],
                   atom_name=labels[f"atom_name_{k}"], linker_length=labels[f"linker_length_{k}"],
                   linker_width=labels[f"linker_width_{k}"], radius1=labels[f"radius1_{k}"],
                   radius2=labels[f"radius2_{k}"], radius3=labels[f"radius3_{k}"],
                   simulation_grid_resolution=labels["simulation_grid_resolution"])

    counts, _ = volume(1).pRDA(volume(2), rda_axis=axis, same_size=False)
    p = np.zeros(len(axis))
    p[1:1 + len(counts)] = counts
    return p


class FRETStructure(for_family("tcspc_fret_tabulated")):
    """FRET: structure fit -- the fractions of an ensemble of PDB structures."""

    name = "FRET: Structure fit"

    def __init__(self, fit, **kwargs):
        labels = {k: kwargs.pop(k) for k in list(kwargs) if k in LABEL_DEFAULTS}
        super().__init__(fit, **kwargs)
        self.__dict__["_labels"] = {**LABEL_DEFAULTS, **labels}
        self.__dict__["_structure_files"] = []
        self.names = []
        self.set_port_values("distance_axis", self.rda_axis)
        threshold = cs.core.settings.cs_settings.get("tcspc", {}).get("threshold", 0.001)
        self.set_scalar("distribution_threshold", float(threshold))

    @property
    def rda_axis(self) -> np.ndarray:
        """The distance axis every structure's distribution is computed on (Å)."""
        import chisurf.core.fluorescence
        return np.asarray(chisurf.core.fluorescence.rda_axis, dtype=float)

    def __getattr__(self, name):
        labels = self.__dict__.get("_labels")
        if labels is not None and name in labels:
            return labels[name]
        return super().__getattr__(name)

    def __setattr__(self, name, value):
        labels = self.__dict__.get("_labels")
        if labels is not None and name in LABEL_DEFAULTS:
            labels[name] = value
            return
        super().__setattr__(name, value)

    def append(self, structure, amplitude: float = 1.0, **labels) -> None:
        """Add one structure's distance distribution to the ensemble."""
        self._labels.update({k: v for k, v in labels.items() if k in LABEL_DEFAULTS})
        name = getattr(structure, "name", f"structure {len(self.names) + 1}")
        self.append_values(av_distance_distribution(structure, self.rda_axis, **self._labels), name=name)
        self.names.append(name)
        problem = self.problem
        if problem is not None:
            port = problem.get_parameter(f"distance.amplitude.{len(self.names) - 1}")
            held = port.fixed
            port.fixed = False
            port.value = float(amplitude)
            port.fixed = held

    def pop(self) -> None:
        if self.names:
            self.names.pop()
            self.pop_model()

    def clear(self) -> None:
        self.names = []
        self.clear_sources()

    @property
    def structure_files(self) -> list:
        return list(self._structure_files)

    @structure_files.setter
    def structure_files(self, paths) -> None:
        wanted = [str(p) for p in (paths or [])]
        if wanted != list(self._structure_files):
            self.load_structures(wanted)

    def load_structures(self, paths) -> None:
        """Rebuild the ensemble from PDB files; an unreadable file is skipped and logged."""
        from chisurf.core.structure import Structure

        self.clear()
        self._structure_files = []
        for path in (paths or []):
            try:
                self.append(Structure(str(path)))
            except Exception as error:
                cs.logging.warning(f"FRETStructure: could not load {path!r} ({error}); skipped")
                continue
            self._structure_files.append(str(path))

    def view_spec(self):
        from chisurf.core.models import view_spec as vs

        spec = super().view_spec()

        def label(k, title):
            return vs.PanelSection(title=title, sections=tuple(
                vs.ValueSection(label=text, kind=kind, attr=f"{key}_{k}")
                for key, text, kind in (("res", "Residue", "int"), ("atom_name", "Atom", "str"),
                                        ("linker_length", "Linker length", "float"),
                                        ("linker_width", "Linker width", "float"),
                                        ("radius1", "Radius 1", "float"), ("radius2", "Radius 2", "float"),
                                        ("radius3", "Radius 3", "float"))))
        extra = (
            vs.PanelSection(title="Labels / AV", sections=(
                label(1, "Donor label"), label(2, "Acceptor label"),
                vs.ValueSection(label="Resolution", kind="float", attr="simulation_grid_resolution"))),
            vs.PanelSection(title="Structures", sections=(
                vs.CustomSection(key="path_list", target="structure_files", options={
                    "extensions": [".pdb"], "add_folders": True,
                    "dialog_filter": "PDB files (*.pdb)", "title": "PDB ensemble"}),)),
        )
        return vs.ModelView(sections=tuple(spec.sections) + extra, plots=spec.plots)

    def get_state(self) -> dict:
        state = super().get_state()
        state["labels"] = dict(self._labels)
        state["structure_files"] = list(self._structure_files)
        return state

    def set_state(self, state: dict) -> None:
        # A project saved by the classic structure model keeps its labels and
        # structures under "extra"; read those too.
        extra = state.get("extra") or {}
        self._labels.update({k: v for k, v in extra.items() if k in LABEL_DEFAULTS})
        self._labels.update(state.get("labels", {}))
        files = state.get("structure_files")
        if files is None:
            files = [s.get("filename") for s in extra.get("structures", []) if s.get("filename")]
        self.load_structures(files)
        if "family" in state:
            super().set_state(state)
