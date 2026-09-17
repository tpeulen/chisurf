"""The RPC surface and the contract that describes it must agree.

A contract that drifts from the handlers is worse than none: a caller reads it,
believes it, and gets a differently-shaped answer. These tests tie the two
together, and tie both to the manifest a plugin is discovered through.
"""

from __future__ import annotations

import json
import pathlib

from chisurf.plugins.burst.burst_fusion.api.contract import (
    CANONICAL_METHODS,
    METHOD_ANALYZE,
    METHOD_FUSE,
    contract_descriptor,
    service_error,
    service_success,
    settings_from_payload,
)
from chisurf.plugins.burst.burst_fusion.api.models import FusionSettings
from chisurf.plugins.burst.burst_fusion.backend import services

MANIFEST = pathlib.Path(services.__file__).resolve().parents[1] / "manifest.json"


def test_the_manifest_declares_exactly_the_registered_methods():
    declared = {entry["name"] for entry in json.loads(MANIFEST.read_text())["rpc_methods"]}
    assert declared == set(CANONICAL_METHODS) == set(services.list_methods())


def test_every_registered_method_is_dispatchable():
    registered: dict[str, object] = {}

    class _Dispatcher:
        @staticmethod
        def register(name, handler):
            registered[name] = handler

    services.register_services(_Dispatcher())
    assert set(registered) == set(CANONICAL_METHODS)
    for handler in registered.values():
        assert callable(handler)


def test_the_contract_is_reachable_at_run_time():
    response = services.contract_handler()
    assert response["status"] == "ok"
    contract = response["contract"]
    assert contract == contract_descriptor()
    assert contract["plugin_id"] == "burst_fusion"
    assert set(contract["methods"]) == set(CANONICAL_METHODS)
    # The side effects are part of the contract: analysing must not write.
    assert "none" in contract["side_effects"]["Analyze"]


def test_the_contract_describes_the_settings_it_actually_takes():
    properties = contract_descriptor()["definitions"]["FusionSettings"]["properties"]
    assert set(properties) == set(FusionSettings().to_dict())
    assert properties["threshold"]["type"] == "number"
    assert properties["n_bins"]["type"] == "integer"
    assert properties["pool_measurements"]["type"] == "boolean"


def test_settings_payloads_ignore_keys_this_version_lacks():
    settings = settings_from_payload({"threshold": 0.8, "from_the_future": 3})
    assert settings.threshold == 0.8
    assert settings_from_payload(None).threshold == FusionSettings().threshold
    assert settings_from_payload(settings) is settings


def test_both_envelopes_carry_a_status_field():
    assert service_success({"a": 1}) == {"status": "ok", "a": 1}
    assert service_error("boom") == {"status": "error", "error": "boom"}


def test_a_missing_folder_is_an_error_response_not_an_exception():
    for handler in (services.analyze_handler, services.fuse_handler):
        response = handler()
        assert response["status"] == "error"
        assert "analysis_folder" in response["error"]


def test_prepare_resolves_the_folder_and_detectors_from_a_workflow_context():
    response = services.prepare_handler(
        workflow_context={
            "burst_folder": "/data/burstwise",
            "channel_settings": {
                "detectors": {"green": {"chs": [0]}},
                "windows": {"prompt": [0, 4096]},
            },
        }
    )
    assert response["status"] == "ok"
    assert response["analysis_folder"] == "/data/burstwise"
    assert response["detectors"] == {"green": {"chs": [0]}}
    assert response["windows"] == {"prompt": [0, 4096]}
    assert response["settings"]["threshold"] == FusionSettings().threshold


def test_analyze_over_rpc_returns_the_curve_json_shape(tmp_path):
    """``None`` in ``p_same`` means "too few pairs to judge", not zero."""
    from chisurf.plugins.burst.burst_fusion.demo import create_demo

    demo = create_demo(directory=tmp_path / "demo")
    response = services.analyze_handler(analysis_folder=demo["folder"], settings={"threshold": 0.7})
    assert response["status"] == "ok"
    curve = response["curve"]
    assert len(curve["tau_s"]) == len(curve["p_same"]) == len(curve["pairs"])
    assert all(value is None or 0.0 <= value <= 1.0 for value in curve["p_same"])
    assert curve["threshold"] == 0.7
    assert curve["tau_max_s"] > 0
    # The whole response must survive a JSON round trip — it goes over the wire.
    assert json.loads(json.dumps(response))["statistics"]["n_bursts_after"] > 0


def test_fuse_over_rpc_writes_a_folder(tmp_path):
    from chisurf.plugins.burst.burst_fusion.demo import create_demo

    demo = create_demo(directory=tmp_path / "demo")
    response = services.fuse_handler(
        analysis_folder=demo["folder"],
        settings={"threshold": 0.7},
        output_folder=str(tmp_path / "fused"),
    )
    assert response["status"] == "ok", response.get("error")
    assert (pathlib.Path(response["output_folder"]) / "bi4_bur").is_dir()
    assert response["tau_used_s"] > 0
    assert json.loads(json.dumps(response))["per_measurement"]


def test_the_method_names_are_the_ones_the_cli_and_gui_use():
    assert METHOD_ANALYZE == "burst_fusion.jobs.analyze"
    assert METHOD_FUSE == "burst_fusion.jobs.fuse"
