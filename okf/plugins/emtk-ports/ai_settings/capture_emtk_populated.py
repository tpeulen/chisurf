"""Capture the emtk AI Settings app in populated states: TEMPORARY settings, STUBBED http, FAKE key.

Usage: CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/m.db
python capture_emtk_populated.py <out_dir>   (PYTHONPATH with the repo and emtk; provider key env vars unset).
No network call is made: ``chisurf.core.support.http.get`` is replaced.
"""
import pathlib
import sys
import time

from test.gui.emtk_port_parity import build_emtk_app, emtk_screenshot  # first: ``test`` is also a stdlib package

from emtk.testing import RecordingPainter

from chisurf.core.support import http

out = pathlib.Path(sys.argv[1])
FAKE_KEY = "sk-test-0000"


class Response:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        return self._payload


MODELS = {"data": [{"id": "mistral-large-latest"}, {"id": "mistral-small-latest"},
                   {"id": "mistral-embed"}, {"id": "pixtral-large-latest"}]}
mode = {"response": Response(200, MODELS)}
http.get = lambda url, **kw: mode["response"]
app = build_emtk_app("ai_settings")
SECTIONS = ("API Configuration", "Models", "Generation Settings")


def shot(name, size=(1200, 800)):
    emtk_screenshot(app, out / name, size)
    print("wrote", name)


def frames(size=(1200, 800), n=3):
    for _ in range(n):
        app.draw(RecordingPainter(), 0, 0, *size)


def wait(size=(1200, 800)):
    deadline = time.monotonic() + 5
    frames(size, 2)
    while app.job.busy and time.monotonic() < deadline:
        time.sleep(0.02)
        frames(size, 1)
    frames(size, 2)


def click(name, size=(1200, 800)):
    frames(size)
    r = app.form.rects[name]
    x, y = r[0] + r[2] / 2, r[1] + r[3] / 2
    app.hover(x, y); frames(size, 1)
    app.press(x, y); frames(size, 1)
    app.release(); frames(size, 2); app.hover(900, 450); frames(size, 1)


shot("after_populated_default_1200x800.png")
for t in SECTIONS:
    app.form.folds[t] = True
object.__setattr__(app.model, "api_key", FAKE_KEY)   # as if pasted; no auto-save, no check
wait()
shot("after_populated_expanded_key_hidden_1200x800.png")
shot("after_populated_expanded_key_hidden_800x600.png", (800, 600))
shot("after_populated_expanded_key_hidden_narrow_480x700.png", (480, 700))
click("show_key")
shot("after_populated_expanded_key_shown_1200x800.png")
click("show_key")
click("fetch_models")
wait()
shot("after_populated_models_fetched_1200x800.png")
shot("after_populated_models_fetched_800x600.png", (800, 600))
mode["response"] = Response(401, text='{"message":"Unauthorized"}')
click("test_connection")
wait()
shot("after_populated_connection_failed_1200x800.png")
mode["response"] = Response(200, MODELS)
click("test_connection")
wait()
shot("after_populated_connection_ok_1200x800.png")
shot("after_populated_connection_ok_800x600.png", (800, 600))
app.model.set_provider("custom")
frames()
click("fetch_models")
wait()
shot("after_populated_validation_empty_url_1200x800.png")
app.model.set_provider("acp")
shot("after_populated_acp_1200x800.png")
app.model.set_provider("mistral")
app.model.text_model = "my-private-model"
app.model.reset()
shot("after_populated_reset_1200x800.png")
app.close()
