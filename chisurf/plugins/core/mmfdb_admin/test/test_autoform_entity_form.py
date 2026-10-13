"""The dictionary-driven entity form of the native admin (ported from the Qt ``EntityForm`` tests).

The form's sections are generated from :class:`~..gui.entity_schema.FieldSpec` lists
(:func:`~..gui.entity_values.view_section`), its values coerced in and out by
:mod:`~..gui.entity_values`, and a foreign key is a choice of ``(id, label)`` pairs
fetched with the rows -- the behaviour the Qt AutoForm wrapper had.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.core.mmfdb_admin.gui.entity_schema import FieldSpec
from chisurf.plugins.core.mmfdb_admin.gui.native.entity import EntityPanel

from .native_support import admin, admin_folder, client, seeded_template  # noqa: F401


def _specs():
    return [
        FieldSpec(name="sample_id", label="Sample ID", widget="str", readonly=True),
        FieldSpec(name="description", label="Description", widget="str"),
        FieldSpec(name="num_of_probes", label="# Probes", widget="int"),
        FieldSpec(name="conc", label="Conc", widget="float"),
        FieldSpec(
            name="solvent_phase",
            label="Phase",
            widget="choice",
            choices=["liquid", "vitrified", "other"],
        ),
        FieldSpec(name="details", label="Details", widget="text"),
        FieldSpec(name="is_public", label="Public", widget="bool"),
        FieldSpec(
            name="sample_condition_id", label="Condition", widget="str", fk_target="condition"
        ),
    ]


@pytest.fixture
def panel(admin):  # noqa: F811
    p = EntityPanel(admin, admin.entity_spec("sample"), _specs())
    p.refresh()
    return p


def test_all_field_kinds_build(panel):
    sections = [s for s in panel.form_sections() if s.get("attr") in {f.name for f in _specs()}]
    kinds = [(s["type"], s.get("kind")) for s in sections]
    assert sum(1 for t, _ in kinds if t == "value") == 5  # str, str, int, float, text
    assert sum(1 for t, _ in kinds if t == "choice") == 2  # choice + foreign key
    assert sum(1 for t, _ in kinds if t == "toggle") == 1
    assert ("value", "text") in kinds


def test_set_get_roundtrip(panel):
    panel.form.load(
        {
            "sample_id": "s1",
            "description": "my sample",
            "num_of_probes": 2,
            "conc": 1.5,
            "solvent_phase": "vitrified",
            "details": "line1\nline2",
            "is_public": 1,
            "sample_condition_id": "cond_gui",
        }
    )
    out = panel.form.data()
    assert out["sample_id"] == "s1"
    assert out["description"] == "my sample"
    assert out["num_of_probes"] == 2 and isinstance(out["num_of_probes"], int)
    assert out["conc"] == 1.5
    assert out["solvent_phase"] == "vitrified"
    assert out["details"] == "line1\nline2"
    assert out["is_public"] == 1
    assert out["sample_condition_id"] == "cond_gui"  # the id, not the label


def test_commit_not_fired_during_load(panel, monkeypatch):
    fired = []
    monkeypatch.setattr(panel, "form_committed", fired.append)
    panel.form.load({"description": "x", "num_of_probes": 1})
    assert fired == []
    panel.form.description = "edited"  # an edit committed in the form
    assert fired == ["description"]


def test_json_fields_roundtrip(admin):  # noqa: F811
    specs = [
        FieldSpec(name="laser_wavelengths", widget="text"),
        FieldSpec(name="detector_channels", widget="text"),
    ]
    p = EntityPanel(admin, admin.entity_spec("setup"), specs)
    p.form.load({"laser_wavelengths": [488, 640], "detector_channels": {"0": "green"}})
    out = p.form.data()
    assert out["laser_wavelengths"] == [488, 640]
    assert out["detector_channels"] == {"0": "green"}


def test_fk_dropdown_shows_labels_not_ids(panel):
    section = next(s for s in panel.form_sections() if s.get("attr") == "sample_condition_id")
    assert section["type"] == "choice"
    options = getattr(panel.form, section["options_source"])()
    assert options[0] == ("", "(none)")
    assert "cond_gui" in {v for v, _ in options}
    # a target record with a name is listed as "id — name", committing the id
    devices = EntityPanel(panel.admin, panel.admin.entity_spec("sample"), _device_fk())
    devices.refresh()
    assert ("dev_gui", "dev_gui — GUI Detector") in devices.fk_choices("measured_by_device_id")


def _device_fk():
    return [
        FieldSpec(name="sample_id", widget="str", readonly=True),
        FieldSpec(name="measured_by_device_id", widget="str", fk_target="device"),
    ]


def test_fk_dropdown_is_live_after_refresh(panel, client):  # noqa: F811
    before = {v for v, _ in panel.fk_choices("sample_condition_id")}
    client._call(
        "mmfdb.sample_conditions.save", {"condition": {"condition_id": "cond_new", "ph": 6.0}}
    )
    panel.refresh()
    after = {v for v, _ in panel.fk_choices("sample_condition_id")}
    assert after - before == {"cond_new"}


def test_fk_options_cached_between_loads(panel, monkeypatch):
    calls = {"n": 0}
    real = panel._fetch_fk_options

    def counted():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(panel, "_fetch_fk_options", counted)
    panel.jump_to("sample_gui")
    panel.jump_to("sample_hp3")
    panel.fk_choices("sample_condition_id")
    assert calls["n"] == 0  # record navigation makes no extra calls
    panel.refresh()
    assert calls["n"] == 1  # a refresh fetches once


def test_empty_optional_strings_become_none(panel):
    panel.form.clear()
    out = panel.form.data()
    assert out["description"] is None
    assert out["num_of_probes"] == 0
    assert out["is_public"] == 0
