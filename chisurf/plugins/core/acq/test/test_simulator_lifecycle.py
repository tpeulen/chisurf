"""Source selection owns the simulated instrument, with no real device access."""
import json
from types import SimpleNamespace


def test_default_source_is_complete_and_only_one_control(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        assert model.source_kind == 'simulator' and model.simulation_connected
        assert len(model.laser.state().heads) == 2
        assert model.shutters.get_parameter('reported_excitation') == 0
        assert model.laser.state().emission_blocked
        assert not model.enabled('disconnect_laser')
        assert not model.enabled('connect_scanner')
        view = json.dumps(app.sections)
        assert 'connect_instrument_simulator' not in view
        assert 'disconnect_instrument_simulator' not in view
    finally:
        app.close()


def test_source_transition_detaches_simulator_without_connecting_hardware(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live import devices
    monkeypatch.setattr(devices, 'open_device', lambda *_: (_ for _ in ()).throw(AssertionError('hardware opened')))
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        rig = model._instrument_sim
        model.source_kind = 'replay'
        assert model.source_changed()
        assert rig.shutters.closed and model.laser is None and model.shutters is None
        assert model.output_dir == tmp_path and model.device is None
        model.mode = 'image'
        model.source_kind = 'simulator'
        assert model.source_changed() and model.simulation_connected
        assert model.mode == 'image'
        model.source_kind = 'device'
        assert model.source_changed()
        assert model.device is None and model.laser is None and model.shutters is None
    finally:
        app.close()


def test_source_change_during_recording_is_rejected(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        rig = model._instrument_sim
        model.session = SimpleNamespace(running=True)
        model.source_kind = 'device'
        assert not model.source_changed()
        assert model.source_kind == 'simulator' and model._instrument_sim is rig
        assert not model.enabled('source_kind')
        model.session = None
    finally:
        app.close()


def test_simulator_refuses_real_connections_and_profile_hardware(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        monkeypatch.setattr(model, 'connect_scanner', lambda *_: (_ for _ in ()).throw(AssertionError('scanner opened')))
        monkeypatch.setattr(model, 'connect_shutters', lambda *_: (_ for _ in ()).throw(AssertionError('shutters opened')))
        assert not model.connect_device()
        from chisurf.plugins.core.acq.live import settings_file
        doc = settings_file.new_settings()
        doc['scanner'] = {'address': 'real', 'line_markers': {'start': 3, 'stop': 4, 'edge': 'falling'}}
        assert model.adopt_settings(doc, 'profile', [])
        assert model.simulation_connected and model.scanner is None
        assert 'SIMULATION ONLY' in model.settings_detail
        path = tmp_path / 'profile.json'
        settings_file.save(settings_file.new_settings(storage={
            'local_directory': str(tmp_path / 'real'), 'archive_directory': str(tmp_path / 'archive')
        }), path)
        assert model.load_settings_path(path)
        assert model.output_dir == tmp_path / 'simulator'
        assert model.archive_directory is None
    finally:
        app.close()


def test_restore_device_profile_does_not_connect_hardware(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        monkeypatch.setattr(model, 'settings_chosen', lambda: (_ for _ in ()).throw(AssertionError('hardware settings applied')))
        monkeypatch.setattr(model, 'connect_device', lambda: (_ for _ in ()).throw(AssertionError('hardware opened')))
        app.restore_settings({'source_kind': 'device', 'settings_address': 'profile:real'})
        assert model.source_kind == 'device' and model.device is None
        assert model.laser is None and model.shutters is None
        assert 'Choose Load' in model.settings_detail
    finally:
        app.close()


def test_real_profile_does_not_replace_simulated_clock_or_program(tmp_path):
    from pathlib import Path
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live import settings_file
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        profile = Path(__file__).resolve().parents[1] / 'profiles' / 'mt200_pie.json'
        doc = settings_file.load(profile)
        program = model.laser.capture()
        setup = model.setup_address, model.preset, model.settings_setup, model.sim_scheme
        assert model.adopt_settings(doc, 'real profile', [])
        assert model.laser.capture() == program
        assert model.laser_program == program and model.laser_applied
        assert (model.setup_address, model.preset, model.settings_setup, model.sim_scheme) == setup
        assert model.simulation_connected and model.scanner is None and model.device is None
    finally:
        app.close()


def test_image_and_point_simulation_obey_rig_and_preserve_markers(tmp_path):
    import numpy as np
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live.sources import PhotonBatch
    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    try:
        model.mode = 'image'
        sources = [model.make_image_source(), model._point_source(model._point_scanner())]
        for source in sources:
            assert source.rig is model._instrument_sim
            source.source.read = lambda timeout: PhotonBatch(
                np.arange(4, dtype=np.uint64), np.zeros(4, dtype=np.uint16),
                np.array([1, 0, 1, 2], dtype=np.int8),
                event=np.array([1, 0, 0, 1], dtype=np.int8))
            dark = source.read()
            assert dark.event.tolist() == [1, 1]
            model.laser.set_head(200, intensity_pct=100)
            model.laser.set_emission(True)
            model.set_shutter('Excitation', True)
            model.set_shutter('Green', True)
            model.set_shutter('Red', False)
            green = source.read()
            assert green.event.tolist() == [1, 0, 1]
            assert green.channel.tolist() == [1, 0, 2]
            model.set_shutter('Red', True)
            assert len(source.read().macro) == 4
            model.laser.set_emission(False)
    finally:
        app.close()


def test_leaving_simulator_restores_laser_backend_for_explicit_connect(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    model = RecordModel(output_dir=tmp_path)
    model.laser_kind = 'sepia'
    app = RecordApp(model)
    try:
        assert model.laser_kind == 'simulated'
        assert app.export_settings()['laser_kind'] == 'sepia'
        model.source_kind = 'device'
        assert model.source_changed() and model.laser_kind == 'sepia'
        calls = []
        class FakeLaser:
            is_open = False
            def open(self): self.is_open = True
            def close(self): self.is_open = False
            def capture(self): return {}
        monkeypatch.setattr(model, '_sepia_status', lambda fresh=False: (True, ''))
        monkeypatch.setattr(model, '_new_laser', lambda: (calls.append(model.laser_kind) or FakeLaser()))
        monkeypatch.setattr(model, '_laser_status', lambda: None)
        assert model.connect_laser()
        assert calls == ['sepia']
    finally:
        app.close()


def test_measurement_settings_never_offer_real_windows_in_simulation(tmp_path, monkeypatch):
    from pathlib import Path
    from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
    from chisurf.plugins.core.acq.live import settings_file
    model = RecordModel(output_dir=tmp_path)
    app = RecordApp(model)
    try:
        profile = Path(__file__).resolve().parents[1] / 'profiles' / 'mt200_pie.json'
        doc = settings_file.load(profile)
        doc['laser']['oscillator'] = model.laser.capture()['oscillator']
        assert doc['laser'].get('oscillator')
        monkeypatch.setattr(model, '_picked', lambda: ('photons', 'external.ptu'))
        monkeypatch.setattr(settings_file, 'from_address', lambda _: (doc, []))
        model.proposed_windows = {'stale': [0, 1]}
        assert model.use_measurement_settings()
        assert model.proposed_windows is None
        assert model.simulation_connected
    finally:
        app.close()
