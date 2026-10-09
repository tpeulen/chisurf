"""Native helper imports and translations must remain independent of Qt."""

import os
import subprocess
import sys
from pathlib import Path


def test_native_helpers_do_not_load_qt():
    script = '''
import importlib.abc
import sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise RuntimeError('Qt import blocked: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.emtk import code_links, doc_links, help_guide, i18n, dataset_picker
from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
from chisurf.plugins.core.mmfdb_admin.gui.session import cached_token
assert not code_links._is_qt_active()
assert doc_links._loaded_qt_core() is None
assert 'chisurf.gui' not in sys.modules
'''
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ}, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_catalog_skips_unfinished_and_plural_translations(tmp_path):
    from chisurf.emtk.i18n import read_catalog

    catalog = tmp_path / "sample.ts"
    catalog.write_text('''<TS><context><name>tool</name>
<message><source>Save</source><translation>Speichern</translation></message>
<message><source>Cancel</source><translation type="unfinished">Abbrechen</translation></message>
<message numerus="yes"><source>Files</source><translation><numerusform>Dateien</numerusform></translation></message>
</context></TS>''')
    assert read_catalog(catalog) == {"tool": {"Save": "Speichern"}}


def test_catalog_language_switching():
    from emtk import i18n as toolkit_i18n
    from emtk import im
    from emtk.testing import RecordingPainter

    from chisurf.core.support import i18n as core_i18n
    from chisurf.emtk import i18n

    previous_locale = toolkit_i18n.get_locale()
    previous_backend = core_i18n._backend
    try:
        i18n.install("de")
        translations = {
            "en": "Save", "de": "Speichern", "fr": "Enregistrer",
            "es": "Guardar", "pt": "Guardar", "ru": "Сохранить",
        }
        for locale, expected in translations.items():
            i18n.set_locale(locale)
            assert toolkit_i18n.tr("Save") == expected
            assert core_i18n.tr("Save", context="MainWindow") == expected
            assert toolkit_i18n.tr("Uncatalogued source text") == "Uncatalogued source text"
            painter = RecordingPainter()
            with im.frame(painter, (0, 0, 200, 80)):
                im.text("Save")
            assert expected in painter.strings
    finally:
        toolkit_i18n.set_locale(previous_locale)
        core_i18n.set_translation_backend(previous_backend)


def test_shared_image_and_region_controls_use_all_six_locales():
    from emtk import i18n as toolkit_i18n

    from chisurf.emtk.i18n import install

    previous = toolkit_i18n.get_locale()
    try:
        install("en")
        expected = {
            "en": ("Analysis regions", "Remove region", "Colormap"),
            "de": ("Analyseregionen", "Region entfernen", "Farbskala"),
            "fr": ("Régions d’analyse", "Supprimer la région", "Palette de couleurs"),
            "es": ("Regiones de análisis", "Eliminar región", "Mapa de color"),
            "pt": ("Regiões de análise", "Remover região", "Mapa de cores"),
            "ru": ("Области анализа", "Удалить область", "Цветовая карта"),
        }
        for locale, labels in expected.items():
            toolkit_i18n.set_locale(locale)
            assert toolkit_i18n.tr("Analysis regions") == labels[0]
            assert toolkit_i18n.tr("Remove region") == labels[1]
            assert toolkit_i18n.tr("Colormap") == labels[2]
    finally:
        toolkit_i18n.set_locale(previous)


def test_native_document_launch_does_not_construct_qt(monkeypatch, tmp_path):
    from chisurf.emtk import doc_links
    from chisurf.plugins.core.help.gui import help_app

    path = tmp_path / "guide.md"
    path.write_text("# Guide")
    commands = []
    monkeypatch.setattr(help_app, "open_help_page", lambda *args, **kwargs: False)
    monkeypatch.setattr(doc_links, "_is_qt_active", lambda: False)
    monkeypatch.setattr(subprocess, "Popen", lambda command: commands.append(command))
    assert doc_links._open_document(path, "section")
    assert commands == [[sys.executable, "-m", "chisurf.emtk", "--plugin", "help", "--path", str(path), "--anchor", "section"]]


def test_dataset_filters_selection_and_local_resolution(tmp_path):
    from chisurf.emtk.dataset_picker import DatasetPicker

    opened = []
    calls = []
    local = tmp_path / "photons.ptu"

    class Client:
        def call(self, method, params):
            calls.append((method, params))
            if method == "mmfdb.datasets.browse":
                return {"total": 51, "datasets": [{"artifact_id": "raw-1", "artifact_kind": "raw_measurement", "data_format": "ptu", "original_filename": "photons.ptu"}]}
            if method == "mmfdb.datasets.open":
                return {"local_path": str(local)}
            raise AssertionError(method)

    picker = DatasetPicker(client=Client(), kinds=["raw_measurement"], formats=["ptu"], scope="mine", on_paths=opened.append)
    picker.query = "photons"
    picker.page = 1
    picker.is_open = True
    assert picker.refresh()
    assert calls[0] == ("mmfdb.datasets.browse", {"scope": "own", "query": "photons", "kinds": ["raw_measurement"], "formats": ["ptu"], "limit": 50, "offset": 50})
    assert picker.select("unknown") is None
    assert not picker.accept()
    selected = picker.select("raw-1")
    assert selected.label == "photons.ptu"
    assert picker.accept()
    assert opened == [[local]]
    assert selected.local_path == str(local)
    assert not picker.is_open


