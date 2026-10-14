"""Qt-free helpers for comparing canonical scientific archives (parameters, structures, snapshots).

The driver that ran one actual Main lifetime went with the Qt main window; what is left are the
archive-comparison helpers other tests import.
"""

from __future__ import annotations

import importlib.abc
import json
import math
import os
import traceback

import numpy as np


class _BlockMMFDB(importlib.abc.MetaPathFinder):
    """Make optional database imports impossible before any ordinary GUI import."""

    def __init__(self, report):
        """Record swallowed import failures that can silently remove GUI plots."""
        self.report = report

    def find_spec(self, fullname, path=None, target=None):
        """Reject the entire optional database package, including submodules."""
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            self.report.setdefault("blocked_mmfdb_imports", []).append(
                {"module": fullname, "stack": traceback.format_stack()}
            )
            raise AssertionError(f"optional MMFDB import in actual Main: {fullname}")


def _parameters(project):
    """Index persisted scientific parameters by their exact portable identities."""
    return {
        parameter["uid"]: parameter
        for record in project.fits
        for model in (
            [member["model"] for member in record["members"]]
            + ([record["aggregate_model"]] if record.get("aggregate_model") else [])
        )
        for parameter in model["parameters"]
    }


def _members(fits):
    """Keep canonical scientific member ordering across presentation wrappers."""
    return [member for fit in fits for member in getattr(fit, "grouped_fits", [fit])]


def package_gui(directory):
    """Wrap existing real fits without reconstructing data, models or parameters.

    Canonical public single-Fit restoration is exercised separately and remains
    a failure when unsupported. This packaging is only for the additional real
    FitGroup GUI surface; it cannot replace that regression.
    """
    from chisurf.core.data import DataGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file
    from test.project.scientific_catalogue_probe import scientific_observables

    wrapper_uids = {}
    for iteration in range(2):
        project = load_file(directory / f"science-{iteration}.cs.pto")
        restored = restore_session(project)
        expected = json.loads((directory / f"expected-{iteration}.json").read_text())
        canonical_members = _members(restored.fits)
        assert [scientific_observables(fit) for fit in canonical_members] == expected["observables"]
        groups = []
        for fit in restored.fits:
            if isinstance(fit, FitGroup):
                groups.append(fit)
                continue
            # The default model_class=type creates no scientific model. Replace
            # its provisional member with the existing canonical scientific fit.
            group = FitGroup(data=DataGroup([fit.data]))
            group.grouped_fits[:] = [fit]
            group._model.fits = group.grouped_fits
            group.name = fit.name
            wrapper_uids.setdefault(
                fit.unique_identifier, (group.unique_identifier, group._model.unique_identifier)
            )
            group.unique_identifier, group._model.unique_identifier = wrapper_uids[
                fit.unique_identifier
            ]
            groups.append(group)
        assert _members(groups) == canonical_members
        wrapped = capture_session(restored.datasets, groups)
        originals = {
            member["uid"]: member for record in project.fits for member in record["members"]
        }
        for record in wrapped.fits:
            for member in record["members"]:
                original = originals[member["uid"]]
                # Reference owner addresses change to the new wrapper; every
                # scientific model/parameter/native identity remains exact.
                assert member["model"]["uid"] == original["model"]["uid"]
                for parameter, previous in zip(
                    member["model"]["parameters"], original["model"]["parameters"]
                ):
                    assert {k: v for k, v in parameter.items() if k != "link_target"} == {
                        k: v for k, v in previous.items() if k != "link_target"
                    }
        destination = save_file(wrapped, directory / f"grouped-science-{iteration}.cs.pto")
        again = restore_session(load_file(destination))
        _assert_snapshot(wrapped, again.datasets, again.fits)
        assert [scientific_observables(fit) for fit in _members(again.fits)] == expected[
            "observables"
        ]


def _assert_snapshot(project, datasets, fits):
    """Keep topology, bounds, fixed flags, ranges, selections and links exact."""
    from chisurf.core.project.session import capture_session
    from test.project.scientific_catalogue_probe import _differences

    captured = capture_session(datasets, fits)
    assert captured.datasets == project.datasets, list(
        _differences(project.datasets, captured.datasets, "datasets")
    )[:10]
    assert captured.fits == project.fits, list(_differences(project.fits, captured.fits, "fits"))[
        :10
    ]


