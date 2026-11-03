"""The saturation calculator window: numbers, tables, summary, tooltips, layout, files and session.

For six states every plotted series is checked against the plugin's headless core (``core.py``) run directly on the
model's scheme and optics, and against what holds by construction: the unperturbed curve is the analytic 3-D Gaussian,
the excitation profile is ``exp(-2 r^2 / w_r^2)``, the state populations sum to one, the emission is ``sum_i Q_i P_i``,
zero power leaves the curve unsaturated and the volume unexpanded. The fitted curves are checked against an independent
Gauss-Newton fit (``assert_saturation_series``). Rates, brightness and the scheme list are the shipped scheme files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.calculator.fcs_saturation_calc.gui.app import PLOT_TABS, SPEC, make_app
from chisurf.plugins.calculator.fcs_saturation_calc.gui.panel import TABS

from .driving import BIG, SMALL, clipped_texts, draw_clip, hermetic_env, layout_problems

#: The six states the window is checked in: settings applied in this order.
STATES = {
    "default": {},
    "power_2mW": {"power_mW": 2.0},
    "power_0": {"power_mW": 0.0},
    "cy5_1mW": {"scheme_preset": "Cyanine 5 (4-state, isomer + triplet)", "power_mW": 1.0},
    "two_state_640_ms": {
        "scheme_preset": "Two-state (ground + excited)",
        "wavelength_nm": 640.0,
        "rate_unit": "1/ms",
        "power_mW": 0.5,
    },
    "oxazine_normalised_nobunching": {
        "scheme_preset": "Oxazine 1 (3-state, triplet)",
        "normalize_fcs": True,
        "include_bunching": False,
        "power_mW": 0.3,
    },
}
SERIES = (
    "fcs_curves_series",
    "fcs_residual_series",
    "volume_profile_series",
    "volume_power_series",
    "tau_d_power_series",
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def app():
    window = make_app(restore=False)
    yield window
    window.close()


def independent_gaussian(t, q, normalized=False):
    """Evaluate the declared Gaussian and its analytic log-parameter Jacobian."""
    td, s = np.exp(q)
    a = t / td
    b = t / (s * s * td)
    f = 1 / (1 + a) / np.sqrt(1 + b)
    jac = np.column_stack((f * (a / (1 + a) + 0.5 * b / (1 + b)), f * b / (1 + b)))
    if normalized:
        jac = (jac * f[0] - f[:, None] * jac[0]) / f[0] ** 2
        f = f / f[0]
    return f, jac


def independent_refine(t, y, q, normalized=False):
    """Refine a bounded two-parameter fit by analytic Gauss-Newton with backtracking."""
    lower, upper = np.log([1e-12, 0.5]), np.log([1.0, 100.0])
    q = np.clip(np.asarray(q, dtype=float), lower, upper)
    for count in range(300):
        f, J = independent_gaussian(t, q, normalized)
        e = f - y
        sse = float(e @ e)
        g = J.T @ e
        if np.max(np.abs(g)) < 1e-13:
            break
        step = np.linalg.lstsq(J, -e, rcond=None)[0]
        step = np.clip(step, -2.0, 2.0)
        accepted = False
        for scale in [2.0**-k for k in range(35)]:
            cand = np.clip(q + scale * step, lower, upper)
            ee = independent_gaussian(t, cand, normalized)[0] - y
            new = float(ee @ ee)
            if new < sse:
                q = cand
                accepted = True
                break
        if not accepted:
            break
    f, J = independent_gaussian(t, q, normalized)
    e = f - y
    return q, f, float(e @ e), J, count


def independent_solve(t, y, guess, normalized=False):
    """Choose the best independent fit from five distinct starting points."""
    candidates = []
    for tdscale, sscale in [(1.0, 1.0), (0.1, 1.0), (10.0, 1.0), (1.0, 0.2), (1.0, 5.0)]:
        candidates.append(
            independent_refine(t, y, np.log([guess[0] * tdscale, guess[1] * sscale]), normalized)
        )
    return min(candidates, key=lambda x: x[2])


def saturation_fit_reference(model):
    """Derive a reference minimum and display envelope from declared convergence tolerances."""
    from chisurf.core.fluorescence.fcs.saturation import (
        compute_bunching_factor,
        excitation_rate_peak,
    )

    series = {entry["name"]: entry for entry in model.fcs_curves_series}
    tau = np.asarray(series["Saturated"]["x"]) * 1e-3
    saturated = np.asarray(series["Saturated"]["y"])
    scheme = model.saturation
    bunching = (
        compute_bunching_factor(
            excitation_rate_peak(
                model.power_mW * 1e-3,
                scheme.extinction,
                model.w_r_nm * 1e-9,
                model.wavelength_nm * 1e-9,
            ),
            scheme.dark_matrix_hz,
            scheme.exc.rate_matrix(),
            scheme.brightness.array,
            tau,
        )
        if model.include_bunching
        else np.ones_like(tau)
    )
    diffusion = saturated / np.where(bunching > 0, bunching, 1.0)
    target = diffusion / diffusion[0]
    guess = (
        model.w_r_nm**2 * 1e-18 / (4.0 * model.D_um2s * 1e-12),
        max(1.0, model.w_z_nm / model.w_r_nm),
    )
    parameters, reference, minimum, jacobian, _ = independent_solve(tau, target, guess)
    # The IMP MINPACK solver declares ftol=1e-8. Cy5's weakly conditioned
    # structure direction converges within ftol, not within machine roundoff.
    budget = 1e-8 * minimum + 64.0 * np.finfo(float).eps * float(target @ target)
    if model.normalize_fcs:
        display_jacobian = (jacobian * reference[0] - reference[:, None] * jacobian[0]) / reference[
            0
        ] ** 2
        display_jacobian *= (bunching / bunching[0])[:, None]
        display = reference / reference[0] * bunching / bunching[0]
    else:
        display_jacobian = jacobian * (bunching * diffusion[0])[:, None]
        display = reference * bunching * diffusion[0]
    leverage = np.sum(
        (display_jacobian @ np.linalg.inv(jacobian.T @ jacobian)) * display_jacobian, axis=1
    )
    envelope = np.sqrt(budget * np.maximum(leverage, 0.0))
    return tau, target, bunching, diffusion, parameters, minimum, budget, display, envelope


def assert_saturation_series(model, source, name, actual, expected):
    """Keep exact physics curves; assess fitted curves against an independent scientific minimum."""
    actual, expected = np.asarray(actual), np.asarray(expected)
    if name not in {"1-component Gaussian fit", "saturated − 1-component fit"}:
        assert np.allclose(actual, expected, rtol=1e-9, atol=1e-12), (source, name)
        return
    tau, target, bunching, diffusion, reference_parameters, minimum, budget, reference, envelope = (
        saturation_fit_reference(model)
    )
    tau_d, structure, _ = model._apparent
    assert 1e-12 <= tau_d <= 1.0 and 0.5 <= structure <= 100.0
    shape = independent_gaussian(tau, np.log([tau_d, structure]))[0]
    residual = shape - target
    assert float(residual @ residual) <= minimum + budget
    shown = shape * bunching * diffusion[0]
    if model.normalize_fcs:
        shown /= shown[0]
    saturated = np.asarray(
        next(entry["y"] for entry in model.fcs_curves_series if entry["name"] == "Saturated")
    )
    expected_actual = saturated - shown if source == "fcs_residual_series" else shown
    # Exact mathematical reconstruction guards display amplitude and residual wiring.
    np.testing.assert_allclose(actual, expected_actual, rtol=1e-12, atol=1e-14)
    old_fit = saturated - expected if source == "fcs_residual_series" else expected
    # Both independently converged fits occupy an objective ellipsoid. The
    # Jacobian converts that declared accuracy into a pointwise curve bound.
    roundoff = 64.0 * np.finfo(float).eps * np.maximum(1.0, np.abs(reference))
    assert np.all(np.abs(old_fit - reference) <= 2.0 * envelope + roundoff)
    assert np.all(np.abs(shown - reference) <= 2.0 * envelope + roundoff)


def _optics(model):
    """The scheme and optics arguments the core functions take, read off the model."""
    sat = model.saturation
    return dict(
        extinction=float(sat.extinction),
        dark_matrix=sat.dark_matrix_hz,
        exc_matrix=sat.exc.rate_matrix(),
        brightness=sat.brightness.array,
        w_r_nm=float(model.w_r_nm),
        w_z_nm=float(model.w_z_nm),
        wavelength_nm=float(model.wavelength_nm),
    )


def expected_series(model, source):
    """``{name: (x, y)}`` of one plot source, from the headless core run directly on the model's settings.

    The fitted curve and its residual are taken from the model itself: ``assert_saturation_series`` checks
    those against an independent fit, not against this table.
    """
    from chisurf.plugins.calculator.fcs_saturation_calc import core

    shown = {s["name"]: (np.asarray(s["x"]), np.asarray(s["y"])) for s in getattr(model, source)}
    power = float(model.power_mW)
    if source in ("fcs_curves_series", "fcs_residual_series"):
        tau_ms, g_u, g_s = core.calculate_fcs_curves(
            power_mW=power,
            D_um2s=float(model.D_um2s),
            N=1.0,
            include_bunching=bool(model.include_bunching),
            **_optics(model),
        )
        g_u, g_s = np.asarray(g_u) / model.N, np.asarray(g_s) / model.N
        if model.normalize_fcs:
            g_u, g_s = g_u / g_u[0], g_s / g_s[0]
        out = {"Unperturbed Gaussian": (tau_ms, g_u), "Saturated": (tau_ms, g_s)}
        fitted = bool(model.show_gaussian_fit) and power > 0.0  # a fit only of a saturated curve
        if source == "fcs_residual_series":
            out = {"zero": (tau_ms, np.zeros_like(tau_ms))} if fitted else {}
        for name in ("1-component Gaussian fit", "saturated − 1-component fit"):
            if fitted and name in shown:
                out[name] = shown[name]
        assert set(out) == set(shown), (source, sorted(out), sorted(shown))
        return {name: out[name] for name in shown}
    if source == "volume_profile_series":
        prof = core.compute_volume_profile(
            power_mW=power, state_labels=model.saturation.state_labels, **_optics(model)
        )
        r = prof["r_nm"]
        out = {"Excitation k_exc(r) / peak": (r, prof["k_exc_norm"])}
        for i, label in enumerate(prof["labels"]):
            out[f"P{i + 1} ({label})"] = (r, prof["P_states"][i])
        out["Emission Σ Q_i P_i(r)"] = (r, prof["emission"])
        return {k: v for k, v in out.items() if k in shown}
    # the power sweeps run up to the decade above max(50 mW, 2 P); the marker sits on the curve at P
    ceiling = float(10.0 ** np.ceil(np.log10(max(50.0, 2.0 * power))))
    powers, v_rel, tau_d = core.compute_power_sweep_curves(
        power_mW=ceiling, D_um2s=float(model.D_um2s), **_optics(model)
    )
    y = v_rel if source == "volume_power_series" else tau_d
    name = "V_eff / V_0" if source == "volume_power_series" else "τ_D (ms)"
    return {name: (powers, y), "Current Power": ([power], [float(np.interp(power, powers, y))])}


def assert_series_by_construction(model):
    """The identities every state's series obey, whatever the scheme."""
    w_r, n = float(model.w_r_nm), float(model.N)
    curves = {s["name"]: np.asarray(s["y"]) for s in model.fcs_curves_series}
    tau = np.asarray(model.fcs_curves_series[0]["x"]) * 1e-3
    tau_d = (w_r * 1e-9) ** 2 / (4.0 * float(model.D_um2s) * 1e-12)
    k = float(model.w_z_nm) / w_r
    gauss = 1.0 / (1.0 + tau / tau_d) / np.sqrt(1.0 + tau / (k * k * tau_d))  # the 3-D Gaussian
    gauss = gauss / gauss[0] if model.normalize_fcs else gauss / n
    np.testing.assert_allclose(curves["Unperturbed Gaussian"], gauss, rtol=1e-9)
    profile = {s["name"]: (np.asarray(s["x"]), np.asarray(s["y"])) for s in model.volume_profile_series}
    r, k_exc = profile["Excitation k_exc(r) / peak"]
    gaussian_beam = np.exp(-2.0 * r**2 / w_r**2) if float(model.power_mW) > 0.0 else 0.0 * r
    np.testing.assert_allclose(k_exc, gaussian_beam, atol=1e-12)  # no light: no excitation
    populations = [y for name, (_x, y) in profile.items() if name.startswith("P")]
    np.testing.assert_allclose(np.sum(populations, axis=0), 1.0, atol=1e-9)
    q = np.ravel(model.saturation.brightness.array)
    np.testing.assert_allclose(
        profile["Emission Σ Q_i P_i(r)"][1],
        np.sum([qi * p for qi, p in zip(q, populations)], axis=0),
        atol=1e-12,
    )
    if float(model.power_mW) == 0.0:
        np.testing.assert_allclose(curves["Saturated"], curves["Unperturbed Gaussian"], rtol=1e-12)
        from chisurf.plugins.calculator.fcs_saturation_calc import core

        assert core.volume_expansion(power_mW=0.0, **_optics(model)) == 1.0  # no light: V_eff = V_0


