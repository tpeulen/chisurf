"""Excitation Windows plugin: API, RPC, CLI and the emtk tool on the simulated PIE demo."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.simulation.pie_demo import (  # noqa: E402
    TRUTH,
    make_demo,
    wrong_setup,
)
from chisurf.plugins.core.excitation_windows import api  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return make_demo(tmp_path_factory.mktemp("demo"))


def test_detect_finds_the_demo_pulses(demo):
    det = api.detect(str(demo))
    assert det["kind"] == "pie"
    ns = det["windows_ns"]
    assert ns["prompt"][0] <= TRUTH["donor_pulse_ns"] < ns["prompt"][1]
    assert ns["delayed"][0] <= TRUTH["acceptor_pulse_ns"] < ns["delayed"][1]
    assert det["donor_detectors"] == ["ch 0"]


def test_check_flags_the_setup_of_another_instrument_and_apply_fixes_it(demo):
    rep = api.check(str(demo), wrong_setup())
    assert rep["mismatch"] and rep["status"] == "error"
    assert rep["issues"][0]["code"] == "resolution_mismatch"
    fixed = api.apply_to_setup(wrong_setup(), rep)
    assert fixed["tttr_reading"]["micro_time_resolution"] == pytest.approx(32.0)
    assert api.check(str(demo), fixed)["status"] == "ok"


def test_rpc_services(demo):
    from chisurf.plugins.core.excitation_windows.backend.services import (
        METHOD_CHECK,
        METHOD_DETECT,
        register_services,
    )

    handlers = {}

    class Dispatcher:
        def register(self, name, fn):
            handlers[name] = fn

    register_services(Dispatcher())
    assert handlers[METHOD_DETECT]({"path": str(demo)})["kind"] == "pie"
    assert handlers[METHOD_CHECK]({"path": str(demo), "setup": wrong_setup()})["mismatch"]


def test_cli_detect_and_check(demo, tmp_path):
    from chisurf.plugins.core.excitation_windows.cli.main import cli

    runner = CliRunner()
    out = runner.invoke(cli, ["detect", str(demo)])
    assert out.exit_code == 0 and out.output.startswith("pie:")
    setup = tmp_path / "wrong.json"
    setup.write_text(json.dumps(wrong_setup()))
    fixed = tmp_path / "fixed.json"
    out = runner.invoke(cli, ["check", str(demo), "--setup", str(setup), "--write", str(fixed)])
    assert out.exit_code == 1 and "converted" in out.output
    out = runner.invoke(cli, ["check", str(demo), "--setup", str(fixed)])
    assert out.exit_code == 0, out.output


def test_the_tool_draws_and_accept_saves_a_setup(demo, tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.excitation_windows.gui.app import ExcitationWindowsApp

    saved = {}
    monkeypatch.setattr(
        "chisurf.plugins.tttr.workspace_io.add_setup",
        lambda path, setup: saved.setdefault("setup", setup) and str(path),
    )
    app = ExcitationWindowsApp(setup=wrong_setup(), workspace=False)
    app.review.set_measurement(str(demo))
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, 860.0, 900.0)
    texts = " ".join(t[5] for t in painter.texts)
    assert "Use detected windows" in texts and "Detected" in texts
    for key in ("detect", "accept", "keep", "windows_plot", "guide", "help"):
        assert key in app.item_rects, key
    assert app.review.accept()
    assert saved["setup"]["windows"] == app.review.check.proposal


def test_a_donor_only_measurement_offers_nothing(tmp_path):

    from chisurf.core.fluorescence.simulation import pie_demo as d
    from chisurf.emtk.excitation_windows import WindowsReview
    path = tmp_path / "donly.ptu"
    d.make_demo(path.parent, donor_only=True, name=path.name, n_photons=100_000)
    review = WindowsReview(wrong_setup(), workspace=False)
    review.set_measurement(str(path))
    assert review.detection.kind == "single"
    assert not review.enabled("accept") and not review.accept()
    assert "donor-only" in review.status_text