def _document_owned_parameter_index(fits):
    """Index exact parameter objects declared by the canonical document owner.

    Active optimizer vectors are deliberately narrower for models such as
    GeneralFCS.  The shared owner graph is also what public parameter services
    use; it includes inactive presets without traversing Qt or process-global
    registry state.
    """
    from types import SimpleNamespace

    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.project.session import owned_scientific_objects

    owner = SimpleNamespace(fits=list(fits))
    objects = owned_scientific_objects(owner, include_plugins=False)
    return {
        uid: parameter
        for uid, parameter in objects.items()
        if isinstance(parameter, FittingParameter)
    }


def _display_owner(model, binding):
    """Resolve the symbolic binding owner without retaining any Qt object."""
    if binding["owner"] == "model":
        return model
    if binding["owner"] == "fit.data":
        return getattr(getattr(model, "fit", None), "data", None)
    raise AssertionError(f"unsupported display binding owner: {binding['owner']!r}")


def _display_path_value(owner, path):
    """Read a dotted public property or metadata key from its declared owner."""
    value = owner
    for part in path.split("."):
        if isinstance(value, dict):
            value = value[part]
        else:
            value = getattr(value, part)
    return value


def _declared_display_binding(editor, parameter):
    """Validate one table-only scalar/output against its real non-port owner."""
    binding = getattr(parameter, "display_binding", None)
    if binding is None:
        return None
    from chisurf.core.dataspec.display_binding import (
        COMPUTED_OUTPUT,
        DATA_METADATA,
        MODEL_SCALAR,
        validate_display_binding,
    )

    binding = validate_display_binding(binding)
    model = editor.model
    owner = _display_owner(model, binding)
    assert owner is not None, ("display binding owner is absent", binding)
    kind = binding["kind"]
    if kind == MODEL_SCALAR:
        assert owner is model
        assert binding["path"] in model.scalar_names(), (
            "declared scalar display path is not a persisted model scalar",
            binding,
        )
        assert not parameter.is_output
    elif kind == COMPUTED_OUTPUT:
        assert owner is model and parameter.is_output
        source_value = float(_display_path_value(owner, binding["path"]))
        shown_value = float(parameter.value)
        assert source_value == shown_value or (
            math.isnan(source_value) and math.isnan(shown_value)
        ), ("computed display row is stale", binding, source_value, shown_value)
    elif kind == DATA_METADATA:
        assert parameter.is_output
        metadata = getattr(owner, "meta_data", None) or {}
        assert binding["path"].split(".")[0] in metadata, (
            "declared metadata display has no source namespace",
            binding,
            metadata,
        )
    else:  # ``validate_display_binding`` makes this unreachable; retain a clear probe error.
        raise AssertionError(f"unsupported display binding kind: {kind!r}")
    return binding










def _structural_coordinates(state):
    """Extract structure coordinates from a ProteinMC-style adapter payload."""
    payload = state.get("proteinmc") or {}
    structure = payload.get("structure") or payload.get("current_structure") or {}
    atoms = structure.get("atoms") or {}
    for field in atoms.get("fields", []):
        if field.get("name") == "xyz":
            array = field.get("array") or {}
            values = array.get("values")
            if values is None and "value" in array:
                values = [array["value"]]
            if values is not None:
                return values
    return structure.get("xyz")


def _model_inputs(model):
    """Model record minus adapter state and the values of declared outputs.

    Output parameters (``is_output``) are recomputed from the structure, so a
    coordinate edit legitimately changes their values.
    """
    record = {k: v for k, v in model.items() if k not in {"adapter_state", "parameters"}}
    record["parameters"] = [
        {k: v for k, v in parameter.items() if k != "value"}
        if parameter.get("is_output")
        else parameter
        for parameter in model.get("parameters", [])
    ]
    return record


def _structural_edit(first, second):
    """Detect a coordinate-only scientific edit between canonical archives.

    Some producers edit structural model state (ProteinMCModel shifts an atom
    and the recomputed distances are declared outputs). Their parameter diff is
    empty by design. Returns ``(member_uid, coordinates)`` for the changed
    member when the adapter structure coordinates differ and everything else
    about the member except declared output values is identical; ``None``
    otherwise. Accepts either a
    :class:`~chisurf.core.project.storage.Project` (``.fits``) or an already
    unwrapped fits list/dict payload.
    """
    first_records = first.fits if hasattr(first, "fits") else first["fits"]
    second_records = second.fits if hasattr(second, "fits") else second["fits"]
    for record_first, record_second in zip(first_records, second_records):
        for member_first, member_second in zip(record_first["members"], record_second["members"]):
            model_first, model_second = member_first["model"], member_second["model"]
            if _model_inputs(model_first) != _model_inputs(model_second):
                continue
            state_first = model_first.get("adapter_state") or {}
            state_second = model_second.get("adapter_state") or {}
            if state_first == state_second:
                continue
            changed = {
                key
                for key in state_first.keys() | state_second.keys()
                if state_first.get(key) != state_second.get(key)
            }
            if len(changed) != 1:
                continue
            key = next(iter(changed))
            coordinates_first = _structural_coordinates({key: state_first.get(key) or {}})
            coordinates_second = _structural_coordinates({key: state_second.get(key) or {}})
            if coordinates_second is None or coordinates_second == coordinates_first:
                # A non-structural adapter change (settings, traces) is not the
                # producer's coordinate edit.
                continue
            return member_first["uid"], coordinates_second
    return None


