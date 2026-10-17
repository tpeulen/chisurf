"""The configured structure reader keeps single-file import."""

from importlib import import_module
from pathlib import Path

import numpy as np
import yaml

from chisurf.core.experiments.core import Experiment
from chisurf.core.experiments.modelling.reader import StructureReader

SOURCE = Path("test/data/atomic_coordinates/pdb_files/148l.pdb").resolve()


def _configured_reader(require_native=True):
    """Construct the actual scientific row; native retirement is a separate gate."""
    entry = yaml.safe_load(Path("chisurf/core/settings/experiment_configs.yaml").read_text())[
        "structure"
    ]["readers"][0]
    if require_native:
        assert entry["controller_class"] is None
    module, class_name = entry["reader_class"].rsplit(".", 1)
    cls = getattr(import_module(module), class_name)
    assert cls is StructureReader
    return cls(
        experiment=Experiment(name="Structure"),
        record_provenance=False,
        **entry.get("reader_params", {}),
    )


def test_configured_reader_imports_the_actual_148l_structure_once(monkeypatch):
    """The original path and internal-coordinate toggle reach one owning import."""
    import chisurf.core.structure

    reader = _configured_reader()
    reader.filename = str(SOURCE)
    reader.compute_internal_coordinates = True
    loaded = []
    original_structure = chisurf.core.structure.Structure

    def actual_structure(*args, **kwargs):
        """Count real structure construction, retaining the original file and option."""
        loaded.append(kwargs.copy())
        return original_structure(*args, **kwargs)

    monkeypatch.setattr(chisurf.core.structure, "Structure", actual_structure)
    imports = reader.get_data(filename=SOURCE.as_posix())
    assert len(loaded) == 1
    assert loaded[0] == {"p_object": str(SOURCE), "make_coarse": True}
    structure = imports[0]
    assert reader.n_atoms == structure.n_atoms == 1300
    assert reader.n_residues == structure.n_residues == 164
    assert reader.filename == str(SOURCE)
    reference = original_structure(p_object=str(SOURCE), make_coarse=True)
    np.testing.assert_array_equal(structure.atoms, reference.atoms)
