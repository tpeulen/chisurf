"""A recorded operation must resolve back to the tool that performs it.

This is the half of provenance a container cannot carry. It records *what was
done* in dictionary terms and deliberately never names a program; without the
inverse index a reader can see that a burst table came from a burst search and
still have nothing to press.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chisurf.core.plugin.manifest import PluginManifest, validate_manifest
from chisurf.core.plugin.operations import clear_cache, operation_index, tools_for_operation

PLUGINS = Path(__file__).resolve().parents[3]


def test_the_manifest_field_round_trips():
    """Declared, parsed and re-serialised — a key parsed but not written drifts."""
    data = {
        "id": "x",
        "version": "1.0.0",
        "operation_types": ["burst_selection", "filtering"],
    }
    manifest = PluginManifest.from_dict(data)
    assert manifest.operation_types == ["burst_selection", "filtering"]
    assert manifest.to_dict()["operation_types"] == ["burst_selection", "filtering"]
    assert validate_manifest(data) == []


def test_an_unknown_key_is_still_rejected():
    """The closed key set is what stops a typo becoming a silently ignored field."""
    errors = validate_manifest({"id": "x", "version": "1", "operation_typos": ["a"]})
    assert errors


@pytest.mark.parametrize(
    "operation,plugin_id",
    [
        ("burst_selection", "burst_selection"),
        ("burst_lifetime_fitting", "burst_mle_analysis"),
        ("burst_2cde", "burst_2cde"),
        ("burst_fusion", "burst_fusion"),
        ("photon_hmm", "burst_h2mm"),
        ("phasor_analysis", "img_pixel_phasor"),
        ("flow_field_estimation", "img_flow"),
        ("microtime_shift", "microtime_shifter"),
    ],
)
def test_a_shipped_step_names_a_shipped_tool(operation: str, plugin_id: str):
    """Each of these operations is written by a plugin that must claim it back."""
    clear_cache()
    ids = {m.id for m in tools_for_operation(operation)}
    assert plugin_id in ids, f"{operation!r} resolved to {sorted(ids)}"


def test_an_unclaimed_step_answers_empty_rather_than_raising():
    """A container may carry a result another program computed. That is normal."""
    clear_cache()
    assert tools_for_operation("no_such_operation") == []
    assert tools_for_operation("") == []


def test_every_declared_operation_is_a_dictionary_term():
    """A manifest term that is not in the dictionary can never match a file.

    A ``.pto`` refuses to *write* a term the dictionary does not have, so a
    plugin claiming an invented one would sit in the index unreachable — the
    button would simply never light up, with nothing to see.
    """
    from chisurf.core.fio.pto import _terms

    valid = _terms("_mmfdb_operation.operation_type")
    if not valid:
        pytest.skip("the MMFDB dictionaries are not available")
    clear_cache()
    for operation, manifests in operation_index().items():
        assert operation in valid, (
            f"{operation!r} is declared by "
            f"{[m.id for m in manifests]} but is not an "
            "_mmfdb_operation.operation_type term"
        )


def test_declaring_plugins_have_a_gui_or_say_they_do_not():
    """The jump opens a window; a claim with no entry point must be visible here."""
    clear_cache()
    index = operation_index()
    assert index, "no plugin declares an operation_type"
    without = {
        m.id for manifests in index.values() for m in manifests if not m.entrypoints.gui
    }
    # Headless-only tools are allowed to claim a step — the inspector says so
    # rather than opening nothing — but the set is worth seeing when it grows.
    assert without <= {"burst_ebfret"}, sorted(without)


def test_manifests_on_disk_parse_with_the_new_key():
    """Every shipped manifest still validates after the field was added."""
    bad = []
    for path in PLUGINS.rglob("manifest.json"):
        if "{{" in str(path):  # the cookiecutter template
            continue
        errors = validate_manifest(json.loads(path.read_text()))
        if errors:
            bad.append((str(path.relative_to(PLUGINS)), errors))
    assert not bad, bad
