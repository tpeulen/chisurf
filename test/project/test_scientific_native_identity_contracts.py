"""Detached native graphs contain only the restored scientific topology."""

from pathlib import Path

import numpy as np

from chisurf.core.project.session import capture_session, restore_session
from test.project.test_transform_snapshot_contracts import _transform


def test_restored_native_registry_has_only_current_transform_node_and_ports():
    """Constructor and superseded catalogue nodes must not survive detached routing."""
    fit = _transform()
    restored = restore_session(capture_session([fit.data], [fit]))
    node = restored.fits[0].model._model._node
    assert list(restored.native_session.get_nodes()) == [node.get_uid()]
    ports = {p.get_uid() for p in restored.native_session.get_ports()}
    expected = {p._port.get_uid() for p in restored.fits[0].model.parameters_all}
    expected.update(p.get_uid() for p in node.get_ports().values())
    assert ports == expected


def test_output_dependencies_recompute_before_consumer_in_reversed_fit_order():
    """Archive fit ordering cannot leave a consumer using an unevaluated output."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
    from test.gui.test_pda2c_model_editor import _make_pda_data

    source = _transform()
    consumer = Fit(data=_make_pda_data(nmax=24), model_class=Pda2cSimpleModel)
    consumer.model.pch0._pch0[0].link = source.model.parameters_all_dict["p0"]
    consumer.model.update()
    expected = consumer.model.y.copy()
    project = capture_session([consumer.data, source.data], [consumer, source])
    restored = restore_session(project)
    np.testing.assert_allclose(restored.fits[0].model.y, expected, rtol=1e-12, atol=1e-12)
    assert capture_session(restored.datasets, restored.fits).fits == project.fits


def test_atom_backed_fret_distribution_input_ports_keep_exact_native_uids(tmp_path):
    """Owned array-valued structure inputs retain identities as well as their values."""
    from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.tcspc.fret_structure import FRETStructure

    data = TCSPCSimulatorSetup(
        n_tac=128, dt=0.1, add_noise=False, seed=47, record_provenance=False
    ).get_data()[0]
    fit = Fit(data=data, model_class=FRETStructure, xmin=45, xmax=len(data.y))
    pdb = tmp_path / "148l.pdb"
    pdb.write_bytes(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes())
    fit.model.res_1, fit.model.res_2 = 47, 86
    fit.model.load_structures([str(pdb)])
    fit.model.update()
    original = {name: fit.model._value_ports[name].get_uid() for name in fit.model._bound_ports}
    assert original
    project = capture_session([data], [fit])
    pdb.unlink()
    restored = restore_session(project).fits[0].model
    assert {
        name: restored._value_ports[name].get_uid() for name in restored._bound_ports
    } == original
    restored.linker_length_1 = 14.0
    restored.recompute_structures()
    assert {
        name: restored._value_ports[name].get_uid() for name in restored._bound_ports
    } == original
