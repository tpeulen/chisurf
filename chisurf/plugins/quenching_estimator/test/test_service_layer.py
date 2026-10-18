"""Tests for the RPC service layer and the layering rules it exists to enforce.

The point of the service layer is that every surface calls the same operation
under the same name and gets the same shape back. These tests pin that
contract, and the guardrails below pin the layering that makes it true.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from chisurf.plugins.quenching_estimator.core.scan import simulate_site, site_project
from chisurf.plugins.quenching_estimator.rpc import (
    METHODS,
    InProcessClient,
    RemoteError,
    ServiceDispatcher,
    local_client,
    register_services,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestRegistry:
    def test_every_documented_method_is_registered(self) -> None:
        dispatcher = ServiceDispatcher()
        register_services(dispatcher)
        assert dispatcher.methods == sorted(METHODS)

    def test_registering_a_name_twice_is_refused(self) -> None:
        """One operation, one name: a silent overwrite would depend on import order."""
        dispatcher = ServiceDispatcher()
        register_services(dispatcher)
        with pytest.raises(ValueError):
            register_services(dispatcher)

    def test_unknown_method_fails_without_raising(self) -> None:
        response = local_client().call("quest.does_not_exist")
        assert response == {
            "ok": False,
            "error": "Unknown method: quest.does_not_exist",
            # A host branches on the code, never on the message. Added
            # 2026-07-28 with the contract; the envelope previously carried no
            # code at all, so improving a message was a breaking change.
            "error_code": "unknown_method",
        }

    def test_a_raising_handler_becomes_a_failure_envelope(self) -> None:
        dispatcher = ServiceDispatcher()

        def boom(params):
            raise KeyError("nope")

        dispatcher.register("quest.boom", boom)
        response = dispatcher.dispatch("quest.boom")
        assert response["ok"] is False
        assert "KeyError" in response["error"]

    def test_result_raises_on_failure(self) -> None:
        client = local_client()
        with pytest.raises(RemoteError):
            client.result("quest.validate", {"project": {"tau0": 1.0}})


class TestMethods:
    def test_template_round_trips_through_validate(self) -> None:
        client = local_client()
        project = client.result("quest.template", {"with_fret": True})["project"]
        # The template names a structure that does not exist, so validation is
        # asked about everything else by supplying a resolvable override.
        project.pop("pdb")
        response = client.call("quest.validate", {"project": project})
        assert response["ok"] is False
        assert "pdb" in response["error"]

    def test_template_without_fret(self) -> None:
        project = local_client().result("quest.template", {"with_fret": False})["project"]
        assert project["fret"]["enabled"] is False
        assert len(project["fret"]["dyes"]) == 1

    def test_validate_names_every_missing_key(self) -> None:
        response = local_client().call("quest.validate", {"project": {"tau0": 1.0}})
        assert response["ok"] is False
        for key in ("n_photons", "t_max", "dg", "amino_acid_interactions"):
            assert key in response["error"]

    def test_parameter_catalog_is_the_shipped_one(self) -> None:
        catalog = local_client().result("quest.parameter_catalog")
        assert catalog["version"] == 1
        assert "pdb" in catalog["parameters"]

    def test_dyes_carry_complete_stickiness(self) -> None:
        dyes = local_client().result("quest.dyes.list")
        assert "Alexa488" in dyes
        for dye in dyes.values():
            assert "slow_radius" in dye
            assert "TRP" in dye["amino_acid_interactions"]

    def test_saving_a_nameless_dye_fails(self) -> None:
        response = local_client().call("quest.dyes.save", {"dye": {"tau0": 4.0}})
        assert response["ok"] is False
        assert "name" in response["error"]

    def test_quenching_defaults_expose_the_pet_chemistry(self) -> None:
        defaults = local_client().result("quest.quenching_defaults")
        assert len(defaults["residues"]) == 20
        assert set(defaults["reference_pet_quenching"]) == {
            "TRP",
            "TYR",
            "MET",
            "HIS",
            "CYS",
            "PRO",
        }
        # The quenching centre of TRP is the indole ring, not CB.
        assert "NE1" in defaults["default_quench_atoms"]["TRP"]


class TestScanRecordShape:
    """Every surface reports a site the same way, success or failure."""

    POSITION = {
        "chain_identifier": "A",
        "residue_seq_number": 12,
        "atom_name": "CB",
        "residue_name": "TRP",
    }

    def test_failure_and_success_records_have_the_same_keys(self) -> None:
        failed = simulate_site({}, self.POSITION, name="site-1")
        assert failed["status"] == "failed"
        assert failed["error"]
        # A failure carries the full key set with nulls, so a table of results
        # never has ragged rows.
        expected = {
            "name",
            "chain",
            "residue",
            "residue_name",
            "atom",
            "status",
            "error",
            "lifetime",
            "quantum_yield",
            "contact_fraction",
            "av_volume",
            "contact_volume",
            "contact_to_free_ratio",
            "dominant_quencher",
            "dominant_quencher_fraction",
            "quenchers",
        }
        assert set(failed) == expected

    def test_failure_reports_which_site_failed(self) -> None:
        failed = simulate_site({}, self.POSITION, name="site-1")
        assert failed["name"] == "site-1"
        assert failed["chain"] == "A"
        assert failed["residue"] == 12
        assert failed["residue_name"] == "TRP"

    def test_site_project_moves_the_attachment_and_the_donor_dye(self) -> None:
        base: dict[str, Any] = {
            "av_parameter": {"linker_length": 21.5},
            "fret": {"enabled": True, "dyes": [{"name": "donor", "D": 7.5}, {"name": "acceptor"}]},
        }
        site = site_project(base, {**self.POSITION, "linker_length": 30.0})

        assert site["attachment"] == {"chain": "A", "residue": 12, "atom": "CB"}
        assert site["av_parameter"]["linker_length"] == 30.0
        donor = site["fret"]["dyes"][0]
        assert donor["attachment"] == site["attachment"]
        assert donor["av_parameter"]["linker_length"] == 30.0
        # The acceptor is left alone, and the caller's project is not mutated.
        assert site["fret"]["dyes"][1] == {"name": "acceptor"}
        assert base["av_parameter"] == {"linker_length": 21.5}
        assert "attachment" not in base["fret"]["dyes"][0]

    def test_grid_resolution_maps_onto_dg(self) -> None:
        site = site_project({}, {**self.POSITION, "simulation_grid_resolution": 0.4})
        assert site["dg"] == 0.4
        assert "simulation_grid_resolution" not in site["av_parameter"]


class TestManifest:
    """The manifest is what a host learns QuEst from without importing it."""

    @staticmethod
    def _manifest() -> dict:
        return json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf8"))

    def test_identity_matches_the_contract(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.contract import PLUGIN_ID

        assert self._manifest()["id"] == PLUGIN_ID == "quenching_estimator"

    def test_declared_methods_are_exactly_the_registered_ones(self) -> None:
        """A manifest that over- or under-declares is a lie a host acts on."""
        declared = {method["name"] for method in self._manifest()["rpc_methods"]}
        assert declared == set(METHODS)

    def test_declared_summaries_match_the_registry(self) -> None:
        for method in self._manifest()["rpc_methods"]:
            assert method["summary"] == METHODS[method["name"]], method["name"]

    def test_every_method_documents_its_shapes(self) -> None:
        for method in self._manifest()["rpc_methods"]:
            assert method["params_schema"].get("type") == "object", method["name"]
            assert method["result_schema"], method["name"]

    def test_the_long_running_methods_are_flagged(self) -> None:
        flags = {m["name"]: m["long_running"] for m in self._manifest()["rpc_methods"]}
        assert flags["quest.simulate"] is True
        assert flags["quest.scan"] is True
        assert flags["quest.template"] is False

    def test_entrypoints_resolve(self) -> None:
        import importlib

        for kind, target in self._manifest()["entrypoints"].items():
            module_name, _, attribute = target.split("=", 1)[-1].partition(":")
            module = importlib.import_module(module_name)
            assert hasattr(module, attribute), target


class TestSurfacesShareTheChemistry:
    """The GUI once shipped its own quenching model; it must not again.

    These run without Qt: they check the data the widget is built from, which
    is where the divergence lived (a settings file with every quencher on CB
    and one global rate). `tests/test_gui_widget.py` checks the widget itself
    wherever a Qt binding exists.
    """

    def test_the_gui_has_no_settings_file_of_its_own(self) -> None:
        """There is no second place for the GUI's chemistry to live.

        `dye_diffusion.json` used to seed the form, and it pinned a *legacy*
        chemistry — every quencher on CB with one global rate — so the desktop
        surface simulated something no other surface did. It is gone: the form
        starts from `template_project()` like everything else.
        """
        assert not (REPO_ROOT / "gui" / "dye_diffusion.json").exists()

        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        project = ProjectFormModel().to_project_dict()
        assert project["critical_distance"] == 8.5
        assert "quencher" not in project, "the legacy chemistry block came back"

    def test_the_gui_default_table_matches_the_reference_chemistry(self) -> None:
        from chisurf.plugins.quenching_estimator.core.dye_diffusion import (
            DEFAULT_QUENCHER_ATOMS,
            REFERENCE_PET_QUENCHING,
            default_quencher_table,
        )

        table = default_quencher_table()
        assert set(table) == set(REFERENCE_PET_QUENCHING)
        for residue, entry in table.items():
            assert entry["atoms"] == list(DEFAULT_QUENCHER_ATOMS[residue]), residue
            assert entry["kQ"] == REFERENCE_PET_QUENCHING[residue]["kQ"], residue
        assert table["MET"]["atoms"] == ["SD"]
        assert table["TRP"]["kQ"] == 3.5


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


class TestLayering:
    """Guardrails for the rules in okf/specs/plugin-integration.md."""

    def test_the_library_does_not_import_the_cli(self) -> None:
        # __main__.py is the console entry point; importing the CLI is its job.
        for path in REPO_ROOT.rglob("*.py"):
            parts = path.relative_to(REPO_ROOT).parts
            if path.name == "__main__.py" or parts[0] in {"cli", "test"}:
                continue
            source = path.read_text(encoding="utf8")
            assert "from quest.cli import" not in source, path
            assert "from .cli import" not in source, path

    def test_importing_the_domain_does_not_import_qt(self) -> None:
        """Structural, not by convention: Qt lives in `quest.gui` and nowhere else.

        Run in a subprocess because this test session may already have imported
        a Qt binding for the widget tests.
        """
        import subprocess
        import sys

        code = (
            "import sys, chisurf.plugins.quenching_estimator.api.local, chisurf.plugins.quenching_estimator.rpc, chisurf.plugins.quenching_estimator.core;"
            "loaded = [m for m in sys.modules if m.split('.')[0] in "
            "('qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6')];"
            "print(','.join(sorted(set(loaded))))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT.parents[2], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.strip() == "", (
            f"importing the domain pulled in a Qt binding: {result.stdout.strip()}"
        )

    def test_importing_the_domain_does_not_import_imp(self) -> None:
        """IMP is a hard dependency but must still be loaded *lazily*.

        Not a matter of taste or start-up time. A child of a process that has
        already loaded IMP resolves `libimp_kernel` against the wrong
        `libboost_filesystem` (okf/references/known-issues.md), so a
        module-scope `import IMP.bff` anywhere in the domain would turn a
        latent environment fault into a hard failure of the service layer —
        including of the subprocess-based tests above.

        Every `IMP.bff` use in `quest.core` is therefore inside a function.
        """
        import subprocess
        import sys

        code = (
            # What the interpreter has before the domain is imported (an editable
            # install's .pth can load the IMP namespace at start) is not the domain's.
            "import sys; pre = {m for m in sys.modules if m.split('.')[0] == 'IMP'};"
            "import chisurf.plugins.quenching_estimator.api.local, chisurf.plugins.quenching_estimator.rpc, chisurf.plugins.quenching_estimator.core;"
            "loaded = [m for m in sys.modules if m.split('.')[0] == 'IMP' and m not in pre];"
            "print(','.join(sorted(set(loaded))))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT.parents[2], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr[-2000:]
        assert result.stdout.strip() == "", (
            f"importing the domain pulled IMP in: {result.stdout.strip()}"
        )

    def test_the_service_layer_is_gui_free(self) -> None:
        """The backend must import without any Qt binding present."""
        for name in ("dispatcher.py", "services.py", "contract.py", "__init__.py"):
            modules = _imported_modules(REPO_ROOT / "rpc" / name)
            assert not any(m.startswith(("qtpy", "PyQt5", "PySide")) for m in modules)
