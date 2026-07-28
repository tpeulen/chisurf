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

from chisurf.plugins.calculator.rics_precision import core

# Small settings throughout: the estimator costs O(n_lags**4) per realisation.
# Not arbitrarily small, though -- below about three lags the fast end of the
# curve carries too little information to have a minimum at all, and below a few
# tens of realisations the Monte-Carlo scatter swamps the shape being tested.
_FAST = dict(n_lags=3, n_repeats=40, n_images=50, ny=32, seed=1)


def _reject(constant: str):
    """Fail a JSON parse on ``NaN``/``Infinity``, which are not JSON at all."""
    raise AssertionError(f"payload carries the non-JSON constant {constant!r}")


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


def test_a_request_no_acquisition_satisfies_takes_the_sweep_down():
    """An impossible *request* is reported; only an impossible scan is skipped.

    ``n_lags`` too large for the image is the case that motivates the split: it
    fails at every dwell time alike, so letting the per-point recovery swallow
    it would return a curve of NaNs, which the panel then blames on the waists
    and the pixel size. It has to reach the caller with its own message.
    """
    with pytest.raises(ValueError, match="too large for a 8x8 image"):
        core.sweep_dwell(
            10.0, core.default_dwell_range(3), nx=8, ny=8, n_lags=8,
            n_repeats=5, pixel_size=0.05,
        )


def test_summary_is_json_friendly():
    """``to_dict`` survives a round trip through a *strict* JSON reader.

    The CLI prints this payload for other programs to read, and bare ``NaN`` --
    what a dwell time the estimator cannot evaluate leaves behind -- is a Python
    extension that a strict parser in another language rejects. Such a point is
    reported as a null instead.
    """
    import json

    sweep = core.sweep_dwell(
        10.0, [0.0, *core.default_dwell_range(3)], nx=32, pixel_size=0.05,
        current_dwell=8e-6, **_FAST,
    )
    back = json.loads(json.dumps(sweep.to_dict()), parse_constant=_reject)
    assert len(back["dwell_s"]) == 4
    assert back["relative_error"][0] is None, "the impossible dwell must be null"
    assert back["current"] is not None


# --- the view model --------------------------------------------------------
def _view_model():
    """Return a view model configured for a fast test run."""
    from chisurf.plugins.calculator.rics_precision.gui.view_model import (
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


def test_the_frame_time_is_in_milliseconds_like_its_header():
    """The table's frame column carries the unit its label promises.

    ``Frame [ms]`` is the only number in the panel that prices the
    precision/time trade-off, and it is a scan line repeated ``ny`` times --
    so it must be the line time (already in ms) times ``ny``, spelled the same
    way the CLI spells it (``line * ny * 1e3``). A frame column left in
    seconds reads as 8 ms for an acquisition that costs 7.8 s.
    """
    vm = _view_model()
    assert vm.compute() is True

    rows = vm.sweep_rows()
    for row, line in zip(rows, vm.sweep.line_time):
        assert float(row["frame"]) == pytest.approx(
            float(f"{line * vm.ny * 1e3:.3g}")
        ), "the frame time must agree with the CLI's formatter"
        assert float(row["frame"]) == pytest.approx(
            float(row["line"]) * vm.ny, rel=1e-2
        ), "a frame is ny lines, in the same unit"


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

    from chisurf.plugins.calculator.rics_precision.cli import cli

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

    from chisurf.plugins.calculator.rics_precision.cli import cli

    result = CliRunner().invoke(cli, [
        "10", "--points", "3", "--nx", "32", "--ny", "32", "--frames", "50",
        "--n-lags", "3", "--repeats", "20", "--json",
    ])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.output, parse_constant=_reject)
    assert len(payload["dwell_s"]) == 3


def test_cli_json_reports_a_total_failure_instead_of_a_curve_of_nulls():
    """Settings nothing can be predicted for exit non-zero, in both output modes.

    The scripting path is the one that most needs this: a zero exit code
    carrying nulls where the errors should be reads as a result, and the same
    invocation without ``--json`` has always failed loudly. Both must agree.
    """
    import json as _json

    from click.testing import CliRunner

    from chisurf.plugins.calculator.rics_precision.cli import cli

    # no focus at all, so every point in the sweep is unevaluable
    args = ["10", "--points", "3", "--nx", "32", "--ny", "32", "--frames", "50",
            "--n-lags", "3", "--repeats", "20", "--w-r", "0"]

    result = CliRunner().invoke(cli, [*args, "--json"])
    assert result.exit_code == 1, result.output
    payload = _json.loads(result.output, parse_constant=_reject)
    assert "realisable" in payload["error"]

    assert CliRunner().invoke(cli, args).exit_code == 1


# --- hub integration -------------------------------------------------------
def test_precision_is_registered_with_the_calculators():
    """The predictor is a calculator, and is reachable as one.

    It belongs beside the FRET and FCS calculators because it shares their
    defining property: it consumes no dataset, and turns typed-in settings into
    a derived quantity. The entry must point at a widget that actually exists —
    the hub resolves it lazily, so a wrong path fails only when a user clicks.
    """
    import importlib

    from chisurf.plugins.calculator.hub.core.registry import default_calculators

    entry = next(e for e in default_calculators() if e.id == "rics_precision")
    module_name, attr = entry.widget.split(":", 1)
    assert hasattr(importlib.import_module(module_name), attr)
    assert entry.description.strip()


def test_precision_is_not_a_panel_of_the_imaging_pipeline():
    """It is *not* in Image Tools: that toolbox threads one dataset through steps.

    The Back/Next walk carries a recorded dataset from panel to panel, and this
    tool takes none — it answers before the recording exists.
    """
    from chisurf.plugins.microscopy.imaging_tools.gui.tool import (
        IMAGING_PANELS,
        ImagingToolsTool,
    )

    assert "precision" not in [p.get("role") for p in IMAGING_PANELS]
    assert "precision" not in ImagingToolsTool.PIPELINE_ORDER
