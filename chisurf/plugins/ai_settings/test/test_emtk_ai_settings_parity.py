"""The native AI Settings app against the Qt tool: fields, providers, key, network, save, no Qt.

Hermetic: the settings file is a temporary one (``CHISURF_SETTINGS_DIR`` and the module's
path function both point into ``tmp_path``), the provider key variables are removed from the
environment, and the HTTP transport (``chisurf.core.support.http.get``) is replaced by a
stub for the whole module, so no test reaches the network or a real API. Every key used is
the fake ``sk-test-0000``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest
from emtk.testing import PixelPainter, RecordingPainter
from emtk.view_form import _commit, parse_value

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "ai_settings_emtk.view.json"
QT_SPEC_FILE = GUI / "ai_settings.view.json"
FAKE_KEY = "sk-test-0000"
MODELS = {
    "data": [
        {"id": "mistral-large-latest"},
        {"id": "mistral-small-latest"},
        {"id": "mistral-embed"},
        {"id": "pixtral-large-latest"},
    ]
}


# --------------------------------------------------------------------------- #
# the stubbed transport and a temporary settings folder
# --------------------------------------------------------------------------- #
class FakeResponse:
    """What ``http.get`` returns: a status, a JSON body and a text."""

    def __init__(self, status=200, payload=None, text="", bad_json=False):
        self.status_code = status
        self._payload = payload
        self._bad_json = bad_json
        self.text = text

    def json(self):
        if self._bad_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class FakeHTTP:
    """Replaces ``http.get``: records each call and answers from ``behaviour``."""

    def __init__(self):
        self.calls: list[dict] = []
        self.behaviour = lambda url, headers: FakeResponse(200, MODELS)
        self.gate: threading.Event | None = None

    def get(self, url, headers=None, timeout=None, **_kw):
        self.calls.append({"url": url, "headers": dict(headers or {}), "timeout": timeout})
        if self.gate is not None:
            self.gate.wait(5)
        result = self.behaviour(url, headers or {})
        if isinstance(result, BaseException):
            raise result
        return result


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """Temporary settings, no provider keys in the environment, a stubbed transport."""
    folder = tmp_path / "settings"
    folder.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(folder / "m.db"))
    from chisurf.core.settings import ai_settings

    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: folder / "ai_api_settings.json")
    for provider_key, *_rest in ai_settings.PROVIDERS.values():
        for name in ai_settings.provider_key_env_names(provider_key):
            monkeypatch.delenv(name, raising=False)
    from chisurf.core.support import http

    stub = FakeHTTP()
    monkeypatch.setattr(http, "get", stub.get)
    import webbrowser

    opened: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)
    return type(
        "Env",
        (),
        {"folder": folder, "http": stub, "opened": opened, "file": folder / "ai_api_settings.json"},
    )


@pytest.fixture
def env(hermetic):
    return hermetic


def make_model():
    from chisurf.plugins.ai_settings.gui.model import AISettingsModel

    return AISettingsModel()


def make_app(model=None):
    from chisurf.plugins.ai_settings.gui.app import AISettingsApp

    return AISettingsApp(model) if model is not None else AISettingsApp()


def frames(app, size=(1200, 800), n=3):
    painter = None
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def settle(app, size=(1200, 800), seconds=5.0):
    """Draw frames until the job has finished and its answer was delivered."""
    deadline = time.monotonic() + seconds
    painter = frames(app, size, 2)
    while app.job.busy and time.monotonic() < deadline:
        time.sleep(0.01)
        painter = frames(app, size, 1)
    return frames(app, size, 2)


def click(app, name, size=(1200, 800)):
    """Press the control *name* the way a user does (hover, press, release)."""
    frames(app, size)
    x0, y0, w, h = app.form.rects.get(name) or app.item_rects[name]
    x, y = x0 + w / 2, y0 + h / 2
    app.hover(x, y)
    frames(app, size, 1)
    app.press(x, y)
    frames(app, size, 1)
    app.release()
    frames(app, size, 2)
    app.hover(size[0] - 5, size[1] / 2)
    frames(app, size, 1)


def spec():
    return json.loads(SPEC_FILE.read_text(encoding="utf-8"))


def walk(sections):
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def find_fields(attr):
    return [s for s in walk(spec()["sections"]) if s.get("attr") == attr]


def commit_field(app, attr, value):
    """Write *value* through the form's own path (setattr, then the ``call``)."""
    section = next(s for s in find_fields(attr))
    _commit(app.model, section, value, app.form)


