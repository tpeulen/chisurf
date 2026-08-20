"""Every plugin a manifest declares must actually load.

This file used to be a *script*: module-level prints that imported each
top-level plugin package, counted successes and asserted nothing. pytest
collected no tests from it, so it reported "21 plugins loaded" to nobody while
the tree grew to ~100 plugins in subdirectories it never looked at.

What matters is the manifest: it is the contract the registry reads, and each
``entrypoints`` value names a module and an object the application will import
at load time. A rename on either side turns into a plugin that quietly fails to
appear in the menu, which is exactly the kind of failure nothing else catches.
"""
from __future__ import annotations

import importlib
import json
import pathlib

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "plugins"

#: Plugins whose entrypoints may legitimately fail to import here, and why.
OPTIONAL: dict[str, str] = {
    "quenching_estimator": "needs the optional QuEsT extension (modules/quest)",
}


def _manifests() -> list[pathlib.Path]:
    """Return every plugin manifest, excluding scaffolds and test fixtures.

    ``manifest.json`` is a common enough name that a plugin's own test data can
    claim it — ChiMOL's render baselines index their scenes in one — and such a
    file is not a plugin manifest in any sense the tests below mean. Matching it
    fails every assertion about ids, entrypoints and menu paths, for a file that
    correctly has none of those.
    """
    return sorted(
        p for p in PLUGIN_ROOT.rglob("manifest.json")
        if "{{" not in str(p)  # the plugin template, not a plugin
        and not {"test", "tests"} & set(p.relative_to(PLUGIN_ROOT).parts)
    )


def _entrypoint_targets(manifest: dict) -> list[tuple[str, str, str]]:
    """Return ``(kind, module, object)`` for each declared entrypoint.

    A CLI entry is written ``name=module:object``; the others are plain
    ``module:object``.
    """
    out = []
    for kind, spec in (manifest.get("entrypoints") or {}).items():
        if not isinstance(spec, str) or not spec:
            continue
        if kind == "script":
            # ``script`` names a file the menu *executes*, not a module it
            # imports. Checked as a file below, not resolved through importlib.
            continue
        target = spec.split("=", 1)[1] if "=" in spec else spec
        module, _, obj = target.partition(":")
        out.append((kind, module.strip(), obj.strip()))
    return out


@pytest.mark.parametrize(
    "manifest_path", _manifests(), ids=lambda p: p.parent.name
)
def test_plugin_entrypoints_import(manifest_path: pathlib.Path):
    """Each declared entrypoint imports and exposes the object it names."""
    manifest = json.loads(manifest_path.read_text())
    plugin_id = manifest.get("id") or manifest_path.parent.name
    if plugin_id in OPTIONAL:
        pytest.skip(f"{plugin_id}: {OPTIONAL[plugin_id]}")

    problems = []
    for kind, module, obj in _entrypoint_targets(manifest):
        try:
            mod = importlib.import_module(module)
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            problems.append(f"{kind}: {module} -> {type(exc).__name__}: {exc}")
            continue
        if obj and not hasattr(mod, obj):
            problems.append(f"{kind}: {module} has no {obj!r}")

    script = (manifest.get("entrypoints") or {}).get("script")
    if script and not (manifest_path.parent / script).is_file():
        problems.append(f"script: {script} is not a file in the plugin directory")

    assert not problems, (
        f"{plugin_id} declares entrypoints that do not resolve, so the plugin "
        f"cannot load:\n  " + "\n  ".join(problems)
    )


def test_every_plugin_declares_an_id():
    """A manifest without an id cannot be addressed by the registry."""
    missing = [
        str(p.relative_to(PLUGIN_ROOT.parent.parent))
        for p in _manifests()
        if not json.loads(p.read_text()).get("id")
    ]
    assert not missing, "manifests without an 'id':\n  " + "\n  ".join(missing)
