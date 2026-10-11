"""The PDA reader form of the emtk shell scrolls: every control, down to *Load dropped files*, is reachable."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from emtk.testing import Driver

from test.native_emtk.test_emtk_shell_readers import (  # noqa: F401 - fixtures
    _reader_child,
    reveal_in_reader,
    _select_pda,
    pda_setups,
    shell,
)

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))


@pytest.mark.parametrize("size", [(1920, 1080), (1300, 900), (800, 600)], ids=lambda s: f"{s[0]}x{s[1]}")
def test_the_last_control_of_the_pda_form_can_be_scrolled_into_view(shell, pda_setups, size):
    driver = Driver(shell, size=size)
    driver.frame(2)
    _select_pda(shell, driver)
    driver.frame(2)
    app, _box = _reader_child(shell)
    names = [n for n in app.form.rects if n.startswith("pda_files.")]
    assert names, sorted(app.form.rects)
    target = max(names, key=lambda n: app.form.rects[n][1])
    reveal_in_reader(driver, shell, target)
    _app, box = _reader_child(shell)
    x, y, w, h = app.form.rects[target]
    assert 0 <= y and y + h <= box[3] and box[1] + box[3] <= size[1]
    SHOTS.mkdir(parents=True, exist_ok=True)
    driver.screenshot(SHOTS / f"pda_reader_scrolled_{size[0]}x{size[1]}.png")