def apply(model, settings):
    """Set the model's fields in the given order."""
    for key, value in settings.items():
        setattr(model, key, value)


def plain(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", "", text)).strip()


# -- the numbers ----------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("state", list(STATES))
def test_every_series_equals_the_core_and_obeys_its_identities(app, state):
    apply(app.model, STATES[state])
    for source in SERIES:
        ours = getattr(app.model, source)
        expected = expected_series(app.model, source)
        assert [s["name"] for s in ours] == list(expected), source
        for entry in ours:
            x, y = expected[entry["name"]]
            assert np.allclose(entry["x"], x, rtol=1e-9, atol=0.0), (source, entry["name"])
            assert_saturation_series(app.model, source, entry["name"], entry["y"], y)
    assert_series_by_construction(app.model)


def _scheme_file(model):
    """The shipped scheme file of the model's preset."""
    name = model.SCHEME_PRESETS[model.scheme_preset]
    return json.loads((Path(__file__).parents[1] / "schemes" / name).read_text())


@pytest.mark.parametrize("state", list(STATES))
def test_the_summary_shows_the_cores_numbers(app, state):
    from chisurf.plugins.calculator.fcs_saturation_calc import core

    apply(app.model, STATES[state])
    info = plain(app.model.info_text())
    ratio = core.volume_expansion(power_mW=float(app.model.power_mW), **_optics(app.model))
    shown = float(re.search(r"Volume expansion V_?eff/V_?0:\s*([\d.]+)", info).group(1))
    assert shown == pytest.approx(ratio, abs=5e-4)
    rows = app.panel.info_rows()
    assert rows, "the summary has rows"
    flat = " ".join(label + " " + value for label, value in rows)
    # every number of the summary is shown in the Info table
    for number in re.findall(r"\d+\.?\d*(?:e[+-]?\d+)?", info):
        assert number in flat + " " + app.panel.info_footer() + " " + app.panel.info_title(), number


@pytest.mark.parametrize("state", list(STATES))
def test_the_tables_show_the_schemes_rates_and_brightness(app, state):
    apply(app.model, STATES[state])
    panel, sat = app.panel, app.model.saturation
    labels = list(sat.state_labels)
    n = len(labels)
    for group, rows, prefix in (
        (sat.dark, panel.dark_rows(), "k"),
        (sat.exc, panel.exc_rows(), "sigma"),
    ):
        rates = {k: float(p.value) for k, p in group.rates_by_name().items()}
        assert [r["state"] for r in rows] == labels
        for i, row in enumerate(rows):
            for j in range(n):
                shown = row[f"c{j}"]
                if i == j:
                    assert shown is None  # the diagonal is derived, not a rate
                else:
                    assert shown == pytest.approx(rates.get(f"{prefix}{i + 1}_{j + 1}", 0.0))
    q = panel.brightness_rows()
    assert [r["value"] for r in q] == pytest.approx([float(p.value) for p in sat.brightness._brightness])
    assert [r["name"] for r in q] == [f"Q({s})" for s in labels]
    optics = {r["name"]: r for r in panel.optics_rows()}
    assert optics["P"]["value"] == pytest.approx(app.model.power_mW)
    assert optics["λ_exc"]["value"] == pytest.approx(app.model.wavelength_nm)
    for row in optics.values():
        if row["_output"]:
            assert row["fixed"] is None and row["lo"] is None and row["bounds"] is None  # outputs: no bounds


def test_every_preset_is_a_shipped_scheme_file_and_its_series_equal_the_core(app):
    names = [n for n, f in app.model.SCHEME_PRESETS.items() if f]
    assert names == [n for n in app.model.scheme_names() if n != "Custom"]
    for preset in names:
        app.model.scheme_preset = preset
        scheme = _scheme_file(app.model)
        assert scheme, preset
        for source in SERIES:
            expected = expected_series(app.model, source)
            for entry in getattr(app.model, source):
                assert_saturation_series(
                    app.model, source, entry["name"], entry["y"], expected[entry["name"]][1]
                )
        assert_series_by_construction(app.model)
    # The dye list is what the database holds: the dyes with an absorption spectrum.
    from chisurf.core.fluorescence.fret.dyes import list_absorbing_dyes

    assert app.model.dye_names() == [""] + list_absorbing_dyes()


def test_the_physical_anchors_of_the_guide_hold(app):
    """The worked example: no excitation gives the Gaussian, 0.05 mW 1.33x, 2 mW about 3.3x (guide steps 4 to 6)."""
    model = app.model
    for key, value in {
        "scheme_preset": "Rhodamine 6G (3-state, triplet)",
        "wavelength_nm": 488.0,
    }.items():
        setattr(model, key, value)
    sat = model.saturation
    sat._extinction.value, sat._w_r.value, sat._w_z.value, sat._D.value = 1e5, 250.0, 1000.0, 400.0

    def veff():
        model._on_changed()
        return model.volume_power_series[0]["y"], model.volume_power_series[0]["x"]

    model.power_mW = 0.0
    assert "1.000" in plain(model.info_text())
    model.power_mW = 0.05
    assert "1.3" in plain(model.info_text()).split("Volume expansion")[1][:30]
    model.power_mW = 2.0
    ratio = float(
        re.search(r"Volume expansion V_?eff/V_?0:\s*([\d.]+)", plain(model.info_text())).group(1)
    )
    assert 3.0 < ratio < 3.6


# -- the AutoForm spec (view.json) and the emtk spec declare the same controls ------------------------------------------------------------------------ #


def autoform_fields():
    spec = json.loads((Path(__file__).parents[1] / "gui" / "view.json").read_text())
    out = {}

    def walk(sections):
        for s in sections:
            if s.get("attr"):
                out[s["attr"]] = s
            walk(s.get("sections", []))

    walk(spec["sections"])
    return out


def our_fields():
    out = {}
    for block in SPEC.values():
        if not isinstance(block, dict):
            continue

        def walk(sections):
            for s in sections:
                if s.get("attr"):
                    out[s["attr"]] = s
                walk(s.get("sections", []))
                walk(s.get("items", []))

        walk(block.get("sections", []))
    return out


def test_every_field_of_the_autoform_spec_is_in_the_emtk_spec_with_its_range_and_choices():
    declared, ours = autoform_fields(), our_fields()
    for attr, section in declared.items():
        if section.get("type") not in ("value", "choice", "toggle"):
            continue
        assert attr in ours, f"{attr} of view.json is not in the emtk spec"
        for key in ("kind", "maximum", "decimals"):
            if key in section and attr != "power_mW":
                assert ours[attr].get(key) == section[key], (attr, key)
        if "options" in section:
            assert ours[attr]["options"] == section["options"]
        if "options_source" in section:
            assert ours[attr].get("options_source") in (section["options_source"], "dye_options")
    assert ours["power_mW"]["minimum"] == 0.0  # zero power is allowed (the slider starts at 0.001)
    assert (
        ours["power_log"]["minimum"] == -3.0 and ours["power_log"]["maximum"] == 2.0
    )  # 0.001 .. 100 mW


def test_the_plot_tabs_draw_every_plot_of_the_spec():
    declared_plots = {
        s["source"]
        for s in json.loads((Path(__file__).parents[1] / "gui" / "view.json").read_text())[
            "sections"
        ][0]["sections"]
        for s in _plots(s)
    }
    shown = {source for sources in PLOT_TABS.values() for source in sources}
    assert declared_plots == shown


def _plots(section):
    if section.get("type") == "plot":
        yield section
    for child in section.get("sections", []):
        yield from _plots(child)


def test_the_tabs_are_in_order():
    assert TABS == (
        "State diagram",
        "FCS curve",
        "Info",
        "Volume profile",
        "Volume(P)",
        "Diffusion time",
    )


# -- tooltips, descriptions, no Qt import ------------------------------------------------------------------------------ #


def walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def test_every_section_button_and_column_of_the_spec_has_a_description(app):
    missing = []
    for node in walk(SPEC):
        kind = node.get("type")
        if kind in ("button_row", "toggle", "value", "choice", "table") and not node.get(
            "description"
        ):
            missing.append((kind, node.get("attr") or node.get("name")))
        if kind == "panel" and node.get("title") and not node.get("description"):
            missing.append(("panel", node["title"]))
        if "action" in node and not node.get("description"):
            missing.append(("button", node["action"]))
    for column in app.panel.matrix_columns() + app.panel.parameter_columns():
        if not column.get("description"):
            missing.append(("column", column["key"]))
    assert not missing, missing


@pytest.mark.parametrize("tab", TABS)
def test_every_control_has_a_tooltip(app, tab):
    from test.gui.emtk_port_parity import emtk_inventory

    app.select_tab(tab)
    inventory = emtk_inventory(app, BIG)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 12


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    verdict = qt_free("fcs_saturation")
    assert verdict["ok"], verdict["output"]


# -- the layout ------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("tab", TABS)
@pytest.mark.parametrize(
    "preset", ["Rhodamine 6G (3-state, triplet)", "Cyanine 5 (4-state, isomer + triplet)"]
)
def test_every_tab_draws_and_the_layout_is_clean(app, size, tab, preset):
    app.model.scheme_preset = preset
    app.select_tab(tab)
    painter = draw_clip(app, size)
    plots = [
        app.item_rects[k]
        for k in (
            "fcs_curves_series",
            "fcs_residual_series",
            "volume_profile_series",
            "volume_power_series",
            "tau_d_power_series",
            "state_scheme",
        )
        if k in app.item_rects
    ]
    problems = layout_problems(painter, size, ignore=plots) + clipped_texts(painter, ignore=plots)
    assert not problems, problems[:6]
    assert {
        "Compute",
        "Save scheme",
        "Load session",
        "Save session",
        "Scheme",
        "Laser power",
    } <= set(painter.strings)
    # the shared toolbar vocabulary prefixes the icon: "❓  Help", "📖  Guide"
    for label in ("Guide", "Help"):
        assert any(s.strip().endswith(label) for s in painter.strings), label
    assert set(TABS) <= set(painter.strings)  # every tab button is whole
    state_labels = app.model.saturation.state_labels
    assert set(state_labels) <= set(
        painter.strings
    )  # the tables (and the diagram) name every state


def test_a_six_state_scheme_draws_in_the_small_window(app):
    app.model.saturation.n_states = 6
    app.model._on_changed()
    for tab in TABS:
        app.select_tab(tab)
        painter = draw_clip(app, SMALL)
        problems = layout_problems(
            painter,
            SMALL,
            ignore=[
                app.item_rects[k]
                for k in app.item_rects
                if k.endswith("_series") or k == "state_scheme"
            ],
        )
        assert not problems, (tab, problems[:4])


def test_the_plots_have_titles_axes_and_the_data_is_framed(app):
    from emtk.testing import RecordingPainter

    for tab, labels in {
        "FCS curve": ("FCS Saturation Effect", "τ (ms)", "G(τ)"),
        "Volume profile": ("Radial Spatial Volume Profiles", "Radial Position r (nm)"),
        "Volume(P)": ("Volume Expansion vs Laser Power", "Power (mW)", "V_eff / V_0"),
        "Diffusion time": ("Diffusion Time vs Laser Power", "Power (mW)", "τ_D (ms)"),
    }.items():
        app.select_tab(tab)
        painter = draw_clip(app, BIG)
        for label in labels:
            assert label in painter.strings, (tab, label)
        ticks = [s for s in painter.strings if re.fullmatch(r"-?[\d.]+(e[+-]?\d+)?", s)]
        assert len(ticks) >= 4, (tab, ticks)


# -- files and session ---------------------------------------------------------------------------------------------- #


def test_a_scheme_saved_and_loaded_gives_the_same_curves(app, tmp_path):
    app.model.scheme_preset = "Cyanine 5 (4-state, isomer + triplet)"
    app.model.power_mW = 0.7
    before = [np.array(s["y"]) for s in app.model.fcs_curves_series]
    app.model.save_scheme_to_file(str(tmp_path / "cy5.json"))
    other = make_app(restore=False)
    try:
        other.model.power_mW = 0.7
        other.model.load_scheme_from_file(str(tmp_path / "cy5.json"))
        after = [np.array(s["y"]) for s in other.model.fcs_curves_series]
        assert other.model.saturation.n_states == 4
        for a, b in zip(before, after):
            assert np.allclose(a, b, rtol=1e-9)
    finally:
        other.close()


def test_the_session_round_trips_through_the_settings_file(app, tmp_path):
    app.model.scheme_preset = "Two-state (ground + excited)"
    app.model.power_mW = 1.25
    app.model.wavelength_nm = 561.0
    app.model.normalize_fcs = True
    app.model.include_bunching = False
    app.model.show_power_profile = False
    app.save_session()
    path = Path(app.model.get_user_settings_path())
    assert path.is_file() and str(tmp_path) in str(
        path
    )  # the temporary settings folder, never ~/.chisurf
    saved = json.loads(path.read_text())
    assert (
        saved["power_mW"] == 1.25
        and saved["wavelength_nm"] == 561.0
        and saved["normalize_fcs"] is True
    )
    other = make_app(restore=True)
    try:
        m = other.model
        assert (
            m.power_mW,
            m.wavelength_nm,
            m.normalize_fcs,
            m.include_bunching,
            m.show_power_profile,
        ) == (1.25, 561.0, True, False, False)
        assert m.saturation.n_states == 2
    finally:
        other.close()


def test_the_real_user_settings_are_never_touched(app):
    """Saving a session and closing the window write into the temporary settings folder, not the account's ~/.chisurf."""
    import os
    import pwd

    real = (
        Path(pwd.getpwuid(os.getuid()).pw_dir)
        / ".chisurf"
        / "plugins"
        / "fcs_saturation_calc"
        / "settings.json"
    )
    before = real.stat().st_mtime_ns if real.exists() else None
    app.model.power_mW = 3.0
    app.save_session()
    app.close()
    assert (real.stat().st_mtime_ns if real.exists() else None) == before
    assert Path(app.model.get_user_settings_path()) != real


def test_independent_fit_guard_rejects_wrong_displayed_curve(app):
    """A changed fitted curve cannot hide behind the conditioned optimizer precision envelope."""
    shown = next(s for s in app.model.fcs_curves_series if s["name"] == "1-component Gaussian fit")
    with pytest.raises(AssertionError):
        assert_saturation_series(
            app.model,
            "fcs_curves_series",
            shown["name"],
            np.asarray(shown["y"]) * 1.0001,
            shown["y"],
        )
    tau, target, _, _, reference, minimum, budget, _, _ = saturation_fit_reference(app.model)
    wrong = independent_gaussian(tau, reference + np.array([1e-4, 0.0]))[0]
    residual = wrong - target
    assert float(residual @ residual) > minimum + budget
