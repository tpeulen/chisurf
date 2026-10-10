"""The native PSF calculator against the numbers of the Qt tool it replaced (recorded in ``qt_reference.json``).

What the Qt tool handed its 3-D renderer (the volume, the colormap, threshold and gamma, the polarization segments) is compared;
the rendered 3-D image itself is not comparable. Hermetic: temporary HOME and settings.
"""

from __future__ import annotations

import json
import pathlib
import time

import numpy as np
import pytest

from chisurf.plugins.calculator.psf_calculator.gui.app import SETTINGS, SPEC, PSFApp, make_app

from .driving import BIG, SMALL, PSFDriver, clipped_texts, draw_clip, hermetic_env, layout_problems


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def app():
    a = make_app()
    yield a
    a.close()
    a._executor.shutdown(wait=True)


def small(app):
    """A small grid (fast), the Qt defaults otherwise."""
    app.model.nxy, app.model.nz = 24, 7


def settle(app, size=BIG):
    d = PSFDriver(app, size)
    d.settle()
    return d


# -- the same numbers as the retired Qt tool (recorded in qt_reference.json) ---------------------------- #
#
# ``qt_reference.json`` was recorded from the committed Qt ``PSFCalculator`` before it was deleted: for each scenario the
# volume signature (shape, sum, max, argmax, 16 sampled voxels), the summary lines, what the tool handed its 3-D renderer
# (colormap, threshold, gamma, polarization segments), the choice-list labels, the spec field table and the two export files.

REF = json.loads((pathlib.Path(__file__).parent / "qt_reference.json").read_text())


def sig(a):
    """The signature recorded for an array (see ``qt_reference.json``)."""
    flat = np.asarray(a, dtype=float).ravel()
    return flat.sum(), flat.max(), int(flat.argmax()), flat[np.linspace(0, flat.size - 1, 16).astype(int)]


def assert_sig(array, ref):
    """The array equals the recorded signature."""
    arr = np.asarray(array)
    assert list(arr.shape) == ref["shape"]
    total, peak, argmax, samples = sig(arr)
    assert total == pytest.approx(ref["sum"], rel=1e-9)
    assert peak == pytest.approx(ref["max"], rel=1e-9)
    assert argmax == ref["argmax"]
    assert samples == pytest.approx(np.asarray(ref["samples"]), rel=1e-9, abs=1e-15)


SCENARIOS = [r["params"] for r in REF["scenarios"]]


@pytest.mark.parametrize(
    "ref",
    REF["scenarios"],
    ids=lambda r: (
        "-".join(f"{k}={v}" for k, v in r["params"].items() if k not in ("nxy", "nz"))[:60]
        or "defaults"
    ),
)
def test_the_volume_the_summary_and_what_the_renderer_gets_equal_the_recorded_qt_tool(app, ref):
    for k, v in ref["params"].items():
        setattr(app.model, k, v)
    app.model.compute()
    assert_sig(app.model.volume, ref["volume"])
    assert app.panel.summary_lines().splitlines() == ref["summary"]
    renderer = ref["renderer"]
    assert (renderer["colormap"], renderer["threshold"], renderer["gamma"]) == (
        app.model.colormap,
        app.model.threshold,
        app.model.gamma,
    )
    segments = app.model.polarization_segments() if app.model.show_polarization else None
    assert (ref["vectors"] is None) == (segments is None)
    if segments is not None:
        assert_sig(segments, ref["vectors"])


def test_every_field_of_the_qt_spec_is_in_the_emtk_spec_with_the_same_range_step_and_choices():
    def leaves(sections):
        for s in sections:
            if "attr" in s:
                yield s
            yield from leaves(s.get("sections", []))

    qt = REF["spec_fields"]
    ours = {s["attr"]: s for s in leaves(SPEC["parameters"]["sections"])}
    assert set(qt) - {"psf_volume_view"} <= set(ours) and set(ours) <= set(qt)
    for name, theirs in ours.items():
        for key in ("kind", "minimum", "maximum", "step", "decimals", "options", "labels", "label"):
            assert theirs.get(key) == qt[name].get(key), (name, key)
        if name == "quality":
            assert (
                theirs.get("style") is None and qt[name].get("style") == "radio"
            )  # deliberate: the inline radios were cut at 800 px
        else:
            assert theirs.get("style") in (
                qt[name].get("style"),
                "spin",
            )  # the number fields gain the Qt spin arrows


