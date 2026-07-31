"""Flow-map plugin: the whole stack, from a simulated photon stream to the arrows.

The closed loop is the point. A flow map on real data cannot be checked — arrows
appear over a picture and there is nothing to compare them with — so the plugin
ships a simulator whose velocity field is known analytically, and these tests
walk it all the way through the layers a user would: PTU on disk → image stack →
velocity field → RPC payload → CLI.

Two claims are pinned by name because they fail silently otherwise: the arrows
must point **along the flow** (a mirrored axis inverts the physics while every
number stays plausible), and a tile whose correlation peak left the tile must be
**refused**, not reported.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

import chisurf.plugins.microscopy.img_flow
from chisurf.plugins.microscopy.img_flow import core
from chisurf.plugins.microscopy.img_flow.api import flow as flow_api
from chisurf.plugins.microscopy.img_flow.client import FlowClient
from chisurf.plugins.microscopy.img_flow.demo import DEMO, create_demo, expected_profile

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def have_simulator() -> bool:
    """Whether this tttrlib build can simulate a photon stream."""
    try:
        import tttrlib
    except Exception:
        return False
    return hasattr(tttrlib, "SimEngine") and hasattr(tttrlib, "SimVectorGrid")


needs_simulator = pytest.mark.skipif(
    not have_simulator(), reason="tttrlib was built without the photon simulator"
)


# ──────────────────────────────────────────────────────────────────────────────
# A synthetic stack, so the estimator can be tested without a 30 s simulation
# ──────────────────────────────────────────────────────────────────────────────
def drifting_stack(velocity=0.5, n=48, n_frames=80, n_molecules=60, width=1.6,
                   brightness=30.0, seed=11, axis="x"):
    """Return a ``(n_frames, n, n)`` stack of blobs drifting at *velocity* px/frame."""
    rng = np.random.default_rng(seed)
    molecules = rng.uniform(0, n, size=(n_molecules, 2))
    ys, xs = np.indices((n, n))
    frames = []
    for f in range(n_frames):
        image = np.zeros((n, n))
        for cy, cx in molecules:
            if axis == "x":
                cx = (cx + velocity * f) % n
            else:
                cy = (cy + velocity * f) % n
            dx = np.minimum(np.abs(xs - cx), n - np.abs(xs - cx))
            dy = np.minimum(np.abs(ys - cy), n - np.abs(ys - cy))
            image += np.exp(-(dx ** 2 + dy ** 2) / (2.0 * width ** 2))
        frames.append(image)
    return rng.poisson(np.asarray(frames) * brightness).astype(float)


def timing_for(n=48, line_ms=0.32, pixel_nm=100.0):
    """Timing for an ``n``-line square scan."""
    return core.scan_timing(
        n, pixel_duration_us=line_ms * 1e3 / n, line_duration_ms=line_ms,
        frame_duration_ms=n * line_ms, pixel_size_nm=pixel_nm,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Core
# ──────────────────────────────────────────────────────────────────────────────
def test_the_arrows_point_along_the_flow():
    """The sign convention, pinned. Reverse the sample, reverse the arrows.

    This is the one error the tool would make silently: the speed stays right,
    the peak stays sharp, the fit stays good, and the physics is backwards.
    """
    timing = timing_for()
    scale = timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)

    # 0.5 px per frame, expressed in the units the tool reports.
    truth = 0.5 * scale

    forward = core.analyse(drifting_stack(+0.5), timing, tile=16, n_lags=4)
    backward = core.analyse(drifting_stack(-0.5), timing, tile=16, n_lags=4)
    down = core.analyse(drifting_stack(+0.5, axis="y"), timing, tile=16, n_lags=4)

    # The magnitude is checked loosely on purpose: a correlation peak in a
    # 16-pixel tile reads a few per cent low, and the claim under test is the
    # direction.
    assert 0.6 * truth < np.nanmedian(forward.vx) < 1.2 * truth
    assert -1.2 * truth < np.nanmedian(backward.vx) < -0.6 * truth
    assert abs(np.nanmedian(forward.vy)) < 0.2 * truth
    # Motion across the lines shows up in vy, not in vx.
    assert 0.6 * truth < np.nanmedian(down.vy) < 1.2 * truth
    assert abs(np.nanmedian(down.vx)) < 0.2 * abs(np.nanmedian(down.vy))


def test_a_still_sample_keeps_its_arrows_to_itself():
    """Peak jitter fitted to a line is always *some* velocity; quality catches it."""
    timing = timing_for()
    scale = timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)
    still = core.analyse(drifting_stack(0.0), timing, tile=16, n_lags=4)
    speeds = still.speed[np.isfinite(still.vx)]
    assert np.all(speeds < 0.25 * scale)
    assert still.summary(0.9)["n_kept"] < still.vx.size


def test_a_peak_that_left_its_tile_is_refused():
    """Too fast for the tile is a wrap-around, and a wrap-around looks convincing."""
    timing = timing_for()
    fast = core.analyse(drifting_stack(2.0), timing, tile=16, n_lags=5)
    assert fast.n_escaped > 0
    assert not np.any(np.isfinite(fast.vx))
    # The same data read with a lag range that keeps the peak inside is measured.
    ok = core.analyse(drifting_stack(2.0), timing, tile=16, n_lags=3)
    assert ok.n_escaped == 0
    assert np.nanmedian(ok.vx) > 0.0


def test_a_flow_map_refuses_what_it_cannot_measure():
    """A single frame, a 2-D image and an unknown estimator are all errors."""
    timing = timing_for()
    with pytest.raises(ValueError, match="not enough"):
        core.analyse(np.zeros((2, 16, 16)), timing, tile=8)
    with pytest.raises(ValueError, match="n_frames, n_lines, n_pixels"):
        core.analyse(np.zeros((16, 16)), timing, tile=8)
    with pytest.raises(ValueError, match="unknown method"):
        core.analyse(np.zeros((8, 16, 16)), timing, method="magic")
    with pytest.raises(ValueError, match="pixel size must be positive"):
        core.scan_timing(16, pixel_size_nm=0.0)


def test_the_summary_separates_a_structured_field_from_no_field():
    """Coherence is what tells 'arrows in two directions' from 'arrows at random'."""
    timing = timing_for()
    uniform = core.analyse(drifting_stack(0.5), timing, tile=16, n_lags=4)
    summary = uniform.summary(0.5)
    assert summary["coherence"] > 0.8
    assert summary["n_kept"] > 0
    assert summary["mean_speed"] > 0

    rows = core.to_rows(uniform, 0.5)
    assert rows and set(rows[0]) == {"x", "y", "vx", "vy", "speed", "angle", "quality"}


def test_the_field_can_be_written_and_read_back(tmp_path):
    """The CSV holds one row per kept tile, with a header."""
    timing = timing_for()
    analysis = core.analyse(drifting_stack(0.5), timing, tile=16, n_lags=4)
    path = core.write_csv(analysis, tmp_path / "flow.csv", 0.5)
    lines = pathlib.Path(path).read_text().strip().split("\n")
    assert lines[0] == "x,y,vx,vy,speed,angle,quality"
    assert len(lines) - 1 == int(analysis.summary(0.5)["n_kept"])


# ──────────────────────────────────────────────────────────────────────────────
# The demo — the closed loop
# ──────────────────────────────────────────────────────────────────────────────
@needs_simulator
@pytest.mark.slow
def test_the_demo_is_a_readable_ptu_whose_flow_comes_back(tmp_path):
    """Simulate, write, re-read and recover — the whole path a user takes.

    The demo has to open with **no special reader arguments**, which is the part
    that is easy to get wrong: a PTU carries its scanner geometry in image-header
    tags, and without them the file loads as a few thousand frames of nothing and
    reports no error at all.
    """
    from chisurf.core.fluorescence.imaging import load_image_stack

    result = create_demo(tmp_path / "demo.ptu", n_frames=30)
    assert result["created"] is True
    path = pathlib.Path(result["path"])
    assert path.is_file() and path.stat().st_size > 100_000

    # Opens as an image with no marker arguments, and the markers are *not*
    # mistaken for detector channels.
    stack = load_image_stack(str(path))
    assert stack.data.shape[0] == 30
    assert stack.data.shape[2:] == (DEMO["n_pixel"], DEMO["n_pixel"])
    assert stack.channel_names == ["ch0"]

    # Asking again for the *same* demo returns the file instead of simulating it
    # twice -- but asking for different settings regenerates, because a cached
    # file made with another flow is not the demo that was requested and would
    # quietly produce a map that does not match what the tool says it is showing.
    again = create_demo(tmp_path / "demo.ptu", n_frames=30)
    assert again["created"] is False
    changed = create_demo(tmp_path / "demo.ptu", n_frames=10)
    assert changed["created"] is True

    analysis = core.analyse_file(
        str(path), tile=24, n_lags=5, **{k: v for k, v in result["timing"].items()}
    )
    assert analysis.n_escaped == 0
    summary = analysis.summary(0.5)
    assert summary["n_kept"] >= 0.8 * summary["n_tiles"]

    # The simulated channel flows along +x, so the arrows must too — and the
    # profile across the channel must be parabolic, not flat.
    assert summary["mean_vx"] > 0.0
    assert abs(summary["mean_vy"]) < 0.3 * summary["mean_vx"]
    rows = np.nanmean(np.where(analysis.kept(0.5), analysis.vx, np.nan), axis=1)
    assert rows[len(rows) // 2] > 1.3 * max(rows[0], rows[-1])

    # Magnitude is expected to read low inside a shear -- documented, measured,
    # and not a reason to fail; what must hold is that it is neither zero nor
    # above the truth.
    truth = expected_profile(np.asarray(analysis.y)[:, 0]).max()
    assert 0.4 * truth < np.nanmax(rows) < 1.1 * truth


@needs_simulator
@pytest.mark.slow
def test_the_demo_reports_its_own_ground_truth(tmp_path):
    """The descriptor carries what the tool has to be checked against."""
    result = create_demo(tmp_path / "demo.ptu", n_frames=10)
    truth, timing = result["truth"], result["timing"]
    assert truth["profile"] == "poiseuille" and truth["axis"] == "x"
    assert truth["v_max_um_s"] == DEMO["v_max"]
    # The peak displacement per frame is what bounds the usable lag range, so it
    # is part of the contract rather than something the user has to work out.
    expected = truth["v_max_um_s"] * timing["frame_duration_ms"] * 1e-3 / (
        timing["pixel_size_nm"] * 1e-3
    )
    assert truth["peak_shift_px_per_frame"] == pytest.approx(expected, rel=1e-9)

    # The profile is parabolic and pinned to the walls of the scanned field.
    field = truth["field_um"]
    assert expected_profile(np.asarray([0.5 * field]))[0] == pytest.approx(
        truth["v_max_um_s"]
    )
    assert expected_profile(np.asarray([0.0, field]))[0] == pytest.approx(0.0)


# ──────────────────────────────────────────────────────────────────────────────
# The layers above core: API, RPC, client, view model
# ──────────────────────────────────────────────────────────────────────────────
def test_the_rpc_payload_is_plain_json(tmp_path):
    """Every layer above core has to survive a JSON round trip."""
    import tifffile

    path = tmp_path / "drift.tif"
    tifffile.imwrite(path, drifting_stack(0.5, n=32, n_frames=40).astype(np.float32))

    payload = flow_api.compute_map(
        str(path), tile=16, n_lags=4, pixel_duration_us=10.0, pixel_size_nm=100.0
    )
    assert json.loads(json.dumps(payload))["summary"]["n_kept"] > 0
    assert payload["shape"] == [3, 3]
    assert payload["vectors"] and payload["vectors"][0]["vx"] > 0

    methods = flow_api.list_methods()
    assert set(methods["methods"]) == set(core.METHODS)
    assert set(methods["labels"]) == set(core.METHODS)


def test_the_client_speaks_the_contract(tmp_path):
    """The in-process client reaches every registered method."""
    import tifffile

    path = tmp_path / "drift.tif"
    tifffile.imwrite(path, drifting_stack(0.5, n=32, n_frames=40).astype(np.float32))

    client = FlowClient()
    described = client.describe()
    assert described["plugin_id"] == "img_flow"
    assert "img_flow.map.compute" in described["methods"]
    assert set(client.methods()["methods"]) == set(core.METHODS)

    result = client.flow_map(
        str(path), tile=16, n_lags=4, pixel_duration_us=10.0, pixel_size_nm=100.0,
        output_path=str(tmp_path / "vectors.csv"),
    )
    assert result["summary"]["n_kept"] > 0
    assert pathlib.Path(result["output_path"]).is_file()


def test_a_failing_call_comes_back_as_an_error_not_an_exception():
    """The service envelope carries the failure; the client turns it into one."""
    from chisurf.plugins.microscopy.img_flow.backend.services import _handle_map

    envelope = _handle_map({"filename": "/no/such/file.tif"})
    assert envelope["ok"] is False and "error" in envelope
    with pytest.raises(RuntimeError):
        FlowClient().flow_map("/no/such/file.tif")


def test_the_view_model_exposes_what_the_view_spec_names(tmp_path):
    """Every source the view.json names must exist and be callable Qt-free."""
    import tifffile

    from chisurf.plugins.microscopy.img_flow.gui.view_model import FlowViewModel

    path = tmp_path / "drift.tif"
    tifffile.imwrite(path, drifting_stack(0.5, n=32, n_frames=40).astype(np.float32))

    model = FlowViewModel()
    seen: list[str] = []
    model.add_observer(seen.append)
    model.set_filename(str(path))
    assert model.channel_names() == ["ch0"]
    assert seen

    model.tile, model.n_lags = 16, 4
    model.pixel_duration_us, model.pixel_size_nm = 10.0, 100.0
    assert model.compute() is True
    assert model.result is not None
    assert model.flow_image().shape == (32, 32)
    assert len(model.flow_extent()) == 4
    assert model.flow_vectors() and set(model.flow_vectors()[0]) == {"x", "y", "dx", "dy"}
    assert model.vector_rows()
    assert model.profile_series()
    assert "mean speed" in model.summary_html()
    # No demo loaded, so nothing pretends to know the truth.
    assert model.demo_truth is None
    assert model.export_csv(str(tmp_path / "out.csv"))


#: Toolbar actions the tool defines, lower-cased, as the tour matches them.
TOOLBAR_ACTIONS = ("▶ map flow", "🧪 load demo", "💾 export csv")


def test_the_view_spec_and_the_tour_are_well_formed():
    """The authored JSON is valid, and every tour target names something real."""
    from chisurf.core.dataspec import load_view_spec
    from chisurf.gui.widgets.tools.guided_tour import load_tour

    here = pathlib.Path(__file__).resolve().parent.parent / "gui"
    assert load_view_spec(here / "flow.view.json") is not None

    steps = load_tour(here / "guide.json")
    assert len(steps) >= 5
    assert all(step.title and step.text for step in steps)

    # Every attribute a step points at must exist on the view model, and every
    # toolbar action it names must exist on the tool -- a target that resolves to
    # nothing leaves the step pointing at the middle of the window, and a
    # *waiting* step whose control cannot be found would strand the user.
    from chisurf.plugins.microscopy.img_flow.gui.view_model import FlowViewModel

    model = FlowViewModel()
    spec = pathlib.Path(here / "flow.view.json").read_text()
    for step in steps:
        attr = step.target.get("attr")
        if attr:
            assert hasattr(model, attr), attr
        title = step.target.get("title")
        if title:
            assert f'"title": "{title}"' in spec, title
        action = step.target.get("action")
        if action:
            assert any(action.lower() in a for a in TOOLBAR_ACTIONS), action

    # The tour asks the user to press the buttons rather than pressing them for
    # them, so every waiting step must point at something clickable.
    waiting = [s for s in steps if s.waits]
    assert waiting, "a tour that never asks the user to do anything is a slide deck"
    for step in waiting:
        assert step.target.get("action"), step.title
        assert step.expect.get("hint"), step.title


def test_the_manifest_declares_what_the_code_implements():
    """The manifest, the contract and the registered services must agree."""
    from chisurf.core.plugin.manifest import load_manifest
    from chisurf.plugins.microscopy.img_flow.api import contract

    here = pathlib.Path(__file__).resolve().parent.parent
    manifest = load_manifest(here / "manifest.json")
    declared = {m.name for m in manifest.rpc_methods}
    assert declared == set(contract.ALL_METHODS)
    # Every declared parameter carries a description, so AutoForm can render the
    # method as a form with tooltips.
    for method in manifest.rpc_methods:
        for name, schema in (method.params_schema.get("properties") or {}).items():
            assert schema.get("description"), f"{method.name}.{name}"


def test_the_field_is_drawn_through_chiplot_and_nothing_falls_through(qapp):
    """No pyqtgraph, and nothing quietly passing *through* chiplot either.

    Two different mistakes. Importing pyqtgraph is caught by
    ``test/test_pyqtgraph_seam.py``; calling a chiplot object with a spelling
    chiplot does not have is not — it *falls through* to the backend with a
    warning and keeps working, so the plugin silently opts itself out of the
    migration while every screenshot still looks right (PRD-64).
    """
    import numpy as np

    from chisurf.gui import chiplot
    from chisurf.gui.autoform.sections.quiver_section import QuiverSectionWidget

    class Model:
        arrow_scale = 1.0

        def flow_image(self):
            return np.random.default_rng(0).random((24, 24))

        def flow_vectors(self):
            return [{"x": 1.0 + i, "y": 1.0, "dx": 0.4, "dy": 0.2} for i in range(4)]

        def flow_extent(self):
            return (0.0, 2.4, 0.0, 2.4)

    before = set(chiplot.passthrough_gaps())
    widget = QuiverSectionWidget(
        Model(), "", image_source="flow_image", vectors_source="flow_vectors",
        extent_source="flow_extent", scale_attr="arrow_scale", units="µm/s",
    )
    widget.refresh()
    assert "4 of 4 arrows" in widget.caption.text()
    assert set(chiplot.passthrough_gaps()) - before == set()

    banned = "import " + "pyqtgraph"  # split so this file is not its own hit
    source = pathlib.Path(chisurf.plugins.microscopy.img_flow.__file__).parent
    modules = [m for m in source.rglob("*.py") if "test" not in m.parts]
    modules.append(pathlib.Path(QuiverSectionWidget.__module__.replace(".", "/") + ".py"))
    for module in modules:
        if module.is_file():
            assert banned not in module.read_text(encoding="utf-8"), module
