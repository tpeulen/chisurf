"""Scan-precision planner: the sweep, the view model and the toolbox entry.

This tool predicts rather than measures, so the tests pin the *shape* of the
prediction (a curve with an interior minimum, moving the right way when the
sample changes) and not its numbers: every point is a Monte-Carlo estimate that
carries an uncertainty of order ``1/sqrt(2N)`` itself, so a frozen value would
only be pinning one seed.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.microscopy.img_precision import core

# Small settings throughout: the estimator costs O(n_lags**4) per realisation.
# Not arbitrarily small, though -- below about three lags the fast end of the
# curve carries too little information to have a minimum at all, and below a few
# tens of realisations the Monte-Carlo scatter swamps the shape being tested.
_FAST = dict(n_lags=3, n_repeats=40, n_images=50, ny=32, seed=1)


# --- the sweep -------------------------------------------------------------
def test_the_error_curve_has_an_interior_minimum():
    """Both extremes of dwell time are worse than somewhere in the middle.

    This is the whole reason the tool exists: scan too fast and the molecule
    has not moved between neighbouring pixels, so the correlation carries no
    information about D; scan too slow and it has already decorrelated. The
    optimum lies between, which no monotone rule of thumb would find.
    """
    sweep = core.sweep_dwell(
        10.0, core.default_dwell_range(7), nx=32, pixel_size=0.05, **_FAST
    )
    err = np.asarray(sweep.relative_error, dtype=float)
    good = np.isfinite(err)
    assert good.sum() >= 5

    best = int(np.nanargmin(np.where(good, err, np.inf)))
    assert 0 < best < len(err) - 1, "the optimum sits at an edge of the sweep"
    assert err[0] > err[best] and err[-1] > err[best]


def test_the_current_setting_is_evaluated_alongside_the_sweep():
    """A dwell time the user asked about is predicted even if it is off-grid.

    The marked point has to come from its own prediction rather than being read
    off the curve, or it could only ever land on a grid value.
    """
    sweep = core.sweep_dwell(
        10.0,
        core.default_dwell_range(5),
        nx=32,
        pixel_size=0.05,
        current_dwell=7.3e-6,
        **_FAST,
    )
    assert sweep.current is not None
    assert sweep.current.relative_error > 0.0
    assert sweep.current.pixel_time == pytest.approx(7.3e-6)
    assert 7.3e-6 not in list(sweep.dwell)


def test_line_time_grows_with_the_dwell_and_respects_the_floor():
    """A line cannot stay short while its pixels grow, but it has a minimum."""
    assert core.line_time_for(1e-5, 64, overhead=1.2) == pytest.approx(64 * 1e-5 * 1.2)
    # a scanner-imposed floor wins when the pixels are fast enough
    assert core.line_time_for(1e-9, 64, overhead=1.0, floor=1e-3) == pytest.approx(1e-3)


def test_an_unrealisable_timing_yields_a_gap_not_a_crash():
    """Settings the estimator cannot evaluate leave NaN, and the sweep goes on.

    The point matters for the GUI: a single impossible dwell time must not take
    the whole curve down with it. A dwell of zero is the sharpest case -- it
    used to divide by zero inside the estimator instead of being rejected.
    """
    sweep = core.sweep_dwell(
        10.0, [0.0, 1e-5, 2e-5], nx=32, pixel_size=0.05, **_FAST
    )
    err = np.asarray(sweep.relative_error, dtype=float)
    assert not np.isfinite(err[0])
    assert np.isfinite(err[1:]).all()


def test_the_estimator_rejects_unphysical_settings():
    """Quantities that must be positive raise ValueError, not ZeroDivisionError.

    Every one of these divides somewhere inside the algebra, so without the
    check the failure surfaced as an arithmetic error from deep in the
    estimator, which callers cannot reasonably distinguish from a bug.
    """
    from chisurf.core.experiments.ics.precision import rics_precision

    base = dict(pixel_time=1e-5, line_time=1e-3, pixel_size=0.05, nx=16, ny=16,
                n_lags=2, n_repeats=5)
    for bad in ("pixel_time", "line_time", "pixel_size", "w_r", "w_z"):
        with pytest.raises(ValueError, match=bad):
            rics_precision(10.0, **{**base, bad: 0.0})
    with pytest.raises(ValueError, match="diffusion_coefficient"):
        rics_precision(0.0, **base)


def test_summary_is_json_friendly():
    """``to_dict`` survives a round trip through JSON (used by the CLI)."""
    import json

    sweep = core.sweep_dwell(
        10.0, core.default_dwell_range(4), nx=32, pixel_size=0.05,
        current_dwell=8e-6, **_FAST,
    )
    text = json.dumps(sweep.to_dict())
    back = json.loads(text)
    assert len(back["dwell_s"]) == 4
    assert back["current"] is not None


# --- the view model --------------------------------------------------------
def _view_model():
    """Return a view model configured for a fast test run."""
    from chisurf.plugins.microscopy.img_precision.gui.view_model import (
        PrecisionViewModel,
    )

    vm = PrecisionViewModel()
    vm.n_lags, vm.n_repeats, vm.n_images = 3, 40, 50
    vm.nx = vm.ny = 32
    return vm


def test_view_model_drives_the_whole_flow():
    """Compute, then serve the plot and the table the view spec asks for."""
    vm = _view_model()
    assert vm.compute() is True
    assert vm.sweep is not None

    series = vm.sweep_series()
    assert len(series) == 2, "the curve and the user's own setting"
    for s in series:
        assert {"x", "y", "name"} <= set(s), "AutoForm needs x/y/name mappings"
        assert len(s["x"]) == len(s["y"])
    # the single-point marker would be invisible drawn as a line
    marker = series[1]
    assert marker["symbol"] and marker["no_line"]

    rows = vm.sweep_rows()
    assert rows and {"dwell", "line", "frame", "error"} == set(rows[0])
    assert "%" in vm.status or "error" in vm.status


def test_view_model_reports_a_bad_setting_without_raising():
    """An impossible configuration leaves a message, not a traceback."""
    vm = _view_model()
    vm.w_r = 0.0  # no focus at all
    assert vm.compute() is False
    assert vm.sweep is None
    assert vm.sweep_series() == [] and vm.sweep_rows() == []
    assert "failed" in vm.status.lower()


def test_view_spec_loads_and_names_real_sources():
    """Every source and attribute the view spec names exists on the model."""
    vm = _view_model()
    spec = vm.view_spec()
    assert spec is not None
    for attr in ("sweep_series", "sweep_rows", "diffusion_coefficient",
                 "n_particles", "brightness_khz", "w_r", "w_z", "pixel_size_nm",
                 "two_d", "pixel_time_us", "line_overhead", "nx", "ny",
                 "n_images", "n_lags", "n_repeats", "seed"):
        assert hasattr(vm, attr), f"view spec references missing {attr!r}"


def test_the_plot_is_logarithmic_on_both_axes():
    """A linear axis would flatten the usable range into a line.

    A badly-matched dwell time is wrong by orders of magnitude, so one such
    point on a linear axis crushes the 2-10 % region the user is choosing
    between. This was a real defect caught by looking at the rendered plot.
    """
    import json
    import pathlib

    spec = json.loads(
        (
            pathlib.Path(core.__file__).parent / "gui" / "precision.view.json"
        ).read_text()
    )

    def _find(node):
        if isinstance(node, dict):
            if node.get("type") == "plot":
                return node
            for value in node.values():
                found = _find(value)
                if found:
                    return found
        elif isinstance(node, list):
            for item in node:
                found = _find(item)
                if found:
                    return found
        return None

    plot = _find(spec)
    assert plot is not None and plot["source"] == "sweep_series"
    assert plot["log_x"] and plot["log_y"]


# --- CLI -------------------------------------------------------------------
def test_cli_predicts_and_exports(tmp_path):
    """The headless path produces the same curve and writes it out."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_precision.cli import cli

    out = tmp_path / "sweep.csv"
    result = CliRunner().invoke(cli, [
        "10", "--pixel-time", "8", "--points", "4", "--nx", "32", "--ny", "32",
        "--frames", "50", "--n-lags", "3", "--repeats", "20",
        "--out-csv", str(out),
    ])
    assert result.exit_code == 0, result.output
    assert "best around" in result.output and "your 8 µs" in result.output

    rows = out.read_text().strip().splitlines()
    assert rows[0] == "dwell_us,line_ms,frame_ms,error_percent"
    assert len(rows) == 5


