"""The configured SDT reader imports every curve of a real file."""

from importlib import import_module
from pathlib import Path

import numpy as np
import yaml

from chisurf.core.experiments.core import Experiment
from chisurf.core.experiments.tcspc.sdt_reader import SDTReader
from chisurf.core.fio.fluorescence.sdtfile import SdtFile

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
    assert entry.get("controller_class") is None
    cls = getattr(import_module(module), class_name)
    assert cls is SDTReader
    return cls(experiment=Experiment(name="SDT"), record_provenance=False, **entry["reader_params"])


def test_configured_reader_imports_all_real_sdt_curves_once(monkeypatch):
    """The real header import payload is neither filtered nor duplicated."""
    from chisurf.core.experiments.tcspc import sdt_reader

    reader = _configured_reader()
    reader.load_file(str(SOURCE))
    reader.curve_nbr = 2
    parsed = []
    parse_sdt = sdt_reader.SdtFile

    def parse_once(filename):
        """Count actual SDT decodes after the initial preview load."""
        parsed.append(filename)
        return parse_sdt(filename)

    monkeypatch.setattr(sdt_reader, "SdtFile", parse_once)
    decoded = reader.get_data(filename=SOURCE.as_posix())
    assert len(decoded) == 3
    assert parsed == [str(SOURCE)]
    source = SdtFile(str(SOURCE))
    for index, curve in enumerate(decoded):
        assert len(curve.y) == 1024
        assert curve.data_reader is reader
        np.testing.assert_array_equal(curve.y, source.data[index][0])
        np.testing.assert_array_equal(curve.x, source.times[index] * 1e9)
    assert reader.curve_nbr == 2