def saved():
    from chisurf.core.settings import ai_settings

    return ai_settings.get_api_settings


# --------------------------------------------------------------------------- #
# 1. model defaults and the provider table equal the Qt widget's
# --------------------------------------------------------------------------- #
def test_provider_options_and_defaults_equal_the_qt_tool(qapp):
    """The emtk provider list is the Qt choice's list; a fresh model equals the Qt widget's."""
    pytest.importorskip("qtpy")
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget
    from chisurf.plugins.ai_settings.gui.tool import AISettingsWidget

    widget = AISettingsWidget()
    try:
        combo = next(
            c.combo for c in widget.form.findChildren(ChoiceWidget) if c._section.attr == "provider"
        )
        qt_labels = [combo.itemText(i) for i in range(combo.count())]
        app = make_app()
        assert [label for _key, label in app.model.available_providers()] == qt_labels
        for attr in (
            "provider",
            "base_url",
            "api_key",
            "text_model",
            "image_model",
            "temperature",
            "top_p",
            "max_tokens",
        ):
            assert getattr(app.model, attr) == getattr(widget.model, attr), attr
        assert app.model.provider == "mistral"
        assert app.model.base_url == "https://api.mistral.ai/v1"
        assert (app.model.temperature, app.model.top_p, app.model.max_tokens) == (0.3, 0.9, 4096)
    finally:
        widget.close()


def test_numeric_ranges_equal_the_qt_spec():
    """Temperature, Top-p and Max tokens carry the Qt spinbox ranges, steps and decimals."""
    qt = {
        s["attr"]: s
        for s in walk(json.loads(QT_SPEC_FILE.read_text())["sections"])
        if s.get("attr") in ("temperature", "top_p", "max_tokens")
    }
    assert set(qt) == {"temperature", "top_p", "max_tokens"}
    for attr, qt_section in qt.items():
        (mine,) = find_fields(attr)
        for key in ("kind", "minimum", "maximum", "step", "decimals"):
            assert mine.get(key) == qt_section.get(key), (attr, key)
        assert mine.get("style") != "slider", "Qt has spin boxes, not sliders"
    assert (qt["temperature"]["minimum"], qt["temperature"]["maximum"]) == (0.0, 2.0)
    assert (qt["top_p"]["minimum"], qt["top_p"]["maximum"]) == (0.0, 1.0)
    assert (qt["max_tokens"]["minimum"], qt["max_tokens"]["maximum"]) == (1, 1000000)


@pytest.mark.parametrize(
    ("attr", "typed", "expected"),
    [
        ("temperature", "5", 2.0),
        ("temperature", "-1", 0.0),
        ("temperature", "0.75", 0.75),
        ("top_p", "1.7", 1.0),
        ("top_p", "-0.2", 0.0),
        ("max_tokens", "0", 1),
        ("max_tokens", "99999999", 1000000),
        ("max_tokens", "2048", 2048),
        ("max_tokens", "abc", None),
    ],
)
def test_numbers_are_clamped_to_the_qt_ranges_and_typos_are_ignored(attr, typed, expected):
    (section,) = find_fields(attr)
    assert parse_value(typed, section) == expected


def test_a_typed_number_reaches_the_model_and_the_settings_file(env):
    app = make_app()
    commit_field(app, "temperature", parse_value("0.65", find_fields("temperature")[0]))
    commit_field(app, "max_tokens", parse_value("100", find_fields("max_tokens")[0]))
    stored = saved()("mistral")
    assert (stored["temperature"], stored["max_tokens"]) == (0.65, 100)


# --------------------------------------------------------------------------- #
# 2. changing the provider updates Base URL and models as in Qt
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("key", ["mistral", "local", "openai", "openrouter", "acp", "custom"])
def test_changing_the_provider_loads_its_defaults(key):
    from chisurf.core.settings.ai_settings import DEFAULT_PROVIDER_SETTINGS

    app = make_app()
    commit_field(app, "provider", key)
    defaults = DEFAULT_PROVIDER_SETTINGS[key]
    assert app.model.provider == key
    assert app.model.base_url == defaults["base_url"]
    assert app.model.text_model == defaults["text_model"]
    assert app.model.image_model == defaults["image_model"]
    assert app.model.api_key == ""
    # the Qt tool does the same through the same model call
    qt_like = make_model()
    qt_like.set_provider(key)
    assert (qt_like.base_url, qt_like.text_model, qt_like.image_model) == (
        app.model.base_url,
        app.model.text_model,
        app.model.image_model,
    )


