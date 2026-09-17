"""Coarse-grained Monte-Carlo structure sampling, driven by FRET restraints.

This is the model half of ProteinMC: the structure to start from, the labelling
file that supplies the FRET restraints, the energy terms and their weights, the
sampling settings, and the trajectory the run produces. The sampling itself lives
in :mod:`chisurf.core.models.structure.proteinmc`; this class is what an editor,
a script or a project file addresses.

It is deliberately Qt-free, including the run: the sampler goes into a plain
:class:`threading.Thread` and reports through :attr:`sampling_progress` and the
trajectory attributes, so a headless script can start a run, watch it and stop it
with the same calls the editor's buttons make. The predecessor put all of this in
a ``QWidget``, which is why nothing about ProteinMC could be scripted.
"""

from __future__ import annotations

import json
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

import chisurf.core.fitting
from chisurf import logging
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import Model
from chisurf.core.models.structure.proteinmc import (
    ProteinMCProgress,
    ProteinMCRunner,
    list_flexfit_sets,
    load_json,
)

#: The energy terms ProteinMC can score with: the label shown, the name the
#: runner takes, the default weight, whether it is on in a fresh model, and the
#: term's own parameters with their defaults (which also fix each parameter's
#: type — a ``bool`` default renders as a checkbox, a ``str`` as a text field).
POTENTIAL_SPECS: dict[str, dict] = {
    "default": {
        "label": "Default clash",
        "name": "default",
        "weight": 1.0,
        "enabled": False,
        "params": {"clash_tolerance": 2.0, "covalent_radius": 1.5},
    },
    "hbond": {
        "label": "H-bond",
        "name": "hbond",
        "weight": 2.0,
        "enabled": True,
        "params": {
            "cutoff_ca": 8.0,
            "cutoff_hbond": 3.0,
            "oh": 1.0,
            "on": 1.0,
            "cn": 1.0,
            "ch": 1.0,
        },
    },
    "mj": {
        "label": "MJ",
        "name": "mj",
        "weight": 1.0,
        "enabled": False,
        "params": {"ca_cutcoff": 6.5},
    },
    "unres": {
        "label": "UNRES",
        "name": "unres",
        "weight": 1.0,
        "enabled": True,
        "params": {
            "ca_cutoff": 15.0,
            "repulsion": 100.0,
            "min_dist": 3.5,
            "max_dist": 19.0,
            "bin_width": 0.05,
            "centroid_number": 4.0,
        },
    },
    "go": {
        "label": "Gō-Potential",
        "name": "go",
        "weight": 1.0,
        "enabled": False,
        "params": {
            "epsilon": 1.0,
            "cutoff": 6.5,
            "native_cutoff_on": True,
            "nnEFactor": 0.7,
            "non_native_contact_on": True,
        },
    },
    "rama": {
        "label": "Ramachandran",
        "name": "rama",
        "weight": 1.0,
        "enabled": False,
        "params": {},
    },
    "asa": {
        "label": "ASA-Cα",
        "name": "asa",
        "weight": 1.0,
        "enabled": False,
        "params": {"probe": 1.0, "n_sphere_point": 590, "radius": 2.5},
    },
    "rg": {
        "label": "Radius of Gyration",
        "name": "rg",
        "weight": 1.0,
        "enabled": False,
        "params": {},
    },
    "fps": {
        "label": "Dye potential",
        "name": "dye",
        "weight": 1.0,
        "enabled": True,
        "params": {"labeling_file": "", "score_set": ""},
    },
}

#: Term parameters the runner needs as integers, whatever the editor stored.
_INT_SETTINGS = ("centroid_number", "n_sphere_point")

#: Aliases accepted when restoring a project written by an older version.
_POTENTIAL_ALIASES = {
    "default": "default",
    "clash potential": "default",
    "clash-potential": "default",
    "hbond": "hbond",
    "h-bond": "hbond",
    "h-potential": "hbond",
    "mj": "mj",
    "miyazawa-jernigan": "mj",
    "unres": "unres",
    "go": "go",
    "gō-potential": "go",
    "go-potential": "go",
    "rama": "rama",
    "ramachandran": "rama",
    "asa": "asa",
    "asa-cα": "asa",
    "rg": "rg",
    "radius of gyration": "rg",
    "fps": "fps",
    "dye": "fps",
    "dye potential": "fps",
}


