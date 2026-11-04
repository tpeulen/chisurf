"""Setup-reference QC must not be confused with burst/acquisition QC."""
from datetime import date
import pytest


def test_missing_reference_measurements_are_visible_not_green(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    m=RecordModel(output_dir=tmp_path);qc=SetupQualityModel(m)
    rows=qc.quality_rows()
    assert {r['dye'] for r in rows}>={'Rh110','Alexa647'}
    assert all(r['status']=='missing' for r in rows)
    assert all(r['value']=='—' for r in rows)
    m.close()


def test_reference_fits_are_stored_and_compared_only_at_matching_conditions(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    m=RecordModel(output_dir=tmp_path);qc=SetupQualityModel(m)
    qc.dye='Rh110';qc.lifetime_ns='4.1';qc.diffusion_ms='.4';qc.brightness_khz='20'
    qc.laser_nm='488';qc.power_uw='5';qc.optics='test optics';qc.detector='green0'
    qc.excitation='cw';qc.file='fitted_reference.ptu';qc.fit_notes='External fit; background corrected.'
    assert qc.save_reference(),qc.message
    records=qc.history.records();assert len(records)==1
    assert records[0]['provenance']['lifetime_ns']==pytest.approx(4.1)
    assert records[0]['provenance']['timestamp_kind'] == 'entry_time'
    assert records[0]['provenance']['measurement_time'] is None
    assert records[0]['power_verified'] is False
    rows=[r for r in qc.quality_rows() if r['dye']=='Rh110']
    assert len(rows)==3
    assert all(r['status'] not in ('pass','within reference') for r in rows)
    assert any(r['metric']=='Diffusion time' and r['value']==pytest.approx(.4) for r in rows)
    assert date.today().isoformat() in records[0]['timestamp_utc']
    m.close()


def test_setup_quality_is_reachable_in_record_app(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    model=RecordModel(output_dir=tmp_path)
    model.ui_mode='advanced'; model.ui_mode_changed()
    app=RecordApp(model)
    try:
        ui=Driver(app,(1500,950));app.focus_dock('setup_quality');ui.draw(3)
        assert 'setup_quality_rows' in app.item_rects
        assert any('Rh110' in text for text in ui.strings())
        assert any('Alexa647' in text for text in ui.strings())
        assert any('SIMULATION ONLY' in text for text in ui.strings())
        assert any('entry time' in text for text in ui.strings())
    finally:app.close()


def test_quality_rows_cache_and_external_change_invalidation(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    from chisurf.plugins.core.acq.live.reference_history import ReferenceHistory
    m = RecordModel(output_dir=tmp_path)
    qc = SetupQualityModel(m)
    calls = []
    original = ReferenceHistory.records
    def counted(history):
        calls.append(1)
        return original(history)
    monkeypatch.setattr(ReferenceHistory, 'records', counted)
    assert qc.quality_rows()[0]['status'] == 'missing'
    qc.quality_rows()
    assert len(calls) == 1
    qc.lifetime_ns, qc.diffusion_ms, qc.brightness_khz = '4.1', '.4', '20'
    qc.laser_nm, qc.power_uw, qc.optics, qc.detector = '488', '5', 'optics', 'green0'
    assert qc.save_reference(), qc.message
    assert qc.quality_rows()[0]['status'] != 'missing'
    assert len(calls) == 2
    # Atomic replacement by an independent writer must invalidate the cached rows.
    external = qc.history
    record = original(external)[0]
    fields = {key: value for key, value in record.items()
              if key not in ('uid', 'stored_at_utc', 'key')}
    fields['dye'] = 'Alexa647'
    external.add(**fields)
    assert qc.quality_rows()[3]['status'] != 'missing'
    assert len(calls) == 3
    m.close()


def test_verified_bounds_produce_per_metric_verdicts_only(tmp_path):
    from datetime import datetime, timezone
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    m = RecordModel(output_dir=tmp_path)
    qc = SetupQualityModel(m)
    history = qc.history
    record = history.add(timestamp_utc=datetime.now(timezone.utc), dye='Rh110',
                         laser_nm=488., power_uw=5., power_verified=True,
                         excitation_mode='cw', optical_configuration='optics', detector='green0',
                         tau_diff_s=.0004, brightness_cps=20000.,
                         provenance={'lifetime_ns': 4.1})
    history.set_bounds(record, {'tau_diff_s': {'max': .0003}})
    rows = {row['metric']: row['status'] for row in qc.quality_rows() if row['dye'] == 'Rh110'}
    assert rows == {'Lifetime': 'no_verdict', 'Diffusion time': 'recommend_inspection',
                    'Brightness': 'no_bounds'}
    history.set_bounds(record, {'tau_diff_s': {'max': .0003},
                                'brightness_cps': {'min': 10000., 'max': 30000.}})
    rows = {row['metric']: row['status'] for row in qc.quality_rows() if row['dye'] == 'Rh110'}
    assert rows == {'Lifetime': 'no_verdict', 'Diffusion time': 'recommend_inspection',
                    'Brightness': 'within_reference'}
    m.close()


def test_history_follows_output_directory_and_separates_simulation(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    m = RecordModel(output_dir=tmp_path)
    qc = SetupQualityModel(m)
    qc.lifetime_ns, qc.diffusion_ms, qc.brightness_khz = '4.1', '.4', '20'
    qc.laser_nm, qc.power_uw, qc.optics, qc.detector = '488', '5', 'optics', 'green0'
    m.output_dir = tmp_path / 'simulator'
    assert qc.save_reference(), qc.message
    assert len(qc.history.records()) == 1
    m.output_dir = tmp_path
    assert qc.history.records() == []
    assert not (tmp_path / 'setup-reference-history.json').exists()
    m.close()


def test_settings_storage_cannot_mix_simulated_and_real_references(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel
    from chisurf.plugins.core.acq.live import settings_file
    real_dir = tmp_path / 'real'
    real_dir.mkdir()
    path = tmp_path / 'settings.json'
    settings_file.save(settings_file.new_settings(storage={
        'local_directory': str(real_dir), 'archive_directory': str(tmp_path / 'archive')
    }), path)
    m = RecordModel(output_dir=tmp_path / 'initial')
    qc = SetupQualityModel(m)
    qc.lifetime_ns, qc.diffusion_ms, qc.brightness_khz = '4.1', '.4', '20'
    qc.laser_nm, qc.power_uw, qc.optics, qc.detector = '488', '5', 'optics', 'green0'
    assert m.load_settings_path(path)
    assert m.output_dir == real_dir
    # The default photon simulator has no connected simulated rig.
    assert m.source_kind == 'simulator' and not m.simulation_connected
    assert qc.save_reference(), qc.message
    assert (real_dir / 'setup-reference-history-simulation.json').exists()
    m.source_kind = 'device'
    assert qc.history.records() == []
    assert not (real_dir / 'setup-reference-history.json').exists()
    # A still-attached simulated rig remains simulated even if source selection changes.
    monkeypatch.setattr(RecordModel, 'simulation_connected', property(lambda self: True))
    assert len(qc.history.records()) == 1
    monkeypatch.undo()
    m.close()


def test_setup_quality_is_hidden_outside_advanced_mode(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        ui = Driver(app, (1500, 950))
        app.focus_dock('setup_quality'); ui.draw(3)
        assert 'setup_quality_rows' not in app.item_rects
        model.ui_mode = 'advanced'; model.ui_mode_changed()
        app.focus_dock('setup_quality'); ui.draw(3)
        assert 'setup_quality_rows' in app.item_rects
        model.ui_mode = 'simple'; model.ui_mode_changed(); ui.draw(3)
        assert 'setup_quality_rows' not in app.item_rects
    finally:
        app.close()
