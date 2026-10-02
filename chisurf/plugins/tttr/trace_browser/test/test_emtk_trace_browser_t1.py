"""The native Trace Browser, card T1: the Setup page, Continue, Back and what is remembered.

Hermetic: the autouse fixture in ``conftest.py`` redirects the settings folder, the MMFDB and the
setups file to a temporary folder, and the setups these tests offer come from a temporary JSON file,
so nothing is read from or written to the user's real settings.
"""

import contextlib
import json
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX, OVERLAP  # noqa: E402

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
ENTRY = "chisurf.plugins.tttr.trace_browser.gui.app:make_app"

@pytest.fixture
def setups_file(tmp_path):
    """A setups JSON with two saved setups, ``last_used`` = ALEX Suite (auto)."""
    path = tmp_path / "detector_setups.json"
    path.write_text(
        json.dumps({"setups": {"ALEX Suite (auto)": ALEX, "Overlap": OVERLAP},
                    "last_used": "ALEX Suite (auto)"})
    )
    return path


def make(setups_file=None):
    """The app on its Setup page (card T2: with a saved setup it opens on the Browser page)."""
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp(setups_file=setups_file)
    app.back_to_setup()
    # undo what the start-up Continue accepted, so these tests drive Continue themselves
    app.model.setup_settings = app.model.setup_filetype = app.model.selected_channels = None
    return app


def frames(app, size=(1200, 800), n=3):
    """Draw *n* frames; return the strings of the last one."""
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter.strings


@contextlib.contextmanager
def pressing(monkeypatch, label):
    """Make the next button *label* report a click (the real button path).

    Patches ``im.button`` (hand-drawn buttons) and ``emtk.im_widgets.button`` (the buttons of a
    view spec, whose label carries a ``##action`` id).
    """
    from emtk import im, im_widgets

    fired = []

    def wrap(real):
        def button(text, *args, **kwargs):
            result = real(text, *args, **kwargs)
            if str(text).split("##")[0] == label and not fired:
                fired.append(text)
                return True
            return result

        return button

    originals = (im.button, im_widgets.button)
    monkeypatch.setattr(im, "button", wrap(originals[0]))
    monkeypatch.setattr(im_widgets, "button", wrap(originals[1]))
    yield fired
    monkeypatch.setattr(im, "button", originals[0])
    monkeypatch.setattr(im_widgets, "button", originals[1])
    assert fired, f"no button {label!r} was drawn"


# 1. the model keys the Setup page uses exist (the Setup page is the shared editor, no spec;
#    the Browser page's spec has its own key test in the T2 file)
def test_model_has_every_key_the_app_uses():
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    for name in ("page", "setup_settings", "setup_filetype", "selected_channels"):
        assert hasattr(model, name), name
    for name in ("accept_setup", "back_to_setup", "apply_setup", "filetype_of", "build_channel_labels"):
        assert callable(getattr(model, name)), name
    assert model.page == "setup"


# 2. the app draws the Setup page, empty and with a setup selected, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_setup_page_draws_empty_and_with_a_setup(size, setups_file, tmp_path):
    empty = make(tmp_path / "no_such_setups.json")
    try:
        text = " | ".join(frames(empty, size))
        assert empty.model.page == "setup"
        assert "Continue" in text and "Setup definition" in text and "Setup:" in text and "TTTR Reading routine" in text
        assert "ALEX Suite (auto)" not in text      # nothing invented when none is saved
        assert empty.editor.model.get_settings()["detectors"] == {}
    finally:
        empty.close()
    app = make(setups_file)
    try:
        text = " | ".join(frames(app, size))
        # the last used saved setup is selected, as in the Qt setup page
        assert app.editor.model.current_name == "ALEX Suite (auto)"
        assert text.count("ALEX Suite (auto)") >= 1          # the Setup drop-down shows it
        assert "Continue" in text
        assert app.editor.model.get_settings()["detectors"]["green"]["chs"] == [1]
    finally:
        app.close()


# 3. Continue applies the setup to the model and switches the page; Back returns
def test_continue_applies_the_setup_and_back_returns(setups_file, monkeypatch):
    app = make(setups_file)
    try:
        frames(app)
        model = app.model
        assert model.setup_settings is None and model.selected_channels is None
        with pressing(monkeypatch, "Continue"):
            frames(app, n=1)
        assert model.page == "browser"
        assert model.selected_channels == [0, 1]
        assert model.setup_filetype == "PTO"
        assert model.setup_settings["detectors"]["red"]["chs"] == [0]
        assert model.setup_settings["setup_name"] == "ALEX Suite (auto)"
        browser = " | ".join(frames(app))
        assert "Select a file to write an annotation" in browser and "Files" in browser   # the Browser page (card T2)
        assert "Continue" not in browser            # the setup page is not drawn
        accepted = model.setup_settings
        with pressing(monkeypatch, "← Select setup"):
            frames(app, n=1)
        assert model.page == "setup"
        assert model.setup_settings is accepted      # Back keeps the accepted setup
        assert "Continue" in " | ".join(frames(app))
        assert app.editor.model.current_name == "ALEX Suite (auto)"   # editor keeps its state
    finally:
        app.close()