def _decode(value: Any) -> str:
    """Return a structured-array field as a stripped ``str``."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    decode = getattr(value, "decode", None)
    if callable(decode):
        try:
            return decode("utf-8", errors="ignore").strip()
        except Exception:
            pass
    return str(value).strip()


class ProteinMCModel(Model):
    """Sample protein conformations by Monte Carlo against FRET restraints.

    The model owns everything a run needs and everything a run produces, so a
    project can be saved mid-way and a run continued from the frames already in
    hand. It computes no curve: the "fit" is the sampling, and what the plots
    draw is the trajectory and its energy traces.
    """

    name = "ProteinMC"
    view_spec_file = "proteinmc.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Initialize the ProteinMC model with the default energy terms on.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        super().__init__(fit, **kwargs)

        data = getattr(self.fit, "data", None)
        self.structure = data
        #: Path or PDB ID of the structure sampling starts from.
        self.structure_file: str = str(getattr(data, "filename", "") or "")
        #: FPS JSON file holding positions, distances and score sets.
        self.labeling_file: str = ""
        #: Which χ² group of the labelling file scores the run.
        self.score_set: str = ""
        #: Restrict the moving residues to a FlexFit set.
        self.use_flexfit: bool = False
        self.flexfit_set: str = ""
        #: Where the trajectory and the autosaved project are written.
        self.output_directory: str = ""

        # Sampling settings.
        self.n_iter: int = 10000
        self.n_out: int = 100
        self.n_written: int = 100
        self.scale: float = 0.0025
        self.kt: float = 1.5
        self.n_runs: int = 1
        self.labeling_weight: float = 1.0

        # Energy terms: one dict per active term.
        self._potentials: list[dict] = []
        #: Row dict of the term selected in the energy table.
        self.selected_potential: dict | None = None
        #: Key of the term the "Add" button appends.
        self.new_potential: str = next(iter(POTENTIAL_SPECS))
        for key, spec in POTENTIAL_SPECS.items():
            if spec["enabled"]:
                self.add_potential(key)

        # Trajectory state. The plots read these directly.
        self.proteinmc_structure = None
        self.trajectory_frames: list[np.ndarray] = []
        self.current_frame_index: int = 0
        self.rmsd: list[float] = []
        self.drmsd: list[float] = []
        self.energy: list[float] = []
        self.chi2r: list[float] = []

        # Run state.
        self._thread: threading.Thread | None = None
        self._runner: ProteinMCRunner | None = None
        self._stop_requested = False
        self._sampling_status: str = ""
        self._total_frames_target: int = 0
        self._start_frame_count: int = 0
        self._resume_traces: dict[str, list] = {}

        # Distances read from the labelling file, shown as outputs.
        self._distance_parameters: dict[str, FittingParameter] = {}
        self._distance_definitions: dict[str, dict] = {}
        self._all_positions: dict = {}
        self._distance_position_indices: dict[str, int] = {}

        self.find_parameters()

    # -- labelling file ------------------------------------------------

    def _labeling_payload(self) -> dict:
        """Return the parsed labelling file, or an empty mapping."""
        if not self.labeling_file:
            return {}
        try:
            return load_json(self.labeling_file) or {}
        except Exception as exc:
            logging.warning(f"ProteinMC: could not read labelling file: {exc}")
            return {}

    def score_set_names(self) -> list[str]:
        """Return the χ² groups the labelling file defines."""
        return [""] + list((self._labeling_payload().get("χ²", {}) or {}).keys())

    def flexfit_set_names(self) -> list[str]:
        """Return the FlexFit sets the labelling file defines."""
        if not self.labeling_file:
            return [""]
        try:
            return [""] + list(list_flexfit_sets(self.labeling_file))
        except Exception:
            return [""]

    @property
    def flexfit_summary(self) -> str:
        """How many residues the active FlexFit set leaves mobile."""
        if not (self.use_flexfit and self.flexfit_set and self.labeling_file):
            return ""
        payload = self._labeling_payload()
        entry = (payload.get("FlexFit", {}) or {}).get(self.flexfit_set, {})
        if not isinstance(entry, dict):
            return ""
        flexible = len(entry.get("Flexible residues", []) or [])
        positions = payload.get("Positions", {}) or {}
        seen = {
            (str(p.get("chain_identifier", "")).strip(), int(p.get("residue_seq_number", 0)))
            for p in positions.values()
            if isinstance(p, dict)
        }
        return f"{flexible}/{len(seen)} residues flexible"

    def on_labeling_file_changed(self) -> None:
        """Re-read the labelling file: score sets, FlexFit sets and distances.

        Called by the editor when the path changes; safe to call from a script.
        """
        names = self.score_set_names()
        if self.score_set not in names:
            self.score_set = names[1] if len(names) > 1 else ""
        sets = self.flexfit_set_names()
        if self.flexfit_set not in sets:
            self.flexfit_set = sets[1] if len(sets) > 1 else ""
        self._sync_labeling_into_dye_potential()
        self.reload_distances()

    # -- energy terms --------------------------------------------------

    def potential_choices(self) -> list[str]:
        """Return the ``(key, label)`` pairs of every available energy term."""
        return [(key, str(spec["label"])) for key, spec in POTENTIAL_SPECS.items()]

    def potential_rows(self) -> list[dict]:
        """Return one row mapping per active energy term, for the term table."""
        return [
            {
                "index": i,
                "term": str(POTENTIAL_SPECS[p["key"]]["label"]),
                "eval_every": int(p["eval_interval"]),
                "weight": float(p["weight"]),
            }
            for i, p in enumerate(self._potentials)
        ]

    def set_potential_field(self, row: int, column: str, value: Any) -> None:
        """Write an edited cell of the energy-term table back onto the term.

        Parameters
        ----------
        row : int
            Row index into :meth:`potential_rows`.
        column : str
            ``"eval_every"`` or ``"weight"``; anything else is ignored (the term
            name is not editable).
        value : Any
            The edited cell text.
        """
        if not (0 <= row < len(self._potentials)):
            return
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        if column == "weight":
            self._potentials[row]["weight"] = number
        elif column == "eval_every":
            self._potentials[row]["eval_interval"] = max(1, int(number))

    def add_potential(self, key: str | None = None) -> None:
        """Append an energy term with its default weight and parameters.

        Parameters
        ----------
        key : str, optional
            Which term; :attr:`new_potential` when omitted. A term already in the
            list is not added twice — the runner sums each term once.
        """
        key = str(key or self.new_potential)
        spec = POTENTIAL_SPECS.get(key)
        if spec is None or any(p["key"] == key for p in self._potentials):
            return
        settings = deepcopy(spec["params"])
        if key == "fps":
            settings["labeling_file"] = settings.get("labeling_file") or self.labeling_file
            settings["score_set"] = settings.get("score_set") or self.score_set
        self._potentials.append(
            {
                "key": key,
                "weight": float(spec["weight"]),
                "eval_interval": 1,
                "settings": settings,
            }
        )

    def remove_selected_potential(self) -> None:
        """Drop the selected energy term (the last one when none is selected)."""
        if not self._potentials:
            return
        index = self._selected_index()
        self._potentials.pop(index if index is not None else -1)
        self.selected_potential = None

    def _selected_index(self) -> int | None:
        """Return the index of the selected energy term, or ``None``."""
        row = self.selected_potential
        if isinstance(row, dict) and isinstance(row.get("index"), int):
            index = int(row["index"])
            if 0 <= index < len(self._potentials):
                return index
        return None

    def potential_setting_rows(self) -> list[dict]:
        """Return the selected term's own parameters, one row each."""
        index = self._selected_index()
        if index is None:
            index = len(self._potentials) - 1
        if index < 0:
            return []
        term = self._potentials[index]
        spec = POTENTIAL_SPECS[term["key"]]
        return [
            {"name": name, "value": term["settings"].get(name, default)}
            for name, default in spec["params"].items()
        ]

    def set_potential_setting(self, row: int, column: str, value: Any) -> None:
        """Write an edited parameter of the selected energy term.

        The parameter's type is taken from its default in
        :data:`POTENTIAL_SPECS`, so a text cell cannot turn a bool into the
        string ``"True"`` on its way into the runner.

        Parameters
        ----------
        row : int
            Row index into :meth:`potential_setting_rows`.
        column : str
            Only ``"value"`` is editable.
        value : Any
            The edited cell text.
        """
        if column != "value":
            return
        index = self._selected_index()
        if index is None:
            index = len(self._potentials) - 1
        if index < 0:
            return
        term = self._potentials[index]
        spec = POTENTIAL_SPECS[term["key"]]
        names = list(spec["params"])
        if not (0 <= row < len(names)):
            return
        name = names[row]
        default = spec["params"][name]
        if isinstance(default, bool):
            term["settings"][name] = str(value).strip().lower() in ("1", "true", "yes", "on")
        elif isinstance(default, str):
            term["settings"][name] = str(value)
        else:
            try:
                term["settings"][name] = float(value)
            except (TypeError, ValueError):
                return
        if term["key"] == "fps":
            self._sync_dye_potential_into_labeling()

    def potential_settings(self) -> list[dict]:
        """Return the active terms in the form :class:`ProteinMCRunner` takes."""
        out = []
        for term in self._potentials:
            spec = POTENTIAL_SPECS[term["key"]]
            settings = dict(term["settings"])
            for key in _INT_SETTINGS:
                if key in settings:
                    settings[key] = int(settings[key])
            for name, default in spec["params"].items():
                if isinstance(default, bool) and name in settings:
                    settings[name] = bool(settings[name])
            out.append(
                {
                    "name": spec["name"],
                    "weight": float(term["weight"]),
                    "eval_interval": int(term["eval_interval"]),
                    "settings": settings,
                }
            )
        return out

    def _dye_potential(self) -> dict | None:
        """Return the FRET (``fps``) energy term, if it is active."""
        return next((p for p in self._potentials if p["key"] == "fps"), None)

    def _sync_labeling_into_dye_potential(self) -> None:
        """Push the labelling file and score set into the FRET term."""
        term = self._dye_potential()
        if term is None or not self.labeling_file:
            return
        term["settings"]["labeling_file"] = self.labeling_file
        if self.score_set:
            term["settings"]["score_set"] = self.score_set

    def _sync_dye_potential_into_labeling(self) -> None:
        """Pull the labelling file and score set back out of the FRET term.

        The two are one setting shown in two places; a project written with only
        the term's copy filled in must still restore the model's.
        """
        term = self._dye_potential()
        if term is None:
            return
        path = str(term["settings"].get("labeling_file", "")).strip()
        score_set = str(term["settings"].get("score_set", "")).strip()
        if path and path != self.labeling_file:
            self.labeling_file = path
            self.reload_distances()
        if score_set:
            self.score_set = score_set

    # -- distances -----------------------------------------------------

    def reload_distances(self) -> None:
        """Rebuild the distance outputs from the labelling file's score set."""
        self._distance_parameters.clear()
        self._distance_definitions.clear()
        self._all_positions.clear()
        self._distance_position_indices.clear()
        payload = self._labeling_payload()
        if not payload:
            return

        all_distances = payload.get("Distances", {}) or {}
        groups = payload.get("χ²", {}) or {}
        resolved = self.score_set
        if resolved and resolved not in groups:
            resolved = next(
                (
                    key
                    for key in groups
                    if resolved.lower() in key.lower() or key.lower() in resolved.lower()
                ),
                resolved,
            )
        group = groups.get(resolved) if resolved else None
        keys = group.get("distances", []) if isinstance(group, dict) else []

        self._all_positions = dict(payload.get("Positions", {}) or {})
        self._distance_definitions = {k: all_distances[k] for k in keys if k in all_distances}
        for name in self._distance_definitions:
            self._distance_parameters[name] = FittingParameter(
                name=name,
                label_text=f"{name}[Å]",
                value=float("nan"),
                lb=float("-inf"),
                ub=float("inf"),
                bounds_on=False,
                fixed=True,
                is_output=True,
            )

    def _distance_parameter_rows(self) -> list:
        """Return the inter-fluorophore distances of the active frame."""
        return list(self._distance_parameters.values())

    def _resolve_position_index(self, position: dict, atoms) -> int | None:
        """Resolve a labelling position to an atom index in the structure.

        Parameters
        ----------
        position : dict
            A labelling-position definition from the FPS JSON.
        atoms : numpy.ndarray
            The structure's structured atom array.

        Returns
        -------
        int or None
            Index of the matching atom, or ``None``.
        """
        if "chain_identifier" in position and "residue_seq_number" in position:
            chain = str(position["chain_identifier"]).strip()
            residue = int(position["residue_seq_number"])
            atom_name = str(position.get("atom_name", "CA")).strip()
            mask = np.ones(len(atoms), dtype=bool)
            if "chain" in atoms.dtype.names:
                chain_mask = np.array([_decode(v) == chain for v in atoms["chain"]])
                if np.any(chain_mask):
                    mask &= chain_mask
            if "res_id" in atoms.dtype.names:
                mask &= atoms["res_id"] == residue
            if "atom_name" in atoms.dtype.names:
                atom_mask = np.array([_decode(v) == atom_name for v in atoms["atom_name"]])
                selected = np.where(mask & atom_mask)[0]
                if selected.size == 0:
                    fallback = np.array([_decode(v) == "CA" for v in atoms["atom_name"]])
                    selected = np.where(mask & fallback)[0]
            else:
                selected = np.where(mask)[0]
            if selected.size:
                return int(selected[0])
        if "attachment_atom_index" in position:
            index = int(position["attachment_atom_index"])
            if 0 <= index < len(atoms):
                return index
        return None

    def _resolve_position_by_guessing(self, name: str, atoms) -> int | None:
        """Resolve a position from the residue number embedded in its name.

        Parameters
        ----------
        name : str
            e.g. ``"19"`` or ``"19D"``.
        atoms : numpy.ndarray
            The structure's structured atom array.

        Returns
        -------
        int or None
            Index of the residue's Cα (or its first atom), or ``None``.
        """
        match = re.search(r"\d+", name)
        if not match:
            return None
        residue = int(match.group())
        mask = np.ones(len(atoms), dtype=bool)
        if "res_id" in atoms.dtype.names:
            mask &= atoms["res_id"] == residue
        if "atom_name" in atoms.dtype.names:
            ca = np.array([_decode(v) == "CA" for v in atoms["atom_name"]])
            selected = np.where(mask & ca)[0]
            if selected.size:
                return int(selected[0])
        selected = np.where(mask)[0]
        return int(selected[0]) if selected.size else None

    def _position_index(self, name: str, atoms) -> int | None:
        """Resolve one position name to an atom index, caching the result."""
        if name in self._distance_position_indices:
            return self._distance_position_indices[name]
        position = self._all_positions.get(name)
        index = self._resolve_position_index(position, atoms) if position else None
        if index is None:
            index = self._resolve_position_by_guessing(name, atoms)
        if index is not None:
            self._distance_position_indices[name] = index
        return index

    def _candidate_names(self, distance_name: str) -> tuple[list[str], list[str]]:
        """Guess the two position names of a distance from its own name.

        ``"19-119_C3"`` names the pair ``19``/``119`` measured at ``C3``; a
        labelling file that does not spell the positions out still resolves.

        Parameters
        ----------
        distance_name : str
            Key of the distance in the FPS JSON.

        Returns
        -------
        tuple of list of str
            Candidate names for the first and the second position.
        """
        base, _, suffix = distance_name.partition("_")
        parts = base.split("-")
        if len(parts) != 2:
            return [], []
        out = []
        for residue in parts:
            names = [f"{residue}_{suffix}", f"{residue}{suffix}"] if suffix else []
            names.append(residue)
            out.append(names)
        return out[0], out[1]

    def update_distance_values(self, xyz: np.ndarray | None = None) -> None:
        """Recompute the distance outputs for a set of coordinates.

        Parameters
        ----------
        xyz : numpy.ndarray, optional
            Coordinates to measure; the active trajectory frame (or the starting
            structure) when omitted.
        """
        if xyz is None:
            xyz = self._active_coordinates()
        if xyz is None or not self._distance_parameters or not self._distance_definitions:
            return
        structure = (
            self.proteinmc_structure if self.proteinmc_structure is not None else self.structure
        )
        atoms = getattr(structure, "atoms", None)
        if atoms is None:
            return

        self._distance_position_indices.clear()
        for name, definition in self._distance_definitions.items():
            parameter = self._distance_parameters.get(name)
            if parameter is None:
                continue
            i = self._position_index(str(definition.get("position1_name", "")), atoms)
            j = self._position_index(str(definition.get("position2_name", "")), atoms)
            if i is None or j is None:
                first, second = self._candidate_names(name)
                i = (
                    i
                    if i is not None
                    else next(
                        (
                            k
                            for k in (self._position_index(c, atoms) for c in first)
                            if k is not None
                        ),
                        None,
                    )
                )
                j = (
                    j
                    if j is not None
                    else next(
                        (
                            k
                            for k in (self._position_index(c, atoms) for c in second)
                            if k is not None
                        ),
                        None,
                    )
                )
            if i is None or j is None:
                continue
            try:
                # Written straight onto the parameter. The hand-written version
                # published this through the GUI fitting client inside a bare
                # ``except``, so the distances stayed NaN headless and until the
                # editor had registered the fit.
                parameter.value = float(np.linalg.norm(xyz[i] - xyz[j]))
            except (IndexError, ValueError) as exc:
                logging.debug(f"ProteinMC: distance {name} not measurable: {exc}")

    def _active_coordinates(self) -> np.ndarray | None:
        """Return the coordinates of the active frame, or of the start structure."""
        if self.trajectory_frames:
            index = max(0, min(self.current_frame_index, len(self.trajectory_frames) - 1))
            return self.trajectory_frames[index]
        structure = (
            self.proteinmc_structure if self.proteinmc_structure is not None else self.structure
        )
        return getattr(structure, "xyz", None)

    # -- trajectory ----------------------------------------------------

    @property
    def frame_count(self) -> int:
        """Number of trajectory frames currently available."""
        return len(self.trajectory_frames)

    def set_current_frame(self, index: int, **kwargs) -> None:
        """Select the frame every ProteinMC view shows.

        Parameters
        ----------
        index : int
            Frame index, clamped to the available range.
        **kwargs
            Accepted and ignored, so the view's ``update_plots`` keyword still
            works.
        """
        if self.frame_count <= 0:
            self.current_frame_index = 0
            return
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = 0
        self.current_frame_index = max(0, min(index, self.frame_count - 1))
        self.update_distance_values()

    def load_starting_structure(self) -> None:
        """Load :attr:`structure_file` as the structure sampling starts from."""
        if not self.structure_file:
            return
        try:
            from chisurf.core.structure import Structure

            self.proteinmc_structure = Structure(self.structure_file)
        except Exception as exc:
            logging.warning(
                f"ProteinMC: could not load starting structure {self.structure_file!r}: {exc}"
            )
            return
        self.trajectory_frames = []
        self.current_frame_index = 0
        self.update_distance_values()

    # -- sampling ------------------------------------------------------

    @property
    def is_sampling(self) -> bool:
        """Whether a sampling run is in flight."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def sampling_progress(self) -> float:
        """Fraction of the requested frames written so far, in ``0 … 1``."""
        target = self._total_frames_target - self._start_frame_count
        if target <= 0:
            return 0.0
        done = self.frame_count - self._start_frame_count
        return max(0.0, min(1.0, done / float(target)))

    @property
    def sampling_status(self) -> str:
        """One line describing the run, for the editor's status field."""
        return self._sampling_status

    def start_sampling(self) -> None:
        """Start (or continue) a ProteinMC run in a background thread.

        Continuing is automatic: when a trajectory is already in hand the run
        picks up from it rather than discarding it, which is what makes a saved
        project resumable.
        """
        if self.is_sampling:
            return
        directory = Path(self.output_directory) if self.output_directory else None
        if directory is None:
            logging.warning("ProteinMC: choose an output directory first")
            return
        directory.mkdir(parents=True, exist_ok=True)

        continuing = self.proteinmc_structure is not None and bool(self.trajectory_frames)
        source = self.proteinmc_structure if continuing else (self.structure_file or self.structure)
        if not source:
            logging.warning("ProteinMC: select a structure or enter a PDB ID first")
            return

        if continuing:
            initial_frames = [np.asarray(f, dtype=float) for f in self.trajectory_frames[:-1]]
            self._resume_traces = {
                "rmsd": list(self.rmsd),
                "drmsd": list(self.drmsd),
                "energy": list(self.energy),
                "chi2r": list(self.chi2r),
            }
        else:
            initial_frames = []
            self._resume_traces = {"rmsd": [], "drmsd": [], "energy": [], "chi2r": []}
            self.trajectory_frames = []
            self.current_frame_index = 0
            self.proteinmc_structure = None
            self.rmsd, self.drmsd, self.energy, self.chi2r = [], [], [], []

        self._start_frame_count = self.frame_count
        self._total_frames_target = self._start_frame_count + int(self.n_written) + 1
        self._stop_requested = False
        self._sampling_status = "starting…"

        settings = {
            "n_iter": int(self.n_iter),
            "n_out": int(self.n_out),
            "pdbOut": int(self.n_written),
            "scale": float(self.scale),
            "kt": float(self.kt),
            "n_runs": max(1, int(self.n_runs)),
            "potentials": self.potential_settings(),
        }
        self._thread = threading.Thread(
            target=self._run_sampling,
            kwargs={
                "structure_source": source,
                "flexfit_set": self.flexfit_set if self.use_flexfit else "",
                "settings": settings,
                "output_file": directory / "proteinmc.rmf3",
                "initial_frames": initial_frames,
            },
            daemon=True,
            name="proteinmc-sampling",
        )
        self._thread.start()

    def run_sampling(
        self,
        output_directory: str | Path | None = None,
        run_count: int = 1,
        n_iter: int | None = None,
    ) -> None:
        """Start sampling from ChiSurf's generic **Sampling** button.

        The fit controller looks for this name on a model that samples itself,
        and hands it the folder and the run length its own panel collected.

        Parameters
        ----------
        output_directory : str or pathlib.Path, optional
            Where to write; keeps :attr:`output_directory` when omitted.
        run_count : int
            Number of independent runs.
        n_iter : int, optional
            MC trials per run; keeps :attr:`n_iter` when omitted.
        """
        if output_directory:
            self.output_directory = str(output_directory)
        try:
            self.n_runs = max(1, int(run_count))
        except (TypeError, ValueError):
            self.n_runs = 1
        if n_iter is not None:
            try:
                self.n_iter = max(1, int(n_iter))
            except (TypeError, ValueError):
                pass
        self.start_sampling()

    def stop_sampling(self) -> None:
        """Ask the running sampler to stop at the next opportunity."""
        self._stop_requested = True
        if self._runner is not None:
            self._runner.stop()
        self._sampling_status = "stopping…"

    def _run_sampling(self, **runner_kwargs) -> None:
        """Thread body: build the runner, sample, record the outcome."""
        try:
            self._runner = ProteinMCRunner(progress_callback=self._on_progress, **runner_kwargs)
            self.proteinmc_structure = self._runner.structure
            if self._stop_requested:
                self._runner.stop()
            result = self._runner.run()
        except Exception as exc:
            self._sampling_status = f"failed: {exc}"
            logging.error(f"ProteinMC failed: {exc}")
            return
        finally:
            self._runner = None
        self.proteinmc_structure = getattr(result, "structure", self.proteinmc_structure)
        self._sampling_status = f"finished: {getattr(result, 'output_file', '')}"
        logging.info(self._sampling_status)

    def _on_progress(self, progress: ProteinMCProgress) -> None:
        """Record one frame reported by the sampler."""
        self.rmsd = self._resume_traces.get("rmsd", []) + list(progress.rmsd)
        self.drmsd = self._resume_traces.get("drmsd", []) + list(progress.drmsd)
        self.energy = self._resume_traces.get("energy", []) + list(progress.energies)
        self.chi2r = self._resume_traces.get("chi2r", []) + list(progress.labeling_energies)
        if progress.xyz is not None:
            self.trajectory_frames.append(np.asarray(progress.xyz, dtype=float))
            self.current_frame_index = len(self.trajectory_frames) - 1
            self.update_distance_values(progress.xyz)
        self._sampling_status = (
            f"frame {self.frame_count} — energy {progress.energy:.4g}, "
            f"labelling {progress.labeling_energy:.4g}"
        )

    # -- Model contract ------------------------------------------------

    def _update_model(self, **kwargs) -> None:
        """Refresh the distance outputs; the trajectory is produced by sampling.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments accepted for signature compatibility.
        """
        self.update_distance_values()

    def get_state(self, **kwargs) -> dict:
        """Return the project-serializable ProteinMC state."""
        state = super().get_state(**kwargs) if hasattr(super(), "get_state") else {}
        state["proteinmc"] = {
            "structure_source": self.structure_file,
            "labeling_file": self.labeling_file,
            "score_set": self.score_set,
            "use_flexfit": bool(self.use_flexfit),
            "flexfit_set": self.flexfit_set,
            "output_directory": self.output_directory,
            "settings": {
                "n_iter": int(self.n_iter),
                "n_out": int(self.n_out),
                "n_written": int(self.n_written),
                "pdbOut": int(self.n_written),
                "scale": float(self.scale),
                "kt": float(self.kt),
                "labeling_weight": float(self.labeling_weight),
                "potentials": self.potential_settings(),
            },
        }
        return state

    def set_state(self, state: dict, **kwargs) -> None:
        """Restore the ProteinMC state written by :meth:`get_state`.

        Parameters
        ----------
        state : dict
            Either the whole model state or the ``"proteinmc"`` payload.
        **kwargs
            Forwarded to the base implementation.
        """
        payload = state.get("proteinmc", state) if isinstance(state, dict) else {}
        if not isinstance(payload, dict):
            return

        self.structure_file = str(payload.get("structure_source", "") or "")
        self.labeling_file = str(payload.get("labeling_file", "") or "")
        self.score_set = str(payload.get("score_set", "") or "")
        self.use_flexfit = bool(payload.get("use_flexfit", False))
        self.flexfit_set = str(payload.get("flexfit_set", "") or "")
        directory = payload.get("output_directory") or ""
        if not directory and payload.get("output_file"):
            directory = str(Path(payload["output_file"]).parent)
        self.output_directory = str(directory)

        settings = payload.get("settings") or {}
        if isinstance(settings, dict):
            for attr, key in (
                ("n_iter", "n_iter"),
                ("n_out", "n_out"),
                ("n_written", "n_written"),
                ("scale", "scale"),
                ("kt", "kt"),
                ("labeling_weight", "labeling_weight"),
            ):
                value = settings.get(key)
                if value is None and key == "n_written":
                    value = settings.get("pdbOut")
                if value is not None:
                    setattr(self, attr, type(getattr(self, attr))(value))
            self._restore_potentials(settings.get("potentials", []))

        if self.structure_file:
            self.load_starting_structure()
        self._sync_labeling_into_dye_potential()
        self._sync_dye_potential_into_labeling()
        self.reload_distances()
        self.update_distance_values()

    def _restore_potentials(self, potentials: object) -> None:
        """Rebuild the energy terms from a serialized list.

        Parameters
        ----------
        potentials : object
            The ``"potentials"`` entry of a saved project. Term names are matched
            case-insensitively through :data:`_POTENTIAL_ALIASES`, because they
            have been spelled several ways across versions.
        """
        if not isinstance(potentials, (list, tuple)):
            return
        self._potentials = []
        for item in potentials:
            if not isinstance(item, dict):
                continue
            raw = str(item.get("name", "")).strip().lower()
            key = _POTENTIAL_ALIASES.get(raw)
            if key is None or key not in POTENTIAL_SPECS:
                continue
            self.add_potential(key)
            term = self._potentials[-1]
            try:
                term["weight"] = float(item.get("weight", term["weight"]))
            except (TypeError, ValueError):
                pass
            try:
                term["eval_interval"] = max(1, int(item.get("eval_interval", 1)))
            except (TypeError, ValueError):
                pass
            stored = item.get("settings")
            if isinstance(stored, dict):
                term["settings"].update(stored)

    def scheme_json(self) -> str:
        """Return the sampling setup as JSON (for logs and bug reports)."""
        return json.dumps(self.get_state()["proteinmc"], indent=2, default=str)
