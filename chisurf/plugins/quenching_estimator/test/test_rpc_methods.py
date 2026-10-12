"""Exhaustive tests for every RPC method QuEst registers.

Every surface — CLI, web backend, desktop GUI, host plugin — calls the same
registry under the same names. This file pins each of the 16 methods through
the in-process transport: its success shape, its error shape, and the JSON
serializability of its payload. The ZMQ wire format is covered separately in
``test_zmq_rpc.py``; the manifest/schema guardrails live in
``test_contract.py`` and ``test_service_layer.py``.

Method list (see ``quest.rpc.services.METHODS``):

    quest.template             quest.runs.list
    quest.validate             quest.runs.get
    quest.simulate             quest.jobs.list
    quest.scan                 quest.jobs.get
    quest.parameter_catalog    quest.jobs.cancel
    quest.locales              quest.contract.describe
    quest.dyes.list
    quest.dyes.save
    quest.quenching_defaults
    quest.structure.metadata
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, MutableMapping

import pytest

from chisurf.plugins.quenching_estimator.rpc import (
    InProcessClient,
    RemoteError,
    ServiceDispatcher,
    local_client,
    to_payload,
)
from chisurf.plugins.quenching_estimator.rpc.services import register_services

REPO_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = REPO_ROOT / "test" / "148l.pdb"


@pytest.fixture(autouse=True)
def _isolate_artefacts(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


@pytest.fixture
def client() -> InProcessClient:
    return local_client()


# E36: labelable under IMP.bff's default AV (linker width 4.5 A). E96, the old fixture, is empty there;
# see okf/references/known-issues.md in ChiSurf ("a third of T4L sites have no AV at the default width").
def _project(residue: int = 36) -> MutableMapping[str, Any]:
    """A minimal valid project pointing at the bundled 148l.pdb."""
    from chisurf.plugins.quenching_estimator.api import local as api

    project = api.template(with_fret=False)
    project["pdb"] = str(STRUCTURE)
    project["attachment"] = {"chain": "E", "residue": residue, "atom": "CB"}
    project["fret"]["dyes"][0]["attachment"] = dict(project["attachment"])
    project["n_photons"] = 200
    project["t_max"] = 50.0
    return project


def _scan_positions() -> dict[str, dict[str, Any]]:
    return {
        "E96": {
            "chain_identifier": "E",
            "residue_seq_number": 96,
            "atom_name": "CB",
            "residue_name": "ALA",
        }
    }


# ---------------------------------------------------------------------------
# quest.template
# ---------------------------------------------------------------------------


class TestTemplate:
    def test_with_fret(self, client) -> None:
        r = client.call("quest.template", {"with_fret": True})
        assert r["ok"] is True
        project = r["result"]["project"]
        assert project["fret"]["enabled"] is True
        assert len(project["fret"]["dyes"]) == 2

    def test_without_fret(self, client) -> None:
        r = client.call("quest.template", {"with_fret": False})
        assert r["ok"] is True
        project = r["result"]["project"]
        assert project["fret"]["enabled"] is False
        assert len(project["fret"]["dyes"]) == 1

    def test_default_is_with_fret(self, client) -> None:
        r = client.call("quest.template")
        assert r["ok"] is True
        assert r["result"]["project"]["fret"]["enabled"] is True

    def test_result_is_json_serialisable(self, client) -> None:
        r = client.call("quest.template", {"with_fret": False})
        json.dumps(to_payload(r["result"]))

    def test_template_project_has_required_keys(self, client) -> None:
        project = client.result("quest.template")["project"]
        for key in (
            "tau0",
            "n_photons",
            "t_max",
            "t_step",
            "dg",
            "critical_distance",
            "amino_acid_interactions",
            "av_parameter",
            "fret",
        ):
            assert key in project, f"template missing {key}"


# ---------------------------------------------------------------------------
# quest.validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_valid_project(self, client) -> None:
        r = client.call("quest.validate", {"project": _project()})
        assert r["ok"] is True
        assert r["result"]["valid"] is True

    def test_malformed_project_returns_error_code(self, client) -> None:
        r = client.call("quest.validate", {"project": {"tau0": 1.0}})
        assert r["ok"] is False
        assert r["error_code"] == "invalid_project"
        assert r["exception_type"] == "ProjectValidationError"

    def test_validate_names_missing_keys(self, client) -> None:
        r = client.call("quest.validate", {"project": {"tau0": 1.0}})
        for key in ("n_photons", "t_max", "dg", "amino_acid_interactions"):
            assert key in r["error"]

    def test_validate_with_pdb_path(self, client) -> None:
        project = _project()
        project.pop("pdb")
        r = client.call(
            "quest.validate",
            {"project": project, "pdb_path": str(STRUCTURE)},
        )
        assert r["ok"] is True

    def test_result_raises_remote_error(self, client) -> None:
        with pytest.raises(RemoteError) as exc:
            client.result("quest.validate", {"project": {"tau0": 1.0}})
        assert exc.value.error_code == "invalid_project"

    def test_valid_result_is_json_serialisable(self, client) -> None:
        r = client.call("quest.validate", {"project": _project()})
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.simulate
# ---------------------------------------------------------------------------


@pytest.mark.needs_av
class TestSimulate:
    def test_simulate_returns_native_arrays(self, client) -> None:
        r = client.call("quest.simulate", {"project": _project()})
        assert r["ok"] is True
        result = r["result"]
        import numpy as np

        assert isinstance(result.donor_counts, np.ndarray)
        assert isinstance(result.time, np.ndarray)
        assert result.time.shape == result.donor_counts.shape

    def test_simulate_payload_is_json(self, client) -> None:
        r = client.call("quest.simulate", {"project": _project()})
        payload = to_payload(r["result"])
        assert isinstance(payload["donor_counts"], list)
        assert isinstance(payload["time_ns"], list)
        json.dumps(payload)

    def test_simulate_malformed_project(self, client) -> None:
        r = client.call("quest.simulate", {"project": {"tau0": 1.0}})
        assert r["ok"] is False
        assert r["error_code"] == "invalid_project"

    def test_simulate_with_explicit_tac_range(self, client) -> None:
        r = client.call(
            "quest.simulate",
            {"project": _project(), "tac_range": [0.0, 25.0]},
        )
        assert r["ok"] is True

    def test_simulate_with_nbins(self, client) -> None:
        r = client.call(
            "quest.simulate",
            {"project": _project(), "nbins": 128},
        )
        assert r["ok"] is True
        assert len(r["result"].donor_counts) == 128

    def test_simulate_save_outputs_creates_job_id(self, client, tmp_path) -> None:
        r = client.call(
            "quest.simulate",
            {
                "project": _project(),
                "save_outputs": True,
                "project_dir": str(tmp_path),
            },
        )
        assert r["ok"] is True
        assert r["result"].job_id is not None


# ---------------------------------------------------------------------------
# quest.scan
# ---------------------------------------------------------------------------


class TestScan:
    def test_scan_single_site(self, client) -> None:
        r = client.call(
            "quest.scan",
            {"project": _project(), "positions": _scan_positions()},
        )
        assert r["ok"] is True
        results = r["result"]["results"]
        assert "E96" in results
        record = results["E96"]
        for key in (
            "name",
            "status",
            "quantum_yield",
            "av_volume",
            "quenchers",
        ):
            assert key in record, f"scan record missing {key}"

    def test_scan_payload_is_json(self, client) -> None:
        r = client.call(
            "quest.scan",
            {"project": _project(), "positions": _scan_positions()},
        )
        json.dumps(to_payload(r["result"]))

    def test_scan_returns_job_id(self, client) -> None:
        r = client.call(
            "quest.scan",
            {"project": _project(), "positions": _scan_positions()},
        )
        assert r["result"]["job_id"] is not None

    def test_scan_malformed_project_produces_failed_records(self, client) -> None:
        """A malformed project does not crash the scan; each site fails gracefully."""
        r = client.call(
            "quest.scan",
            {"project": {"tau0": 1.0}, "positions": _scan_positions()},
        )
        assert r["ok"] is True
        record = r["result"]["results"]["E96"]
        assert record["status"] == "failed"
        assert record["error"]

    def test_scan_empty_positions(self, client) -> None:
        r = client.call("quest.scan", {"project": _project(), "positions": {}})
        assert r["ok"] is True
        assert r["result"]["results"] == {}


# ---------------------------------------------------------------------------
# quest.parameter_catalog
# ---------------------------------------------------------------------------


class TestParameterCatalog:
    def test_returns_catalog(self, client) -> None:
        r = client.call("quest.parameter_catalog")
        assert r["ok"] is True
        catalog = r["result"]
        assert catalog["version"] == 1
        assert "parameters" in catalog
        assert "pdb" in catalog["parameters"]

    def test_with_locale(self, client) -> None:
        r = client.call("quest.parameter_catalog", {"locale": "de"})
        assert r["ok"] is True
        assert r["result"]["version"] == 1

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.parameter_catalog")
        json.dumps(to_payload(r["result"]))

    def test_unknown_locale_falls_back(self, client) -> None:
        r = client.call("quest.parameter_catalog", {"locale": "xx"})
        assert r["ok"] is True


# ---------------------------------------------------------------------------
# quest.locales
# ---------------------------------------------------------------------------


class TestLocales:
    def test_returns_available_languages(self, client) -> None:
        r = client.call("quest.locales")
        assert r["ok"] is True
        result = r["result"]
        assert "available" in result
        assert "en" in result["available"]

    def test_returns_strings(self, client) -> None:
        r = client.call("quest.locales", {"locale": "de"})
        assert r["ok"] is True
        result = r["result"]
        assert result["locale"] == "de"
        assert isinstance(result["strings"], dict)

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.locales")
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.dyes.list
# ---------------------------------------------------------------------------


class TestDyesList:
    def test_returns_dye_presets(self, client) -> None:
        r = client.call("quest.dyes.list")
        assert r["ok"] is True
        dyes = r["result"]
        assert "Alexa488" in dyes

    def test_each_dye_has_required_fields(self, client) -> None:
        dyes = client.result("quest.dyes.list")
        for name, dye in dyes.items():
            assert "tau0" in dye, f"{name} missing tau0"
            assert "slow_radius" in dye, f"{name} missing slow_radius"
            assert "amino_acid_interactions" in dye, f"{name} missing chemistry"

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.dyes.list")
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.dyes.save
# ---------------------------------------------------------------------------


class TestDyesSave:
    def test_nameless_dye_fails(self, client) -> None:
        r = client.call("quest.dyes.save", {"dye": {"tau0": 4.0}})
        assert r["ok"] is False
        assert "name" in r["error"]

    def test_valid_dye_is_saved_and_returned(self, client, monkeypatch) -> None:
        from chisurf.plugins.quenching_estimator import settings

        saved: dict[str, Any] = {}

        original = settings.dye_repository

        def fake_repository():
            dyes = original()
            if saved:
                dyes[saved["name"]] = saved
            return dyes

        def fake_save(dye):
            if "name" not in dye:
                raise ValueError("dye needs a name")
            saved.update(dye)
            return dye

        monkeypatch.setattr(settings, "save_dye", fake_save)
        monkeypatch.setattr(settings, "dye_repository", fake_repository)

        r = client.call(
            "quest.dyes.save",
            {"dye": {"name": "TestFluor", "tau0": 3.5}},
        )
        assert r["ok"] is True


# ---------------------------------------------------------------------------
# quest.quenching_defaults
# ---------------------------------------------------------------------------


class TestQuenchingDefaults:
    def test_returns_defaults(self, client) -> None:
        r = client.call("quest.quenching_defaults")
        assert r["ok"] is True
        defaults = r["result"]
        assert len(defaults["residues"]) == 20

    def test_pet_quenching_residues(self, client) -> None:
        defaults = client.result("quest.quenching_defaults")
        assert set(defaults["reference_pet_quenching"]) == {
            "TRP",
            "TYR",
            "MET",
            "HIS",
            "CYS",
            "PRO",
        }

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.quenching_defaults")
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.structure.metadata
# ---------------------------------------------------------------------------


class TestStructureMetadata:
    def test_valid_structure(self, client) -> None:
        r = client.call("quest.structure.metadata", {"pdb_path": str(STRUCTURE)})
        assert r["ok"] is True
        meta = r["result"]
        assert meta["atom_count"] > 0
        assert "chains" in meta

    def test_nonexistent_path(self, client) -> None:
        r = client.call(
            "quest.structure.metadata",
            {"pdb_path": "/nonexistent/structure.pdb"},
        )
        assert r["ok"] is False

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.structure.metadata", {"pdb_path": str(STRUCTURE)})
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.runs.list / quest.runs.get
# ---------------------------------------------------------------------------


class TestRuns:
    def test_list_empty(self, client) -> None:
        r = client.call("quest.runs.list")
        assert r["ok"] is True
        assert isinstance(r["result"]["runs"], list)

    def test_list_after_simulate(self, client, tmp_path) -> None:
        client.call(
            "quest.simulate",
            {
                "project": _project(),
                "save_outputs": True,
                "project_dir": str(tmp_path),
            },
        )
        r = client.call("quest.runs.list")
        assert r["ok"] is True
        assert len(r["result"]["runs"]) >= 1

    def test_get_missing_run(self, client) -> None:
        r = client.call("quest.runs.get", {"job_id": "nonexistent-uuid"})
        assert r["ok"] is False

    @pytest.mark.needs_av
    def test_get_after_simulate(self, client, tmp_path) -> None:
        sim = client.call(
            "quest.simulate",
            {
                "project": _project(),
                "save_outputs": True,
                "project_dir": str(tmp_path),
            },
        )
        job_id = sim["result"].job_id
        r = client.call("quest.runs.get", {"job_id": job_id})
        assert r["ok"] is True
        assert "project" in r["result"]

    def test_list_json_serialisable(self, client) -> None:
        r = client.call("quest.runs.list")
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# quest.jobs.list / quest.jobs.get / quest.jobs.cancel
# ---------------------------------------------------------------------------


class TestJobs:
    def test_list_returns_jobs_array(self, client) -> None:
        r = client.call("quest.jobs.list")
        assert r["ok"] is True
        assert "jobs" in r["result"]
        assert isinstance(r["result"]["jobs"], list)

    def test_list_json_serialisable(self, client) -> None:
        r = client.call("quest.jobs.list")
        json.dumps(to_payload(r["result"]))

    def test_get_nonexistent_job(self, client) -> None:
        r = client.call("quest.jobs.get", {"job_id": "no-such-job"})
        assert r["ok"] is False
        assert r["error_code"] == "operation_failed"

    def test_cancel_nonexistent_job(self, client) -> None:
        r = client.call("quest.jobs.cancel", {"job_id": "no-such-job"})
        assert r["ok"] is True
        assert r["result"]["cancel_requested"] is False

    def test_cancel_after_scan_completes(self, client) -> None:
        scan_r = client.call(
            "quest.scan",
            {"project": _project(), "positions": _scan_positions()},
        )
        job_id = scan_r["result"]["job_id"]
        r = client.call("quest.jobs.cancel", {"job_id": job_id})
        assert r["ok"] is True
        assert r["result"]["cancel_requested"] is False


# ---------------------------------------------------------------------------
# quest.contract.describe
# ---------------------------------------------------------------------------


class TestContractDescribe:
    def test_returns_descriptor(self, client) -> None:
        r = client.call("quest.contract.describe")
        assert r["ok"] is True
        descriptor = r["result"]
        assert descriptor["plugin_id"] == "quenching_estimator"
        assert "contract_version" in descriptor
        assert "methods" in descriptor
        assert "error_codes" in descriptor

    def test_every_method_is_listed(self, client) -> None:
        descriptor = client.result("quest.contract.describe")
        from chisurf.plugins.quenching_estimator.rpc.services import METHODS

        assert set(descriptor["methods"]) == set(METHODS)

    def test_serialization_is_documented(self, client) -> None:
        descriptor = client.result("quest.contract.describe")
        assert "native" in descriptor["serialization"]["in_process"]
        assert "JSON" in descriptor["serialization"]["wire"]

    def test_json_serialisable(self, client) -> None:
        r = client.call("quest.contract.describe")
        json.dumps(to_payload(r["result"]))


# ---------------------------------------------------------------------------
# Cross-cutting: envelope consistency
# ---------------------------------------------------------------------------


class TestEnvelopeConsistency:
    """Every call returns ``{"ok": bool, ...}`` — never raises, never omits."""

    READ_ONLY_METHODS = [
        ("quest.template", {"with_fret": False}),
        ("quest.parameter_catalog", {}),
        ("quest.locales", {}),
        ("quest.dyes.list", {}),
        ("quest.quenching_defaults", {}),
        ("quest.jobs.list", {}),
        ("quest.contract.describe", {}),
    ]

    @pytest.mark.parametrize("method,params", READ_ONLY_METHODS)
    def test_success_envelope(self, client, method, params) -> None:
        r = client.call(method, params)
        assert r["ok"] is True
        assert "result" in r
        assert "error" not in r

    @pytest.mark.parametrize("method,params", READ_ONLY_METHODS)
    def test_no_params_still_works(self, client, method, params) -> None:
        """Calling with empty params should not crash read-only methods."""
        r = client.call(method)
        assert r["ok"] is True

    def test_call_with_none_params(self, client) -> None:
        r = client.call("quest.template", None)
        assert r["ok"] is True

    def test_dispatch_directly(self) -> None:
        """The dispatcher itself returns the same envelope."""
        dispatcher = ServiceDispatcher()
        register_services(dispatcher)
        r = dispatcher.dispatch("quest.template", {"with_fret": False})
        assert r["ok"] is True
