"""PTO workflows on real instrument data without a Qt host."""
import numpy as np
import pytest

from chisurf.core.fio.pto import Measurement
from chisurf.plugins.core.pto_inspector.gui.app import PtoInspectorApp
from chisurf.plugins.core.pto_inspector.test.test_core import container as source_container


@pytest.fixture
def container(tmp_path):
    return source_container.__wrapped__(tmp_path)

def test_selection_payload_units_and_export(container, tmp_path):
    app = PtoInspectorApp()
    app.on_paths_dropped([container])
    assert app.model.selected.name == 'fcs'
    assert len(app.model.curve_series()[0]['x']) == 64
    assert app.model.curve_axes()['log_x']
    assert 'ms' in app.model.curve_axes()['x_label']
    item = next(i for i in app.model.inspection.infos() if i.name == 'lifetimes')
    app.model.select_uid(item.uid)
    assert app.artifacts.control.selected_key == item.uid
    app.refresh_payload()
    np.testing.assert_allclose(app.payload['tau'], np.linspace(1, 4, 32))
    assert app.payload_columns[1]['title'] == 'tau [nanoseconds]'
    assert len(app.graph.document.edges) >= 2
    # Selecting an artifact never resets graph zoom.
    app.graph.editor.canvas.zoom = 1.7
    app.model.select_uid(next(i for i in app.model.inspection.infos() if i.name == 'bursts').uid)
    assert app.graph.editor.canvas.zoom == 1.7
    output = tmp_path / 'bursts.csv'
    app.export_payload(output)
    assert 'First Photon' in output.read_text()
    raw = next(i for i in app.model.inspection.infos() if i.kind == 'tttr_photon_stream')
    app.model.select_uid(raw.uid)
    output = tmp_path / 'raw.ptu'
    app.export_payload(output)
    assert output.read_bytes() == app.model.inspection.measurement.get_blob(raw.uid)
    app.verify()
    assert 'matches' in app.notice
    app.close()


def test_state_reload_and_invalid_file(container, tmp_path):
    app = PtoInspectorApp()
    app.model.set_filename(str(container))
    app.artifacts.control.filter.set_text('burst')
    saved = app.export_settings()
    other = PtoInspectorApp()
    other.restore_settings(saved)
    assert other.model.selected_uid == app.model.selected_uid
    assert other.artifacts.control.filter.text == 'burst'
    other.close()
    app.model.close()
    with Measurement.open(container, writable=True) as measurement:
        measurement.put_table('new table', {'value': np.array([2., 4.])}, artifact_kind='analysis_result', operation_type='fcs_correlation', row_grain='curve_point')
    app.model.reload()
    assert app.model.selected.name == 'new table'
    app.refresh_payload()
    np.testing.assert_allclose(app.payload['value'], [2, 4])
    invalid = tmp_path / 'invalid.pto'
    invalid.write_bytes(b'bad')
    app.model.set_filename(str(invalid))
    assert app.model.inspection is None
    assert 'Cannot open' in app.model.status
    app.close()


def test_native_tool_launch_handoff_and_unported_notice(container):
    from types import SimpleNamespace

    from chisurf.plugins.core.pto_inspector.gui.view_model import PtoInspectorViewModel
    model = PtoInspectorViewModel()
    model.set_filename(str(container))
    calls = []
    child = SimpleNamespace(model=SimpleNamespace(set_filename=lambda p: calls.append(p)), close=lambda: calls.append('closed'))
    app = PtoInspectorApp(model, tool_loader=lambda plugin_id: child)
    app.tools = [SimpleNamespace(id='test', entrypoints=SimpleNamespace(emtk='test:make_app'))]
    assert app.open_tool() is child
    assert calls == [str(container)]
    app.tools = [SimpleNamespace(id='legacy', entrypoints=SimpleNamespace(emtk=None))]
    assert app.open_tool() is None
    assert 'not been ported' in app.notice
    app.close()
    assert calls[-1] == 'closed'


def test_populated_native_drawing(container, caplog):
    from emtk.testing import RecordingPainter
    app = PtoInspectorApp()
    app.model.set_filename(str(container))
    for size in [(1200, 800), (800, 600)]:
        painter = RecordingPainter()
        for _ in range(3):
            app.draw(painter, 0, 0, *size)
        assert any('fcs' in text for text in painter.strings)
    assert not [r for r in caplog.records if r.levelname == 'ERROR']
    app.close()


def test_all_existing_locales():
    from emtk import i18n

    from chisurf.plugins.core.pto_inspector.gui.translations import install, tr
    install()
    original = i18n.get_locale()
    try:
        for locale in ['de', 'fr', 'es', 'pt', 'ru']:
            i18n.set_locale(locale)
            assert tr('Open') != 'Open'
            assert tr('Check every stored checksum.') != 'Check every stored checksum.'
    finally:
        i18n.set_locale(original)


def test_damaged_payload_is_reported(container):
    with Measurement.open(container) as measurement:
        raw = next(obj for obj in measurement.artifacts() if obj.kind == 'tttr_photon_stream')
        offset = raw.offset
    with open(container, 'r+b') as file:
        file.seek(offset + 128)
        original = file.read(1)
        file.seek(offset + 128)
        file.write(bytes([original[0] ^ 1]))
    app = PtoInspectorApp()
    app.model.set_filename(str(container))
    app.verify()
    assert 'mismatch' in app.notice.lower()
    assert app.model._verify
    app.close()


def test_vendor_pack_preserves_sources_and_refuses_overwrite(tmp_path):
    import shutil

    from chisurf.plugins.core.pto_inspector.test.test_core import PTU
    raw = tmp_path / 'raw.ptu'
    shutil.copy(PTU, raw)
    app = PtoInspectorApp()
    app.on_paths_dropped([raw])
    assert app.vendor_paths == [raw]
    target_dir = tmp_path / 'containers'
    app.pack_vendor_files(target_dir)
    assert app.model.inspection.verify() == []
    assert app.model.filename == str(target_dir / 'raw.pto')
    assert raw.exists()
    with pytest.raises(FileExistsError):
        app.on_paths_dropped([raw])
        app.pack_vendor_files(target_dir)
    assert app.model.inspection.verify() == []
    app.close()


def test_database_container_selection_opens_resolved_path(container, monkeypatch):
    import chisurf.plugins.core.pto_inspector.gui.app as module
    calls = []

    class Picker:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def open(self):
            calls[0]['on_paths']([container])

    monkeypatch.setattr(module, 'DatasetPicker', Picker)
    monkeypatch.setattr(module, 'session_client', lambda: 'authenticated client')
    app = PtoInspectorApp()
    app.open_database()
    assert calls[0]['client'] == 'authenticated client'
    assert calls[0]['formats'] == ['pto']
    assert app.model.filename == str(container)
    app.close()
