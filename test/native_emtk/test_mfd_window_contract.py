"""MFD Prepare owns its native host size and preserves measured preparation results."""

from pathlib import Path

from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.burst.mfd_prepare.gui import app as owner
from chisurf.plugins.burst.mfd_prepare.gui.model import MfdPrepareModel

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/burst_analysis_handoff"
)


def test_primary_dimensions_reach_constructor():
    """The raw primary supplies the native tool default before layout adaptation."""
    app = owner.make_app()
    assert app.window_size == (1100, 720)


def test_authored_dimensions_are_used(monkeypatch):
    """A valid authored size reaches the common metadata reader."""
    read = owner.window_size
    received = []

    def authored(spec, fallback):
        """Keep production validation when exercising another native size."""
        received.append(spec["window"])
        return read({**spec, "window": {"width": 960, "height": 680}}, fallback)

    monkeypatch.setattr(owner, "window_size", authored)
    app = owner.make_app()
    assert app.window_size == (960, 680)
    assert received == [{"width": 1100, "height": 720}]


def test_measured_preparation_survives_default_and_narrow():
    """Actual local preparation counts and detector agreements survive rendering."""
    model = MfdPrepareModel()
    assert model.set_folder(str(FIXTURE))
    model.prepare()
    assert not model.error
    assert model.result["n_bursts"] == 152
    assert all(value == 1.0 for value in model.result["count_agreement"].values())
    before = (model.report, model.detector_rows(), model.source_rows(), model.summary_rows())
    app = owner.MfdPrepareApp(model)
    for size in [(1100, 720), (736, 552)]:
        Driver(app, size).draw(3)
        assert before == (
            model.report, model.detector_rows(), model.source_rows(), model.summary_rows()
        )
        assert {"browse", "prepare", "report"} <= app.item_rects.keys()


def test_saved_geometry_wins(tmp_path, monkeypatch):
    """The common native host preference seam restores the user's dimensions."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    first = attach_native_state("mfd_window_contract", owner.make_app())
    first.window_resized(1330, 870)
    first.close()
    reopened = attach_native_state("mfd_window_contract", owner.make_app())
    try:
        assert reopened.window_size == (1330, 870)
    finally:
        reopened.close()


def test_narrow_report_reaches_the_last_detector_line():
    """Actual wheel scrolling exposes the complete measured preparation report."""
    model = MfdPrepareModel()
    assert model.set_folder(str(FIXTURE))
    model.prepare()
    assert not model.error
    app = owner.MfdPrepareApp(model)
    driver = Driver(app, (736, 552))
    driver.draw(3)
    driver.wheel(-20, at=(720, 520))
    painter = driver.draw(3)
    last = model.report.splitlines()[-1]
    matches = [t for t in painter.texts if t[5].strip() == last.strip()]
    assert matches
    assert any(0 <= t[1] < 540 for t in matches)
    assert model.result["n_bursts"] == 152


def test_actual_prepare_button_publishes_measured_results():
    """A real drop/click and SnapshotJob produce the local API's measured report."""
    app = owner.make_app()
    try:
        driver = Driver(app, (1100, 720))
        assert app.files_dropped([str(FIXTURE)])
        driver.draw(3)
        driver.click("prepare")
        driver.settle(timeout=20)
        assert not app.model.error
        assert app.model.result["n_bursts"] == 152
        assert app.model.result["total_photons"] == 17282
        assert app.model.result["count_agreement"] == {"green": 1., "red": 1., "yellow": 1.}
    finally:
        app.close()