def test_changing_the_provider_drops_fetched_models_and_the_key_is_not_carried_over(env):
    app = make_app()
    commit_field(app, "provider", "openai")
    app.model.api_key = FAKE_KEY
    app.model.fetch_models()
    settle(app)
    assert app.model.has_text_models
    commit_field(app, "provider", "mistral")
    assert not app.model.has_text_models and not app.model.has_image_models
    assert app.model.api_key == ""
    assert app.model.status_text == ""
    # the first provider kept its own key
    assert saved()("openai")["api_key"] == FAKE_KEY


def test_each_provider_keeps_its_own_saved_settings(env):
    app = make_app()
    commit_field(app, "provider", "local")
    app.model.base_url = "http://localhost:9999/v1"
    app.model.text_model = "my-local"
    commit_field(app, "provider", "openai")
    assert app.model.base_url == "https://api.openai.com/v1"
    commit_field(app, "provider", "local")
    assert (app.model.base_url, app.model.text_model) == ("http://localhost:9999/v1", "my-local")


def test_acp_fields_show_only_for_the_acp_provider(env):
    app = make_app()
    strings = "\n".join(frames(app).strings)
    assert "ACP command" not in strings
    commit_field(app, "provider", "acp")
    strings = "\n".join(frames(app).strings)
    assert "ACP command" in strings and "In-tree server API" in strings
    commit_field(app, "command", 'agent --stdio "quoted path"')
    commit_field(app, "acp_backend_provider", "local")
    stored = saved()("acp")
    assert stored["command"] == 'agent --stdio "quoted path"'
    assert stored["acp_backend_provider"] == "local"


# --------------------------------------------------------------------------- #
# 3. the key: masked by default, clear only with the toggle
# --------------------------------------------------------------------------- #
def _all_text(app, size=(1200, 800)):
    painter = frames(app, size)
    return "\n".join(painter.strings)


