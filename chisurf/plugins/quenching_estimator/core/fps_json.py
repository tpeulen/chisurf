import json
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple, Union

import numpy as np

from chisurf.plugins.quenching_estimator.core.av import DEFAULT_ALLOWED_SPHERE_RADIUS


def load_fps_json(path_or_dict: Union[Path, str, dict]) -> dict:
    """Load and parse an fps.json file or dictionary, validating its structure."""
    if isinstance(path_or_dict, (Path, str)):
        with open(path_or_dict, encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(path_or_dict, dict):
        data = path_or_dict
    else:
        raise TypeError("Expected path or dict for fps.json data.")

    if "Positions" not in data:
        raise ValueError("fps.json structure must contain a 'Positions' key.")

    return data


def normalize_to_fps_positions(sites_list_or_dict: Any, project: dict) -> dict:
    """Normalize a list of sites or a dictionary containing 'Positions' to standard fps.json structure."""
    if isinstance(sites_list_or_dict, dict) and "Positions" in sites_list_or_dict:
        return sites_list_or_dict

    # Otherwise, it might be a dictionary that is just the raw Positions map, or a list of sites.
    if isinstance(sites_list_or_dict, dict):
        # If it looks like a Positions map directly (where values have residue_seq_number or similar)
        first_val = next(iter(sites_list_or_dict.values())) if sites_list_or_dict else None
        if (
            first_val
            and isinstance(first_val, dict)
            and ("residue_seq_number" in first_val or "residue" in first_val)
        ):
            return {"Positions": sites_list_or_dict}
        # Otherwise, try to convert it
        raise ValueError(
            "Invalid dictionary structure for sites. Expected 'Positions' key or a positions map."
        )

    if not isinstance(sites_list_or_dict, list):
        raise TypeError("Sites must be a list or a dict conforming to fps.json format.")

    positions = {}
    for idx, site in enumerate(sites_list_or_dict):
        chain = site.get("chain", "") or site.get("chain_identifier", "")
        res = site.get("residue") or site.get("residue_seq_number")
        if res is None:
            raise ValueError(
                f"Site entry at index {idx} must define a 'residue' or 'residue_seq_number'."
            )
        res = int(res)
        atom = site.get("atom", "CB") or site.get("atom_name", "CB")
        res_name = site.get("residue_name", "")

        # Determine the name: use name/key if present, or construct res+chain
        name = site.get("name") or site.get("key") or f"{res}{chain}" or f"site_{idx}"

        av_param = project.get("av_parameter", {})
        if not isinstance(av_param, dict):
            av_param = {}

        positions[name] = {
            "chain_identifier": chain,
            "residue_seq_number": res,
            "atom_name": atom,
            "residue_name": res_name,
            "linker_length": float(
                project.get("linker_length") or av_param.get("linker_length") or 20.0
            ),
            "linker_width": float(
                project.get("linker_width") or av_param.get("linker_width") or 0.5
            ),
            "radius1": float(project.get("radius1") or av_param.get("radius1") or 3.5),
            "radius2": float(project.get("radius2") or av_param.get("radius2") or 4.5),
            "radius3": float(project.get("radius3") or av_param.get("radius3") or 3.5),
            "simulation_grid_resolution": float(
                project.get("dg") or project.get("simulation_grid_resolution") or 1.5
            ),
            "simulation_type": project.get("simulation_type") or "AV1",
            "allowed_sphere_radius": float(
                project.get("allowed_sphere_radius") or DEFAULT_ALLOWED_SPHERE_RADIUS
            ),
            "anchor_atoms": project.get("anchor_atoms", ""),
            "chain_weighting": project.get("chain_weighting", False),
            "contact_volume_thickness": float(project.get("contact_volume_thickness", 0.0)),
            "contact_volume_trapped_fraction": float(
                project.get("contact_volume_trapped_fraction", -1.0)
            ),
            "min_sphere_volume_fraction": float(project.get("min_sphere_volume_fraction", 0.0)),
            "strip_mask": project.get("strip_mask", ""),
        }

    return {"Positions": positions}


def run_fps_scan(
    fps_data: dict,
    pdb_path: Optional[Union[Path, str]],
    project: dict,
    nbins: Optional[int] = None,
    tac_range: tuple[float, float] = (0.0, 50.0),
    project_dir: Optional[Union[Path, str]] = None,
) -> Generator[dict, None, dict]:
    """Simulate every position in *fps_data*, yielding one record per site.

    Yields the same record shape the CLI and the web UI report — including the
    quencher attribution — because all three go through
    :func:`quest.scan.simulate_site`. Returns the records keyed by position
    name.
    """
    import tempfile

    from chisurf.plugins.quenching_estimator.core.scan import scan_positions

    positions = fps_data.get("Positions", {})
    p_dir = Path(project_dir) if project_dir is not None else Path(tempfile.gettempdir())

    results: dict[str, Any] = {}
    for res in scan_positions(
        project,
        positions,
        pdb_path=pdb_path,
        nbins=nbins,
        tac_range=tac_range,
        project_dir=p_dir,
    ):
        results[res["name"]] = res
        yield res

    return results