def _observables_close(actual, expected, rtol=1e-6, atol=1e-6):
    """Compare observables with a bound for PDB-precision structural edits.

    A structural edit reaches the live model through PDB text, which stores
    coordinates to ~1e-7 Å, so coordinate-derived observables differ from the
    archive's full-precision values at ~1e-8. Structure (keys, lengths, types)
    must still match exactly; only floating-point leaves use ``rtol``/``atol``.
    Scalar-port edits keep the exact ``==`` comparison in :func:`run`.
    """
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_observables_close(actual[k], expected[k], rtol, atol) for k in expected)
        )
    if isinstance(expected, (list, tuple)):
        return (
            isinstance(actual, (list, tuple))
            and len(actual) == len(expected)
            and all(_observables_close(a, e, rtol, atol) for a, e in zip(actual, expected))
        )
    if isinstance(expected, float) or isinstance(actual, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and bool(np.isclose(actual, expected, rtol=rtol, atol=atol))
        )
    return actual == expected


def _structural_reference(fits, member_uid, committed_path):
    """The producer archive as the structural GUI edit legitimately records it.

    The producer shifts coordinates in memory; the GUI performs the same
    scientific operation by loading a PDB through the Structure control. That
    load deliberately records the file as ``structure_source`` (and as the
    structure's own ``filename``) and seeds the sampler's
    ``current_structure`` with a copy of the loaded structure. Every
    other field must match the archive (numbers to PDB precision, see
    :func:`_observables_close`).
    """
    import copy

    reference = copy.deepcopy(fits)
    for record in reference:
        for member in record["members"]:
            if member["uid"] != member_uid:
                continue
            payload = member["model"]["adapter_state"]["proteinmc"]
            payload["structure_source"] = str(committed_path)
            if isinstance(payload.get("structure"), dict) and "filename" in payload["structure"]:
                payload["structure"]["filename"] = str(committed_path)
            payload["current_structure"] = copy.deepcopy(payload["structure"])
    return reference


def _adopt_loaded_structure_identities(reference_fits, captured_fits, member_uid):
    """Take the freshly loaded structures' object ``uid`` from the live capture.

    Loading a file creates new structure objects, so their identities cannot
    be predicted from the producer archive. Adopting them here (and only them)
    keeps the later save/readback comparison checking that they persist.
    """
    for record, live_record in zip(reference_fits, captured_fits):
        for member, live_member in zip(record["members"], live_record["members"]):
            if member["uid"] != member_uid:
                continue
            payload = member["model"]["adapter_state"]["proteinmc"]
            live = live_member["model"]["adapter_state"]["proteinmc"]
            for key in ("structure", "current_structure"):
                if (
                    isinstance(payload.get(key), dict)
                    and isinstance(live.get(key), dict)
                    and "uid" in live[key]
                ):
                    payload[key]["uid"] = live[key]["uid"]


def _assert_structural_snapshot(reference_fits, reference_datasets, datasets, fits, member_uid):
    """Exact datasets; fits equal ``reference_fits`` to PDB precision."""
    from chisurf.core.project.session import capture_session
    from test.project.scientific_catalogue_probe import _differences

    captured = capture_session(datasets, fits)
    _adopt_loaded_structure_identities(reference_fits, captured.fits, member_uid)
    assert captured.datasets == reference_datasets, list(
        _differences(reference_datasets, captured.datasets, "datasets")
    )[:10]
    assert _observables_close(captured.fits, reference_fits), list(
        _differences(reference_fits, captured.fits, "fits")
    )[:10]






def _exit_after_report(report):
    """Exit the child immediately once its evidence report is safely on disk.

    Everything the parent consumes (exit-code-as-verdict plus the JSON report
    and captures) is written before this runs. Returning into normal
    interpreter teardown is the remaining hazard: Python unloads ~170 native
    extensions while Qt/pyqtgraph objects are still alive, which observably
    killed completed ParseFCS children with SIGBUS *after* ``phase: complete``
    was recorded. ``os._exit`` skips that teardown by design; buffers are
    flushed by the explicit writes above, and stdout/stderr carry no evidence.
    """
    os._exit(0)
