"""Click-driven Open / Add / edit / Delete / Save-as-PTU round trip on a real PTU."""

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.keys import KEY_END
from emtk.testing import Driver

from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

SOURCE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
pytestmark = pytest.mark.skipif(not SOURCE.exists(), reason="Real PTU fixture unavailable")


def _wait(driver, app):
    """Draw frames until the background job has published its result."""
    deadline = time.monotonic() + 60
    driver.frame(2)
    while app.job.running:
        assert time.monotonic() < deadline, "background job did not finish"
        time.sleep(0.02)
        driver.frame()
    return driver.frame(3)


def _texts(driver):
    return [entry[5] for entry in driver.painter.texts]


def _scroll_to(driver, caption):
    """Wheel the tag table until the last row with ``caption`` is on screen."""
    for _ in range(100):
        hits = [e for e in driver.painter.texts if e[5] == caption]
        if hits and 150 < hits[-1][1] < 785:
            return hits[-1]
        driver.wheel(-3, at=(300, 300))
    raise AssertionError(f"{caption!r} never scrolled into view")


def test_open_add_edit_delete_save_round_trip(tmp_path):
    import tttrlib

    digest = hashlib.sha256(SOURCE.read_bytes()).digest()
    app = create_app()
    driver = Driver(app, (1200, 800))
    try:
        driver.frame(2)
        assert "No file loaded" in " ".join(_texts(driver))

        # Open: the dialog appears, the file is picked by clicking its name.
        driver.click("📂  Open…")
        assert app.dialog is not None
        app.dialog.directory = str(SOURCE.parent)
        driver.frame(2)
        driver.click(SOURCE.name)
        assert app.dialog.selection == [SOURCE.name]
        driver.click("Open")
        _wait(driver, app)
        assert app.dialog is None
        assert app.message == "Header loaded."
        assert app.model.opened_path == str(SOURCE)
        original_tags = len(app.model.tags)
        assert original_tags > 6
        assert "No file loaded" not in " ".join(_texts(driver))

        # Delete: the first row's cross removes that (visible) tag.
        driver.frame(2)
        first_name = app.model.tags[0]["name"]
        top = min((e for e in driver.painter.texts if e[5] == "✕"), key=lambda e: e[1])
        driver.click(tuple(top[:4]))
        assert len(app.model.tags) == original_tags - 1
        assert app.model.tags[0]["name"] != first_name

        # Add: a new row appears and reaches the model and the JSON view.
        driver.click("➕ Add")
        assert len(app.model.tags) == original_tags
        assert app.model.tags[-1]["name"] == "NewTag"

        # Edit: type into the real name field of the new row.
        _scroll_to(driver, "NewTag")
        driver.click("NewTag")
        driver.press(KEY_END)
        driver.type("Y")
        assert app.model.tags[-1]["name"] == "NewTagY"
        assert any("NewTagY" in t for t in _texts(driver))

        # Save as PTU: pick a destination through the dialog.
        for _ in range(100):  # the dock scrolled with the table; scroll back up
            if driver.rect("💾 Save as PTU")[1] > 40:
                break
            driver.wheel(5, at=(300, 300))
        driver.click("💾 Save as PTU")
        assert app.dialog is not None, (app.message, app.validation_error)
        assert app.dialog.mode == "save"
        app.dialog.directory = str(tmp_path)
        app.dialog.filename = "edited.ptu"
        driver.frame(2)
        driver.click("Save")
        _wait(driver, app)
        output = tmp_path / "edited.ptu"
        assert output.is_file()
        assert app.message == f"Saved edited PTU: {output}"

        original, saved = tttrlib.TTTR(str(SOURCE)), tttrlib.TTTR(str(output))
        for attr in ("macro_times", "micro_times", "routing_channels", "event_types"):
            np.testing.assert_array_equal(getattr(original, attr), getattr(saved, attr))
        names = [tag["name"] for tag in json.loads(saved.header.json)["tags"]]
        assert "NewTagY" in names and first_name not in names
        assert hashlib.sha256(SOURCE.read_bytes()).digest() == digest
    finally:
        app.close()
