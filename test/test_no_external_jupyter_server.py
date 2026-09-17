"""Guardrail: the external Jupyter notebook server stays removed.

ChiSurf used to spawn ``python -m notebook`` on startup and populate a
Notebooks menu / ribbon category pointing at it. That integration was removed
in 2026-08 — the startup services, the ``start_jupyter_on_startup`` setting,
the ``launch_jupyter_process`` startup path and the ``__jupyter_*`` globals are
all gone. The in-tree notebook editor
(``chisurf/plugins/core/code_editor/``) is unaffected: it is an in-process
nbformat/console feature with no Jupyter server.

These tests fail if any of it silently creeps back, which is the failure mode
that matters here — nothing crashes when the feature returns, the GUI just
quietly starts a server and opens a port again.
"""

from __future__ import annotations

import json
import pathlib

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_startup_services_do_not_declare_a_jupyter_server():
    """No ``gui.start_jupyter`` / ``gui.populate_notebooks`` service exists."""
    services_dir = REPO_ROOT / "chisurf" / "startup" / "services.d"
    ids: list[str] = []
    for config in sorted(services_dir.glob("*.json")):
        payload = json.loads(config.read_text(encoding="utf-8"))
        ids.extend(spec["id"] for spec in payload.get("services", []))
    assert "gui.start_jupyter" not in ids
    assert "gui.populate_notebooks" not in ids


def test_packaged_settings_do_not_declare_jupyter_startup():
    """The ``start_jupyter_on_startup`` setting is gone from the shipped YAML."""
    settings_path = REPO_ROOT / "chisurf" / "core" / "settings" / "settings_chisurf.yaml"
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    gui = data.get("gui", {})
    assert "start_jupyter_on_startup" not in gui


def test_jupyter_entrypoints_are_gone_from_source():
    """No startup entrypoint or launch helper for the external server remains.

    Source scanning rather than importing keeps this Qt-free and fast, and the
    ``_populate_notebooks_menu`` in the code editor is deliberately not matched
    (that one opens the in-tree editor, not a server).
    """
    needles = (
        "def launch_jupyter_process",
        "def get_free_port",
        "def start_jupyter(",
        "def populate_notebooks(",
    )
    sources = [
        REPO_ROOT / "chisurf" / "gui" / "__init__.py",
        REPO_ROOT / "chisurf" / "startup" / "gui_services.py",
    ]
    offenders = []
    for path in sources:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(needle in line for needle in needles):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    assert not offenders, (
        "external Jupyter server code has crept back into the startup path:\n"
        + "\n".join(offenders)
    )
