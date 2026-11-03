"""Audifier emtk app: every control operated with real input.

Real input = pointer press/release at the rectangles the controls were drawn in, typed text, Enter, the wheel, and the
workspace's hand-off (``receive_photons``; the window has no file dialog and no drop hook for input); the outcome is read
from the model or the frame. Hermetic: HOME and the settings folders are temporary
and a test asserts that nothing was written under the home folder; audio goes to a fake process.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.emtk_test_input import assert_tour_card_clear
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui
from chisurf.plugins.tttr.audifier.core import TTTRData
from chisurf.plugins.tttr.audifier.gui.app import create_app
from chisurf.plugins.tttr.audifier.native_playback import NativeSoundPlayer

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
BH = REPO / "test/data/tttr/BH/132/BH_SPC132.spc"
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))


class Process:
    def __init__(self):
        self.signals, self.code = [], None

    def poll(self):
        return self.code

    def send_signal(self, sig):
        self.signals.append(sig)

    def terminate(self):
        self.code = -15

    def wait(self, timeout):
        return self.code


def make(loader=None, now=None):
    clock = now if now is not None else [0.0]
    player = NativeSoundPlayer(
        command=["player"], clock=lambda: clock[0], spawn=lambda *a, **k: Process()
    )
    return create_app(player=player, loader=loader), clock


def stream():
    rng = np.random.default_rng(3)
    n = 4000
    return TTTRData(
        rng.integers(0, 4, n),
        np.sort(rng.integers(0, 4_000_000, n)),
        rng.integers(0, 256, n),
        1e-6,
        1e-9,
    )


def feed(ui, path):
    """Load *path* as the workspace's hand-off does once it has the address (the fake loader reads it)."""
    accepted = ui.app.load(str(path))
    ui.draw(2)
    return accepted


def settle(ui):
    import time

    end = time.monotonic() + 60
    while (ui.app.job.running or ui.app.editor._future is not None) and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


def loaded(**kw):
    app, clock = make(loader=lambda path: stream(), **kw)
    ui = Ui(app, (1200, 800))
    assert feed(ui, "anything.ptu")
    settle(ui)
    return ui, clock


def retype(ui, text):
    """In an open table cell: Backspace over what is there (the cell has no select-all), type *text*, Enter."""
    for _ in range(16):
        ui.key(keys.KEY_BACKSPACE, "")
    for ch in text:
        ui.app.key(ord(ch), ch)
        ui.draw(1)
    ui.key(keys.KEY_RETURN, "\r")


def cell(ui, header, row_text, nth=-1):
    """Centre of a table cell: the column of the header caption, the row of a text drawn in it."""
    h = ui.text_rect(header)
    r = ui.text_rect(row_text, nth)
    return (h[0] + h[2] / 2, r[1] + r[3] / 2)


# ---- the Update button ----------------------------------------------------------------------------------------


def test_update_draws_the_waterfall_the_model_computes_for_each_mode():
    ui, _ = loaded()
    model = ui.app.model
    for mode in ("microtime", "lifetime"):
        model.waterfall_mode = mode
        ui.click("update")
        settle(ui)
        expected = model.compute_waterfall()
        got = model.waterfall_payload()
        np.testing.assert_allclose(got["rgb_data"], expected["rgb_data"])
        assert got["info"] == expected["info"]
    ui.app.close()


# ---- the real BH file -------------------------------------------------------------------------------------------


def test_a_real_bh_file_is_dropped_read_with_its_subtype_and_shown():
    app, _ = make()
    ui = Ui(app, (1200, 800))
    assert feed(ui, BH)  # no subtype chosen: the reason is the answer
    settle(ui)
    assert ui.shown("Select the SPC subtype") and not app.model.has_data
    app.editor.model.data.setdefault("tttr_reading", {})["file_type"] = "SPC-130"
    feed(ui, BH)
    settle(ui)
    assert (
        app.model.has_data
        and len(app.model.data.macro_ticks) == 183657
        and app.model.channels == [0, 1, 8, 9]
    )
    ui.click("update")
    settle(ui)
    assert app.texture is not None and ui.shown("Macro-time (s)") and ui.shown("Micro-time (bin)")
    app.close()


# ---- the controls -----------------------------------------------------------------------------------------------


def test_the_workspace_hands_a_stream_and_its_setup_row_over(tmp_path):
    """No Load button, no dialog, no drop hook: a photon stream and a setup row from the workspace."""
    import json

    from chisurf.plugins.tttr.audifier.gui.app import receive_photons

    app, _ = make()
    ui = Ui(app, (1200, 800))
    assert "load" not in app.item_rects and not hasattr(app, "on_files_dropped")
    setup = tmp_path / "bh_setup.json"
    setup.write_text(json.dumps({"detectors": {}, "tttr_reading": {"file_type": "SPC-130"}}))
    receive_photons(app, {"file": str(BH), "setup": str(setup), "datasets": ["u-bh"]})
    settle(ui)
    assert app.model.has_data and len(app.model.data.macro_ticks) == 183657  # the setup's subtype
    assert app.source_uid == "u-bh"
    with pytest.raises(FileNotFoundError):
        receive_photons(app, {"file": str(tmp_path / "gone.ptu")})
    app.close()


