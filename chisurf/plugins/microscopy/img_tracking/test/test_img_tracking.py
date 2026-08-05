"""Tests for the particle-tracking plugin (core, RPC, CLI, view model)."""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import tracking as tk
from chisurf.plugins.microscopy.img_tracking import core
from chisurf.plugins.microscopy.img_tracking.backend import services

PLUGIN = pathlib.Path(__file__).parent.parent


@pytest.fixture(scope="module")
def movie():
    """A small, well-posed movie with a known diffusion coefficient."""
    frames, _ = tk.simulate_particle_movie(
        n_frames=40, shape=(160, 160), n_particles=6, diffusion_coefficient=0.5,
        sigma_psf=1.5, amplitude=250.0, background=10.0, seed=1,
    )
    return frames


# ──────────────────────────────────────────────────────────────────────────────
# Core orchestration
# ──────────────────────────────────────────────────────────────────────────────
def test_the_pipeline_produces_tracks_and_a_fit(movie):
    """Detect, link and fit in one call."""
    result = core.analyse(movie, max_distance=4.0, min_track_length=10, n_bootstrap=50)
    assert len(result.detections) > 0
    assert len(result.tracks) >= 6
    assert result.fit is not None
    assert result.fit.diffusion_coefficient == pytest.approx(0.5, rel=0.6)
    assert "D =" in result.report()


def test_a_run_with_no_long_tracks_reports_rather_than_raises(movie):
    """Detections and tracks are still worth seeing when the fit is impossible.

    They are usually what shows *why* nothing was long enough, so taking the
    whole result down with an exception would remove the diagnostic.
    """
    result = core.analyse(movie, max_distance=4.0, min_track_length=10_000)
    assert result.fit is None
    assert "no track has at least" in result.message
    assert len(result.detections) > 0
    assert "no transport fit" in result.report().lower() or "no track" in result.message


def test_the_result_serialises(movie):
    """``to_dict`` is JSON-clean, which the RPC layer depends on."""
    result = core.analyse(movie, max_distance=4.0, min_track_length=10, n_bootstrap=20)
    payload = json.loads(json.dumps(result.to_dict()))
    assert payload["n_tracks"] == len(result.tracks)
    assert payload["fit"]["diffusion_coefficient"] > 0


def test_the_csv_carries_every_linked_detection(movie, tmp_path):
    """One row per linked detection, with its track."""
    result = core.analyse(movie, max_distance=4.0, min_track_length=10, n_bootstrap=0)
    path = tmp_path / "tracks.csv"
    result.write_csv(str(path))
    lines = path.read_text().strip().split("\n")
    assert lines[0] == "track,frame,y,x,intensity"
    assert len(lines) - 1 == int(np.count_nonzero(result.tracks.track_id >= 0))


def test_the_track_table_is_sorted_longest_first(movie):
    """The longest tracks are the ones that carry the fit, so they come first."""
    result = core.analyse(movie, max_distance=4.0, min_track_length=10, n_bootstrap=0)
    lengths = [row["length"] for row in result.tracks_table()]
    assert lengths == sorted(lengths, reverse=True)


def test_calibration_changes_the_units_not_the_physics(movie):
    """Setting pixel size and frame interval rescales D by exactly the factor.

    D has units of length squared over time, so a pixel size of 0.1 um and a
    frame interval of 0.05 s must scale it by 0.1^2 / 0.05 = 0.2 and nothing
    else. A discrepancy would mean a unit is applied twice, or not at all.
    """
    raw = core.analyse(movie, max_distance=4.0, min_track_length=10, n_bootstrap=0)
    cal = core.analyse(
        movie, pixel_size=0.1, frame_interval=0.05, max_distance=4.0,
        min_track_length=10, n_bootstrap=0,
    )
    assert cal.fit.diffusion_coefficient == pytest.approx(
        raw.fit.diffusion_coefficient * 0.1 ** 2 / 0.05, rel=1e-6
    )
    assert cal.info["calibrated"] is True
    assert "µm²/s" in cal.report()


def test_loading_a_missing_channel_is_refused(tmp_path):
    """A channel index past the end must say so, not silently take channel 0."""
    from chisurf.core.fio.image import imread, imwrite

    path = tmp_path / "stack.tif"
    imwrite(str(path), np.zeros((4, 32, 32), dtype=np.uint16))
    with pytest.raises(ValueError, match="does not exist"):
        core.load_frames(path, channel=7)


# ──────────────────────────────────────────────────────────────────────────────
# RPC
# ──────────────────────────────────────────────────────────────────────────────
def test_the_rpc_can_simulate_and_track():
    """``img_tracking.jobs.simulate`` needs no files."""
    reply = services.simulate(
        {
            "n_frames": 30, "shape": [128, 128], "n_particles": 5,
            "diffusion_coefficient": 0.5, "seed": 2,
            "max_distance": 4.0, "min_track_length": 8, "n_bootstrap": 20,
        }
    )
    assert reply["ok"], reply.get("error")
    assert reply["result"]["n_tracks"] >= 5


def test_the_rpc_rejects_an_unknown_setting():
    """Silently ignoring a typo would return a result nobody asked for."""
    reply = services.track({"filename": "x.tif", "wobble": 3})
    assert reply["ok"] is False


def test_the_rpc_requires_a_filename():
    """A missing path is an error message, not a traceback across the wire."""
    reply = services.track({})
    assert reply["ok"] is False
    assert "filename" in reply["error"]


def test_an_oversized_simulation_is_refused_over_rpc():
    """The memory budget must hold on the backend too, where nobody is watching."""
    reply = services.simulate({"n_frames": 200, "shape": [2048, 2048], "n_particles": 2})
    assert reply["ok"] is False
    assert "budget" in reply["error"]


