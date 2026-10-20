"""The plugin's shape: its manifest, its method table, and that nothing heavy is imported at discovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

PLUGIN_DIR = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((PLUGIN_DIR / "manifest.json").read_text(encoding="utf8"))


class TestTheManifest:
    """`LAY-05`'s ChiSurf half: the plugin had no manifest at all and loaded
    through the host's legacy AST discovery.
    """

    def test_it_declares_the_three_entry_points(self) -> None:
        entrypoints = MANIFEST["entrypoints"]
        assert entrypoints["emtk"].endswith(".gui.app:make_app")
        assert "register_services" in entrypoints["services"]
        assert entrypoints["cli"].startswith("quest=")

    def test_it_declares_what_the_registry_will_register(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import (
            registered_method_names,
        )

        assert {m["name"] for m in MANIFEST["rpc_methods"]} == set(registered_method_names())


def _preloaded() -> set[str]:
    """What an empty interpreter of this environment already has of IMP.

    A ``.pth`` file of an editable install can import the ``IMP`` namespace package at
    interpreter start; that is the environment's, not the plugin's.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; print('PRE:' + ','.join(m for m in sys.modules "
            "if m.split('.')[0] in {'IMP'}))",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    line = next(l for l in result.stdout.splitlines() if l.startswith("PRE:"))
    return {name for name in line[len("PRE:") :].split(",") if name}


class TestItDoesNotImportTheEngineAtStartup:
    """ChiSurf imports every plugin at discovery.

    The engine (``core/``) reaches IMP; importing the plugin, or its RPC
    module, must not, or every ChiSurf start pays for IMP whether or not anyone
    opens the tool.
    """

    def test_importing_the_plugin_does_not_import_imp(self) -> None:
        script = (
            "import sys\n"
            "import chisurf.plugins.quenching_estimator as plugin\n"
            "leaked = sorted(m for m in sys.modules if m.split('.')[0] in {'IMP'})\n"
            "print('LEAKED:' + ','.join(leaked))\n"
            "assert plugin.icon\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stderr[-2000:]
        leaked = [
            line[len("LEAKED:") :]
            for line in result.stdout.splitlines()
            if line.startswith("LEAKED:")
        ][0]
        leaked = ",".join(sorted(set(filter(None, leaked.split(","))) - _preloaded()))
        assert leaked == "", f"importing the plugin pulled in: {leaked}"

    def test_the_rpc_module_is_also_clean(self) -> None:
        script = (
            "import sys\n"
            "import chisurf.plugins.quenching_estimator.rpc.services as services\n"
            "leaked = sorted(m for m in sys.modules if m.split('.')[0] in {'IMP'})\n"
            "print('LEAKED:' + ','.join(leaked))\n"
            "assert callable(services.register_services)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stderr[-2000:]
        leaked = [
            line[len("LEAKED:") :]
            for line in result.stdout.splitlines()
            if line.startswith("LEAKED:")
        ][0]
        leaked = ",".join(sorted(set(filter(None, leaked.split(","))) - _preloaded()))
        assert leaked == "", f"importing rpc.services pulled in: {leaked}"


class TestTheServicesRegisterIntoAHostDispatcher:
    def test_quests_handlers_serve_the_host(self) -> None:
        """`register_services` is duck-typed on `register(name, handler)`, so
        ChiSurf's dispatcher and the plugin's own in-process client run the same
        handlers rather than two copies that can drift."""
        from chisurf.plugins.quenching_estimator.rpc.services import register_services

        registered: dict[str, Callable[..., Any]] = {}

        class Dispatcher:
            def register(self, name, handler):
                registered[name] = handler

        register_services(Dispatcher())
        assert "quest.simulate" in registered
        assert "quest.contract.describe" in registered
        assert callable(registered["quest.simulate"])

    def test_the_manifest_declares_exactly_the_methods_quest_registers(self) -> None:
        """The manifest is the contract's written form: a method on one side only is a dead or undeclared RPC."""
        import json
        from pathlib import Path

        from chisurf.plugins.quenching_estimator.rpc.services import (
            register_services,
            registered_method_names,
        )

        manifest = json.loads(
            (Path(__file__).parents[1] / "manifest.json").read_text(encoding="utf-8")
        )
        declared = {entry["name"] for entry in manifest["rpc_methods"]}
        registered: dict[str, Callable[..., Any]] = {}

        class Dispatcher:
            def register(self, name, handler):
                registered[name] = handler

        register_services(Dispatcher())
        assert declared == set(registered) == set(registered_method_names())
        assert len(declared) == 20

    def test_a_registered_method_actually_runs(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import register_services

        registered: dict[str, Callable[..., Any]] = {}

        class Dispatcher:
            def register(self, name, handler):
                registered[name] = handler

        register_services(Dispatcher())
        response = registered["quest.template"]({"with_fret": False})
        assert response["ok"] is True
        assert response["result"]["project"]["fret"]["enabled"] is False


class TestTheContractIsDefinedOnce:
    def test_it_reexports_rather_than_restates(self) -> None:
        from chisurf.plugins.quenching_estimator.api import contract
        from chisurf.plugins.quenching_estimator.rpc.contract import CONTRACT_VERSION, ERROR_CODES

        assert contract.CONTRACT_VERSION == CONTRACT_VERSION
        assert contract.ERROR_CODES == ERROR_CODES

    def test_the_descriptor_names_the_host_surface(self) -> None:
        from chisurf.plugins.quenching_estimator.api import contract

        descriptor = contract.contract_descriptor()
        assert descriptor["host_plugin_id"] == "quenching_estimator"
        assert descriptor["transport"]["emtk"].endswith(".gui.app:make_app")
