"""The guided UI uses the same prerequisite and metric engine as scripts."""
import pytest


def test_guided_confirm_rejects_missing_setup_and_persists(tmp_path):
    from chisurf.plugins.core.acq.gui.guided_panel import GuidedPanelModel
    m = GuidedPanelModel(tmp_path / 'guide.json')
    assert m.workflow_kind == 'fret'
    assert not m.confirm_step()
    assert 'Setup name' in m.message
    m.input_0 = 'MT200 PIE'
    m.input_1 = '488/640; green=0 red=2; confirm physical filters separately'
    assert m.confirm_step()
    assert m.workflow.state['instrument_setup'].confirmed
    assert m.step_id == 'water_irf'
    assert m.quality_rows()[0]['status'] == 'not computable'
    assert m.save_workflow()
    n = GuidedPanelModel(tmp_path / 'guide.json')
    assert n.load_workflow()
    assert n.workflow.state['instrument_setup'].confirmed
    assert n.workflow.state['instrument_setup'].values['setup_name'] == 'MT200 PIE'


def test_guided_numeric_empty_is_not_an_invented_measurement(tmp_path):
    from chisurf.plugins.core.acq.gui.guided_panel import GuidedPanelModel
    m = GuidedPanelModel(tmp_path / 'guide.json')
    m.step_id = 'buffer_background'
    m.select_step()
    assert m.input_0 == ''
    assert m.apply_inputs()
    assert m.workflow.metrics('buffer_background')[0]['value'] is None
    m.input_0 = '2000'
    m.input_1 = '2'
    assert m.apply_inputs()
    row = m.quality_rows()[0]
    assert row['value'] == pytest.approx(1.)
    assert row['status'] == 'not configured'
    m.limit_min_0, m.limit_max_0 = '0', '0.5'
    assert m.apply_inputs()
    assert m.quality_rows()[0]['status'] == 'outside bounds'
