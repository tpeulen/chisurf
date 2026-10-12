"""The contract, and the guardrail that keeps local and remote from diverging.

Since 2026-07-28 an in-process call returns **native** objects — numpy arrays
intact — and only a transport serialises. That is what stops a fitting loop
(`OBJ-02`'s host optimiser, which calls `simulate` thousands of times) paying a
numpy→list conversion per iteration.

The cost of that rule is that **payload shape now depends on the transport**,
which is exactly the "same capability behaves differently depending on the path"
shape that produced `LAY-01`'s triplicated `simulate_site`. The defence is
mechanical rather than a review promise: every method's native result is
round-tripped through `to_payload` and validated against the schema
`quest/manifest.json` declares. If they drift, this file fails — not a host.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, MutableMapping

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.api import local as api
from chisurf.plugins.quenching_estimator.rpc import (
    CONTRACT_VERSION,
    ERROR_CODES,
    METHODS,
    PLUGIN_ID,
    RemoteError,
    ServiceDispatcher,
    contract_descriptor,
    error_code_for,
    local_client,
    register_services,
    service_error,
    to_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = REPO_ROOT / "test" / "148l.pdb"
MANIFEST = json.loads((REPO_ROOT / "manifest.json").read_text(encoding="utf8"))


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


@pytest.fixture(autouse=True)
def _isolate_artefacts(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


class TestTheDescriptorMatchesTheManifest:
    """One declaration, not two.

    A hand-written second copy of the method list is the defect shape this
    project keeps finding, so the descriptor is *built* from the manifest and
    this asserts the registry agrees with both.
    """

    def test_identity(self) -> None:
        descriptor = contract_descriptor()
        assert descriptor["plugin_id"] == PLUGIN_ID == MANIFEST["id"]
        assert descriptor["contract_version"] == CONTRACT_VERSION
        assert descriptor["quest_version"] == MANIFEST["version"]

    def test_every_registered_method_is_described(self) -> None:
        dispatcher = ServiceDispatcher()
        register_services(dispatcher)
        assert set(contract_descriptor()["methods"]) == set(dispatcher.methods)

    def test_the_method_table_and_the_manifest_agree(self) -> None:
        assert set(METHODS) == {m["name"] for m in MANIFEST["rpc_methods"]}

    def test_it_is_reachable_as_a_method(self) -> None:
        """A host must be able to ask without importing QuEst."""
        described = local_client().result("quest.contract.describe")
        assert described["contract_version"] == CONTRACT_VERSION
        assert "quest.simulate" in described["methods"]

    def test_it_is_json_serialisable(self) -> None:
        json.dumps(contract_descriptor())

    def test_it_states_where_serialization_happens(self) -> None:
        """The one thing a caller cannot infer from the schemas."""
        serialization = contract_descriptor()["serialization"]
        assert "native" in serialization["in_process"]
        assert "JSON" in serialization["wire"]


class TestTheSerializationBoundary:
    def test_an_in_process_simulate_returns_native_arrays(self) -> None:
        result = api.simulate(_project())
        assert isinstance(result.donor_counts, np.ndarray)
        assert isinstance(result.time, np.ndarray)

    def test_the_transport_converts_it(self) -> None:
        payload = to_payload(api.simulate(_project()))
        assert isinstance(payload["donor_counts"], list)
        assert isinstance(payload["time_ns"], list)

    def test_the_payload_is_json_serialisable(self) -> None:
        """The actual requirement. `tolist()` on a float32 array is not enough
        by itself — numpy scalars anywhere else in the structure would still
        break `json.dumps`."""
        json.dumps(to_payload(api.simulate(_project())))

    def test_to_payload_is_idempotent(self) -> None:
        """A transport that converts twice must not corrupt the payload."""
        once = to_payload(api.simulate(_project()))
        assert to_payload(once) == once

    def test_it_converts_bare_numpy_too(self) -> None:
        assert to_payload(np.arange(3)) == [0, 1, 2]
        assert to_payload({"a": np.float64(1.5)}) == {"a": 1.5}
        assert to_payload([np.int64(2)]) == [2]
        assert to_payload(Path("/tmp/x")) == "/tmp/x"


class TestTheRoundTripValidatesAgainstTheManifest:
    """Native result → `to_payload` → the schema the manifest declares."""

    @staticmethod
    def _schema(method: str) -> dict[str, Any]:
        for entry in MANIFEST["rpc_methods"]:
            if entry["name"] == method:
                return entry.get("result_schema") or {}
        raise AssertionError(f"{method} is not declared in the manifest")

    @staticmethod
    def _check(payload: Any, schema: dict[str, Any], where: str = "result") -> None:
        """A small structural check, deliberately not a full JSON-Schema engine.

        `jsonschema` is an imp-tricks dependency, not QuEst's, and taking it on
        for this would be a heavier commitment than the guarantee is worth. What
        matters is that declared keys exist with declared types.
        """
        kind = schema.get("type")
        if kind == "object":
            assert isinstance(payload, dict), f"{where}: expected object"
            for key in schema.get("required", []):
                assert key in payload, f"{where}: missing required key {key!r}"
            for key, subschema in (schema.get("properties") or {}).items():
                if key in payload and payload[key] is not None:
                    TestTheRoundTripValidatesAgainstTheManifest._check(
                        payload[key], subschema, f"{where}.{key}"
                    )
        elif kind == "array":
            assert isinstance(payload, list), f"{where}: expected array"
        elif kind == "number":
            assert isinstance(payload, (int, float)), f"{where}: expected number"
        elif kind == "string":
            assert isinstance(payload, str), f"{where}: expected string"
        elif kind == "boolean":
            assert isinstance(payload, bool), f"{where}: expected boolean"

    def test_simulate(self) -> None:
        payload = to_payload(local_client().result("quest.simulate", {"project": _project()}))
        self._check(payload, self._schema("quest.simulate"))
        json.dumps(payload)

    def test_template(self) -> None:
        payload = to_payload(local_client().result("quest.template", {"with_fret": True}))
        self._check(payload, self._schema("quest.template"))
        json.dumps(payload)

    def test_validate(self) -> None:
        payload = to_payload(local_client().result("quest.validate", {"project": _project()}))
        self._check(payload, self._schema("quest.validate"))
        json.dumps(payload)

    def test_scan(self) -> None:
        positions = {
            "E96": {
                "chain_identifier": "E",
                "residue_seq_number": 96,
                "atom_name": "CB",
                "residue_name": "ALA",
            }
        }
        payload = to_payload(
            local_client().result("quest.scan", {"project": _project(), "positions": positions})
        )
        self._check(payload, self._schema("quest.scan"))
        json.dumps(payload)

    @pytest.mark.parametrize(
        "method,params",
        [
            ("quest.parameter_catalog", {}),
            ("quest.locales", {}),
            ("quest.dyes.list", {}),
            ("quest.quenching_defaults", {}),
            ("quest.contract.describe", {}),
        ],
    )
    def test_the_read_only_methods(self, method: str, params: dict) -> None:
        payload = to_payload(local_client().result(method, params))
        self._check(payload, self._schema(method))
        json.dumps(payload)


class TestErrorCodes:
    def test_every_code_is_documented(self) -> None:
        assert all(ERROR_CODES.values()), "a code with no description helps nobody"

    def test_an_unknown_code_is_refused(self) -> None:
        """A typo would otherwise produce an envelope no host recognises."""
        with pytest.raises(ValueError, match="Unknown error_code"):
            service_error("boom", "definitely_not_a_code")

    def test_a_malformed_project_says_so(self) -> None:
        response = local_client().call("quest.validate", {"project": {"tau0": 1.0}})
        assert response["ok"] is False
        assert response["error_code"] == "invalid_project"
        assert response["exception_type"] == "ProjectValidationError"

    def test_an_unknown_method_says_so(self) -> None:
        assert local_client().call("quest.nope")["error_code"] == "unknown_method"

    def test_a_buried_site_is_not_just_operation_failed(self) -> None:
        """The distinction a UI needs: unprocessable, not broken."""
        assert error_code_for(ValueError("Accessible Volume is empty (0 points).")) == (
            "unlabelable_site"
        )

    def test_the_exception_type_survives(self) -> None:
        """A host that can only string-match breaks when a message improves."""
        dispatcher = ServiceDispatcher()
        dispatcher.register("quest.boom", lambda p: (_ for _ in ()).throw(KeyError("x")))
        response = dispatcher.dispatch("quest.boom")
        assert response["exception_type"] == "KeyError"
        assert response["error_code"] == "operation_failed"

    def test_remote_error_carries_the_code(self) -> None:
        with pytest.raises(RemoteError) as excinfo:
            local_client().result("quest.validate", {"project": {"tau0": 1.0}})
        assert excinfo.value.error_code == "invalid_project"
        assert excinfo.value.exception_type == "ProjectValidationError"


class TestTheFacadeResolvesToAClient:
    def test_the_verbs_go_through_the_client(self, monkeypatch) -> None:
        """`use_client` is the local/remote resolution LAY-04 asked for."""

        class Recording:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def result(self, method, params=None):
                self.calls.append(method)
                return {"project": {}}

        recorder = Recording()
        monkeypatch.setattr(api, "_CLIENT", recorder)
        api.template()
        assert recorder.calls == ["quest.template"]

    def test_the_default_client_is_in_process(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc import InProcessClient

        assert isinstance(api.client(), InProcessClient)

    def test_validate_raises_with_a_code(self) -> None:
        with pytest.raises(RemoteError) as excinfo:
            api.validate({"tau0": 1.0})
        assert excinfo.value.error_code == "invalid_project"
