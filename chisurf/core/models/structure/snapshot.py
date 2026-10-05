"""Data-only snapshots of molecular atoms and coarse internal coordinates."""

from __future__ import annotations

import numpy as np


def _array_state(array: np.ndarray) -> dict:
    """Encode numeric or text arrays without object payloads or executable types."""
    array = np.asarray(array)
    if array.dtype.names:
        return {
            "shape": list(array.shape),
            "fields": [
                {"name": name, "array": _array_state(array[name])} for name in array.dtype.names
            ],
        }
    if array.dtype.kind not in "biufUS":
        raise ValueError(f"unsupported structural array dtype {array.dtype}")
    values = array.tolist()
    if array.dtype.kind == "S":
        values = [bytes(value).hex() for value in array.ravel()]
    return {"dtype": array.dtype.str, "shape": list(array.shape), "values": values}


def _restore_array(state: dict) -> np.ndarray:
    """Restore an explicit atom field array, rejecting object dtype payloads."""
    shape = tuple(int(value) for value in state["shape"])
    if "fields" in state:
        fields = [(field["name"], _restore_array(field["array"])) for field in state["fields"]]
        dtype = [(name, array.dtype, array.shape[len(shape) :]) for name, array in fields]
        result = np.empty(shape, dtype=dtype)
        for name, array in fields:
            result[name] = array
        return result
    dtype = np.dtype(state["dtype"])
    if dtype.kind not in "biufUS":
        raise ValueError(f"unsupported structural array dtype {dtype}")
    values = state["values"]
    if dtype.kind == "S":
        values = [bytes.fromhex(value) for value in values]
    return np.asarray(values, dtype=dtype).reshape(shape)


def capture_structure(structure) -> dict | None:
    """Capture atoms and explicit coarse state while retaining source references."""
    if structure is None:
        return None
    from chisurf.core.structure import ProteinCentroid, Structure

    if not isinstance(structure, Structure):
        # Legacy callers may provide an atom-bearing structure facade.
        atoms = getattr(structure, "atoms", None)
        if not isinstance(atoms, np.ndarray) or not atoms.dtype.names:
            raise ValueError("structural snapshot requires a structured atom table")
    coarse = isinstance(structure, ProteinCentroid)
    state = {
        "kind": "protein_centroid" if coarse else "structure",
        "atoms": _array_state(structure.atoms),
        "filename": getattr(structure, "filename", None),
        "name": getattr(structure, "name", None),
        "uid": getattr(structure, "unique_identifier", None),
        "pdbid": getattr(structure, "pdbid", None),
        "auto_update": bool(getattr(structure, "auto_update", False)),
    }
    if coarse:
        state["coarse_arrays"] = {
            name: _array_state(np.asarray(getattr(structure, name)))
            for name in (
                "coord_i",
                "dist_ca",
                "l_res",
                "l_ca",
                "l_cb",
                "l_c",
                "l_n",
                "l_h",
                "residue_types",
                "_phi_indices",
                "_omega_indices",
                "_psi_indices",
                "_chi_indices",
            )
        }
    return state


def restore_structure(state: dict | None):
    """Rebuild a known structural type entirely from saved scientific arrays."""
    if state is None:
        return None
    from chisurf.core.structure import ProteinCentroid, Structure

    if state["kind"] not in {"structure", "protein_centroid"}:
        raise ValueError("unknown structural snapshot kind")
    structure = Structure()
    structure.atoms = _restore_array(state["atoms"])
    structure.filename = state.get("filename")
    if state["kind"] == "protein_centroid":
        # Construction builds the normal lookup machinery from atom data only.
        # Saved internal coordinates then replace the freshly derived arrays.
        structure = ProteinCentroid(structure)
        structure.atoms = _restore_array(state["atoms"])
        for name, array in state["coarse_arrays"].items():
            if name not in {
                "coord_i",
                "dist_ca",
                "l_res",
                "l_ca",
                "l_cb",
                "l_c",
                "l_n",
                "l_h",
                "residue_types",
                "_phi_indices",
                "_omega_indices",
                "_psi_indices",
                "_chi_indices",
            }:
                raise ValueError("unknown coarse coordinate field")
            restored = _restore_array(array)
            setattr(structure, name, restored.tolist() if name.endswith("_indices") else restored)
    structure.filename = state.get("filename")
    if state.get("name") is not None:
        structure.name = state["name"]
    if state.get("uid") is not None:
        structure.unique_identifier = state["uid"]
    structure.pdbid = state.get("pdbid")
    structure.auto_update = bool(state.get("auto_update", False))
    return structure