def test_continue_without_a_setup_auto_detects_channels(tmp_path):
    app = make(tmp_path / "none.json")
    try:
        app.continue_to_browser()
        assert app.model.page == "browser"
        assert app.model.selected_channels is None     # the model then reads them from the files
        assert app.model.setup_filetype is None
        text = " | ".join(frames(app))
        assert "Select a file to write an annotation" in text and "No folder selected" in text
    finally:
        app.close()


# 4. selected_channels and the labels: the Qt widget and the emtk app agree
@pytest.mark.parametrize("setup, expected", [(ALEX, [0, 1]), (OVERLAP, [0, 1, 2, 3, 8, 9])])
def test_qt_widget_and_emtk_app_derive_the_same_channels(qapp, qtbot, setup, expected, tmp_path):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.tttr.trace_browser import TraceBrowser

    widget = TraceBrowser()
    qtbot.addWidget(widget)
    widget.detector_page._load_data(json.loads(json.dumps(setup)))
    widget._on_continue()

    path = tmp_path / "setups.json"
    path.write_text(json.dumps({"setups": {setup["setup_name"]: setup},
                                "last_used": setup["setup_name"]}))
    app = make(path)
    try:
        assert app.editor.model.current_name == setup["setup_name"]
        app.continue_to_browser()
        assert widget.selected_channels == expected
        assert app.model.selected_channels == widget.selected_channels
        assert app.model.setup_filetype == widget._setup_filetype()
        every = sorted({c for d in setup["detectors"].values() for c in d["chs"]}) + [5]
        assert app.model.build_channel_labels(every) == widget._build_channel_labels(every)
        assert widget._build_channel_labels(every)[-1] == "5"      # an unnamed channel
    finally:
        app.close()


def test_auto_file_type_means_every_supported_extension():
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    assert model.filetype_of({"tttr_reading": {"file_type": "auto"}}) is None
    assert model.filetype_of({"tttr_reading": {"file_type": "Auto"}}) is None
    assert model.filetype_of({}) is None and model.filetype_of(None) is None
    assert model.filetype_of({"tttr_reading": {"file_type": "PTU"}}) == "PTU"
    model.accept_setup(OVERLAP)
    assert model.setup_filetype is None and model.page == "browser"
    assert ".ptu" in model.allowed_exts() and ".spc" in model.allowed_exts()
    model.accept_setup(ALEX)
    assert model.setup_filetype == "PTO"


# 5. no Qt, no chisurf.gui
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("trace_browser", ENTRY)
    assert result["ok"], result["output"]


# 6. every control has a tooltip, on both pages
def test_every_control_has_a_tooltip(setups_file):
    from test.gui.emtk_port_parity import emtk_inventory

    app = make(setups_file)
    try:
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        labels = {row["label"] for row in inv["interactive"]}
        assert {"Continue", "Save", "Rename", "Delete", "Read", "Optical Setup..."} <= labels
        app.continue_to_browser()
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        assert {"← Select setup", "Open", "Clear", "Clear caches"} <= {
            row["label"] for row in inv["interactive"]
        }
    finally:
        app.close()


# 7. persistence
def test_settings_round_trip(setups_file, tmp_path):
    app = make(setups_file)
    try:
        app.editor.select_setup("Overlap")
        app.editor.model.data["detectors"]["red"]["chs"] = [9, 1]     # an edit of the working setup
        saved = app.export_settings()
    finally:
        app.close()
    saved = json.loads(json.dumps(saved))                      # it must survive JSON
    assert saved["setup_name"] == "Overlap" and saved["setups_file"] == str(setups_file)

    other = make(None)                                          # a fresh app, no setups file
    try:
        assert other.editor.model.get_settings()["detectors"] == {}
        other.restore_settings(saved)
        assert other.setups_file == str(setups_file)
        assert other.editor.model.current_name == "Overlap"
        assert other.editor.model.get_settings()["detectors"]["red"]["chs"] == [9, 1]
        assert sorted(other.editor.model.setups) == ["ALEX Suite (auto)", "Overlap"]
        other.continue_to_browser()
        assert other.model.selected_channels == [0, 1, 2, 3, 8, 9]
        assert other.export_settings()["setup"]["detectors"]["red"]["chs"] == [9, 1]
    finally:
        other.close()

    # only the file remembered: the last used saved setup is selected again
    third = make(None)
    try:
        third.restore_settings({"setups_file": str(setups_file)})
        assert third.editor.model.current_name == "ALEX Suite (auto)"
        third.restore_settings({})                              # nothing remembered: empty, no error
        assert third.editor.model.get_settings()["detectors"] == {}
    finally:
        third.close()