def test_cli_json_is_machine_readable(tmp_path):
    """``--json`` emits the sweep as JSON and nothing else."""
    import json as _json

    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_precision.cli import cli

    result = CliRunner().invoke(cli, [
        "10", "--points", "3", "--nx", "32", "--ny", "32", "--frames", "50",
        "--n-lags", "3", "--repeats", "20", "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output)
    assert len(payload["dwell_s"]) == 3


# --- toolbox integration ---------------------------------------------------
def test_precision_is_registered_in_the_imaging_toolbox():
    """The planner is the first thing in Image Tools, and outside the pipeline.

    Planning precedes acquisition, so the panel sits ahead of the Browser. It
    is deliberately *not* in ``PIPELINE_ORDER``: the Back/Next walk threads one
    dataset through the numbered steps, and this tool consumes no data at all.
    """
    from chisurf.plugins.microscopy.imaging_tools.gui.tool import (
        IMAGING_PANELS,
        ImagingToolsTool,
    )

    names = [p["name"] for p in IMAGING_PANELS]
    roles = [p.get("role") for p in IMAGING_PANELS]
    assert "precision" in roles, "the planner is not registered in the toolbox"

    assert names.index("Plan") < names.index("Browser")
    assert "precision" not in ImagingToolsTool.PIPELINE_ORDER

    panel = IMAGING_PANELS[roles.index("precision")]
    assert callable(panel["factory"])
    assert panel["description"].strip()
