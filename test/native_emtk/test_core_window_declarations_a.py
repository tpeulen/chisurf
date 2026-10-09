"""Core host declarations preserve actual defaults and saved window preferences."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from chisurf.emtk.state import attach_native_state

CASES = [
    ("batch_analysis", "gui.app", "make_app", "gui/batch_emtk.view.json", (1200, 800)),
    ("boarding", "app", "make_app", "boarding_emtk.view.json", (1200, 800)),
    ("code_editor", "gui.editor_app", "make_editor_app", "gui/editor_app.view.json", (1200, 800)),
    ("f_test", "gui.app", "make_app", "gui/ftest.view.json", (1200, 800)),
    ("globalview", "gui.app", "make_app", "gui/globalview.view.json", (1200, 800)),
    ("help", "gui.help_app", "make_help_app", "gui/help_app.view.json", (800, 600)),
    ("hmm", "gui.app", "make_app", "gui/hmm_emtk.view.json", (1200, 800)),
    ("lightpath_simulator", "gui.app", "create_app", "gui/lightpath.view.json", (1200, 800)),
    ("mmfdb_admin", "gui.app", "make_app", "gui/admin.view.json", (1200, 800)),
    ("model_manager", "gui.app", "make_app", "gui/models_emtk.view.json", (1200, 800)),
]
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(params=CASES, ids=[case[0] for case in CASES])
def tool(request, tmp_path, monkeypatch):
    """Isolate persisted preferences and project discovery for each real factory."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.chdir(tmp_path)
    name, module, factory, resource, size = request.param
    owner = importlib.import_module(f"chisurf.plugins.core.{name}.{module}")
    path = REPO / "chisurf/plugins/core" / name / resource
    return name, owner, factory, path, size


def close(app):
    """Release real application resources where the app owns them."""
    callback = getattr(app, "close", None)
    if callable(callback):
        callback()


def test_real_factory_declares_unchanged_host_default(tool):
    """An empty preference store preserves the previously effective host size."""
    name, owner, factory, path, size = tool
    declaration = json.loads(path.read_text(encoding="utf-8"))["window"]
    app = getattr(owner, factory)()
    try:
        assert declaration == dict(zip(("width", "height"), size))
        assert app.window_size == size
        attach_native_state(name, app)
        assert app.window_size == size
    finally:
        close(app)


def test_real_factory_consumes_changed_authored_dimensions(tool, tmp_path, monkeypatch):
    """The existing resource reader consumes a changed JSON declaration."""
    name, owner, factory, path, _ = tool
    document = json.loads(path.read_text(encoding="utf-8"))
    document["window"] = {"width": 1234, "height": 789}
    authored = tmp_path / "authored.view.json"
    authored.write_text(json.dumps(document), encoding="utf-8")
    read_text = Path.read_text
    reads = []

    def read_resource(source, *args, **kwargs):
        """Redirect only this primary resource to a real alternate JSON file."""
        if source.resolve() == path.resolve():
            reads.append(source)
            return read_text(authored, *args, **kwargs)
        return read_text(source, *args, **kwargs)

    try:
        with monkeypatch.context() as patch:
            patch.setattr(Path, "read_text", read_resource)
            # This app deliberately loads its shared form once at module import.
            if name == "lightpath_simulator":
                importlib.reload(owner)
            app = getattr(owner, factory)()
            try:
                assert reads, "The real primary resource must be read"
                assert app.window_size == (1234, 789)
            finally:
                close(app)
    finally:
        if name == "lightpath_simulator":
            importlib.reload(owner)


def test_saved_size_overrides_declaration_without_changing_preferences(tool):
    """Reopening restores resized dimensions through the existing persistence seam."""
    name, owner, factory, _, size = tool
    first = attach_native_state(name, getattr(owner, factory)())
    try:
        assert first.window_size == size
        export = getattr(first, "export_settings", None)
        preferences = export() if callable(export) else None
        first.window_resized(1340, 860)
    finally:
        close(first)
    reopened = attach_native_state(name, getattr(owner, factory)())
    try:
        assert reopened.window_size == (1340, 860)
        if preferences is not None:
            assert reopened.export_settings() == preferences
    finally:
        close(reopened)
