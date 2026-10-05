"""Scientific global membership and exact port ownership contracts."""

import numpy as np

from chisurf.core.fitting.fit import Fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.global_model.globalfit import GlobalFitModel
from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel
from chisurf.core.project.session import capture_session, restore_session
from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data


def _global():
    """Build duplicate-named real fits sharing an owned global rate port."""
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith("ParseStoppedFlowModel"))
    datasets = [_data(entry, ParseStoppedFlowModel) for _ in range(2)]
    sources = [
        Fit(data=data, model_class=ParseStoppedFlowModel, xmin=0, xmax=len(data.y))
        for data in datasets
    ]
    for source in sources:
        source.name = "duplicate-named member"
    entry = next(e for e in CATALOGUE if e["configured_path"].endswith("GlobalFitModel"))
    fit = Fit(data=_data(entry, GlobalFitModel), model_class=GlobalFitModel)
    fit.model.fits = sources
    shared = FittingParameter(name="shared rate", value=0.7, bounds=(0.1, 2.0), bounds_on=True)
    shared.error_estimate = 0.125
    fit.model.append_global_parameter(shared)
    for source in sources:
        # This shipped competing structure has a genuine exponential rate.
        source.model.structure = source.model.structure_options()[0][0]
        source.model.find_parameters()
        rate = source.model.parameters_all_dict["k1"]
        rate.link = shared
    fit.model.update()
    return fit, sources


def test_standalone_global_ports_are_owned_once_and_members_referenced():
    """Shared global ports and duplicate-named members survive exact restoration."""
    fit, members = _global()
    project = capture_session([f.data for f in [fit, *members]], [fit, *members])
    assert len(project.fits[0]["members"][0]["model"]["parameters"]) == 1
    restored = restore_session(project)
    global_model = restored.fits[0].model
    assert global_model.fits == restored.fits[1:]
    shared = global_model.global_parameters_all[0]
    assert shared.unique_identifier == fit.model.global_parameters_all[0].unique_identifier
    for member in global_model.fits:
        assert member.model.parameters_all_dict["k1"].link is shared
    assert capture_session(restored.datasets, restored.fits).fits == project.fits


def test_global_source_edit_reaches_both_member_predictions_and_resaves():
    """Changing the restored shared rate recomputes both scientific predictions."""
    fit, members = _global()
    restored = restore_session(capture_session([f.data for f in [fit, *members]], [fit, *members]))
    model = restored.fits[0].model
    before = [f.model.y.copy() for f in model.fits]
    shared = model.global_parameters_all[0]
    shared.value = 1.1
    model.update()
    for old, member in zip(before, model.fits):
        assert np.all(np.isfinite(member.model.y))
        assert np.any(member.model.y > 0)
        assert not np.allclose(old, member.model.y)
    second = capture_session(restored.datasets, restored.fits)
    again = restore_session(second)
    assert capture_session(again.datasets, again.fits).fits == second.fits


def test_shared_description_source_survives_window_rebuild_and_local_follower_bounds():
    """Linked scalar identity and fixed state remain effective across graph rebuilds."""
    fit, members = _global()
    restored = restore_session(capture_session([f.data for f in [fit, *members]], [fit, *members]))
    model = restored.fits[0].model
    shared = model.global_parameters_all[0]
    target = model.fits[0].model.parameters_all_dict["k1"]
    target.bounds = (0.6, 0.8)
    target.bounds_on = True
    fixed = target.fixed
    target.fixed = True
    model.fits[0].fit_range = (2, 60)
    shared.value = 1.5
    model.update()
    assert target.fixed
    assert target.link is shared and target.value == 1.5
    np.testing.assert_allclose(
        model.fits[0].model.y, np.exp(-model.fits[0].data.x * 1.5), rtol=1e-12
    )
    target.fixed = fixed
    updated = capture_session(restored.datasets, restored.fits)
    again = restore_session(updated)
    assert capture_session(again.datasets, again.fits).fits == updated.fits


def test_restored_shared_global_rate_can_be_refitted_and_resaved(monkeypatch):
    """An actual native joint objective optimises the same owned shared port."""
    import chisurf.core.settings

    fit, members = _global()
    restored = restore_session(capture_session([f.data for f in [fit, *members]], [fit, *members]))
    fit = restored.fits[0]
    for member in fit.model.fits:
        for parameter in member.model.parameters:
            parameter.fixed = True
    shared = fit.model.global_parameters_all[0]
    identity = (shared.unique_identifier, shared._port.get_uid())
    shared.value = 0.4
    fit.model.update()
    before = float(np.sum(fit.model.weighted_residuals**2))
    assert before > 0
    monkeypatch.setitem(chisurf.core.settings.cs_settings["optimization"]["leastsq"], "maxfev", 20)
    fit.run(record_result=False, estimate_errors=False, finalize=False, notify=False)
    assert float(np.sum(fit.model.weighted_residuals**2)) < before * 0.01
    assert (shared.unique_identifier, shared._port.get_uid()) == identity
    assert abs(shared.value - 1.0) < 0.01
    project = capture_session(restored.datasets, restored.fits)
    again = restore_session(project)
    assert capture_session(again.datasets, again.fits).fits == project.fits
