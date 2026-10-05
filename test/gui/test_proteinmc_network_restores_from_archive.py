"""The Distance Network plot draws from the restored model, not from disk.

A ``.cs.pto`` carries the starting structure and the labelling payload, so a
restored, not-yet-sampled ProteinMC model has everything the network needs.
The plot used to require a sampled ``proteinmc_structure`` (showing "No FPS
network data" after restore) and re-read the labelling JSON from its original
path, which a self-contained project must not need.
"""

from types import SimpleNamespace

from test.project.test_structure_snapshot_contracts import _configured_proteinmc


def _restored_without_sources(tmp_path):
    from chisurf.core.models.structure.proteinmc_model import ProteinMCModel

    model, pdb, labeling = _configured_proteinmc(tmp_path)
    state = model.get_state()
    restored = ProteinMCModel(fit=SimpleNamespace(data=model.fit.data, name="restored", plots=[]))
    restored.set_state(state)
    labeling.unlink()
    assert restored.proteinmc_structure is None and not restored.trajectory_frames
    return restored


def test_network_draws_restored_unsampled_model_without_source_files(qapp, qtbot, tmp_path):
    from chisurf.gui.plots.proteinMC import ProteinMCDistanceNetworkPlot

    restored = _restored_without_sources(tmp_path)
    plot = ProteinMCDistanceNetworkPlot(fit=SimpleNamespace(model=restored, name="fit"))
    qtbot.addWidget(plot)
    assert [edge["p1"] + "-" + edge["p2"] for edge in plot._network_edges] == ["47-86"]


def test_structure_view_shows_starting_structure_and_follows_reloads(
    qapp, qtbot, tmp_path, monkeypatch
):
    from qtpy import QtWidgets

    import chisurf.gui.plots.proteinMC as proteinMC_module
    from test.gui.test_proteinmc_structure_control_contract import _shifted_pdb

    events = []

    class RecordingView(QtWidgets.QWidget):
        def __init__(self, *args, **kwargs):
            super().__init__(args[0] if args else kwargs.get("parent"))

        def add_structure(self, structure, *, name=None, source_path=None):
            events.append(("add", structure))
            return f"obj{len(events)}"

        def remove_object(self, object_id):
            events.append(("remove", object_id))
            return True

        def set_representation(self, mode, *, object_id=None):
            pass

        def set_frames(self, frames, *, object_id=None, active_frame=None):
            pass

    monkeypatch.setattr(proteinMC_module, "ChimolView", RecordingView)
    restored = _restored_without_sources(tmp_path)
    plot = proteinMC_module.ProteinMCStructurePlot(fit=SimpleNamespace(model=restored, name="fit"))
    qtbot.addWidget(plot)
    assert events == [("add", restored.structure)]

    restored.load_starting_structure(str(_shifted_pdb(tmp_path, restored)))
    plot.update_all()
    assert events[1][0] == "remove"
    assert events[2] == ("add", restored.proteinmc_structure)
    plot.update_all()
    assert len(events) == 3
