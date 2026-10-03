"""The ALEX Creator's guided tour walked with real pointer input, in a hermetic HOME (nothing of the user's is touched).

Every awaited control is pressed (or edited) at the rectangle it was drawn in, the tour card never sits on the control
it points at, and the awaiting steps release only when the user operates their control.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import tttrlib

from chisurf.plugins.emtk_test_input import assert_tour_card_clear
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

SAMPLE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
SIZE = (1200, 800)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def source(tmp_path):
    if not SAMPLE.is_file():
        pytest.skip("Leica TTTR sample unavailable")
    path = tmp_path / "source.ptu"
    tttrlib.TTTR(str(SAMPLE))[:5000].write(str(path))
    return path


@pytest.fixture
def ui(tmp_path):
    ui = Ui(AlexApp(tmp_path / "preferences.json"), SIZE)
    yield ui
    ui.app.close()


def settle(ui, timeout=30.0):
    end = time.monotonic() + timeout
    while ui.app.running and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    assert not ui.app.running
    return ui.draw(3)


def test_every_guide_target_is_drawn_and_the_card_leaves_it_free(ui, source):
    assert ui.drop(source)
    settle(ui)
    ui.click("guide")
    tour = ui.app.guide
    assert tour.active and len(tour.steps) >= 4
    for index in range(len(tour.steps)):
        tour.start(index)
        ui.draw(3)
        assert_tour_card_clear(tour, ui.size)


def test_the_tour_is_walked_with_the_user_operating_each_awaited_control(ui, source):
    ui.click("guide")
    tour = ui.app.guide
    assert tour.active and tour.awaiting  # the first step waits for Open...
    assert tour.step_idx == 0, "Next must not skip a step that waits for its control"

    seen = []
    for _ in range(30):
        if not tour.active:
            break
        ui.draw(3)
        step = tour.steps[tour.step_idx]
        assert_tour_card_clear(tour, ui.size)
        if tour.awaiting:
            key = tour._target_key(step["target"])
            seen.append(key)
            if key == "choose_input":
                ui.click("choose_input")
                assert ui.dialog_open
                ui.app.dialog.enter(str(source.parent))
                ui.dialog_pick(source.name)
                settle(ui)
                assert ui.app.model.has_data
            elif key == "timing":
                before = ui.app.model.period_shift
                ui.type_into("period_shift", "23")  # a spin field: type the value, Enter
                assert ui.app.model.period_shift != before
            else:
                ui.click(key)
                if ui.dialog_open:
                    ui.press_text("Cancel")
            assert not tour.awaiting, f"operating {key!r} did not release the step"
            ui.draw(2)
        ui.press_text("Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►")
    assert not tour.active
    assert seen == ["choose_input", "timing", "choose_save", "choose_files"]
