"""Standalone scalar parameter files never replace a native port with its repr."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chisurf.core.parameter import Parameter


@pytest.fixture
def parameter():
    """Set public properties on an actual bounded, named, identified scalar."""
    value = Parameter(
        name="kQ scale",
        value=2.0,
        lb=1.0,
        ub=2.5,
        bounds_on=True,
        description="Quenching-rate multiplier",
        meta_data={"source": "148L", "labels": ["TRP", "TYR"], "nested": {"units": "scale"}},
        unique_identifier="b671b0b3-3009-42df-824a-6d690c2b3e54",
    )
    value.fixed = True
    return value


@pytest.mark.parametrize("format", ["json", "yaml"])
def test_actual_save_load_preserves_public_scalar_identity_and_metadata(
    parameter, tmp_path, format
):
    """An actual file restores usable values/flags/metadata on an existing native port."""
    path = tmp_path / f"scalar.{format}"
    parameter.save(str(path), file_type=format)
    restored = Parameter()
    native_port = restored._port
    restored.load(str(path), file_type=format)
    restored.update()
    assert restored._port is native_port
    assert (
        restored.name == parameter.name
        and restored.unique_identifier == parameter.unique_identifier
    )
    assert restored.meta_data == parameter.meta_data
    assert restored.get_state() == parameter.get_state()
    assert restored.value == 2.0 and restored.bounds == (1.0, 2.5) and restored.fixed is True
    assert "GraphPort;" not in path.read_text()


def test_file_load_refreshes_actual_editor(parameter, tmp_path, qtbot):
    """State restoration repaints the attached real controller after restoring the identity."""
    from chisurf.gui.widgets.fitting.parameter_widgets import make_fitting_parameter_widget

    path = tmp_path / "scalar.json"
    parameter.save(str(path), file_type="json")
    restored = Parameter(value=8.0)
    editor = make_fitting_parameter_widget(restored)
    qtbot.addWidget(editor)
    restored.load(str(path), file_type="json")
    assert restored.value == editor.widget_value.value() == 2.0
    assert restored.name == "kQ scale"


def test_json_file_is_readable_by_a_fresh_process(parameter, tmp_path):
    """A cold process reads public data rather than sharing the writer's in-process port."""
    path = tmp_path / "scalar.json"
    parameter.save(str(path), file_type="json")
    environment = os.environ.copy()
    root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = os.pathsep.join([str(root), environment.get("PYTHONPATH", "")])
    code = f"""
from chisurf.core.parameter import Parameter
p=Parameter()
p.load({str(path)!r}, file_type='json')
p.update()
assert p.value == 2.0 and p.fixed and p.bounds == (1.0,2.5)
assert p.name == 'kQ scale' and p.unique_identifier == {parameter.unique_identifier!r}
assert p.meta_data['nested'] == {{'units':'scale'}}
print('cold scalar restored')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("kind", ["linked", "callable"])
def test_standalone_files_reject_context_dependent_parameters_before_write(tmp_path, kind):
    """Links and Python computation need an owning archive, not an opaque standalone file."""
    master = Parameter(value=2.0)
    parameter = Parameter(link=master) if kind == "linked" else Parameter(value=lambda: 3.0)
    path = tmp_path / "scalar.json"
    with pytest.raises(ValueError, match="session|project"):
        parameter.save(str(path), file_type="json")
    assert not path.exists()
    assert parameter.value == (2.0 if kind == "linked" else 3.0)


def test_unbounded_scalar_has_standard_json_bounds(tmp_path):
    """Unbounded endpoints use null on disk and remain disabled/unbounded after restore."""
    parameter = Parameter(value=3.0)
    path = tmp_path / "scalar.json"
    parameter.save(str(path), file_type="json")
    payload = json.loads(path.read_text(), parse_constant=lambda value: pytest.fail(value))
    assert payload["state"]["bounds"] == [None, None]
    restored = Parameter()
    restored.load(str(path), file_type="json")
    assert restored.value == 3.0 and not restored.bounds_on
    assert restored.bounds == (None, None)


@pytest.mark.parametrize(
    "fault", ["repr_port", "invalid_value", "invalid_bounds", "invalid_metadata"]
)
def test_corrupt_or_irrecoverable_legacy_files_do_not_mutate_a_parameter(tmp_path, fault):
    """Bad payloads fail clearly before value/name/port identity is changed."""
    if fault == "repr_port":
        payload = {"_port": "<IMP.bff.GraphPort; proxy of Swig Object>", "_name": "lost"}
    else:
        payload = {
            "format": "chisurf.parameter",
            "version": 1,
            "name": "loaded",
            "verbose": False,
            "meta_data": {"unique_identifier": "restored"},
            "state": {
                "value": 2.0,
                "bounds": [1.0, 3.0],
                "bounds_on": True,
                "fixed": False,
                "description": "scalar",
            },
        }
        if fault == "invalid_value":
            payload["state"]["value"] = "not a scalar"
        elif fault == "invalid_bounds":
            payload["state"]["bounds"] = [3.0, 1.0]
        else:
            payload["meta_data"]["unique_identifier"] = None
    path = tmp_path / "scalar.json"
    path.write_text(json.dumps(payload))
    parameter = Parameter(name="original", value=8.0)
    before = parameter.get_state(), parameter.unique_identifier, parameter.name, parameter._port
    with pytest.raises(ValueError):
        parameter.load(str(path), file_type="json")
    assert (
        parameter.get_state(),
        parameter.unique_identifier,
        parameter.name,
        parameter._port,
    ) == before


def test_runtime_dictionary_keeps_its_existing_live_link_contract():
    """Portable files do not redefine the intentional in-process dictionary copy API."""
    master = Parameter(value=2.0)
    follower = Parameter(link=master)
    clone = Parameter()
    clone.from_dict(follower.to_dict())
    assert clone._port is follower._port and clone.link is master
    master.value = 5.0
    assert clone.value == follower.value == 5.0


def test_disabled_stored_bounds_and_prior_roundtrip(tmp_path):
    """Disabled bounds retain their stored endpoints, and a real prior is not replaced by repr."""
    from chisurf.core.fitting.priors import NormalPrior

    parameter = Parameter(value=2.0, lb=1.0, ub=2.5, bounds_on=False)
    parameter.prior = NormalPrior(mu=2.25, sigma=0.3)
    path = tmp_path / "scalar.json"
    parameter.save(str(path), file_type="json")
    restored = Parameter()
    restored.load(str(path), file_type="json")
    assert restored.lb == 1.0 and restored.ub == 2.5 and not restored.bounds_on
    assert restored.prior.get_state() == parameter.prior.get_state()


def test_genuine_legacy_state_and_unknown_prior_handling(tmp_path):
    """A known scalar-state record is recoverable; unsupported prior metadata is rejected."""
    state = {"value": 2.0, "bounds": [1.0, 3.0], "bounds_on": True, "fixed": True}
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(state))
    restored = Parameter()
    uid = restored.unique_identifier
    restored.load(str(path), file_type="json")
    assert restored.value == 2.0 and restored.fixed and restored.bounds == (1.0, 3.0)
    assert restored.unique_identifier == uid
    state["prior"] = {"kind": "unknown scalar law"}
    path.write_text(json.dumps(state))
    before = restored.get_state()
    with pytest.raises(ValueError, match="prior"):
        restored.load(str(path), file_type="json")
    assert restored.get_state() == before


def test_metadata_that_is_not_json_native_is_rejected_before_write(tmp_path):
    """Metadata objects cannot be silently stringified or container types silently relabeled."""
    parameter = Parameter(meta_data={"tuple": (1, 2)})
    path = tmp_path / "scalar.json"
    with pytest.raises(ValueError, match="metadata|JSON"):
        parameter.save(str(path), file_type="json")
    assert not path.exists()


def test_yaml_integer_metadata_keys_reject_before_any_mutation(tmp_path):
    """A YAML-only metadata key cannot install state that the JSON-native codec cannot save."""
    import yaml

    parameter = Parameter(name="original", value=8.0, meta_data={"source": "original"})
    state = parameter.get_state()
    uid, port, metadata = parameter.unique_identifier, parameter._port, parameter.meta_data.copy()
    payload = {
        "format": "chisurf.parameter",
        "version": 1,
        "name": "loaded",
        "verbose": True,
        "meta_data": {"unique_identifier": "restored", 7: "invalid key"},
        "state": {
            "value": 2.0,
            "bounds": [1.0, 3.0],
            "bounds_on": True,
            "fixed": True,
            "description": "replacement",
        },
    }
    path = tmp_path / "scalar.yaml"
    path.write_text(yaml.safe_dump(payload))
    with pytest.raises(ValueError, match="metadata|JSON"):
        parameter.load(str(path), file_type="yaml")
    assert parameter._port is port
    assert parameter.get_state() == state
    assert parameter.unique_identifier == uid and parameter.name == "original"
    assert parameter.meta_data == metadata and not parameter.verbose
