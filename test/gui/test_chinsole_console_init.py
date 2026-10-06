"""The console's start-up snippet without matplotlib installed."""

from __future__ import annotations

import importlib.util

from chisurf.gui.chinsole import settings as chinsole_settings

OLD_DEFAULT = (
    "%matplotlib inline\n\n    %config Completer.use_jedi = False\n\n"
    "    get_ipython().cache_size = 0\n\n    import pylab as p\n\n    "
)


def test_matplotlib_lines_are_dropped_when_matplotlib_is_absent(monkeypatch):
    """Old settings files start with %matplotlib/pylab; without matplotlib they
    would only print a traceback into every new console."""
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *a: None if name == "matplotlib" else real(name, *a),
    )
    out = chinsole_settings._without_absent_matplotlib(OLD_DEFAULT)
    assert "matplotlib" not in out and "pylab" not in out
    assert "%config Completer.use_jedi = False" in out
    assert "get_ipython().cache_size = 0" in out


def test_matplotlib_lines_run_as_written_when_installed(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: object())
    assert chinsole_settings._without_absent_matplotlib(OLD_DEFAULT) == OLD_DEFAULT


def test_the_shipped_default_asks_for_no_matplotlib():
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "chisurf/core/settings/settings_chisurf.yaml").read_text())

    def find(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if k == "console_init":
                    return v
                r = find(v)
                if r is not None:
                    return r
        return None

    value = find(cfg) or ""
    assert "matplotlib" not in value and "pylab" not in value
