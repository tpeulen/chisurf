"""The model editor over RPC: ``model.editor``, spec-declared state, components and actions.

A client (the emtk shell's Analysis dock) draws a model's own ``view.json`` editor from what
``model.editor`` resolves and writes back through ``model.state.set``, ``model.component.*``,
``model.action`` and the uid-addressed ``parameter.*`` calls. The model's spec is the allow-list
of those writes. Real fits on a fresh :class:`SessionState`, no server process.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.server.session import SessionState

REPO = Path(__file__).resolve().parents[2]
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
MODEL = "FCS (general: diffusion + bunching/anticorr)"


def _reader(name: str):
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered(allow_widgets=False)
    return next(r for r in chisurf.experiment["FCS"].readers if str(r.name) == name)


@pytest.fixture
def session():
    """A session holding Kristine's curve and the FCS demo curve, one general FCS fit on Kristine."""
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.experiments.fcs.demo import DEMO, make_demo
    from chisurf.server.services.fits import fit_create

    state = SessionState()
    state.add_dataset(_reader("Seidel Kristine").get_data(filename=str(KRISTINE)))
    state.add_dataset(_reader(DEMO["reader"]).get_data(filename=str(make_demo())))
    created = fit_create(state, dataset_index=0, model_name=MODEL)
    assert created["ok"], created
    return ChiSurfAPI(mode="local", state=state), created["uid"]


def _sections(editor: dict) -> dict:
    """Every resolved section by its title, key and label, depth first."""
    found = {}

    def walk(sections):
        for section in sections:
            for name in (section.get("title"), section.get("key"), section.get("label")):
                if name:
                    found.setdefault(name, section)
            walk(section.get("sections") or [])

    walk(editor["sections"])
    return found


def test_the_editor_is_the_view_json_resolved_against_the_model(session):
    api, uid = session
    editor = api.model_editor(fit_uid=uid)
    sections = _sections(editor)
    assert editor["state"] == {"diffusion_mode": "gauss"}
    choice = sections["Diffusion"]["sections"][0]
    assert choice["type"] == "choice" and choice["key"] == "diffusion_mode"
    assert [label for _value, label in choice["options"]] == ["MDF", "Gauss", "Two-focus"]
    assert "G(&tau;)" in sections["Equation"]["sections"][0]["text"]
    gauss = sections["3D Gaussian (single-focus)"]
    assert not gauss["hidden"] and sections["MDF (Gauss-Lorentz)"]["hidden"]
    rows = gauss["sections"][0]["rows"]
    assert [r["label"] for r in rows][:4] == ["N", "D[µm²/s]", "w<sub>r</sub>[nm]", "w<sub>z</sub>[nm]"]
    assert all(r["uid"] for r in rows)
    bunching = sections["Bunching terms"]["sections"][0]
    assert bunching["type"] == "components" and bunching["count"] == 0
    assert bunching["add_label"] == "add" and bunching["can_add"]


def test_only_what_the_spec_declares_is_set(session):
    from chisurf.server.services.model_svc import model_state_set

    api, uid = session
    assert api.model_state_set({"diffusion_mode": "mdf"}, fit_uid=uid)["ok"]
    assert api.model_state_get(fit_uid=uid)["state"]["diffusion_mode"] == "mdf"
    refused = model_state_set(api._state, {"diffusion_mode": "bogus"}, fit_uid=uid)
    assert not refused["ok"] and "takes one of" in refused["error"]
    ignored = api.model_state_set({"_diffusion_mode": "gauss"}, fit_uid=uid)
    assert ignored["keys"] == [], "an attribute the spec does not bind is not set"
    assert api.model_state_get(fit_uid=uid)["state"]["diffusion_mode"] == "mdf"
    assert not _sections(api.model_editor(fit_uid=uid))["MDF (Gauss-Lorentz)"]["hidden"]