def test_dataset_errors_remain_visible():
    from chisurf.emtk.dataset_picker import DatasetPicker

    class Client:
        def call(self, *args):
            raise PermissionError("Please sign in")

    picker = DatasetPicker(client=Client())
    picker.is_open = True
    assert not picker.refresh()
    assert picker.is_open
    assert not picker.datasets
    assert picker.error == "Please sign in"


def test_dataset_open_does_not_wait_for_backend():
    import threading

    from chisurf.emtk.dataset_picker import DatasetPicker

    entered = threading.Event()
    release = threading.Event()

    class Client:
        def call(self, *args):
            entered.set()
            assert release.wait(5)
            return {"datasets": [], "total": 0}

    picker = DatasetPicker(client=Client())
    try:
        picker.open()
        assert entered.wait(2)
        assert picker.is_open
        assert picker._pending is not None
        assert not picker._pending.done()
    finally:
        release.set()
        picker._pending.result(timeout=5)


def test_cancelled_dataset_open_does_not_deliver_callback():
    from concurrent.futures import Future

    from chisurf.emtk.dataset_picker import DatasetPicker, DatasetSelection

    paths = []
    picker = DatasetPicker(on_paths=paths.append)
    picker.selection = DatasetSelection("raw-1", "raw_measurement", "ptu", "photons.ptu")
    picker._pending = Future()
    picker._pending_kind = "open"
    picker._pending.set_result("/tmp/photons.ptu")
    picker.close()
    picker._poll()
    assert not paths
    assert not picker.is_open


def test_dataset_picker_renders_controls_and_tooltips(monkeypatch):
    from emtk import im
    from emtk.testing import RecordingPainter

    from chisurf.emtk.dataset_picker import DatasetPicker

    picker = DatasetPicker(client=object(), formats=["ptu"])
    picker.is_open = True
    picker.datasets = [{"artifact_id": "raw-1", "artifact_kind": "raw_measurement", "original_filename": "photons.ptu", "data_format": "ptu"}]
    picker.total = 1
    tooltips = []
    monkeypatch.setattr(im, "set_item_tooltip", tooltips.append)
    painter = RecordingPainter()
    box = (0.0, 0.0, 1000.0, 700.0)
    with im.frame(painter, box):
        picker.render(box)
    assert picker._dialog.content_box is not None
    assert len(tooltips) >= 10
    assert any("dataset raw-1" in text for text in tooltips)
    assert any("previous page" in text for text in tooltips)


def test_guided_tour_waits_for_real_target_when_host_opted_in():
    from chisurf.emtk.help_guide import EmTkGuidedTour

    steps = [{"target": {"attr": "npars"}, "await": {"hint": "Edit parameters"}}, {"target": {"tab": "results"}}]
    tour = EmTkGuidedTour(steps, wait_for_controls=True)
    tour.start()
    tour.next()
    assert tour.step_idx == 0
    tour.notify_used("other_field")
    assert tour.awaiting
    tour.notify_used("npars")
    assert not tour.awaiting
    tour.next()
    assert tour.step_idx == 1
    assert tour._target_key(steps[1]["target"]) == "results"
    # Hosts which have not yet supplied on_used callbacks retain existing navigation.
    legacy = EmTkGuidedTour(steps)
    legacy.start()
    legacy.next()
    assert legacy.step_idx == 1


def test_dataset_picker_respects_embedded_and_remote_client_modes(monkeypatch):
    from chisurf.emtk import dataset_picker
    from chisurf.plugins.core.mmfdb_admin.gui import client, session

    modes = []
    class Client:
        host, cmd_port, pub_port = "127.0.0.1", 8765, 8766
        token = None
        def __init__(self, *, inprocess):
            modes.append(inprocess)
    monkeypatch.setattr(client, "MMFDBClient", Client)
    monkeypatch.setattr(session, "cached_token", lambda *args: "existing-session")
    monkeypatch.setattr(dataset_picker, "_SESSION_CLIENT", None)
    for mode in ("embedded", "remote"):
        monkeypatch.setattr(client, "client_config", lambda settings, selected=mode: {"mode": selected, "username": "existing-user"})
        dataset_picker.reset_session_client()
        connected = dataset_picker.session_client()
        assert connected.token == "existing-session"
    assert modes == [True, False]
