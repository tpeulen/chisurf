"""INC-03 guard: the RPC wire surface carries one name per operation.

The server used to register every dataset/fit/parameter/project/session/model
operation twice — once under a flat snake_case name (``list_datasets``,
``run_fit``) and once under its namespaced name (``dataset.list``,
``fit.run``). These tests pin the namespaced surface as the only one, so the
duplicate spelling cannot creep back in.
"""

import json
from importlib import resources

import pytest

#: The one name that is deliberately not namespaced. The companion
#: photon-data exploration tool probes server health with it before it knows
#: which protocol version it is talking to.
UNNAMESPACED_ALLOWED = {"list_methods"}

#: Names removed with INC-03, each with the namespaced name that replaced it.
RETIRED_ALIASES = {
    "list_datasets": "dataset.list",
    "get_dataset_info": "dataset.get",
    "add_dataset": "dataset.load",
    "remove_datasets": "dataset.remove",
    "clear_datasets": "dataset.clear",
    "dataset_rename": "dataset.rename",
    "dataset_group": "dataset.group",
    "dataset_ungroup": "dataset.ungroup",
    "list_fits": "fit.list",
    "get_fit_info": "fit.get",
    "run_fit": "fit.run",
    "remove_fits": "fit.remove",
    "clear_fits": "fit.clear",
    "fit_set_dataset": "fit.set_dataset",
    "fit_set_result_idx": "fit.set_result_idx",
    "fit_create": "fit.create",
    "fit_update": "fit.update",
    "get_parameter": "parameter.get",
    "set_parameter_value": "parameter.set_value",
    "set_parameter_fixed": "parameter.set_fixed",
    "set_parameter_bounds": "parameter.set_bounds",
    "parameter_link": "parameter.link",
    "parameter_unlink": "parameter.unlink",
    "save_project": "project.save",
    "load_project": "project.load",
    "get_project_info": "project.info",
    "session_describe": "session.describe",
    "session_clear": "session.clear",
    "session_snapshot": "session.snapshot",
    "session_restore": "session.restore",
    "model_finalize": "model.finalize",
    "model_set_parse_function": "model.set_parse_function",
    "ping": "meta.ping",
}


def _methods(filename: str) -> list[dict]:
    """Return the declarative method table stored in ``chisurf/server/<filename>``."""
    with resources.files("chisurf.server").joinpath(filename).open() as fp:
        return json.load(fp)["methods"]


def test_registered_rpc_names_are_namespaced():
    """Every server method name is ``group.action``, bar the documented exception."""
    flat = {
        spec["rpc"]
        for spec in _methods("server_methods.json")
        if "." not in spec["rpc"] and spec["rpc"] not in UNNAMESPACED_ALLOWED
    }
    assert not flat, f"Un-namespaced RPC method names: {sorted(flat)}"


@pytest.mark.parametrize("alias,replacement", sorted(RETIRED_ALIASES.items()))
def test_retired_alias_is_gone_and_its_replacement_is_registered(alias, replacement):
    """A retired flat name is unregistered and its namespaced name still answers."""
    names = {spec["rpc"] for spec in _methods("server_methods.json")}
    assert alias not in names, f"Legacy alias {alias!r} is registered again"
    assert replacement in names, f"Replacement {replacement!r} is missing"


def test_no_rpc_name_is_registered_twice():
    """Two entries for one name would silently shadow each other in the registry."""
    names = [spec["rpc"] for spec in _methods("server_methods.json")]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"Duplicate RPC registrations: {duplicates}"


def test_client_wrappers_target_registered_methods():
    """Every generated client wrapper calls a method the server actually registers."""
    served = {spec["rpc"] for spec in _methods("server_methods.json")}
    called = {spec["rpc"] for spec in _methods("client_methods.json")}
    assert not called - served, (
        f"Client wrappers call unregistered methods: {sorted(called - served)}"
    )
