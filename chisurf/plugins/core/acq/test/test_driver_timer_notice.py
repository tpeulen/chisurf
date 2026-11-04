def test_driver_advertised_limit_is_used_instead_of_stale_one_hour_text(tmp_path):
    from types import SimpleNamespace
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    m=RecordModel(output_dir=tmp_path)
    class Device:
        acquisition_limit_s=360000.
        def information(self):return SimpleNamespace(features=['pqusb','acq-limit-100h'],model='HydraHarp 400')
        def close(self):pass
    try:
        m.device=Device();m.source_kind='device'
        assert '100 h' in m.device_limit_text
        assert 'not unlimited' in m.device_limit_text
        assert '1 h,' not in m.device_limit_text
    finally:m.close()
