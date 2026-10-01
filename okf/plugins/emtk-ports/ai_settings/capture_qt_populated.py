"""Capture the legacy Qt AI Settings tool in populated states (TEMPORARY settings, STUBBED http, FAKE key).

Usage: CHISURF_SETTINGS_DIR=<tmp> MMFDB_SETTINGS_DIR=<tmp> MMFDB_DATABASE_PATH=<tmp>/m.db
python capture_qt_populated.py <out_dir>   (QT_QPA_PLATFORM=offscreen, PYTHONPATH with the repo and emtk;
the provider key environment variables unset). No network call is made: ``http.get`` is replaced.
"""
import sys
import time
from pathlib import Path

out = Path(sys.argv[1])
FAKE_KEY = "sk-test-0000"
from qtpy import QtWidgets  # noqa: E402

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.core.support import http  # noqa: E402
from chisurf.gui.autoform.sections.builtin import ChoiceWidget, ValueWidget  # noqa: E402
from chisurf.gui.widgets.collapsible_box import CollapsibleBox  # noqa: E402
from chisurf.plugins.ai_settings.gui.tool import AISettingsWidget  # noqa: E402


class Response:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text

    def json(self):
        return self._payload


MODELS = {"data": [{"id": "mistral-large-latest"}, {"id": "mistral-small-latest"},
                   {"id": "mistral-embed"}, {"id": "pixtral-large-latest"}]}
mode = {"response": Response(200, MODELS)}
http.get = lambda url, **kw: mode["response"]  # the stubbed transport

w = AISettingsWidget()
w.resize(1200, 800)
w.show()


def pump(n=40):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.005)


def grab(name):
    pump()
    w.grab().save(str(out / name))
    print("wrote", name)


def field(attr):
    return next(v for v in w.form.findChildren(ValueWidget) if getattr(v._section, "attr", None) == attr)


pump()
for b in w.findChildren(CollapsibleBox):
    b.set_expanded(True)
pump(60)
field("api_key").editor.setText(FAKE_KEY)
field("api_key").editor.editingFinished.emit()   # commits, saves and tests (stubbed)
pump(80)
grab("before_populated_expanded_key_hidden.png")
field("api_key").reveal.setChecked(True)
grab("before_populated_expanded_key_shown.png")
field("api_key").reveal.setChecked(False)
w.model.fetch_models()
pump(80)
grab("before_populated_models_fetched.png")
print("text combo items:", [c.combo.itemText(i) for c in w.form.findChildren(ChoiceWidget)
      if getattr(c._section, "attr", "") == "text_model" for i in range(c.combo.count())])
print("image combo items:", [c.combo.itemText(i) for c in w.form.findChildren(ChoiceWidget)
      if getattr(c._section, "attr", "") == "image_model" for i in range(c.combo.count())])
mode["response"] = Response(401, text='{"message":"Unauthorized"}')
w.model.test_connection()
pump(80)
grab("before_populated_connection_failed.png")
mode["response"] = Response(200, MODELS)
w.model.test_connection()
pump(80)
grab("before_populated_connection_ok.png")
w.model.set_provider("custom")   # empty base URL: the validation message
pump(40)
w.model.fetch_models()
pump(40)
grab("before_populated_validation_empty_url.png")
w.model.set_provider("mistral")
pump(40)
w.model.reset()
pump(40)
grab("before_populated_reset.png")
