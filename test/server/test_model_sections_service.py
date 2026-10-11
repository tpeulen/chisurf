"""Curve pickers and custom sections of a model's editor over RPC: resolved data and declared writes.

``model.editor`` resolves ``curve_input`` and ``custom`` sections into plain data
(:mod:`chisurf.server.services.model_sections`); ``model.curve.set`` /
``model.curve.unload`` and ``model.section.call`` write back, and refuse what the
model's ``view.json`` does not declare. Real fits on a fresh :class:`SessionState`,
no server process.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from chisurf.server.session import SessionState

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"


def _reader(experiment: str, name: str):
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered(allow_widgets=False)
    return next(r for r in chisurf.experiment[experiment].readers if str(r.name) == name)


@pytest.fixture
def session():
    from chisurf.core.api import ChiSurfAPI

    state = SessionState()
    reader = _reader("TCSPC", "TXT/CSV")
    state.add_dataset(reader.get_data(filename=str(TCSPC / "Prompt.txt")))
    state.add_dataset(reader.get_data(filename=str(TCSPC / "Decay_577D.txt")))
    return ChiSurfAPI(mode="local", state=state), state


def _fit(state, model: str, dataset: int = 1) -> str:
    from chisurf.server.services.fits import fit_create

    created = fit_create(state, dataset_index=dataset, model_name=model)
    assert created["ok"], created
    return created["uid"]


def _sections(editor: dict) -> dict:
    found = {}

    def walk(sections):
        for section in sections:
            if section.get("type") in ("curve_input", "custom"):
                found[section.get("id") or section["key"]] = section
            for header in section.get("header") or []:
                found[header["id"]] = header
            walk(section.get("sections") or [])

    walk(editor["sections"])
    return found


def test_a_curve_picker_takes_a_session_dataset_and_unloads_it(session):
    api, state = session
    uid = _fit(state, "FRET: Gaussian distances")
    sections = _sections(api.model_editor(fit_uid=uid))
    assert {"convolve.irf", "generic.background_curve", "corrections.lintable"} <= set(sections)
    assert not sections["convolve.irf"]["loaded"] and sections["convolve.irf"]["shows_fwhm"]
    prompt = str(state.datasets[0].unique_identifier)
    result = api.model_curve_set("convolve.irf", prompt, fit_uid=uid)
    assert result["ok"] and result["curve"]["fwhm"] == pytest.approx(18.0)
    model = state.fits[0].model
    assert "Prompt" in model.convolve.irf.name
    assert model.convolve.irf is not state.datasets[0], "a copy is stored"
    assert api.model_curve_set("generic.background_curve", prompt, fit_uid=uid)["ok"]
    assert api.model_curve_unload("generic.background_curve", fit_uid=uid)["ok"]
    assert model.generic.background_curve is None
    assert not api.model_curve_set("convolve.nothing", prompt, fit_uid=uid)["ok"]
    assert not api.model_curve_set("convolve.irf", "no-such-dataset", fit_uid=uid)["ok"]


def test_only_declared_sections_and_operations_are_written(session):
    api, state = session
    uid = _fit(state, "FRET: Gaussian distances")
    refused = api.model_section_call("scalar_table:", "set", {"attr": "x", "value": 1}, fit_uid=uid)
    assert not refused["ok"] and "declares no section" in refused["error"]
    unknown = api.model_section_call("kappa2_controls:", "explode", {}, fit_uid=uid)
    assert not unknown["ok"] and "no operation" in unknown["error"]
    bad = api.model_section_call("kappa2_controls:", "set_mode", {"mode": "sideways"}, fit_uid=uid)
    assert not bad["ok"]


def test_kappa2_controls_regime_distribution_and_forster_radius(session):
    api, state = session
    uid = _fit(state, "FRET: Gaussian distances")
    model = state.fits[0].model
    assert api.model_section_call("kappa2_controls:", "set_mode", {"mode": "slow"}, fit_uid=uid)["ok"]
    assert model.orientation_parameter.mode == "slow"
    shown = api.model_section_call("kappa2_controls:", "distribution", {"use_fast": True}, fit_uid=uid)
    assert shown["ok"] and shown["result"]["k2"] and shown["result"]["ratio"]
    applied = api.model_section_call(
        "kappa2_controls:", "apply_distribution",
        {"k2": [0.0, 0.5, 1.0, 1.5], "p_k2": [1.0, 2.0, 1.0]}, fit_uid=uid,
    )
    # One edge too many is dropped, as the calculator returns bin edges.
    assert applied["ok"] and applied["result"]["kappa2"] == pytest.approx(1.0)
    assert model.fret_parameters.kappa2 == pytest.approx(1.0)
    assert api.model_section_call(
        "kappa2_controls:", "set_forster_radius", {"r0": 57.5}, fit_uid=uid
    )["ok"]
    assert model.fret_parameters.forster_radius == pytest.approx(57.5)
    assert not api.model_section_call(
        "kappa2_controls:", "set_forster_radius", {"r0": -1}, fit_uid=uid
    )["ok"]


def test_lifetime_options_read_and_link_another_group(session):
    api, state = session
    first = _fit(state, "Lifetime")
    second = _fit(state, "Lifetime")
    ident = "lifetime_amplitude_options:lifetimes"
    data = _sections(api.model_editor(fit_uid=second))[ident]["data"]
    target = next(t for t in data["targets"] if t["fit_uid"] == first)
    source, mine = state.fits[0].model, state.fits[1].model
    source.lifetimes.parameters_all[1].value = 3.25
    args = {k: target[k] for k in ("fit_uid", "member", "group")}
    assert api.model_section_call(ident, "read", args, fit_uid=second)["ok"]
    assert mine.lifetimes.parameters_all[1].value == pytest.approx(3.25)
    assert api.model_section_call(ident, "link", args, fit_uid=second)["ok"]
    assert mine.lifetimes.parameters_all[1].link is source.lifetimes.parameters_all[1]
    assert api.model_section_call(ident, "set", {"normalize": False}, fit_uid=second)["ok"]
    assert not mine.lifetimes.normalize_amplitudes


def test_a_mixture_lists_the_fits_of_its_own_session(session, monkeypatch):
    import chisurf

    api, state = session
    lifetime = _fit(state, "Lifetime")
    mixture = _fit(state, "Lifetime mixture")
    # Fits of another session (the Qt one's chisurf.fits) are not candidates.
    monkeypatch.setattr(chisurf, "fits", [], raising=False)
    data = _sections(api.model_editor(fit_uid=mixture))["fit_mixer:"]["data"]
    assert [c["uid"] for c in data["candidates"]] == [lifetime]
    refused = api.model_section_call("fit_mixer:", "add", {"fit_uids": ["nope"]}, fit_uid=mixture)
    assert not refused["ok"]


def test_rate_matrix_scalar_table_and_global_table():
    from chisurf.core.api import ChiSurfAPI

    sys.path.insert(0, str(REPO / "test" / "native_emtk"))
    from capture_shell_s2_models_qt_before import make_pda_curve

    state = SessionState()
    api = ChiSurfAPI(mode="local", state=state)
    state.add_dataset(_reader("FCS", "Seidel Kristine").get_data(filename=str(KRISTINE)))
    reader = _reader("PDA", "PTU/HT3/SPC")
    curve = make_pda_curve()
    curve.experiment = reader.experiment
    curve.setup = reader
    state.add_dataset(curve)
    kinetics = _fit(state, "FCS (kinetics)", dataset=0)
    ident = "rate_matrix:saturation.dark.rate_values"
    data = _sections(api.model_editor(fit_uid=kinetics))[ident]["data"]
    n = data["n"]
    assert len(data["labels"]) == n and len(data["values"]) == n * n
    assert api.model_section_call(ident, "set_cell", {"source": 0, "target": 1, "value": 4.5},
                                  fit_uid=kinetics)["ok"]
    assert list(state.fits[0].model.saturation.dark.rate_values)[1] == pytest.approx(4.5)
    diagonal = api.model_section_call(ident, "set_cell", {"source": 1, "target": 1, "value": 1.0},
                                      fit_uid=kinetics)
    assert not diagonal["ok"]

    pda = _fit(state, "PDA2c-discrete", dataset=1)
    table = next(s for s in _sections(api.model_editor(fit_uid=pda)).values()
                 if s["key"] == "scalar_table")
    row = next(r for r in table["data"]["rows"] if r["kind"] == "float")
    assert api.model_section_call(table["id"], "set", {"attr": row["attr"], "value": 0.125},
                                  fit_uid=pda)["ok"]
    assert not api.model_section_call(table["id"], "set", {"attr": "__class__", "value": 1},
                                      fit_uid=pda)["ok"]

    from chisurf.server.services.fits import fit_create

    glob = fit_create(state, dataset_index=0, model_name="Global fit")
    if glob.get("ok"):
        rows = _sections(api.model_editor(fit_uid=glob["uid"]))["global_parameter_table:"]["data"]["rows"]
        assert rows and rows[0]["row"] == 1 and "owner" in rows[0]


def test_the_described_mixture_state_is_the_same_before_and_after_binding(session):
    """``capture_session`` with a mixture fit (the Qt shell's history recorded every action so)."""
    from chisurf.core.project.session import capture_session

    api, state = session
    _fit(state, "Lifetime")
    _fit(state, "Lifetime mixture")
    assert capture_session(state.datasets, state.fits) is not None


def test_a_mixture_mixes_a_lifetime_fit_made_in_the_app(session):
    """The app's *Lifetime* fit (``tcspc_polarized``) publishes its lifetimes to a mixture.

    Its published ``lifetime_spectrum`` named a port the polarised decay does not write, so
    the mixture read ``[0.]`` and refused it as "not (amplitude, lifetime) pairs".
    """
    import numpy as np

    api, state = session
    _fit(state, "Lifetime")
    _fit(state, "Lifetime mixture")
    lifetime, mixture = state.fits[0].model, state.fits[1].model
    prompt = str(state.datasets[0].unique_identifier)
    for fit in state.fits:
        assert api.model_curve_set("convolve.irf", prompt, fit_uid=str(fit.unique_identifier))["ok"]
    mixture.append_model(lifetime)
    spectrum = np.asarray(lifetime.problem.get_output("lifetime_spectrum"))
    assert spectrum.size >= 2 and spectrum.size % 2 == 0 and np.all(spectrum[1::2] > 0)
    assert mixture.problem is not None
    mixture.update()
    assert np.all(np.isfinite(np.asarray(mixture.y)))