def test_components_grow_and_shrink_through_the_declared_group(session):
    from chisurf.server.services.model_svc import model_component_add, model_component_remove

    api, uid = session
    assert api.model_component_add("bunching", fit_uid=uid)["ok"]
    bunching = _sections(api.model_editor(fit_uid=uid))["Bunching terms"]["sections"][0]
    assert bunching["count"] == 1
    assert [r["label"] for r in bunching["rows"]] == ["a<sub>b1</sub>", "&tau;<sub>b1</sub>[ms]"]
    assert api.model_component_remove("bunching", fit_uid=uid)["ok"]
    floor = model_component_remove(api._state, fit_uid=uid, target="bunching")
    assert not floor["ok"] and "keeps at least" in floor["error"]
    undeclared = model_component_add(api._state, fit_uid=uid, target="gauss")
    assert not undeclared["ok"], "a group the spec does not declare as components cannot grow"


def test_a_parameter_is_edited_by_its_uid(session):
    api, uid = session
    api.model_state_set({"diffusion_mode": "mdf"}, fit_uid=uid)
    sections = _sections(api.model_editor(fit_uid=uid))
    mdf_n = next(r for r in sections["mdf_physical"]["rows"] if r["name"] == "N")
    result = api.edit_parameter(mdf_n["uid"], fit_uid=uid, value=4.0, fixed=True, bounds=(0.5, 10))
    assert result["ok"], result
    sections = _sections(api.model_editor(fit_uid=uid))
    mdf_n = next(r for r in sections["mdf_physical"]["rows"] if r["name"] == "N")
    gauss_n = next(r for r in sections["gauss"]["rows"] if r["name"] == "N")
    assert (mdf_n["value"], mdf_n["fixed"], mdf_n["lo"], mdf_n["hi"]) == (4.0, True, 0.5, 10.0)
    assert gauss_n["value"] == 1.0, "the other preset's N of the same name is untouched"


def test_a_fit_takes_a_dataset_of_another_length(session):
    """``fit.set_dataset`` with a shorter curve: the range follows it and the model updates."""
    from chisurf.server.services.fits import fit_set_dataset, fit_update

    api, uid = session
    state = api._state
    fit = state.fits[0]
    assert len(fit.data.x) == 207
    demo = state.datasets[1]
    assert fit_set_dataset(state, fit_uid=uid, dataset_uid=demo.unique_identifier)["ok"]
    assert fit_update(state, fit_uid=uid)["ok"]
    assert len(fit.data.x) == 160 and fit.fit_range[1] <= 159
    assert fit.model.y.shape == fit.data.x.shape
    assert np.isfinite(fit.chi2r)


def test_a_global_fit_takes_its_local_fits_from_its_session(session):
    """The global fit's candidates and *Add* / *Remove* are the session's fits and model actions."""
    import chisurf
    from chisurf.server.services.fits import fit_create
    from chisurf.server.services.model_svc import model_action

    api, uid = session
    state = api._state
    other = fit_create(state, dataset_index=1, model_name=MODEL)["uid"]
    names = {str(f.unique_identifier): f.name for f in state.fits}
    from chisurf.core.experiments.globalfit.reader import GlobalFitSetup

    state.add_dataset(GlobalFitSetup(name="Global-Fit").get_data(name="Global Dataset"))
    made = fit_create(state, dataset_index=2, model_name="Global fit")
    assert made["ok"], made
    global_uid = made["uid"]
    before = list(getattr(chisurf, "fits", []) or [])
    candidates = _sections(api.model_editor(fit_uid=global_uid))["Add"]
    assert {label for _v, label in candidates["options"]} == {names[uid], names[other]}
    assert list(getattr(chisurf, "fits", []) or []) == before, "the process's fits are not read"
    for fit_uid in (uid, other):
        api.model_state_set({"selected_candidate_fit": names[fit_uid]}, fit_uid=global_uid)
        assert api.model_action("add_selected_fit", fit_uid=global_uid)["ok"]
    local = _sections(api.model_editor(fit_uid=global_uid))["local_fit_rows"]
    assert [r["name"] for r in local["rows"]] == [names[uid], names[other]]
    # A table hands its selection over as the row; Remove takes that row out.
    api.model_state_set({"selected_local_fit": {"name": names[uid]}}, fit_uid=global_uid)
    assert api.model_action("remove_selected_local_fit", fit_uid=global_uid)["ok"]
    local = _sections(api.model_editor(fit_uid=global_uid))["local_fit_rows"]
    assert [r["name"] for r in local["rows"]] == [names[other]]
    refused = model_action(state, "clear_local_fits_now", fit_uid=global_uid)
    assert not refused["ok"], "only a button the spec declares is pressed"