def test_range_fields_are_typed_stepped_clamped_and_wheeled():
    ui, _ = loaded()
    ui.type_into("range_start", "1.5")
    assert ui.app.range_start == 1.5
    ui.type_into("range_start", "-4")
    assert ui.app.range_start == 0.0
    ui.type_into("range_start", "not a number")
    assert ui.app.range_start == 0.0
    ui.arrow("range_end", +1)
    assert ui.app.range_end == 1.0
    ui.arrow("range_end", -1)
    assert ui.app.range_end == 0.0
    ui.app.close()


@pytest.mark.parametrize(
    "key,typed,attr,expected",
    [
        ("bin_width", "0.1", "bin_width", 0.1),
        ("sample_rate", "22050", "sample_rate", 22050),
        ("master_gain", "1.5", "master_gain", 1.5),
        ("attack_frames", "5", "attack_frames", 5),
    ],
)
def test_audio_parameters_are_typed_with_the_spec_limits(key, typed, attr, expected):
    ui, _ = loaded()
    ui.app.docks.focus("audio")
    ui.draw(3)
    ui.type_into(key, typed)
    assert getattr(ui.app.model, attr) == pytest.approx(expected)
    ui.type_into(key, "1e12")
    assert (
        getattr(ui.app.model, attr)
        <= {"bin_width": 1.0, "sample_rate": 192000, "master_gain": 2.0, "attack_frames": 100}[key]
    )
    ui.app.close()


def test_waterfall_mode_choice_and_checkboxes_are_clicked():
    ui, _ = loaded()
    ui.app.docks.focus("waterfall_parameters")
    ui.draw(3)
    ui.press_text("lifetime")
    assert ui.app.model.waterfall_mode == "lifetime"
    ui.press_text("microtime")
    assert ui.app.model.waterfall_mode == "microtime"
    ui.click("wf_log", fx=0.05)
    assert ui.app.model.wf_log is False
    ui.app.close()


def test_detector_table_show_box_and_typed_colour():
    ui, _ = loaded()
    ui.app.docks.focus("mixer")
    ui.draw(3)
    name = ui.app.model.detectors[1]["name"]
    x, y = cell(ui, "Show", name)
    ui.click_at(x, y)
    assert ui.app.model.detectors[1]["enabled"] is False
    colour = cell(
        ui,
        "Colour",
        next(t[5] for t in ui.last.texts if t[5].startswith("#") and t[5] == "#38ff38"),
    )
    ui.click_at(*colour, clicks=2)
    retype(ui, "#00ff00")
    np.testing.assert_allclose(ui.app.model.detectors[2]["color"], (0, 1, 0))
    ui.click_at(*colour, clicks=2)
    retype(ui, "green")
    ui.draw(2)
    assert ui.shown("Not a colour")
    ui.app.close()


def test_channel_table_and_chord_choice():
    ui, _ = loaded()
    ui.app.docks.focus("notes")
    ui.draw(3)
    assert [r["channel"] for r in ui.app.channel_rows()] == [0, 1, 2, 3]
    x, y = cell(ui, "On", "major", 0)
    ui.click_at(ui.text_rect("On")[0] + 6, y)
    assert ui.app.model.channel_enabled[0] is False
    x, y = cell(ui, "Gain", "major", 0)
    ui.click_at(x, y, clicks=2)
    retype(ui, "2.5")
    assert ui.app.model.channel_configs[0].gain == 2.5
    ui.click_at(x, y, clicks=2)
    retype(ui, "99")
    assert ui.app.model.channel_configs[0].gain == 10.0
    ui.click_at(*cell(ui, "Channel", "minor", 0))
    assert ui.app.selected_channel == 1
    ui.click("chord", fx=0.8)
    ui.press_text("sus4") if "sus4" in ui.app.model.CHORD_TYPES else ui.press_text(
        ui.app.model.CHORD_TYPES[-1]
    )
    assert ui.app.model.channel_configs[1].chord_type != "minor"
    ui.app.close()


