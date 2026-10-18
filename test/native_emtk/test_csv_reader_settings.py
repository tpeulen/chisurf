"""The full native CSV reader preserves controls and owns its G-factor calculator."""

from __future__ import annotations

from pathlib import Path
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


def test_g_factor_action_primes_the_real_calculator_and_applies_completed_values():
    """A real native calculator delivers G, channel shift and mixing to the same reader."""
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
    child = app.calibration
    assert child is not None
    assert child.model.fp_dt_ns == reader.effective_dt
    child.model.result = {"g_factor": 1.7}
    child.model.shift = 2.6
    child.model.fp_result = {"l1": 0.12, "l2": 0.23}
    child.close()
    assert app.calibration is None
    assert reader.g_factor == 1.7 and reader.vh_shift == 3
    assert reader.l1 == 0.12 and reader.l2 == 0.23
    app.close()


def test_closing_reader_cancels_owned_inspector_without_applying_late_results():
    """The calibration child cannot mutate a reader after its owning settings view closes."""
    from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp

    reader = TCSPCReader(g_factor=1.2, record_provenance=False)
    app = ReaderSettingsApp(reader, g_factor_factory=lambda: GFactorApp(client=SimpleNamespace()))
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    driver.click("open_gfactor")
    child = app.calibration
    child.model.result = {"g_factor": 1.7}
    app.close()
    assert reader.g_factor == 1.2


def test_in_the_shell_the_calculator_is_a_dock_handed_the_readers_channel_width(monkeypatch):
    """Without a factory the reader asks the shell (``reader_calibration`` hand-off); the delivered app is primed."""
    from chisurf.core.plugin import handoff
    from chisurf.core.plugin.manifest import load_manifest
    from chisurf.emtk.reader_settings import receive_reader_calibration

    asked = []

    def hand_off(plugin_id, kind, payload, *, on_delivered=None):
        asked.append((plugin_id, kind, dict(payload)))
        delivered = SimpleNamespace(
            model=SimpleNamespace(fp_dt_ns=0.0, shift=0.0, g_factor=1.4, fp_result={}),
            close=lambda: None,
        )
        receive_reader_calibration(delivered, payload)
        on_delivered(delivered)
        return delivered

    monkeypatch.setattr(handoff, "hand_off", hand_off)
    reader = TCSPCReader(dt=0.05, record_provenance=False)
    app = ReaderSettingsApp(reader)
    driver = Driver(app, (900, 1050))
    driver.frame(2)
    driver.click("open_gfactor")
    assert asked and asked[0][:2] == ("vv_vh_g_factor", "reader_calibration")
    assert app.calibration.model.fp_dt_ns == reader.effective_dt
    app.calibration.close()
    assert reader.g_factor == 1.4
    manifest = load_manifest(
        Path(__file__).resolve().parents[2] / "chisurf/plugins/vv_vh_g_factor/manifest.json"
    )
    assert any(spec.name == "reader_calibration" for spec in manifest.accepts)
    app.close()
