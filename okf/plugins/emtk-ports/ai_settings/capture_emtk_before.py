"""Capture the CURRENT (pre-upgrade) emtk AI Settings app: TEMPORARY settings, STUBBED http, FAKE key.

Usage: CHISURF_SETTINGS_DIR=<tmp> ... python capture_emtk_before.py <out_dir> (provider key env vars unset)
"""
import pathlib
import sys
import time

from test.gui.emtk_port_parity import build_emtk_app, emtk_screenshot
from chisurf.core.support import http

out = pathlib.Path(sys.argv[1])


class Response:
    status_code = 200

    def json(self):
        return {"data": [{"id": "mistral-large-latest"}, {"id": "mistral-small-latest"}, {"id": "pixtral-large-latest"}]}


http.get = lambda url, **kw: Response()
app = build_emtk_app("ai_settings")
gui = app.settings_gui
emtk_screenshot(app, out / "before_emtk_empty_1200x800.png", (1200, 800))
object.__setattr__(app.model, "api_key", "sk-test-0000")
emtk_screenshot(app, out / "before_emtk_key_hidden_1200x800.png", (1200, 800))
gui.reveal_key = True
emtk_screenshot(app, out / "before_emtk_key_shown_1200x800.png", (1200, 800))
gui.reveal_key = False
app.model.fetch_models()
deadline = time.monotonic() + 3
while gui.busy and time.monotonic() < deadline:
    gui.process_events()
    time.sleep(0.01)
emtk_screenshot(app, out / "before_emtk_models_fetched_1200x800.png", (1200, 800))
app.close()
