"""Bundled scientific readers restore measured arrays without source reads."""

import numpy as np
import pytest

from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.deer.reader import DeerReader
from chisurf.core.experiments.tcspc.tttr_reader import TCSPCTTTRReader
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file


@pytest.mark.parametrize(
    "reader_class,filename,kwargs,size,count",
    [
        (
            TCSPCTTTRReader,
            "test/data/tttr/BH/132/BH_SPC132.spc",
            {"reading_routine": "SPC-130", "channel_numbers": [0, 1, 8, 9]},
            3664,
            183657,
        ),
        (DeerReader, "test/data/deer/deer_twostate.DSC", {}, 588, None),
    ],
)
def test_actual_reader_capture_restore_without_raw_read(
    reader_class, filename, kwargs, size, count, tmp_path, monkeypatch
):
    """Real measured TTTR/DEER arrays and getter configuration remain exact."""
    experiment = Experiment(name="measurement")
    reader = reader_class(experiment=experiment, record_provenance=False, **kwargs)
    group = reader.get_data(filename=filename)
    assert len(group[0].y) == size
    if count is not None:
        assert sum(group[0].y) == count
    project = capture_session([group], [])
    path = save_file(project, tmp_path / "measured.cs.pto")

    def forbidden(*args, **kwargs):
        raise AssertionError("restoration reread raw source")

    monkeypatch.setattr(reader_class, "get_data", forbidden)
    restored = restore_session(load_file(path))
    recaptured = capture_session(restored.datasets, [])
    assert recaptured.datasets == project.datasets
    assert recaptured.ui_state == project.ui_state
    new_group = restored.datasets[0]
    assert new_group[0].data_reader is not reader
    assert new_group[0].data_reader.experiment is new_group[0].experiment
    for field in ("x", "y", "ex", "ey", "mask"):
        np.testing.assert_array_equal(getattr(new_group[0], field), getattr(group[0], field))


def test_fresh_interpreter_real_readers_and_resources_with_mmfdb_blocked(tmp_path):
    """Portable measured-reader loops import no optional MMFDB module."""
    import os
    import subprocess
    import sys

    code = """
import importlib.abc
import sys
from pathlib import Path
class BlockMMFDB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mmfdb' or fullname.startswith('mmfdb.'):
            raise AssertionError('MMFDB imported: ' + fullname)
sys.meta_path.insert(0, BlockMMFDB())
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.tcspc.tttr_reader import TCSPCTTTRReader
from chisurf.core.experiments.deer.reader import DeerReader
from chisurf.core.project.project import ResourceContext
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from chisurf.core.project.transition import replace_project
from chisurf.server.session import SessionState
for cls, filename, kwargs, size in [
    (TCSPCTTTRReader, 'test/data/tttr/BH/132/BH_SPC132.spc',
     dict(reading_routine='SPC-130', channel_numbers=[0,1,8,9]), 3664),
    (DeerReader, 'test/data/deer/deer_twostate.DSC', {}, 588)]:
    reader = cls(experiment=Experiment(name='real'), record_provenance=False, **kwargs)
    group = reader.get_data(filename=filename)
    assert len(group[0].y) == size
    context = ResourceContext(sources={'source': Path(filename).read_bytes()})
    project = capture_session([group], [], resources=context)
    def forbidden(*args, **kwargs):
        raise AssertionError('raw reread on restore')
    cls.get_data = forbidden
    owner = SessionState()
    for iteration in range(3):
        path = save_file(project, Path(sys.argv[1])/(cls.__name__+str(iteration)+'.cs.pto'))
        project = load_file(path)
        replace_project(project, owner=owner)
        project = capture_session(owner.datasets, owner.fits, resources=owner.project_resources)
        assert dict(project.resources.sources) == dict(context.sources)
    print(cls.__name__, size, 'three exact file/owner loops, MMFDB blocked')
assert not any(name == 'mmfdb' or name.startswith('mmfdb.') for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / "fresh-readback.txt").write_text(result.stdout)


def test_simulator_reader_keeps_its_measured_irf_dependency():
    """A reader-held IRF remains a shared scientific curve after restoration."""
    from chisurf.core.data import DataCurve
    from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup

    x = np.arange(128.0) * 0.1
    irf = DataCurve(x=x, y=np.exp(-(((x - 2) / 0.3) ** 2)), ey=np.ones(128))
    reader = TCSPCSimulatorSetup(
        experiment=Experiment(name="TCSPC"),
        n_tac=128,
        instrument_response_function=irf,
        record_provenance=False,
        add_noise=False,
    )
    group = reader.get_data()
    project = capture_session([group], [])
    restored = restore_session(project)
    active_irf = restored.datasets[0][0].data_reader.instrument_response_function
    assert active_irf is not None
    assert active_irf is not irf
    np.testing.assert_array_equal(active_irf.x, irf.x)
    np.testing.assert_array_equal(active_irf.y, irf.y)
    assert capture_session(restored.datasets, []).datasets == project.datasets


def test_configured_sdt_reader_restores_without_constructing_a_widget(qtbot, monkeypatch):
    """The shipped SDT widget yields a portable headless scientific reader."""
    from chisurf.gui.widgets.experiments.tcspc.bh_sdt import TCSPCSetupSDTWidget

    reader = TCSPCSetupSDTWidget(experiment=Experiment(name="SDT"), record_provenance=False)
    qtbot.addWidget(reader)
    group = reader.get_data(filename="test/data/tcspc/BH_SDT/140507p.sdt")
    assert len(group) > 0
    project = capture_session([group], [])

    def forbidden(*args, **kwargs):
        raise AssertionError("constructing legacy reader UI during restoration")

    monkeypatch.setattr(TCSPCSetupSDTWidget, "__init__", forbidden)
    restored = restore_session(project)
    assert restored.datasets[0][0].data_reader.__class__.__module__.startswith("chisurf.core.")
    assert capture_session(restored.datasets, []).datasets == project.datasets


def test_configured_headless_reader_catalog_has_curated_roundtrip():
    """Every other configured scientific reader has an explicit field adapter."""
    import importlib
    from pathlib import Path

    import yaml

    from chisurf.core.project.session import _reader_state, _restore_reader

    config = yaml.safe_load(Path("chisurf/core/settings/experiment_configs.yaml").read_text())
    classes = {
        entry["reader_class"]: entry.get("reader_params", {})
        for section in config.values()
        if isinstance(section, dict)
        for entry in section.get("readers", [])
    }
    for path, params in sorted(classes.items()):
        if path.startswith("chisurf.gui."):
            continue  # The actual SDT measurement is exercised separately above.
        module, name = path.rsplit(".", 1)
        cls = getattr(importlib.import_module(module), name)
        experiment = Experiment(name="catalogued")
        reader = cls(experiment=experiment, record_provenance=False, **params)
        state = _reader_state(reader)
        restored = _restore_reader(state, experiment, {})
        assert _reader_state(restored) == state, path