def test_every_declared_rpc_method_is_registered():
    """The manifest and the dispatcher registration must not drift apart."""
    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    registered: list[str] = []
    services.register_services(
        type("D", (), {"register": lambda self, name, fn: registered.append(name)})()
    )
    assert sorted(registered) == sorted(m["name"] for m in manifest["rpc_methods"])


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────
def test_the_cli_can_simulate_and_report(tmp_path):
    """``img-tracking --simulate`` runs headless and writes JSON and a CSV."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_tracking.cli import cli

    out = tmp_path / "result.json"
    csv = tmp_path / "tracks.csv"
    result = CliRunner().invoke(
        cli,
        ["--simulate", "--sim-frames", "30", "--sim-size", "128", "--sim-particles", "5",
         "--max-distance", "4.0", "--min-track-length", "8", "--bootstrap", "20",
         "--output", str(out), "--tracks-csv", str(csv)],
    )
    assert result.exit_code == 0, result.output
    assert "D =" in result.output
    assert json.loads(out.read_text())["n_tracks"] >= 5
    assert csv.read_text().startswith("track,frame,y,x,intensity")


def test_the_cli_refuses_to_run_with_no_input():
    """No image and no ``--simulate`` is a usage error."""
    from click.testing import CliRunner

    from chisurf.plugins.microscopy.img_tracking.cli import cli

    result = CliRunner().invoke(cli, [])
    assert result.exit_code != 0
    assert "simulate" in result.output


# ──────────────────────────────────────────────────────────────────────────────
# View model
# ──────────────────────────────────────────────────────────────────────────────
def test_the_view_model_refuses_to_run_without_data():
    """``can_run`` explains what is missing rather than failing later."""
    from chisurf.plugins.microscopy.img_tracking.gui.view_model import ImgTrackingViewModel

    model = ImgTrackingViewModel()
    assert "image stack" in model.can_run()
    model.use_simulation = True
    assert model.can_run() == ""


def test_every_view_source_is_a_callable_method():
    """AutoForm skips a source it does not find callable and renders nothing.

    A ``@property`` of the right name passes every attribute check and still
    shows an empty panel with no error anywhere, so callability is the property
    worth asserting — see the blank plots this caught on another plugin.
    """
    from chisurf.plugins.microscopy.img_tracking.gui.view_model import ImgTrackingViewModel

    model = ImgTrackingViewModel()
    model.use_simulation = True
    model.sim_n_frames = 25
    model.sim_size = 128
    model.sim_n_particles = 5
    model.max_distance = 4.0
    model.min_track_length = 8
    model.n_bootstrap = 20
    assert model.compute() is True

    spec = json.loads((PLUGIN / "gui" / "tracking.view.json").read_text())
    sources: list[str] = []

    def walk(section):
        for child in section.get("sections", []):
            if "source" in child:
                sources.append(child["source"])
            if child.get("type") == "custom":
                for key in ("target", "options"):
                    value = child.get(key)
                    if isinstance(value, str):
                        sources.append(value)
                    elif isinstance(value, dict) and "markers_source" in value:
                        sources.append(value["markers_source"])
            walk(child)

    walk(spec)
    assert sources
    for source in sources:
        assert hasattr(model, source), f"the view spec reads '{source}', the model has none"
        assert not isinstance(getattr(type(model), source, None), property), (
            f"'{source}' must be a method, not a property"
        )
        assert callable(getattr(model, source)), f"'{source}' is not callable"


def test_the_view_model_fills_every_view(monkeypatch):
    """Tables, plots and the movie all have content after a run."""
    from chisurf.plugins.microscopy.img_tracking.gui.view_model import ImgTrackingViewModel

    model = ImgTrackingViewModel()
    model.use_simulation = True
    model.sim_n_frames = 25
    model.sim_size = 128
    model.sim_n_particles = 5
    model.max_distance = 4.0
    model.min_track_length = 8
    model.n_bootstrap = 20
    assert model.compute() is True

    assert model.movie_image().shape == (25, 128, 128)
    assert len(model.detection_markers()) == len(model.result.detections)
    assert model.track_series()
    assert model.msd_series()
    assert model.length_series()
    assert model.track_rows()
    assert "<pre" in model.results_html()


def test_the_drawn_track_cap_is_respected():
    """The plot cap must bite, and must keep the longest tracks."""
    from chisurf.plugins.microscopy.img_tracking.gui.view_model import ImgTrackingViewModel

    model = ImgTrackingViewModel()
    model.use_simulation = True
    model.sim_n_frames = 25
    model.sim_size = 128
    model.sim_n_particles = 6
    model.max_distance = 4.0
    model.min_track_length = 8
    model.n_bootstrap = 0
    model.max_drawn_tracks = 2
    assert model.compute() is True
    assert len(model.track_series()) == 2


def test_a_failed_load_is_reported_not_raised():
    """A missing file leaves an explanation in the report and returns False."""
    from chisurf.plugins.microscopy.img_tracking.gui.view_model import ImgTrackingViewModel

    model = ImgTrackingViewModel()
    model.filename = "/nonexistent/nope.tif"
    assert model.compute() is False
    assert "Could not load" in model.results_text


def test_the_manifest_points_at_things_that_exist():
    """Every entry point named in the manifest must be importable."""
    import importlib

    manifest = json.loads((PLUGIN / "manifest.json").read_text())
    for key, target in manifest["entrypoints"].items():
        spec = target.split("=", 1)[-1]
        module, _, attribute = spec.partition(":")
        obj = importlib.import_module(module)
        if attribute:
            assert hasattr(obj, attribute), f"{key}: {target} has no {attribute}"
