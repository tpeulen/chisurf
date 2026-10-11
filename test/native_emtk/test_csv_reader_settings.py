"""The full native CSV reader preserves controls and owns calibration child windows."""

from __future__ import annotations

from types import SimpleNamespace

from emtk.testing import Driver

from chisurf.core.experiments.tcspc import TCSPCReader
from chisurf.emtk.reader_settings import ReaderSettingsApp


def test_full_native_csv_view_renders_every_meaningful_legacy_control():
    """No custom Qt leakage section or duplicate empty column combo is required."""
    reader = TCSPCReader(record_provenance=False)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    assert {
        "filename",
        "reading_routine",
        "colspecs",
        "delimiter",
        "skiprows",
        "use_header",
        "x_on",
        "col_x",
        "col_y",
        "error_x_on",
        "error_y_on",
        "col_ex",
        "col_ey",
        "dt",
        "dt_scaled",
        "rebin_x_key",
        "rebin_y_key",
        "rep_rate",
        "is_vv_vh",
        "polarization",
        "g_factor",
        "l1",
        "l2",
        "link_l1_l2",
        "vh_shift",
        "open_gfactor",
    } <= set(driver.ids())
    app.close()


def test_standard_leakage_controls_keep_the_declared_link():
    """The link checkbox and ordinary numeric editor preserve the same live calibration."""
    from emtk.events import CONTROL_MODIFIER
    from emtk.keys import KEY_A, KEY_RETURN

    reader = TCSPCReader(l1=0.1, l2=0.2, record_provenance=False)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    driver.click("link_l1_l2")
    assert reader.link_l1_l2 and reader.l2 == 0.1
    driver.click("l1")
    driver.key(KEY_A, modifiers=CONTROL_MODIFIER)
    driver.type("0.3")
    driver.key(KEY_RETURN)
    assert reader.l1 == reader.l2 == 0.3
    app.close()


def test_g_factor_action_opens_real_native_inspector_and_applies_completed_values(qapp):
    """A real native child delivers G, channel shift and mixing to the same reader."""
    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp

    class Client:
        """No daemon or account is contacted while proving the native action's lifecycle."""

        def calculate(self, *args, **kwargs):
            """The unopened inspector never performs a calculation in this test."""
            raise AssertionError("unexpected compute")

    reader = TCSPCReader(dt=0.02, l1=0.1, l2=0.2, record_provenance=False)
    app = ReaderSettingsApp(reader, g_factor_factory=lambda: GFactorApp(client=Client()))
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    driver.click("open_gfactor")
    host = app.calibration_host
    assert host is not None and host.isVisible()
    assert host.control.model.fp_dt_ns == reader.effective_dt
    host.control.model.result = {"g_factor": 1.7}
    host.control.model.shift = 2.6
    host.control.model.fp_result = {"l1": 0.12, "l2": 0.23}
    host.close()
    assert reader.g_factor == 1.7 and reader.vh_shift == 3
    assert reader.l1 == 0.12 and reader.l2 == 0.23
    app.close()


def test_closing_reader_cancels_owned_inspector_without_applying_late_results(qapp):
    """The calibration child cannot mutate a reader after its owning settings view closes."""
    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp

    reader = TCSPCReader(g_factor=1.2, record_provenance=False)
    app = ReaderSettingsApp(reader, g_factor_factory=lambda: GFactorApp(client=SimpleNamespace()))
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    driver.click("open_gfactor")
    host = app.calibration_host
    host.control.model.result = {"g_factor": 1.7}
    app.close()
    assert not host.isVisible() and reader.g_factor == 1.2
