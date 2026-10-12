"""Comprehensive tests for the ``quest.api`` facade layer.

The facade is the one door every surface — CLI, web backend, GUI, host plugin —
walks through. Each verb resolves to a *client* (``InProcessClient`` by default,
a remote one when ``use_client`` is called). This file covers:

- Every public verb (``template``, ``validate``, ``simulate``, ``scan``, ``describe``,
  ``parameter_catalog``, ``dyes``, ``structure_metadata``).
- The client swap mechanism (``use_client`` / ``client``).
- Error propagation through the facade (``RemoteError`` carries ``error_code``).
- The native-vs-serialised boundary (in-process returns numpy; transports call
  ``to_payload``).
- The plugin-blueprint contract: a host can discover every method, drive the
  facade with a mock client, and every result is either a native object or a
  plain JSON-compatible dict depending on what client is active.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, MutableMapping

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.core import DecaySimulationResult
from chisurf.plugins.quenching_estimator.rpc import RemoteError, to_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = REPO_ROOT / "test" / "148l.pdb"


@pytest.fixture(autouse=True)
def _reset_client():
    """Ensure each test starts with a clean in-process client."""
    api.use_client(None)
    yield
    api.use_client(None)


@pytest.fixture(autouse=True)
def _isolate_artefacts(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


# E36: labelable under IMP.bff's default AV (linker width 4.5 A). E96, the old fixture, is empty there;
# see okf/references/known-issues.md in ChiSurf ("a third of T4L sites have no AV at the default width").
def _project(residue: int = 36) -> MutableMapping[str, Any]:
    project = api.template(with_fret=False)
    project["pdb"] = str(STRUCTURE)
    project["attachment"] = {"chain": "E", "residue": residue, "atom": "CB"}
    project["fret"]["dyes"][0]["attachment"] = dict(project["attachment"])
    project["n_photons"] = 200
    project["t_max"] = 50.0
    return project


class TestClientResolution:
    """``use_client`` is the local/remote resolution LAY-04 asked for."""

    def test_default_client_is_in_process(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc import InProcessClient

        assert isinstance(api.client(), InProcessClient)

    def test_use_client_swaps_the_backend(self) -> None:
        class Stub:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict]] = []

            def result(self, method: str, params: dict | None = None) -> Any:
                self.calls.append((method, params or {}))
                return {"project": {"stub": True}}

            def call(self, method: str, params: dict | None = None) -> dict:
                return {"ok": True, "result": {"project": {"stub": True}}}

        stub = Stub()
        api.use_client(stub)
        result = api.template()
        assert result == {"stub": True}
        assert stub.calls == [("quest.template", {"with_fret": True})]

    def test_use_client_none_restores_default(self) -> None:
        api.use_client(None)
        assert api.client() is not None
        result = api.template(with_fret=False)
        assert result["fret"]["enabled"] is False


class TestTemplate:
    def test_returns_a_project_dict(self) -> None:
        project = api.template()
        assert isinstance(project, dict)
        assert "fret" in project
        assert "tau0" in project

    def test_with_fret_false(self) -> None:
        project = api.template(with_fret=False)
        assert project["fret"]["enabled"] is False
        assert len(project["fret"]["dyes"]) == 1

    def test_with_fret_true(self) -> None:
        project = api.template(with_fret=True)
        assert project["fret"]["enabled"] is True
        assert len(project["fret"]["dyes"]) == 2


class TestValidate:
    def test_valid_project_does_not_raise(self) -> None:
        api.validate(_project())

    def test_invalid_project_raises_remote_error(self) -> None:
        with pytest.raises(RemoteError) as exc:
            api.validate({"tau0": 1.0})
        assert exc.value.error_code == "invalid_project"

    def test_validate_with_pdb_path(self) -> None:
        project = api.template(with_fret=False)
        project.pop("pdb")
        api.validate(project, pdb_path=str(STRUCTURE))


class TestSimulate:
    def test_returns_native_arrays(self) -> None:
        result = api.simulate(_project())
        assert isinstance(result.donor_counts, np.ndarray)
        assert isinstance(result.time, np.ndarray)
        assert result.time.shape == result.donor_counts.shape

    def test_result_is_not_json_until_payload(self) -> None:
        result = api.simulate(_project())
        with pytest.raises(TypeError):
            json.dumps(result)
        payload = to_payload(result)
        assert isinstance(payload["donor_counts"], list)
        json.dumps(payload)

    def test_simulate_with_nbins(self) -> None:
        result = api.simulate(_project(), nbins=128)
        assert len(result.donor_counts) == 128

    def test_simulate_with_custom_tac_range(self) -> None:
        result = api.simulate(_project(), tac_range=(0.0, 25.0))
        assert result.time.shape[0] > 0

    def test_simulate_invalid_project_raises(self) -> None:
        with pytest.raises(RemoteError) as exc:
            api.simulate({"tau0": 1.0})
        assert exc.value.error_code == "invalid_project"


class TestScan:
    POSITIONS = {
        "E96": {
            "chain_identifier": "E",
            "residue_seq_number": 96,
            "atom_name": "CB",
            "residue_name": "ALA",
        }
    }

    def test_returns_results_dict(self) -> None:
        results = api.scan(_project(), self.POSITIONS)
        assert "E96" in results
        record = results["E96"]
        assert "status" in record
        assert "quantum_yield" in record

    def test_results_are_json_after_payload(self) -> None:
        results = api.scan(_project(), self.POSITIONS)
        json.dumps(to_payload(results))


class TestDescribe:
    def test_returns_contract(self) -> None:
        descriptor = api.describe()
        assert descriptor["plugin_id"] == "quenching_estimator"
        assert "methods" in descriptor
        assert "error_codes" in descriptor

    def test_lists_every_method(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import METHODS

        descriptor = api.describe()
        assert set(descriptor["methods"]) == set(METHODS)


class TestParameterCatalog:
    def test_returns_catalog(self) -> None:
        catalog = api.parameter_catalog()
        assert catalog["version"] == 1
        assert "pdb" in catalog["parameters"]

    def test_translated(self) -> None:
        catalog = api.parameter_catalog("de")
        assert catalog["version"] == 1


class TestDyes:
    def test_returns_dye_library(self) -> None:
        dyes = api.dyes()
        assert "Alexa488" in dyes
        assert dyes["Alexa488"]["tau0"] == 4.2


class TestStructureMetadata:
    def test_returns_metadata(self) -> None:
        meta = api.structure_metadata(STRUCTURE)
        assert meta["atom_count"] > 0
        assert "chains" in meta


class TestFacadeBlueprintContract:
    """The properties that make the facade usable as a plugin blueprint.

    A host (ChiSurf, Electron, a notebook) needs to:
    1. Discover what methods exist (``describe``).
    2. Drive them with its own client (``use_client``).
    3. Know every verb goes through the client, not past it.
    4. Receive results that are either native (in-process) or JSON (wire).
    """

    def test_every_verb_goes_through_client(self, monkeypatch) -> None:
        """If the client is a recording stub, every verb must visit it."""

        class Recorder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def result(self, method: str, params: dict | None = None) -> Any:
                self.calls.append(method)
                if method == "quest.template":
                    return {"project": {}}
                if method == "quest.parameter_catalog":
                    return {"version": 1, "parameters": {}}
                if method == "quest.dyes.list":
                    return {}
                if method == "quest.contract.describe":
                    return {
                        "plugin_id": "quenching_estimator",
                        "methods": {},
                        "error_codes": {},
                        "serialization": {},
                    }
                if method == "quest.structure.metadata":
                    return {"atom_count": 0, "chains": []}
                if method == "quest.simulate":
                    return object()
                if method == "quest.scan":
                    return {}
                return {}

            def call(self, method: str, params: dict | None = None) -> dict:
                self.calls.append(method)
                return {"ok": True, "result": {}}

        rec = Recorder()
        api.use_client(rec)

        api.template()
        api.validate({"pdb": "x"})
        api.describe()
        api.parameter_catalog()
        api.dyes()

        # Every one of those verbs must have visited the recorder.
        assert "quest.template" in rec.calls
        assert "quest.validate" in rec.calls
        assert "quest.contract.describe" in rec.calls
        assert "quest.parameter_catalog" in rec.calls
        assert "quest.dyes.list" in rec.calls

    def test_a_host_can_drive_simulate_with_a_mock(self) -> None:
        """A host that replaces the client can return whatever it wants."""

        class FakeHost:
            def result(self, method, params=None):
                return DecaySimulationResult(
                    time=np.array([0.0, 1.0]),
                    donor_counts=np.array([5.0, 3.0]),
                    fret_counts=None,
                    quantum_yield_donor=0.9,
                    quantum_yield_fret=None,
                    collisions_fraction=0.2,
                    fret_efficiency=None,
                    project={},
                )

            def call(self, method, params=None):
                return {"ok": True, "result": {}}

        api.use_client(FakeHost())
        result = api.simulate({})
        assert isinstance(result, DecaySimulationResult)
        assert result.quantum_yield_donor == 0.9

    def test_the_facade_envelope_is_stable(self) -> None:
        """``RemoteError`` always carries ``error_code``, never a bare message."""
        with pytest.raises(RemoteError) as exc:
            api.validate({"tau0": 1.0})
        assert exc.value.error_code is not None
        assert isinstance(exc.value.error_code, str)
