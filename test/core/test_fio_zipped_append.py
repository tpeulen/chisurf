"""Appending to a text file through open_maybe_zipped (multi-model PDB writes)."""

import gzip

import pytest

from chisurf.core.fio.zipped import open_maybe_zipped


@pytest.mark.parametrize("name", ["models.pdb", "models.pdb.gz"])
def test_append_mode_adds_to_the_file(tmp_path, name):
    """write_pdb opens with "a+" for every model after the first."""
    path = tmp_path / name
    for model in ("MODEL 1\n", "MODEL 2\n"):
        with open_maybe_zipped(str(path), "a+") as fh:
            fh.write(model)
    opener = gzip.open if name.endswith(".gz") else open
    with opener(path, "rt") as fh:
        assert fh.read() == "MODEL 1\nMODEL 2\n"


def test_append_to_zip_is_refused(tmp_path):
    with pytest.raises(ValueError, match="zip"):
        open_maybe_zipped(str(tmp_path / "x.zip"), "a")


def test_multi_model_pdb_has_separate_model_records(tmp_path):
    """Trajectory.save_pdb wrote 'MODELATOM' / 'ENDMDLMODELATOM' fused lines."""
    import re

    import numpy as np

    from chisurf.core.fio.structure.coordinates import write_pdb

    from chisurf.core.fio.structure.coordinates import atom_dtype as ATOM_DTYPE

    atoms = np.zeros(2, dtype=ATOM_DTYPE)
    atoms["atom_id"] = [1, 2]
    atoms["atom_name"] = ["N", "CA"]
    atoms["res_name"] = "MET"
    atoms["chain"] = "A"
    atoms["res_id"] = 1
    atoms["element"] = ["N", "C"]
    path = tmp_path / "m.pdb"
    for frame in range(3):
        write_pdb(str(path), atoms, append_model=frame > 0, model_serial=frame + 1)
    text = path.read_text()
    assert re.findall(r"^MODEL\s+(\d+)$", text, re.M) == ["1", "2", "3"]
    assert text.count("\nENDMDL\n") + text.startswith("ENDMDL\n") == 3
    assert "MODELATOM" not in text and "ENDMDLMODEL" not in text
