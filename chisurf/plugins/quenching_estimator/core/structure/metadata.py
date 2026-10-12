"""What a structure file offers as labeling sites.

Parsing a structure into chains, residues and atom names is domain work -- the
CLI, a notebook and a host application all have reason to ask -- so it does not
belong to whichever surface happened to need it first (it lived in the web
backend).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.plugins.quenching_estimator.core.structure.reader import (
    _WATER_RESIDUE_NAMES,
    strip_water_pdb_text,
)

__all__ = ["structure_metadata"]


def structure_metadata(path: Path | str) -> dict[str, Any]:
    """Chains, residues and atom names of a structure file.

    Reads PDB and mmCIF. Used to populate labeling-site pickers, so it
    reports what a dye could be attached to rather than a full parse: per
    chain, the residues in sequence order, each with its sorted atom names.

    Parameters
    ----------
    path : path
        Structure file. Resolve PDB IDs with
        :func:`quest.core.structure.fetch.resolve_structure_path` first.

    Returns
    -------
    dict
        ``filename``, ``path``, ``atom_count``, ``chains`` and the raw
        ``pdb_text`` (the browser viewer renders it directly).

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No such structure file: {path}")
    chains: dict[str, dict[int, dict[str, Any]]] = {}
    atom_count = 0
    with path.open("r", encoding="utf8", errors="replace") as handle:
        raw_text = handle.read()

    # Strip water from the returned pdb_text so no surface ever renders it.
    # PDB lines are filtered directly; CIF rows are skipped during parsing and
    # the raw text is returned as-is (the browser viewer does not use pdb_text
    # for CIF files).
    is_cif = "loop_" in raw_text and "_atom_site." in raw_text
    pdb_text = raw_text if is_cif else strip_water_pdb_text(raw_text)

    if is_cif:
        rows = pdb_text.splitlines()
        in_loop = False
        loop_headers: list[str] = []

        def clean_val(s):
            s = s.strip()
            if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                return s[1:-1]
            return s

        i = 0
        while i < len(rows):
            line = rows[i].strip()
            if not line or line.startswith("#"):
                i += 1
                continue

            if line == "loop_":
                in_loop = True
                loop_headers = []
                i += 1
                while i < len(rows):
                    next_line = rows[i].strip()
                    if next_line.startswith("_atom_site."):
                        loop_headers.append(next_line)
                        i += 1
                    elif next_line.startswith("_"):
                        in_loop = False
                        break
                    else:
                        break

                if in_loop and loop_headers:
                    header_map = {}
                    for idx, h in enumerate(loop_headers):
                        field = h.split(".")[-1].strip()
                        header_map[field] = idx

                    atom_name_col = header_map.get("auth_atom_id")
                    if atom_name_col is None:
                        atom_name_col = header_map.get("label_atom_id")

                    res_name_col = header_map.get("auth_comp_id")
                    if res_name_col is None:
                        res_name_col = header_map.get("label_comp_id")

                    chain_col = header_map.get("auth_asym_id")
                    if chain_col is None:
                        chain_col = header_map.get("label_asym_id")

                    res_id_col = header_map.get("auth_seq_id")
                    if res_id_col is None:
                        res_id_col = header_map.get("label_seq_id")

                    group_col = header_map.get("group_PDB")

                    while i < len(rows):
                        data_line = rows[i].strip()
                        if not data_line or data_line.startswith("#"):
                            i += 1
                            continue
                        if (
                            data_line == "loop_"
                            or data_line.startswith("_")
                            or data_line.startswith("data_")
                        ):
                            break

                        parts = []
                        current = []
                        in_quote = False
                        quote_char = None
                        for char in data_line:
                            if char in ("'", '"'):
                                if not in_quote:
                                    in_quote = True
                                    quote_char = char
                                elif quote_char == char:
                                    in_quote = False
                                    quote_char = None
                                else:
                                    current.append(char)
                            elif char.isspace():
                                if in_quote:
                                    current.append(char)
                                else:
                                    if current:
                                        parts.append("".join(current))
                                        current = []
                            else:
                                current.append(char)
                        if current:
                            parts.append("".join(current))

                        if len(parts) >= len(loop_headers):
                            group = clean_val(parts[group_col]) if group_col is not None else "ATOM"
                            if group in ("ATOM", "HETATM"):
                                atom_name = (
                                    clean_val(parts[atom_name_col])
                                    if atom_name_col is not None
                                    else ""
                                )
                                residue_name = (
                                    clean_val(parts[res_name_col])
                                    if res_name_col is not None
                                    else ""
                                )
                                if residue_name.strip().upper() in _WATER_RESIDUE_NAMES:
                                    i += 1
                                    continue
                                atom_count += 1
                                chain_id = (
                                    clean_val(parts[chain_col]) if chain_col is not None else "A"
                                )
                                chain_id = chain_id.strip() or "_"
                                raw_residue = (
                                    clean_val(parts[res_id_col]) if res_id_col is not None else "1"
                                )
                                try:
                                    residue_id = int(raw_residue)
                                except ValueError:
                                    i += 1
                                    continue
                                chains.setdefault(chain_id, {}).setdefault(
                                    residue_id,
                                    {"id": residue_id, "name": residue_name, "atoms": []},
                                )
                                if (
                                    atom_name
                                    and atom_name not in chains[chain_id][residue_id]["atoms"]
                                ):
                                    chains[chain_id][residue_id]["atoms"].append(atom_name)
                        i += 1
                    in_loop = False
                else:
                    i += 1
            else:
                i += 1
    else:
        # Standard PDB parser
        for line in pdb_text.splitlines():
            if not line.startswith(("ATOM  ", "HETATM")):
                continue
            atom_count += 1
            atom_name = line[12:16].strip()
            residue_name = line[17:20].strip()
            chain_id = line[21].strip() or "_"
            raw_residue = line[22:26].strip()
            try:
                residue_id = int(raw_residue)
            except ValueError:
                continue
            chains.setdefault(chain_id, {}).setdefault(
                residue_id,
                {"id": residue_id, "name": residue_name, "atoms": []},
            )
            if atom_name and atom_name not in chains[chain_id][residue_id]["atoms"]:
                chains[chain_id][residue_id]["atoms"].append(atom_name)

    chain_payload = []
    for chain_id, residues in sorted(chains.items()):
        chain_payload.append(
            {
                "id": chain_id,
                "residues": [
                    {
                        "id": residue["id"],
                        "name": residue["name"],
                        "atoms": sorted(residue["atoms"]),
                    }
                    for residue in sorted(residues.values(), key=lambda item: item["id"])
                ],
            }
        )
    return {
        "filename": path.name,
        "path": str(path),
        "atom_count": atom_count,
        "chains": chain_payload,
        "pdb_text": pdb_text,
    }
