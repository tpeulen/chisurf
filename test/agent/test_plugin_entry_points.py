"""Every entry point a plugin advertises must resolve.

The assistant discovers plugins through their manifests: it reads what a plugin
claims to offer and then calls it. A manifest that names a module which has
been renamed, or an RPC method no service registers, is worse than a missing
plugin — the agent follows the claim, fails, and has no way to tell a broken
advertisement from its own mistake.

These checks are static: they resolve what the manifests promise without
importing GUI code or starting a server.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import chisurf

PLUGINS = pathlib.Path(chisurf.__file__).parent / "plugins"


def manifests():
    """Return ``(id, path, manifest)`` for every plugin manifest."""
    found = []
    for path in sorted(PLUGINS.rglob("manifest.json")):
        if any(
            part in ("test", "tests") for part in path.relative_to(PLUGINS).parts
        ):  # test data, e.g. render baselines
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:  # noqa: BLE001 - reported as a failure below
            found.append((path.parent.name, path, {"__error__": str(error)}))
            continue
        found.append((str(manifest.get("id") or path.parent.name), path, manifest))
    return found


ALL = manifests()


def test_there_are_plugins_to_check():
    assert len(ALL) > 50, f"only {len(ALL)} manifests found under {PLUGINS}"


def test_every_manifest_is_valid_json():
    broken = [
        f"{path}: {manifest['__error__']}" for _, path, manifest in ALL if "__error__" in manifest
    ]
    assert not broken, "; ".join(broken)


def test_every_manifest_declares_an_id_and_a_description():
    """Both are what the assistant matches a user's request against."""
    incomplete = [
        str(path.parent.relative_to(PLUGINS))
        for _, path, manifest in ALL
        if "__error__" not in manifest and not (manifest.get("id") and manifest.get("description"))
    ]
    assert not incomplete, f"manifests without an id or description: {incomplete}"


def entrypoint_parts(target: object) -> tuple[str, str]:
    """Return ``(module, attribute)`` of an entry point, either possibly "".

    Entry points come in two spellings: ``module:attribute`` for a GUI or a
    service, and the console-script form ``command=module:attribute`` for a
    CLI. A missing one is ``null``.
    """
    if not target:
        return "", ""
    text = str(target)
    if "=" in text.split(":", 1)[0]:
        text = text.split("=", 1)[1]
    module, _, attribute = text.partition(":")
    return module.strip(), attribute.strip()


def entrypoint_module(target: object) -> str:
    """Return only the module half of an entry point."""
    return entrypoint_parts(target)[0]


def test_every_entrypoint_names_a_module_that_exists():
    """An entry point that no longer resolves sends the agent nowhere."""
    import importlib.util

    missing = []
    for name, path, manifest in ALL:
        if "cookiecutter" in str(path):  # a template, not a plugin
            continue
        for kind, target in (manifest.get("entrypoints") or {}).items():
            if kind == "script":
                # A file inside the plugin directory the menu executes, not a module.
                if target and not (path.parent / str(target)).is_file():
                    missing.append(f"{name}.{kind} -> {target}")
                continue
            module = entrypoint_module(target)
            if not module:
                continue
            try:
                if importlib.util.find_spec(module) is None:
                    missing.append(f"{name}.{kind} -> {module}")
            except (ImportError, ValueError, ModuleNotFoundError):
                missing.append(f"{name}.{kind} -> {module}")
    assert not missing, f"entry points naming modules that do not exist: {missing}"


def test_every_rpc_method_is_named_and_unique():
    """A duplicate name means one of the two is unreachable."""
    seen: dict[str, str] = {}
    problems = []
    for name, _path, manifest in ALL:
        for method in manifest.get("rpc_methods") or []:
            if not isinstance(method, dict):
                problems.append(f"{name}: rpc_methods entry is not an object")
                continue
            method_name = str(method.get("name", "")).strip()
            if not method_name:
                problems.append(f"{name}: an rpc_method has no name")
                continue
            if method_name in seen and seen[method_name] != name:
                problems.append(f"{method_name} declared by both {seen[method_name]} and {name}")
            seen[method_name] = name
    assert not problems, "; ".join(problems)


