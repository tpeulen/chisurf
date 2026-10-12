"""Everything about a structure, in one place.

These four concerns were spread across two packages and named by prefix —
`quest/core/structure/fetch.py`, `quest/core/structure/metadata.py`, `quest/core/structure/model.py`
and `quest/core/structure/reader.py` — so "where does a structure come from" had no single
answer and the naming implied a relationship the layout denied.

    fetch     where a structure comes from: a path, a PDB ID, bytes
    reader    turning that into QuEst's atom array (IMP does the parsing)
    model     the `Structure` object and coarse-graining
    metadata  what is in it: chains, residues, atoms, for a picker

The order above is the direction of travel, and it is the seam
[specs/structure-io.md](/specs/structure-io.md) describes: a caller says *what*
it wants labelled, never *how to read it*.
"""

from chisurf.plugins.quenching_estimator.core.structure.fetch import (
    download_pdb_id,
    is_pdb_id,
    resolve_structure_path,
)
from chisurf.plugins.quenching_estimator.core.structure.metadata import structure_metadata
from chisurf.plugins.quenching_estimator.core.structure.model import Structure, move_center_of_mass
from chisurf.plugins.quenching_estimator.core.structure.reader import (
    formats,
    keys,
    read,
    strip_water_pdb_text,
    water_stripped_pdb_path,
)

__all__ = [
    "Structure",
    "move_center_of_mass",
    "read",
    "keys",
    "formats",
    "strip_water_pdb_text",
    "water_stripped_pdb_path",
    "resolve_structure_path",
    "download_pdb_id",
    "is_pdb_id",
    "structure_metadata",
]
