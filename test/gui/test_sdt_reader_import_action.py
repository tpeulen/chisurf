"""Configured native SDT settings retain the existing shell import route."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml
from emtk.testing import Driver
from qtpy import QtWidgets

from chisurf.core.experiments.core import Experiment
from chisurf.core.experiments.tcspc.sdt_reader import SDTReader
from chisurf.core.fio.fluorescence.sdtfile import SdtFile
from chisurf.gui.main import Main
from chisurf.gui.main_helper import SetupMixin

SOURCE = Path("test/data/tcspc/BH_SDT/140507p.sdt").resolve()


def _configured_reader():
    """Construct exactly the SDT reader class selected by shipped settings."""
    config = yaml.safe_load(Path("chisurf/core/settings/experiment_configs.yaml").read_text())
    entry = next(
        reader
        for section in config.values()
        if isinstance(section, dict)
        for reader in section.get("readers", [])
        if reader.get("reader_params", {}).get("name") == "Becker-SDT"
    )
    module, class_name = entry["reader_class"].rsplit(".", 1)
    assert entry["controller_class"] is None
    cls = getattr(import_module(module), class_name)
    assert cls is SDTReader
    return cls(experiment=Experiment(name="SDT"), record_provenance=False, **entry["reader_params"])


def test_configured_native_host_imports_all_real_sdt_curves_once(qtbot, monkeypatch):
    """Preview2 cannot filter or duplicate the real header import payload."""
    import chisurf.core.actions as actions
    from chisurf.core.experiments.tcspc import sdt_reader

    reader = _configured_reader()
    reader.load_file(str(SOURCE))
    parsed = []
    parse_sdt = sdt_reader.SdtFile

    def parse_once(filename):
        """Count actual SDT decodes after the initial preview load."""
        parsed.append(filename)
        return parse_sdt(filename)

    monkeypatch.setattr(sdt_reader, "SdtFile", parse_once)
    panel = QtWidgets.QWidget()
    qtbot.addWidget(panel)
    panel.resize(760, 580)
    panel.layout_experiment_reader = QtWidgets.QVBoxLayout(panel)
    panel.current_setup = reader
    panel.current_experiment = SimpleNamespace(readers=[reader])
    panel.comboBox_setupSelect = QtWidgets.QComboBox()
    panel.comboBox_setupSelect.addItem("Becker-SDT")
    panel.open_context_help_for_reader = lambda: None
    SetupMixin._refresh_setup_ui(panel)
    host = panel.layout_experiment_reader.itemAt(0).widget()
    try:
        assert host.control.model is reader and reader.controller is None
        driver = Driver(host.control, (760, 580))
        driver.frame(2)
        driver.click("curve_nbr")
        driver.click("2")
        assert reader.curve_nbr == 2
        decoded = []

        def dispatch(name, payload):
            """Decode the original path through the reader actually delivered by Main."""
            assert name == "dataset.add"
            assert payload["experiment_reader"] is reader
            assert payload["filename"] == SOURCE.as_posix()
            decoded.append(reader.get_data(filename=payload["filename"]))
            return {"ok": True}

        monkeypatch.setattr(actions, "dispatch", dispatch)
        Main.onAddDataset(panel)
        driver.frame(2)
        assert len(decoded) == 1 and len(decoded[0]) == 3
        assert parsed == [str(SOURCE)]
        source = SdtFile(str(SOURCE))
        for index, curve in enumerate(decoded[0]):
            assert len(curve.y) == 1024
            assert curve.data_reader is reader
            np.testing.assert_array_equal(curve.y, source.data[index][0])
            np.testing.assert_array_equal(curve.x, source.times[index] * 1e9)
        assert reader.curve_nbr == 2
    finally:
        host.close()