def test_the_choice_lists_equal_the_recorded_qt_combo_labels():
    ours = {
        s["attr"]: s.get("labels") or s["options"]
        for p in SPEC["parameters"]["sections"]
        for s in p["sections"]
        if s.get("type") == "choice"
    }
    assert REF["choices"] == ours


def test_both_export_files_equal_the_recorded_qt_exports(app, tmp_path):
    app.model.nxy, app.model.nz = 16, 5
    app.model.compute()
    exports = REF["exports"]
    assert_sig(np.load(app.model.save(tmp_path / "ours.npy")), exports["npy"])
    assert_sig(__import__("tifffile").imread(app.model.save(tmp_path / "ours.tif")), exports["tif"])


# -- spec, tooltips, Qt-free --------------------------------------------------------------------------------- #


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk(v)


def test_every_section_button_and_column_of_the_spec_has_a_description():
    missing = []
    for node in walk(SPEC):
        if (
            node.get("type") in ("button_row", "toggle", "value", "choice", "info", "panel")
            and node.get("type") != "panel"
            and not node.get("description")
        ):
            missing.append((node.get("type"), node.get("attr")))
        if node.get("type") == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    assert not missing, missing


def test_every_control_has_a_tooltip(app):
    from test.gui.emtk_port_parity import emtk_inventory

    small(app)
    settle(app)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 14


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("psf_calculator")
    assert verdict["ok"], verdict["output"]


# -- the idle state and the layout ------------------------------------------------------------------------- #


def test_controls_that_mean_nothing_in_this_state_are_greyed(app):
    p = app.panel
    assert (
        p.enabled("polarization") and not p.enabled("angle_deg") and p.enabled("show_polarization")
    )  # vectorial, circular
    app.model.polarization = "linear"
    assert p.enabled("angle_deg")
    app.model.model = "airy"
    assert (
        not p.enabled("polarization")
        and not p.enabled("angle_deg")
        and not p.enabled("show_polarization")
    )
    assert not p.enabled("export_npy") and not p.enabled("export_tif")  # nothing computed yet


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("state", ["empty", "populated"])
def test_draws_and_the_layout_is_clean(app, size, state):
    if state == "populated":
        small(app)
        settle(app, size)
    painter = draw_clip(app, size)
    assert {"Parameters", "3-D PSF", "Orthogonal Slice", "NA", "Export .npy"} <= set(
        painter.strings
    )
    plots = [app.item_rects[k] for k in ("volume", "slice") if k in app.item_rects]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    # a choice shows its whole label (emtk shortens one that does not fit)
    assert {"Vectorial (Richards-Wolf)", "Circular", "magma", "Preview (fast)", "XY"} <= set(
        painter.strings
    )


def test_settings_round_trip_clamp_and_ignore_garbage(app):
    (
        app.model.na,
        app.model.model,
        app.model.nxy,
        app.model.show_polarization,
        app.model.colormap,
    ) = 1.2, "airy", 32, False, "gray"
    app.slice_plane = "XZ"
    saved = json.loads(json.dumps(app.export_settings()))
    assert set(saved) == set(SETTINGS) | {"slice_plane"}
    other = make_app()
    try:
        other.restore_settings(saved)
        m = other.model
        assert (m.na, m.model, m.nxy, m.show_polarization, m.colormap, other.slice_plane) == (
            1.2,
            "airy",
            32,
            False,
            "gray",
            "XZ",
        )
        other.restore_settings(
            {
                "na": 99,
                "nxy": -4,
                "model": "bogus",
                "colormap": 5,
                "show_polarization": "yes",
                "slice_plane": "AB",
            }
        )
        assert (
            m.na == 1.7
            and m.nxy == 16
            and m.model == "airy"
            and m.colormap == "gray"
            and m.show_polarization is False
            and other.slice_plane == "XZ"
        )
        other.restore_settings("garbage")  # does not raise
    finally:
        other.close()
        other._executor.shutdown(wait=True)
