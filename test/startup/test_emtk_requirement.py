"""ChiSurf refuses a too-old emtk at startup instead of opening a window that draws nothing.

The defect: chisurf HEAD called ``DockManager.focused`` while the environment held an emtk
without it. Every frame raised, the event loop swallowed it, and the window showed solid
magenta. The minimum is declared once (``EMTK_MIN_VERSION``) and checked before any window.
"""

from __future__ import annotations

import pathlib
import re
import sys
import types

import pytest

from chisurf.emtk import requirement

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _fake_emtk(monkeypatch, version, commit=None):
    module = types.ModuleType("emtk")
    module.__version__ = version
    module.__file__ = "/somewhere/site-packages/emtk/__init__.py"
    module.version_info = lambda: {"version": version, "commit": commit}
    monkeypatch.setitem(sys.modules, "emtk", module)


def test_a_too_old_emtk_is_refused_naming_both_versions(monkeypatch):
    _fake_emtk(monkeypatch, "0.1.7", commit="e0f8b67")
    with pytest.raises(requirement.EmtkTooOld) as caught:
        requirement.check_emtk("0.1.8")
    message = str(caught.value)
    assert ">= 0.1.8" in message
    assert "0.1.7" in message and "e0f8b67" in message
    assert "/somewhere/site-packages/emtk" in message


def test_an_emtk_without_version_info_is_still_judged(monkeypatch):
    module = types.ModuleType("emtk")
    module.__version__ = "0.1.6"
    monkeypatch.setitem(sys.modules, "emtk", module)
    with pytest.raises(requirement.EmtkTooOld):
        requirement.check_emtk("0.1.8")


def test_a_new_enough_emtk_passes(monkeypatch):
    _fake_emtk(monkeypatch, "0.2.0")
    assert requirement.check_emtk("0.1.8")["version"] == "0.2.0"


def test_main_exits_with_the_message_before_opening_a_window(monkeypatch, capsys):
    import chisurf.__main__ as entry

    _fake_emtk(monkeypatch, "0.1.7", commit="e0f8b67")
    monkeypatch.setattr(sys, "argv", ["chisurf"])
    opened = []
    monkeypatch.setattr(entry, "_run_with_crash_log", lambda launch: opened.append(launch))
    with pytest.raises(SystemExit) as caught:
        entry.main()
    assert caught.value.code == 2
    assert opened == [], "no window may open against a too-old emtk"
    assert "emtk 0.1.7 (commit e0f8b67)" in capsys.readouterr().err


def test_the_installed_emtk_satisfies_the_tree():
    pytest.importorskip("emtk")
    requirement.check_emtk()


def test_the_packaging_bounds_match_the_declared_minimum():
    minimum = requirement.EMTK_MIN_VERSION
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(rf'"emtk>={re.escape(minimum)}"', pyproject), "pyproject.toml emtk bound"
    recipe = (ROOT / "rattler-recipe" / "recipe.yaml").read_text()
    assert re.search(rf"- emtk >={re.escape(minimum)}\s*$", recipe, re.M), "recipe emtk bound"
