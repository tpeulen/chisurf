"""Plugins take their input from the Datasets workspace (chisurf.core.plugin.workspace_input)."""

from __future__ import annotations

import pytest

from chisurf.core.plugin.manifest import _validate_accepts
from chisurf.core.plugin.workspace_input import (
    WorkspaceInput,
    address_of,
    build_payload,
    input_section,
    matches,
    parse,
    plugins_accepting,
    validate,
    with_workspace_input,
    workspace_rows,
)

PHOTONS = {"uid": "p1", "name": "m000.spc", "kind": "photons", "experiment": "Single photon counting",
           "filename": "/data/m000.pto/m000.spc", "link_status": "ok"}
BURSTS = {"uid": "b1", "name": "burstwise", "kind": "bursts", "experiment": "Single photon counting",
          "filename": "/data/m000.pto/burstwise", "link_status": "ok", "result_of": "p1"}
DECAY = {"uid": "d1", "name": "decay", "kind": "decay", "experiment": "TCSPC", "filename": "/x/d.dat"}
SETUP = {"uid": "s1", "name": "setup.json", "kind": "setup", "experiment": "Instrument setup",
         "filename": "/x/setup.json", "link_status": "ok"}
PHOTON_IMAGE = {"uid": "i1", "name": "beads.ptu", "kind": "image", "experiment": "Imaging",
                "filename": "/x/beads.ptu", "link_status": "ok", "representation": "photons"}


def test_a_declaration_is_validated_and_parsed():
    raw = {"kinds": ["photons"], "many": True, "key": "files", "with_setup": True}
    assert validate(raw) == []
    spec = parse(raw)
    assert spec == WorkspaceInput(kinds=["photons"], many=True, key="files", with_setup=True)
    assert validate({"kinds": ["nonsense"]})  # an unknown kind is an error
    assert validate({"many": True})  # names no kind and no experiment
    assert validate({"kinds": ["image"], "representations": ["colour"]})


def test_required_keys_the_workspace_cannot_give_are_refused_in_the_manifest():
    accepts = [{"name": "tttr_trace", "receive": "m:f", "required": ["file", "window_ms"],
                "from_workspace": {"kinds": ["photons"], "key": "file"}}]
    errors = _validate_accepts({"accepts": accepts})
    assert any("window_ms" in e for e in errors)
    accepts[0]["from_workspace"]["defaults"] = {"window_ms": 1.0}
    assert _validate_accepts({"accepts": accepts}) == []


def test_a_linked_row_is_its_address_and_a_session_row_is_its_uid():
    assert address_of(PHOTONS) == "/data/m000.pto/m000.spc"
    assert address_of(DECAY) == "@d1"  # read from a text file, lives in the session


def test_matching_by_kind_experiment_and_image_representation():
    assert matches(WorkspaceInput(kinds=["photons"]), PHOTONS)
    assert not matches(WorkspaceInput(kinds=["photons"]), BURSTS)
    assert matches(WorkspaceInput(experiments=["TCSPC"]), DECAY)
    assert matches(WorkspaceInput(kinds=["image"], representations=["photons"]), PHOTON_IMAGE)
    assert not matches(WorkspaceInput(kinds=["image"], representations=["intensity"]), PHOTON_IMAGE)


def test_the_payload_carries_addresses_uids_a_setup_and_the_defaults():
    one = WorkspaceInput(kinds=["photons"], key="file", defaults={"window_ms": 1.0})
    assert build_payload(one, [PHOTONS]) == {
        "file": "/data/m000.pto/m000.spc", "datasets": ["p1"], "window_ms": 1.0}
    with pytest.raises(ValueError):
        build_payload(one, [PHOTONS, PHOTONS])  # one at a time
    many = WorkspaceInput(kinds=["photons"], many=True, key="files", with_setup=True)
    payload = build_payload(many, [PHOTONS, SETUP])
    assert payload["files"] == ["/data/m000.pto/m000.spc"]
    assert payload["setup"] == "/x/setup.json"


def test_the_rows_a_tool_takes_and_the_tools_a_row_goes_to():
    rows = workspace_rows(WorkspaceInput(kinds=["bursts"]), [PHOTONS, BURSTS, DECAY])
    assert [r["uid"] for r in rows] == ["b1"]
    assert rows[0]["result_of"] == "p1" and rows[0]["source"] == "burstwise"
    catalog = {
        "tool_a": {"accepts": [{"name": "x", "receive": "m:f",
                                "from_workspace": {"kinds": ["photons"], "many": True}}]},
        "tool_b": {"accepts": [{"name": "y", "receive": "m:f",
                                "from_workspace": {"kinds": ["decay"]}}]},
        "tool_c": {"accepts": [{"name": "z", "receive": "m:f"}]},  # not fed from the workspace
    }
    assert [p for p, _ in plugins_accepting(catalog, [PHOTONS])] == ["tool_a"]
    assert [p for p, _ in plugins_accepting(catalog, [DECAY])] == ["tool_b"]
    assert plugins_accepting(catalog, [DECAY, DECAY]) == []  # tool_b takes one at a time


def test_the_generated_input_section_goes_first_once():
    one = input_section(WorkspaceInput(kinds=["photons"]))
    table = one["sections"][0]["options"]
    assert table["source"] == "workspace_input_rows" and table["selected_call"] == "workspace_input_selected"
    many = input_section(WorkspaceInput(kinds=["photons"], many=True))
    assert many["sections"][0]["options"]["selection_attr"] == "workspace_input_selection"
    assert many["sections"][-1]["buttons"][0]["action"] == "workspace_input_use"
    view = {"sections": [{"type": "panel", "title": "Settings", "sections": []}]}
    once = with_workspace_input(view, WorkspaceInput(kinds=["photons"]))
    twice = with_workspace_input(once, WorkspaceInput(kinds=["photons"]))
    assert [s["title"] for s in twice["sections"]] == ["Input", "Settings"]
    assert view["sections"][0]["title"] == "Settings"  # the original is not modified