def test_local_first_reaches_the_group_run(session, monkeypatch):
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.server.services.fits import run_fit

    api, uid = session
    seen = []
    monkeypatch.setattr(FitGroup, "run", lambda self, local_first=None, **kw: seen.append(local_first))
    assert run_fit(api._state, fit_uid=uid, local_first=True)["ok"]
    assert run_fit(api._state, fit_uid=uid)["ok"]
    assert seen == [True, None]


def test_grouping_datasets_makes_one_fit_member_per_curve(session):
    """``dataset.group`` over RPC: it raised before; a fit over the group has one member per curve."""
    from chisurf.server.services.datasets import dataset_group
    from chisurf.server.services.fits import fit_create, fit_group_select_member, get_fit_info

    api, _uid = session
    state = api._state
    grouped = dataset_group(state, dataset_indices=[0, 1])
    assert grouped["ok"] and grouped["member_count"] == 2, grouped
    made = fit_create(state, dataset_index=len(state.datasets) - 1, model_name=MODEL)
    assert made["ok"], made
    members = get_fit_info(state, fit_uid=made["uid"])["fit"]["members"]
    assert [(m["dataset_name"], m["selected"]) for m in members] == [
        ("Kristine_with_error", True),
        ("fcs_demo", False),
    ]
    assert fit_group_select_member(state, made["uid"], 1)["ok"]
    members = get_fit_info(state, fit_uid=made["uid"])["fit"]["members"]
    assert [m["selected"] for m in members] == [False, True]


def test_the_code_face_writes_only_the_models_own_files(session, tmp_path, monkeypatch):
    """``model.code.files`` lists the model's folder; ``model.code.apply`` writes nothing else."""
    import os

    from chisurf.core.settings import path_utils
    from chisurf.server.services.model_svc import model_code_apply

    api, uid = session
    files = api.model_code_files(fit_uid=uid)
    assert files["source"].endswith(os.path.join("fcs", "general.py"))
    assert files["view_spec"].endswith("general.view.json")
    assert files["source"] in files["files"] and files["view_spec"] in files["files"]
    outside = model_code_apply(api._state, str(tmp_path / "evil.py"), "x = 1", fit_uid=uid)
    assert not outside["ok"] and "not a file of this fit's model" in outside["error"]
    # A read-only installation: the edit is kept as a timestamped copy in the settings folder.
    monkeypatch.setattr(os, "access", lambda path, mode: False)
    monkeypatch.setattr(path_utils, "get_path", lambda kind: tmp_path)
    text = Path(files["view_spec"]).read_text(encoding="utf-8")
    result = model_code_apply(api._state, files["view_spec"], text, fit_uid=uid)
    assert result["ok"] and not result["applied"], result
    saved = Path(result["saved"])
    assert saved.parent == tmp_path / "models" and saved.read_text(encoding="utf-8") == text


def test_a_toggle_row_is_a_row_of_declared_toggles():
    """The PDA model's *Abs.* toggle row: each item is resolved and may be set by its ``target.attr``."""
    from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
    from chisurf.server.services.model_svc import _declared_controls, _resolve_section

    spec = Pda2cSimpleModel.view_spec(Pda2cSimpleModel.__new__(Pda2cSimpleModel))
    rows = [s for s in spec.flat_sections() if type(s).__name__ == "ToggleRowSection"]
    assert rows, "the PDA spec declares a toggle row"
    item = rows[0].items[0]
    key = f"{item['target']}.{item['attr']}"

    class _Owner:
        pass

    model = _Owner()
    target = _Owner()
    setattr(target, item["attr"], True)
    setattr(model, item["target"], target)
    model.view_spec = lambda: spec
    assert key in _declared_controls(model)
    resolved = _resolve_section(rows[0], model, "fit", _declared_controls(model))
    assert resolved["type"] == "toggle_row"
    assert resolved["items"][0]["key"] == key and resolved["items"][0]["value"] is True
