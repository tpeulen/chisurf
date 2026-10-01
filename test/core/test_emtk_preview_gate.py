"""A plugin opens in emtk by default only once its port is accepted.

``emtk_preview.json`` lists the plugins whose emtk entrypoint is declared but not accepted: auto
mode keeps their Qt tool, the ``emtk`` mode still opens the preview. The guard tests keep the list
honest: it names real plugins that have both entrypoints, and no plugin with an accepted report
stays on it.
"""

from __future__ import annotations

import json
import pathlib
import re
from types import SimpleNamespace

import pytest

from chisurf.core.plugin import emtk_readiness

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _manifest(plugin_id: str, emtk: str | None = "pkg.app:make", gui: str | None = "pkg.tool:Tool"):
    return SimpleNamespace(id=plugin_id, entrypoints=SimpleNamespace(emtk=emtk, gui=gui))


def test_the_list_is_read_and_ids_are_strings():
    ids = emtk_readiness.preview_ids()
    assert ids and all(isinstance(i, str) for i in ids)
    assert emtk_readiness.is_preview("switch_user")
    assert not emtk_readiness.is_preview("fcs_channel_preset")
    assert not emtk_readiness.is_preview("model_manager")      # accepted: swapped


def test_a_missing_or_broken_file_means_nothing_is_a_preview(tmp_path, monkeypatch):
    emtk_readiness._read.cache_clear()
    monkeypatch.setattr(emtk_readiness, "PREVIEW_FILE", tmp_path / "absent.json")
    assert emtk_readiness.preview_ids() == frozenset()
    emtk_readiness._read.cache_clear()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    monkeypatch.setattr(emtk_readiness, "PREVIEW_FILE", broken)
    assert emtk_readiness.preview_ids() == frozenset()
    emtk_readiness._read.cache_clear()


def _selector():
    registry = pytest.importorskip("chisurf.core.plugin.registry")
    select = getattr(registry, "select_gui_entrypoint", None)
    if select is None:
        pytest.skip("select_gui_entrypoint is not in this tree")
    return select


def test_a_preview_plugin_opens_qt_in_auto_and_emtk_when_asked():
    select = _selector()
    manifest = _manifest("switch_user")
    assert select(manifest, "auto") == ("qt", "pkg.tool:Tool")
    assert select(manifest, "emtk") == ("emtk", "pkg.app:make")
    assert select(manifest, "qt") == ("qt", "pkg.tool:Tool")


def test_an_accepted_plugin_opens_emtk_in_auto():
    select = _selector()
    assert select(_manifest("fcs_channel_preset"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("model_manager"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("trace_browser"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("user_editor"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("plot_settings"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("ai_settings"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("plugin_manager"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("tttr_lut_tools"), "auto") == ("emtk", "pkg.app:make")
    assert select(_manifest("boarding"), "auto") == ("emtk", "pkg.app:make")


def test_a_preview_plugin_without_a_qt_tool_still_opens_emtk():
    select = _selector()
    assert select(_manifest("switch_user", gui=None), "auto") == ("emtk", "pkg.app:make")


# -- guards ---------------------------------------------------------------------------------
def _manifests():
    found = {}
    for path in (ROOT / "chisurf" / "plugins").rglob("manifest.json"):
        if "cookiecutter" in str(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("id"):
            found[data["id"]] = data
    return found


def test_every_preview_id_is_a_real_plugin_with_both_entrypoints():
    manifests = _manifests()
    for plugin_id in sorted(emtk_readiness.preview_ids()):
        assert plugin_id in manifests, f"{plugin_id}: no plugin with this id"
        entry = manifests[plugin_id].get("entrypoints", {})
        assert entry.get("emtk") and entry.get("gui"), (
            f"{plugin_id}: a preview needs both entrypoints (a plugin with only one has nothing to gate)"
        )


def test_no_plugin_with_an_accepted_report_stays_a_preview():
    """Accepted = a REPORT*.md in okf/plugins/emtk-ports/<id>/ whose review says "Accepted"."""
    accepted = set()
    for report in (ROOT / "okf" / "plugins" / "emtk-ports").glob("*/REPORT*.md"):
        text = report.read_text(encoding="utf-8")
        if re.search(r"\*\*Accepted\*\*|\*\*Accepted\.\*\*", text):
            accepted.add(report.parent.name)
    still_preview = sorted(i for i in emtk_readiness.preview_ids() if i.replace("_", "-") in accepted or i in accepted)
    assert not still_preview, f"accepted but still listed as preview: {still_preview}"