def test_the_key_is_never_drawn_in_clear_by_default(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    for size in ((1200, 800), (800, 600)):
        painter = frames(app, size)
        assert not any(FAKE_KEY in s for s in painter.strings)
        assert any("*" in s for s in painter.strings), "a masked field draws stars"
    assert app.model.show_key is False


def test_show_key_toggle_reveals_and_hides_the_key(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    assert FAKE_KEY not in _all_text(app)
    click(app, "show_key")
    assert app.model.show_key is True
    assert FAKE_KEY in _all_text(app)
    click(app, "show_key")
    assert app.model.show_key is False
    assert FAKE_KEY not in _all_text(app)


def test_a_provider_change_and_close_hide_the_key_again(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    app.model.show_key = True
    commit_field(app, "provider", "openai")
    assert app.model.show_key is False
    app.model.show_key = True
    app.close()
    assert app.model.show_key is False


def test_the_key_is_not_in_tooltips_status_or_remembered_state(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    env.http.behaviour = lambda url, headers: FakeResponse(401, text=f"bad key {FAKE_KEY} given")
    app.model.test_connection()
    settle(app)
    assert "[redacted]" in app.model.status_text
    assert FAKE_KEY not in app.model.status_text
    assert FAKE_KEY not in app.model.status_html
    assert FAKE_KEY not in json.dumps(app.export_settings())
    assert FAKE_KEY not in _all_text(app)
    for section in walk(spec()["sections"]):
        assert FAKE_KEY not in json.dumps(section)


def test_the_key_is_sent_as_a_bearer_token_to_the_models_url(env):
    app = make_app()
    commit_field(app, "provider", "custom")
    app.model.base_url = "https://example.invalid/v1/"
    app.model.api_key = FAKE_KEY
    app.model.fetch_models()
    settle(app)
    (call,) = env.http.calls
    assert call["url"] == "https://example.invalid/v1/models"
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert call["timeout"] == 15


def test_a_pasted_key_is_saved_and_checked(env):
    """Enter on the key field saves the key and tests the endpoint (the Qt ``apply_token``)."""
    app = make_app()
    commit_field(app, "api_key", FAKE_KEY)
    settle(app)
    assert saved()("mistral")["api_key"] == FAKE_KEY
    assert len(env.http.calls) == 1
    assert "successful" in app.model.status_text.lower()


# --------------------------------------------------------------------------- #
# 4. Fetch models and Test connection through the job, stubbed transport
# --------------------------------------------------------------------------- #
def test_fetch_models_fills_the_pick_lists_through_the_job(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    click(app, "fetch_models")
    settle(app)
    model = app.model
    assert "mistral-large-latest" in model.text_model_choices()
    assert "mistral-small-latest" in model.available_text_models()
    from chisurf.core.settings import ai_settings

    reference_text, reference_image = ai_settings.split_models_by_capability(
        MODELS["data"], provider="mistral"
    )
    assert model.available_text_models() == reference_text
    assert model.available_image_models() == reference_image
    assert model.status_text == (
        f"Found {len(model.available_text_models())} text and "
        f"{len(model.available_image_models())} image models."
    )
    text = _all_text(app)
    assert "Fetched text models" in text and "Fetched image models" in text
    # identical to what the Qt tool's model produces for the same answer
    qt_like = make_model()
    qt_like.fetch_models()
    assert qt_like.available_text_models() == model.available_text_models()
    assert qt_like.available_image_models() == model.available_image_models()


def test_picking_a_fetched_model_sets_and_saves_it(env):
    app = make_app()
    app.model.fetch_models()
    settle(app)
    commit_field(app, "text_model_pick", "mistral-small-latest")
    commit_field(app, "image_model_pick", "pixtral-large-latest")
    assert app.model.text_model == "mistral-small-latest"
    assert saved()("mistral")["text_model"] == "mistral-small-latest"
    assert saved()("mistral")["image_model"] == "pixtral-large-latest"


def test_a_custom_model_id_is_kept_and_listed_first_in_the_pick_list(env):
    app = make_app()
    commit_field(app, "text_model", "my-fine-tune")
    app.model.fetch_models()
    settle(app)
    assert app.model.text_model == "my-fine-tune"
    assert app.model.text_model_choices()[0] == "my-fine-tune"
    assert saved()("mistral")["text_model"] == "my-fine-tune"


def test_the_pick_lists_are_hidden_until_models_are_fetched(env):
    app = make_app()
    assert "Fetched text models" not in _all_text(app)
    app.model.fetch_models()
    settle(app)
    assert "Fetched text models" in _all_text(app)


def test_test_connection_ok_and_failed(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    click(app, "test_connection")
    settle(app)
    assert app.model.status_text == "Connection successful!"
    env.http.behaviour = lambda url, headers: FakeResponse(401, text='{"message":"Unauthorized"}')
    click(app, "test_connection")
    settle(app)
    assert app.model.status_text == 'Connection failed: API error 401: {"message":"Unauthorized"}'
    # the same wording as the Qt tool's model
    qt_like = make_model()
    qt_like.test_connection()
    assert qt_like.status_text == app.model.status_text


@pytest.mark.parametrize(
    ("label", "behaviour", "expected"),
    [
        (
            "server error",
            lambda url, h: FakeResponse(500, text="upstream down"),
            "API error 500: upstream down",
        ),
        ("malformed JSON", lambda url, h: FakeResponse(200, bad_json=True), "Expecting value"),
        (
            "timeout",
            lambda url, h: TimeoutError("timed out"),
            "timed out: the endpoint did not answer within 15 s",
        ),
        (
            "transport timeout text",
            lambda url, h: OSError("The read operation timed out"),
            "timed out: the endpoint did not answer within 15 s",
        ),
        (
            "refused",
            lambda url, h: ConnectionRefusedError("[Errno 61] Connection refused"),
            "Connection refused",
        ),
        ("empty message", lambda url, h: RuntimeError(), "RuntimeError"),
    ],
)
@pytest.mark.parametrize("action", ["fetch_models", "test_connection"])
def test_network_failures_give_a_readable_status_and_never_raise(
    env, action, label, behaviour, expected
):
    app = make_app()
    app.model.api_key = FAKE_KEY
    env.http.behaviour = behaviour
    click(app, action)
    painter = settle(app)
    assert not app.job.busy and app.job.error == ""
    assert expected in app.model.status_text, label
    assert app.model.status_text.startswith(
        "Failed: " if action == "fetch_models" else "Connection failed: "
    )
    assert expected in "\n".join(painter.strings), "the result area shows it"
    assert not app.model.has_text_models


def test_the_window_stays_responsive_while_a_request_runs(env):
    app = make_app()
    env.http.gate = threading.Event()
    app.model.api_key = FAKE_KEY
    click(app, "test_connection")
    frames(app, n=2)
    assert app.job.busy and app.model.busy, "the request runs on the job, not in the frame"
    started = time.monotonic()
    painter = frames(app, n=5)
    assert time.monotonic() - started < 2.0, "frames keep being drawn while the request waits"
    assert "Testing connection" in "\n".join(painter.strings)
    # a second request is refused politely, not queued behind the first
    assert app.model.enabled("fetch_models") is False
    app.model.fetch_models()
    assert "Another request is still running" in app.model.status_text
    # the form is still editable and Save still works
    app.model.base_url = "https://example.invalid/v1"
    app.model.save()
    assert saved()("mistral")["base_url"] == "https://example.invalid/v1"
    env.http.gate.set()
    settle(app)
    assert not app.job.busy


def test_an_answer_for_a_provider_that_was_left_is_dropped(env):
    app = make_app()
    env.http.gate = threading.Event()
    commit_field(app, "provider", "openai")
    app.model.api_key = FAKE_KEY
    app.model.fetch_models()
    frames(app, n=2)
    commit_field(app, "provider", "local")
    env.http.gate.set()
    settle(app)
    assert not app.model.has_text_models
    assert "Found" not in app.model.status_text
    assert app.model.provider == "local"


# --------------------------------------------------------------------------- #
# 5. validation messages as in the Qt tool
# --------------------------------------------------------------------------- #
def test_an_empty_base_url_is_refused_with_the_qt_messages(env):
    app = make_app()
    commit_field(app, "provider", "custom")
    assert app.model.base_url == ""
    click(app, "fetch_models")
    settle(app)
    assert app.model.status_text == "Enter a base URL first."
    click(app, "test_connection")
    settle(app)
    assert app.model.status_text == "No base URL provided."
    assert env.http.calls == [], "nothing was sent"
    qt_like = make_model()
    qt_like.set_provider("custom")
    qt_like.fetch_models()
    assert qt_like.status_text == "Enter a base URL first."


def test_the_base_url_is_trimmed_and_a_blank_one_falls_back_to_the_default_on_save(env):
    app = make_app()
    commit_field(app, "provider", "openai")
    app.model.base_url = "  https://proxy.example.invalid/v1  "
    app.model.save()
    assert saved()("openai")["base_url"] == "https://proxy.example.invalid/v1"
    app.model.base_url = ""
    app.model.save()
    assert saved()("openai")["base_url"] == "https://api.openai.com/v1"
    assert app.model.base_url == "https://api.openai.com/v1"


# --------------------------------------------------------------------------- #
# 6. Save and Reset, persistence
# --------------------------------------------------------------------------- #
def test_save_persists_to_the_temporary_settings_file_and_a_fresh_model_reads_it(env):
    app = make_app()
    commit_field(app, "provider", "openai")
    app.model.api_key = FAKE_KEY
    app.model.text_model = "gpt-test"
    app.model.image_model = "image-test"
    app.model.temperature = 1.25
    app.model.top_p = 0.5
    app.model.max_tokens = 123
    click(app, "save")
    assert app.model.status_text == "Settings saved."
    assert env.file.is_file() and env.file.parent == env.folder
    on_disk = json.loads(env.file.read_text())
    assert on_disk["openai"]["api_key"] == FAKE_KEY and on_disk["selected_provider"] == "openai"
    if os.name == "posix":
        assert (env.file.stat().st_mode & 0o777) == 0o600
    fresh = make_model()
    assert fresh.provider == "openai"
    assert (fresh.api_key, fresh.text_model, fresh.image_model) == (
        FAKE_KEY,
        "gpt-test",
        "image-test",
    )
    assert (fresh.temperature, fresh.top_p, fresh.max_tokens) == (1.25, 0.5, 123)
    # and a second app on the same folder shows it, key still masked
    again = make_app()
    painter = frames(again)
    assert any("gpt-test" in s for s in painter.strings)
    assert not any(FAKE_KEY in s for s in painter.strings)


def test_save_failure_is_reported_not_raised(env, monkeypatch):
    from chisurf.core.settings import ai_settings

    def refuse(*_a, **_k):
        raise PermissionError("settings folder is read-only")

    app = make_app()
    monkeypatch.setattr(ai_settings, "save_api_settings", refuse)
    click(app, "save")
    assert "read-only" in app.model.status_text
    assert "read-only" in _all_text(app)


def test_reset_restores_the_defaults_without_saving(env):
    from chisurf.core.settings.ai_settings import DEFAULT_PROVIDER_SETTINGS

    app = make_app()
    commit_field(app, "provider", "openai")
    app.model.api_key = FAKE_KEY
    app.model.base_url = "http://custom.invalid/v1"
    app.model.text_model = "mine"
    app.model.temperature = 1.9
    click(app, "reset")
    defaults = DEFAULT_PROVIDER_SETTINGS["openai"]
    assert app.model.api_key == ""
    assert app.model.base_url == defaults["base_url"]
    assert app.model.text_model == defaults["text_model"]
    assert app.model.temperature == defaults["temperature"]
    assert app.model.status_text == "Fields reset to defaults. Press Save to keep them."
    # nothing was written by Reset: a fresh model still reads the earlier edits
    fresh = make_model()
    assert (fresh.api_key, fresh.text_model) == (FAKE_KEY, "mine")
    click(app, "save")
    fresh = make_model()
    assert (fresh.api_key, fresh.text_model) == ("", defaults["text_model"])


def test_sign_in_opens_the_providers_key_page_and_says_when_there_is_none(env):
    app = make_app()
    click(app, "sign_in")
    assert env.opened == ["https://console.mistral.ai/api-keys/"]
    assert "Opened https://console.mistral.ai/api-keys/" in app.model.status_text
    commit_field(app, "provider", "local")
    click(app, "sign_in")
    assert env.opened == ["https://console.mistral.ai/api-keys/"], "local has no console"
    assert app.model.status_text == "No browser sign-in available for this provider"


# --------------------------------------------------------------------------- #
# 7. layout: sections and their fold state, labels beside the fields
# --------------------------------------------------------------------------- #
def test_the_three_sections_have_the_qt_fold_state(env):
    panels = [s for s in walk(spec()["sections"]) if s.get("collapsible")]
    assert [(p["title"], p["collapsed"]) for p in panels] == [
        ("API Configuration", False),
        ("Models", False),
        ("Generation Settings", True),
    ]
    qt = [s for s in walk(json.loads(QT_SPEC_FILE.read_text())["sections"]) if s.get("collapsible")]
    assert [(p["title"], p["collapsed"]) for p in qt] == [
        (p["title"], p["collapsed"]) for p in panels
    ]


def test_generation_settings_are_folded_until_opened(env):
    app = make_app()
    text = _all_text(app)
    for shown in (
        "API Configuration",
        "Models",
        "Generation Settings",
        "Provider",
        "Base URL",
        "API Key",
        "Text model",
        "Image model",
    ):
        assert shown in text, shown
    for hidden in ("Temperature", "Top-p", "Max tokens"):
        assert hidden not in text, hidden
    click(app, "Generation Settings.fold")
    text = _all_text(app)
    for shown in ("Temperature", "Top-p", "Max tokens"):
        assert shown in text, shown
    click(app, "Models.fold")
    assert "Text model" not in _all_text(app)


def test_folds_round_trip_through_the_remembered_state(env):
    app = make_app()
    click(app, "Generation Settings.fold")
    click(app, "API Configuration.fold")
    state = app.export_settings()
    assert state == {"folds": {"Generation Settings": True, "API Configuration": False}}
    other = make_app()
    other.restore_settings(json.loads(json.dumps(state)))
    text = _all_text(other)
    assert "Temperature" in text and "Base URL" not in text
    other.restore_settings({"folds": "garbage"})  # a bad state is ignored, not raised


def test_labels_sit_beside_their_fields_in_two_columns(env):
    """Base URL and API Key share a line; so do Text model and Image model, Temperature and Top-p."""
    app = make_app()
    click(app, "Generation Settings.fold")
    frames(app)
    rects = app.form.rects
    for left, right in (
        ("base_url", "api_key"),
        ("text_model", "image_model"),
        ("temperature", "top_p"),
    ):
        assert abs(rects[left][1] - rects[right][1]) < 2, (left, right)
        assert rects[left][0] < rects[right][0]
    # a label is left of its field, never at the far edge: the field starts near the label
    assert rects["base_url"][0] < 200 and rects["provider"][0] < 200


# --------------------------------------------------------------------------- #
# 8. spec and model agree; tooltips; draws; guide; Qt-free
# --------------------------------------------------------------------------- #
def test_every_spec_key_exists_on_the_model():
    model = make_model()

    def check(sections):
        for s in sections:
            if s.get("attr"):
                assert hasattr(model, s["attr"]), s["attr"]
            if s.get("call"):
                assert callable(getattr(model, s["call"])), s["call"]
            for key in ("options_source", "source"):
                if s.get(key):
                    assert hasattr(model, s[key]), s[key]
            cond = s.get("hidden_when")
            if cond:
                assert hasattr(model, cond["attr"]), cond["attr"]
            for b in s.get("buttons", []):
                assert callable(getattr(model, b["action"])), b["action"]
            check(s.get("sections", []))

    check(spec()["sections"])


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("ai_settings")
    inventory = emtk_inventory(app)
    assert inventory["controls_without_tooltip"] == []
    for s in walk(spec()["sections"]):
        if s.get("type") in ("value", "choice", "toggle", "info", "panel"):
            if s.get("type") == "panel" and not s.get("title"):
                continue
            assert s.get("description"), s.get("attr") or s.get("title") or s
        for b in s.get("buttons", []):
            assert b.get("description"), b
    app.close()


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (480, 700)])
def test_the_app_draws_empty_and_populated_at_both_sizes(env, size):
    app = make_app()
    empty = frames(app, size)
    assert any("API Configuration" in s for s in empty.strings)
    for attr in ("temperature",):
        app.form.folds["Generation Settings"] = True
    app.model.api_key = FAKE_KEY
    app.model.fetch_models()
    settle(app, size)
    app.model.test_connection()
    settle(app, size)
    painter = frames(app, size)
    text = "\n".join(painter.strings)
    for shown in (
        "Fetched text models",
        "Connection successful!",
        "Temperature",
        "Save",
        "Reset",
        "Test connection",
        "Fetch models",
        "Sign in via browser",
        "Show key",
        "Configure one endpoint per provider",
    ):
        assert shown in text, (size, shown)
    assert FAKE_KEY not in text
    pixels = PixelPainter(*size)
    for _ in range(3):
        pixels = PixelPainter(*size)
        app.draw(pixels, 0.0, 0.0, float(size[0]), float(size[1]))


def test_help_and_guide_buttons_exist_and_the_guide_targets_are_real_controls(env):
    app = make_app()
    frames(app)
    assert "help" in app.item_rects and "guide" in app.item_rects
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert len(steps) == 6
    frames(app)
    known = set(app.item_rects) | set(app.form.rects)
    for step in steps:
        target = step["target"]
        assert target.get("name") in known, step["title"]
    awaited = [s["target"]["name"] for s in steps if s.get("await")]
    assert awaited == ["fetch_models", "test_connection"]


def test_the_tour_waits_for_the_real_buttons(env):
    app = make_app()
    app.model.api_key = FAKE_KEY
    frames(app)
    click(app, "guide")
    assert app.tour.active and app.tour.step_idx == 0
    for index, name in ((2, "fetch_models"), (4, "test_connection")):
        app.tour.start(index)
        frames(app)
        assert app.tour.awaiting, "the step waits for the user"
        app.tour.next()
        assert app.tour.step_idx == index, "the tour does not press or skip on the user's behalf"
        assert not env.http.calls or env.http.calls[-1]["url"].endswith("/models")
        calls_before = len(env.http.calls)
        click(app, name)
        settle(app)
        assert len(env.http.calls) == calls_before + 1, "the real button ran the request"
        assert not app.tour.awaiting
        app.tour.next()
        assert app.tour.step_idx == index + 1


def test_the_help_window_opens_and_its_links_exist(env):
    app = make_app()
    click(app, "help")
    assert app.help_window.open if hasattr(app.help_window, "open") else True
    text = (GUI / "help.md").read_text(encoding="utf-8")
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    import re

    for link in re.findall(r"\]\((docs/[^)#]+)\)", text):
        assert (repo / link).is_file(), link


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("ai_settings")
    assert result["ok"], result["output"]


def test_manifest_keeps_both_entrypoints():
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["gui"].endswith("gui.tool:AISettingsWidget")
    assert (
        manifest["entrypoints"]["emtk"]
        == "chisurf.plugins.ai_settings.gui.app:make_ai_settings_app"
    )
    from chisurf.plugins.ai_settings.gui.app import make_ai_settings_app
    from chisurf.plugins.ai_settings.gui.app import make_app as alias

    assert make_ai_settings_app is alias
    app = make_ai_settings_app()
    frames(app)
    app.close()
