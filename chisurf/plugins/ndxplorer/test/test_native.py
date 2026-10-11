from __future__ import annotations

import numpy as np
from emtk.testing import RecordingPainter


def test_native_ndx_factory_draws_without_qt_and_registers_session_source(tmp_path, monkeypatch):
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "chisurf"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "chisurf"))
    from chisurf.emtk.session_sources import sources
    from chisurf.plugins.ndxplorer.gui.app import make_app

    app = make_app()
    app.draw(RecordingPainter(), 0.0, 0.0, 1000.0, 700.0)
    adapter = app._chisurf_native_source
    assert adapter in sources("ndx")
    assert app.window_title == "ndX"
    assert app.panel.available("open_text")

    def menu_items(entries):
        from emtk.widgets.menus import Menu

        for entry in entries:
            if isinstance(entry, Menu):
                yield from menu_items(entry.entries)
            elif entry is not None:
                yield entry

    mmfdb = next(
        item
        for menu in app.menubar.menus
        for item in menu_items(menu.entries)
        if getattr(item, "action", None) == "open_from_mmfdb"
    )
    assert "authenticated MMFDB" in mmfdb.tooltip
    app.close()
    assert adapter not in sources("ndx")


def test_native_ndx_source_shares_columns_and_accurate_fret_updates(tmp_path, monkeypatch):
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "chisurf"))
    from ndxplorer.core.data_source import DataSource

    from chisurf.core.fluorescence.fret.calibration import CalibrationParameters
    from chisurf.plugins.ndxplorer.gui.app import make_app

    app = make_app()
    app.model.set_source(
        DataSource.from_columns({"I_DD": [10, 20], "I_DA": [4, 8], "I_AA": [7, 9]})
    )
    source = app._chisurf_native_source
    columns = source.get_burst_columns()
    np.testing.assert_array_equal(columns["I_DD"], [10, 20])
    np.testing.assert_array_equal(columns["I_DA"], [4, 8])

    calibration = CalibrationParameters()
    calibration.gamma = 2.0
    calibration.alpha = 0.2
    calibration.beta = 1.5
    calibration.delta = 0.1
    source.apply_fret_calibration(calibration)
    assert app.model.manager.constants["gG/gR"] == 0.5
    assert app.model.manager.constants["alpha"] == 0.2
    assert app.model.stale
    app.close()


def test_native_mmfdb_picker_opens_the_selected_burst_table(tmp_path, monkeypatch):
    monkeypatch.setenv("NDXPLORER_SETTINGS_DIR", str(tmp_path / "ndxplorer"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "chisurf"))
    from chisurf.emtk import dataset_picker
    from chisurf.plugins.ndxplorer.gui.app import make_app

    path = tmp_path / "bursts.csv"
    path.write_text("I_DD,I_DA,I_AA\n10,4,7\n20,8,9\n")
    client = object()
    opened = {}

    class Picker:
        def __init__(self, **kwargs):
            opened.update(kwargs)
            self.is_open = False

        def open(self):
            self.is_open = True

        def render(self, _box):
            pass

        def close(self):
            self.is_open = False

    monkeypatch.setattr(dataset_picker, "session_client", lambda: client)
    monkeypatch.setattr(dataset_picker, "DatasetPicker", Picker)
    app = make_app()
    feature = next(feature for feature in app.features if feature.name == "chisurf_mmfdb")
    feature.open_from_mmfdb()
    assert opened["client"] is client
    assert opened["on_paths"] == feature.open_paths
    opened["on_paths"]([path])
    assert app.model.has_data
    assert app.model.source.size == 2
    app.close()
    assert not feature.picker.is_open


def test_radio_choices_in_one_dock_do_not_share_an_attribute_name():
    """The Playback *Mode* and the Draw Mask *Mode* radios drew the same item id (``mode0``).

    A radio's id is its section name (the ``attr``) plus the option index, and the part of a label
    after ``##`` is all that identifies an item. The disabled Playback radio, drawn first, let go of
    the press on the Draw radio, so no click on it ever registered (found by the click sweep once
    it stopped skipping *Load example*). Both live in the plot-control dock, so their ``attr``
    names must differ.
    """
    import json
    from pathlib import Path

    import ndxplorer

    root = Path(ndxplorer.__file__).parent

    def radio_attrs(path):
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "choice" and node.get("style") in ("radio", "radio_list"):
                    found.append(node.get("attr"))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(json.loads(path.read_text(encoding="utf-8")))
        return found

    playback = radio_attrs(root / "plotting" / "playback.view.json")
    draw_mask = radio_attrs(root / "app" / "features" / "selection" / "draw_mask.view.json")
    assert playback and draw_mask
    assert not set(playback) & set(draw_mask), (playback, draw_mask)