def test_the_agent_sees_every_plugin():
    """Discovery must not quietly drop one."""
    from chisurf.core.agent import AgentContext
    from chisurf.core.agent.tools import codebase

    listed = codebase.list_plugins(AgentContext(working_directory="."))
    assert listed["n_plugins"] == len(ALL)


def test_every_entrypoint_callable_exists():
    """``module:attribute`` must name an attribute that is really there."""
    import importlib

    missing = []
    for name, path, manifest in ALL:
        if "cookiecutter" in str(path):
            continue
        for kind, target in (manifest.get("entrypoints") or {}).items():
            module_name, attribute = entrypoint_parts(target)
            if not module_name or not attribute:
                continue
            try:
                module = importlib.import_module(module_name)
            except Exception:
                continue  # covered by the module test above
            if not hasattr(module, attribute):
                missing.append(f"{name}.{kind} -> {module_name}:{attribute}")
    assert not missing, f"entry points naming callables that do not exist: {missing}"


class _Recorder:
    """Stand-in for the server's ServiceDispatcher."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def register(self, name, handler=None, *args, **kwargs):
        """Record a registered method name."""
        self.names.append(str(name))
        return handler


def test_every_declared_rpc_method_is_actually_registered():
    """The manifest is a promise the service module has to keep.

    A method the assistant is told about but that nothing registers fails only
    at call time, over the wire, with an error that looks like the agent's
    mistake rather than a stale manifest.
    """
    import importlib

    problems = []
    for name, path, manifest in ALL:
        if "cookiecutter" in str(path):
            continue
        declared = [
            str(method.get("name", ""))
            for method in (manifest.get("rpc_methods") or [])
            if isinstance(method, dict)
        ]
        if not declared:
            continue

        module_name, attribute = entrypoint_parts(
            (manifest.get("entrypoints") or {}).get("services")
        )
        if not module_name:
            problems.append(
                f"{name}: declares {len(declared)} rpc_methods but no services entry point"
            )
            continue
        try:
            module = importlib.import_module(module_name)
        except Exception as error:
            problems.append(f"{name}: {module_name} does not import ({type(error).__name__})")
            continue

        register = getattr(module, attribute, None) if attribute else None
        register = (
            register
            or getattr(module, "register_services", None)
            or getattr(module, "register", None)
        )
        if register is None:
            problems.append(f"{name}: {module_name} has no registration function")
            continue

        recorder = _Recorder()
        try:
            register(recorder)
        except Exception as error:
            problems.append(f"{name}: registration raised {type(error).__name__}: {error}")
            continue

        absent = [method for method in declared if method not in recorder.names]
        if absent:
            problems.append(f"{name}: declared but never registered: {absent}")

    assert not problems, "; ".join(problems)


@pytest.mark.parametrize(
    ("plugin_id", "method", "params"),
    [
        (
            "kappa2_dist",
            "kappa2_dist.compute",
            {"model_type": "cone", "r_0": 0.38, "r_Dinf": 0.045, "r_Ainf": 0.1, "r_ADinf": 0.005},
        ),
    ],
)
def test_a_declared_rpc_method_answers(plugin_id, method, params):
    """Spot-check that an advertised computation actually runs head-lessly.

    Static checks prove a manifest is honest about its names; only calling one
    proves the plugin works. Extend this list as workflows come to rely on
    more of them.
    """
    from chisurf.plugins.calculator.kappa2_dist.backend.services import register_services

    handlers: dict = {}
    register_services(
        type("Dispatcher", (), {"register": lambda self, n, h: handlers.__setitem__(n, h)})()
    )

    assert method in handlers, f"{plugin_id} does not register {method}"
    reply = handlers[method](params)
    assert reply.get("ok"), reply