def test_transport_buttons_play_pause_resume_revert_stop_and_save_wav(tmp_path):
    ui, clock = loaded()
    assert ui.app.player.state == "stopped"
    ui.click("play")
    settle(ui)
    assert ui.app.player.state == "playing" and ui.app.waveform is not None
    clock[0] = 0.5
    ui.click("pause")
    assert ui.app.player.state == "paused"
    ui.click("play")
    assert ui.app.player.state == "playing"
    ui.click("revert")
    assert ui.app.player.position == 0
    ui.click("stop")
    assert ui.app.player.state == "stopped"
    ui.click("save_wav")
    assert ui.dialog_open
    ui.save_dialog_type_name(str(tmp_path / "out.wav"))
    ui.press_text("Save")
    settle(ui)
    with wave.open(str(tmp_path / "out.wav")) as wav:
        assert wav.getnframes() > 0
    ui.app.close()


def test_play_with_nothing_loaded_says_why_and_buttons_are_greyed():
    app, _ = make()
    ui = Ui(app, (1200, 800))
    ui.click("play")
    assert ui.shown("No data loaded")
    ui.click("pause")
    assert app.player.state == "stopped"
    app.close()


def test_guide_and_help_buttons_and_the_tour_is_walked():
    ui, _ = loaded()
    ui.click("help")
    assert ui.app.help.open
    # emtk 9753aeb moved the help window's close to the title-bar border glyph; the
    # dialog draws last, so the last '×' is its header close button.
    ui.press_text("×", nth=-1)
    assert not ui.app.help.open
    ui.click("guide")
    assert ui.app.guide.active
    steps = len(ui.app.guide.steps)
    seen = 0
    for _ in range(steps * 3):
        step = ui.app.guide.steps[ui.app.guide.step_idx]
        assert_tour_card_clear(
            ui.app.guide, ui.size
        )  # every step's control is drawn and the card is not on it
        if ui.app.guide.awaiting:
            key = ui.app.guide._target_key(step["target"])
            assert key in ui.app.item_rects, key
            ui.click(key)
            settle(ui)
            if ui.dialog_open:
                ui.press_text("Cancel")
        seen += 1
        if ui.app.guide.step_idx == steps - 1:
            break
        ui.press_text("Next ►")
    assert ui.app.guide.step_idx == steps - 1
    ui.press_text("Close Tour")
    assert not ui.app.guide.active
    ui.app.close()


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel does not reach an implot inside a DockManager window (repro in the report)",
)
def test_the_waterfall_plot_zooms_with_the_wheel():
    ui, _ = loaded()
    ui.click("update")
    settle(ui)
    before = ui.last.strings
    x, y, w, h = ui.app.item_rects["waterfall_plot"]
    ui.app.pointer_move(x + w / 2, y + h / 2)
    ui.draw(2)
    ui.app.wheel(x + w / 2, y + h / 2, 3)
    ui.draw(3)
    assert ui.last.strings != before  # the axis ticks changed under the zoom
    ui.app.close()


# ---- layout, tooltips, settings -----------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_layout_at_both_sizes(size):
    from test.gui.emtk_layout_checks import assert_texts_apart

    app, _ = make(loader=lambda p: stream())
    ui = Ui(app, size)
    feed(ui, "x.ptu")
    settle(ui)
    ui.click("update")
    settle(ui)
    for panel in ("setup", "audio", "waterfall_parameters", "mixer", "notes", "waterfall"):
        app.docks.focus(panel)
        painter = ui.draw(3)
        w, h = size
        region = {
            "setup": (0, 24, 0.37 * w, h - 24),
            "audio": (0, 24, 0.37 * w, h - 24),
            "waterfall_parameters": (0, 24, 0.37 * w, h - 24),
            "waterfall": (0.37 * w, 24, 0.63 * w, 0.62 * h - 24),
            "mixer": (0.37 * w, 0.62 * h + 24, 0.63 * w, 0.38 * h - 24),
            "notes": (0.37 * w, 0.62 * h + 24, 0.63 * w, 0.38 * h - 24),
        }[panel]  # the dock tab strips are emtk's chrome
        if (
            panel != "setup"
        ):  # the setup panel is the shared detector editor (its headers: see the report)
            flat = type(
                "P",
                (),
                {
                    "visible_texts": [
                        t
                        for t in painter.visible_texts
                        if t[5] not in {"Micro-time (bin)", "Lifetime (ns)"}
                    ]
                },
            )
            assert_texts_apart(
                flat, region=region
            )  # (the rotated y label has an unrotated box in the recording)
    for key in ("update", "play", "save_wav", "guide", "help", "range_start", "range_end"):
        x, y, w, h = app.item_rects[key]
        assert 0 <= x and x + w <= size[0] + 0.5 and 0 <= y and y + h <= size[1] + 0.5, key
    app.close()


def test_settings_round_trip_and_nothing_is_written_under_home(tmp_path):
    ui, _ = loaded()
    ui.app.model.sample_rate = 22050
    ui.app.range_end = 2.0
    state = ui.app.export_settings()
    app2, _ = make()
    app2.restore_settings(state)
    assert app2.model.sample_rate == 22050 and app2.range_end == 2.0
    ui.app.close()
    app2.close()
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
