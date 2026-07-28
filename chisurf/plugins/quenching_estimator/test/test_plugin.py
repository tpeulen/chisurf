"""The plugin declares QuEst; it must not reimplement or eagerly import it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((PLUGIN_DIR / "manifest.json").read_text(encoding="utf8"))


def _quest_manifest() -> dict:
    import quest

    return json.loads(
        (Path(quest.__file__).parent / "manifest.json").read_text(encoding="utf8")
    )


class TestTheManifest:
    """`LAY-05`'s ChiSurf half: the plugin had no manifest at all and loaded
    through the host's legacy AST discovery."""

    def test_it_declares_the_three_entry_points(self) -> None:
        entrypoints = MANIFEST["entrypoints"]
        assert entrypoints["gui"].endswith(":QuEstTool")
        assert "register_services" in entrypoints["services"]
        assert entrypoints["cli"].startswith("quest=")

    def test_the_method_table_is_quests_verbatim(self) -> None:
        """Copied, not restated.

        A second hand-maintained list of methods is the drift this split exists
        to remove — if QuEst adds a method and this file is not regenerated,
        this fails rather than a host discovering the gap.
        """
        assert MANIFEST["rpc_methods"] == _quest_manifest()["rpc_methods"]

    def test_it_declares_what_the_registry_will_register(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import (
            registered_method_names,
        )

        assert {m["name"] for m in MANIFEST["rpc_methods"]} == set(
            registered_method_names()
        )

    def test_the_version_tracks_quest(self) -> None:
        assert MANIFEST["version"] == _quest_manifest()["version"]


class TestItDoesNotImportQuestAtStartup:
    """ChiSurf imports every plugin at discovery.

    The previous single-file plugin did `from quest.gui import
    TransientDecayGenerator` at module scope, so launching ChiSurf pulled in
    QuEst, IMP and numba whether or not anyone opened the tool — and a broken
    QuEst install became a broken ChiSurf startup.
    """

    def test_importing_the_plugin_does_not_import_quest(self) -> None:
        script = (
            "import sys\n"
            "import chisurf.plugins.quenching_estimator as plugin\n"
            "leaked = sorted(m for m in sys.modules if m.split('.')[0] in {'quest', 'IMP'})\n"
            "print('LEAKED:' + ','.join(leaked))\n"
            "assert plugin.icon\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stderr[-2000:]
        leaked = [
            line[len("LEAKED:"):]
            for line in result.stdout.splitlines()
            if line.startswith("LEAKED:")
        ][0]
        assert leaked == "", f"importing the plugin pulled in: {leaked}"

    def test_the_rpc_module_is_also_clean(self) -> None:
        script = (
            "import sys\n"
            "import chisurf.plugins.quenching_estimator.rpc.services as services\n"
            "leaked = sorted(m for m in sys.modules if m.split('.')[0] in {'quest', 'IMP'})\n"
            "print('LEAKED:' + ','.join(leaked))\n"
            "assert callable(services.register_services)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=300
        )
        assert result.returncode == 0, result.stderr[-2000:]
        leaked = [
            line[len("LEAKED:"):]
            for line in result.stdout.splitlines()
            if line.startswith("LEAKED:")
        ][0]
        assert leaked == "", f"importing rpc.services pulled in: {leaked}"


class TestTheServicesRegisterIntoAHostDispatcher:
    def test_quests_handlers_serve_the_host(self) -> None:
        """No handler is written in the plugin.

        `quest.backend.services.register_services` is duck-typed on
        `register(name, handler)` for exactly this, so both surfaces run the
        same code rather than two copies that can drift (`LAY-01`).
        """
        from chisurf.plugins.quenching_estimator.rpc.services import register_services

        registered: dict[str, object] = {}

        class Dispatcher:
            def register(self, name, handler):
                registered[name] = handler

        register_services(Dispatcher())
        assert "quest.simulate" in registered
        assert "quest.contract.describe" in registered
        assert callable(registered["quest.simulate"])

    def test_a_registered_method_actually_runs(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import register_services

        registered: dict[str, object] = {}

        class Dispatcher:
            def register(self, name, handler):
                registered[name] = handler

        register_services(Dispatcher())
        response = registered["quest.template"]({"with_fret": False})
        assert response["ok"] is True
        assert response["result"]["project"]["fret"]["enabled"] is False


class TestTheContractIsQuestsOwn:
    def test_it_reexports_rather_than_restates(self) -> None:
        from quest.backend.contract import CONTRACT_VERSION, ERROR_CODES

        from chisurf.plugins.quenching_estimator.api import contract

        assert contract.CONTRACT_VERSION == CONTRACT_VERSION
        assert contract.ERROR_CODES == ERROR_CODES

    def test_the_descriptor_names_the_host_surface(self) -> None:
        from chisurf.plugins.quenching_estimator.api import contract

        descriptor = contract.contract_descriptor()
        assert descriptor["host_plugin_id"] == "quenching_estimator"
        assert descriptor["transport"]["gui"].endswith(":QuEstTool")


class TestTheGuiIsDockable:
    def test_it_is_a_chisurf_dock_tool(self, qapp) -> None:
        """Not a QMainWindow used as a central widget."""
        from chisurf.gui.widgets.tools import ChisurfDockTool
        from chisurf.plugins.quenching_estimator import QuEstTool

        assert issubclass(QuEstTool, ChisurfDockTool)

    def test_the_old_name_is_the_same_widget(self) -> None:
        from chisurf.plugins.quenching_estimator import QuEstTool, QuEstWindow

        assert QuEstWindow is QuEstTool


class TestTheToolbarDoesNotRepeatTheForm:
    """The embedded form has its own footer: Simulate, Load project, Save project.

    A first draft of the toolbar repeated the last two. Caught by rendering the
    widget and looking at the image — no assertion would have.
    """

    def test_it_only_adds_what_the_form_lacks(self, qapp) -> None:
        from qtpy import QtWidgets

        from chisurf.plugins.quenching_estimator import QuEstTool

        tool = QuEstTool()
        labels = {
            action.text()
            for bar in tool.findChildren(QtWidgets.QToolBar)
            for action in bar.actions()
            if action.text()
        }
        assert labels == {"Load PDB…"}
        assert not {"Load project…", "Save project…"} & labels
