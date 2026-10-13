"""The Spectra panel's plot traces (ported from the Qt ``SpectrumView`` tests).

The Qt panel drew a probe's spectra through ``SpectrumView``; the native panel plots the
traces of :mod:`chisurf.core.fluorescence.spectrum_traces` -- one probe in a colour per
spectrum type, several ticked probes overlaid -- and the app draws them with implot.
"""

from __future__ import annotations

from chisurf.core.fluorescence.spectrum_traces import overlay_traces, probe_traces
from chisurf.plugins.emtk_test_input import Driver

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


def _probe_data(probe_id: int, name: str) -> dict:
    return {
        "probe": {"probe_id": probe_id, "chromophore_name": name},
        "spectra": [
            {"spectrum_type": "absorption", "wavelengths": [400, 500, 600], "intensity": [0, 1, 0]},
            {"spectrum_type": "emission", "wavelengths": [450, 550, 650], "intensity": [0, 1, 0]},
        ],
        "optical_properties": [],
    }


def test_display_single_probe():
    traces = probe_traces(_probe_data(1, "Cy3B"))
    assert len(traces) == 2
    assert max(traces[0]["y"]) == 1.0  # normalised to the maximum


def test_display_no_spectra_shows_empty():
    assert probe_traces({"probe": {"probe_id": 1, "chromophore_name": "X"}, "spectra": []}) == []


def test_display_multiple_probes():
    traces = overlay_traces([_probe_data(1, "Cy3B"), _probe_data(2, "ATTO647N")])
    assert len(traces) == 4
    assert len({t["color"] for t in traces}) == 2  # a colour per probe
    assert len({t["style"] for t in traces}) == 2  # a line style per spectrum type


def test_the_panel_plots_the_selected_then_the_ticked_probes(driver, app):  # noqa: F811
    panel = open_panel(driver, "spectra", "Spectra")
    driver.click(Driver.text_rect(driver.draw(2), "Acceptor GUI", last=False))
    assert len(panel.traces) == 2
    gx, gy, gw, gh = driver.rect("spectra_plot")
    assert gw > 100 and gh > 60
    for row in panel.rows:
        if row.get("chromophore_name") in ("Acceptor GUI", "Donor GUI"):
            panel.edited(row, "checked", True)
    assert len(panel.traces) == 4  # overlaid


def test_clear_removes_all_curves(driver, app):  # noqa: F811
    panel = open_panel(driver, "spectra", "Spectra")
    driver.click(Driver.text_rect(driver.draw(2), "Acceptor GUI", last=False))
    assert panel.traces
    panel.component = panel.components[1]["key"]
    panel.set_component(panel.component)  # another component type: nothing selected
    assert panel.traces == []
    assert driver.drawn("Pick a component to see its spectra.")
