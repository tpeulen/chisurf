"""No Qt allowed in emtk plugins — enforced, not assumed.

Every manifest declaring an ``entrypoints.emtk`` must import its factory in a
process where Qt cannot load. A single violation (an eager ``from qtpy import
...`` anywhere in the factory's import chain) breaks the plugin on hosts
without Qt and silently pulls a GUI toolkit into headless tooling. The
authoritative scan lives in ``build_tools/dev_utils/emtk_migration/check_native.py``; this test
runs the same import gate over all declared factories in one batched
subprocess so it stays in regular CI.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]

_PROBE = r'''
import json, sys

class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}:
            raise ImportError("Qt forbidden: " + fullname)
        return None

sys.meta_path.insert(0, BlockQt())

spec = json.loads(sys.argv[1])
failures = {}
for module_name, attribute in spec:
    try:
        module = __import__(module_name, fromlist=[attribute])
        factory = getattr(module, attribute)
        if not callable(factory):
            failures[module_name] = "factory is not callable"
    except Exception as exc:
        failures[f"{module_name}:{attribute}"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(failures))
'''


def _factories() -> list[tuple[str, str]]:
    spec: list[tuple[str, str]] = []
    for manifest_path in sorted((ROOT / "chisurf" / "plugins").rglob("manifest.json")):
        if "cookiecutter" in str(manifest_path):
            continue
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        native = data.get("entrypoints", {}).get("emtk")
        if native and ":" in native:
            module_name, _, attribute = native.partition(":")
            spec.append((module_name, attribute))
    return spec


def test_emtk_plugin_factories_import_without_qt():
    factories = _factories()
    assert len(factories) >= 100, (
        f"only {len(factories)} native factories discovered; the manifest glob broke"
    )
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(factories)],
        capture_output=True,
        text=True,
        timeout=900,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"probe crashed: {proc.stderr[-2000:]}"
    failures = json.loads(proc.stdout.strip().splitlines()[-1])
    assert not failures, (
        f"{len(failures)} of {len(factories)} emtk factories import Qt:\n"
        + "\n".join(f"  {k}: {v}" for k, v in sorted(failures.items())[:20])
    )
