"""The configured native structure settings keep single-file shell import."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml
from emtk.testing import Driver
from qtpy import QtWidgets

from chisurf.core.experiments.core import Experiment
from chisurf.core.experiments.modelling.reader import StructureReader
from chisurf.gui.main import Main
from chisurf.gui.main_helper import SetupMixin

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


def test_configured_native_host_imports_the_actual_148l_structure_once(qtbot, monkeypatch):
    """The original path and internal-coordinate toggle reach one owning import."""
    import chisurf.core.actions as actions
    import chisurf.core.structure

    reader = _configured_reader()
    reader.filename = str(SOURCE)
    panel = QtWidgets.QWidget()
    qtbot.addWidget(panel)
    panel.resize(760, 380)
    panel.layout_experiment_reader = QtWidgets.QVBoxLayout(panel)
    panel.current_setup = reader
    panel.current_experiment = SimpleNamespace(readers=[reader])
    panel.comboBox_setupSelect = QtWidgets.QComboBox()
    panel.comboBox_setupSelect.addItem("Structure")
    panel.open_context_help_for_reader = lambda: None
    SetupMixin._refresh_setup_ui(panel)
    host = panel.layout_experiment_reader.itemAt(0).widget()
    loaded = []
    original_structure = chisurf.core.structure.Structure

    def actual_structure(*args, **kwargs):
        """Count real structure construction, retaining the original file and option."""
        loaded.append(kwargs.copy())
        return original_structure(*args, **kwargs)

    monkeypatch.setattr(chisurf.core.structure, "Structure", actual_structure)
    try:
        assert host.control.model is reader and reader.controller is None
        driver = Driver(host.control, (760, 380))
        driver.frame(2)
        driver.click("compute_internal_coordinates")
        assert reader.compute_internal_coordinates is True
        imports = []

        def dispatch(name, payload):
            """Decode through the scientific reader/path delivered by production Main."""
            assert name == "dataset.add"
            assert payload["experiment_reader"] is reader
            assert payload["filename"] == SOURCE.as_posix()
            imports.append(reader.get_data(filename=payload["filename"]))
            return {"ok": True}

        monkeypatch.setattr(actions, "dispatch", dispatch)
        Main.onAddDataset(panel)
        driver.frame(2)
        assert len(imports) == len(loaded) == 1
        assert loaded[0] == {"p_object": str(SOURCE), "make_coarse": True}
        structure = imports[0][0]
        assert reader.n_atoms == structure.n_atoms == 1300
        assert reader.n_residues == structure.n_residues == 164
        assert reader.filename == str(SOURCE)
        assert reader.compute_internal_coordinates is True
        reference = original_structure(p_object=str(SOURCE), make_coarse=True)
        np.testing.assert_array_equal(structure.atoms, reference.atoms)
        assert {
            "filename",
            "filename.browse",
            "compute_internal_coordinates",
            "n_atoms",
            "n_residues",
        } <= set(host.control.item_rects)
    finally:
        host.close()
