"""Easy Mode of the light-path window: what the retired Qt Easy Mode widget did, on the emtk window.

The Qt ``LightPathEasyWidget`` (and its ``LightPathEasyDialog``) are retired; these are its behaviours driven through
the window's Easy Mode dock: a template picked from the list replaces the optical path (its topology too), the
component pickers show the configuration's spectra, the last simulated configuration is kept for the PDA models and
reopened with the window, κ² and n are the user's FRET settings, and a simulation needs a dye. Before/after evidence:
okf/plugins/emtk-ports/lightpath_simulator/retire_*.
"""

from __future__ import annotations

import json

from .driving import BIG, LPDriver
from .test_emtk_lightpath_parity import in_process_client, load_catalogue


def easy(app):
    drv = LPDriver(app, BIG)
    drv.settle()
    drv.click_text("Easy Mode")
    drv.draw(3)
    return drv


#: A column inside the Easy Mode dock: the wheel scrolls the form there.
EASY_X = 900.0


def reveal(drv, label):
    """Scroll the Easy Mode form until *label* is on screen; its rectangle."""
    for _ in range(20):
        rect = drv.text_rect(label)
        if 0 <= rect[1] and rect[1] + rect[3] + 30 <= drv.size[1]:
            return rect
        drv.wheel(EASY_X, 400.0, -3 if rect[1] > 0 else 3)
    return drv.text_rect(label)


def node_types(app):
    return sorted(n.type for n in app.controller.document.nodes)


def test_the_template_list_names_the_templates_as_the_qt_list_did(app):
    labels = app.easy.template_labels
    assert "Template: 2-color (2 detector)" in labels
    assert all(label.startswith("Template: ") for label in labels)


def test_a_picked_template_replaces_the_optical_path_topology_included(app, catalogue):
    load_catalogue(app)
    drv = easy(app)
    assert node_types(app).count("detector") == 2 and "filter" in node_types(app)
    drv.click_text("Choose template")
    drv.draw(2)
    drv.click_text("Template: 3-color (3 detector)")
    drv.draw(3)
    assert node_types(app).count("detector") == 3
    # the generated path is laid out by signal flow, not stacked on its stored positions
    positions = {(round(n.pos[0]), round(n.pos[1])) for n in app.controller.document.nodes}
    assert len(positions) == len(app.controller.document.nodes)
    assert len(app.easy.config["detectors"]) == 3


def test_the_default_paths_detectors_are_named_as_the_qt_easy_mode_named_them(app, catalogue):
    """The default path titles both detector nodes "Detector" and names them in ``detector_name``."""
    load_catalogue(app)
    drv = easy(app)
    names = sorted(d["name"] for d in app.easy.config["detectors"])
    assert names == ["Green Channel", "Red Channel"]
    strings = drv.draw(2, size=(1200, 2400)).strings
    assert "Green Channel" in strings and "Red Channel" in strings


def test_the_pickers_show_the_configuration_like_the_qt_probe_tables(app, catalogue):
    """The Qt test of the two-detector template: one Dichroic splitter, an excitation dichroic, C1/C2 rows."""
    load_catalogue(app)
    config = {
        "excitation_dichroic_probe_id": catalogue["561LP dichroic"],
        "emission_splitters": [{"type": "Dichroic", "probe_id": catalogue["561LP dichroic"]}],
        "detectors": [
            {
                "name": "Green",
                "bandpass_probe_id": catalogue["BP 500/50 filter"],
                "qe_probe_id": catalogue["APD (flat QE)"],
            },
            {
                "name": "Red",
                "bandpass_probe_id": catalogue["BP 650/60 filter"],
                "qe_probe_id": catalogue["PMT (flat QE)"],
            },
        ],
        "dyes": {str(catalogue["Atto 488"]): {"qy": 0.8, "ec": 90000}},
    }
    app._load_easy(config)
    drv = easy(app)
    strings = drv.draw(2, size=(1200, 2400)).strings
    assert len(app.easy.config["emission_splitters"]) == 1
    assert app.easy.config["emission_splitters"][0]["type"] == "Dichroic"
    for label in ("Excitation dichroic:", "Splitter spectrum:", "Green", "Red", "Bandpass:"):
        assert label in strings, label
    for name in ("561LP dichroic", "BP 500/50 filter", "BP 650/60 filter", "PMT (flat QE)"):
        assert f"{name} ({catalogue[name]})" in strings, name
    for section in ("v Optical components", "v Detectors", "v Fluorophores", "v Simulation"):
        assert section in strings, section


def test_a_simulation_keeps_the_configuration_for_the_pda_models_and_the_next_window(
    app, catalogue, tmp_path
):
    from chisurf.plugins.core.lightpath_simulator.core.easy_config import (
        last_config_path,
        load_last_config,
    )

    load_catalogue(app)
    app.controller.reset()
    from chisurf.core.optical_configuration import _graph_to_config

    for node in app.controller.document.nodes:
        if node.type == "detector":
            node.config["probe_id"] = catalogue["APD (flat QE)"]
    app.controller.on_easy_sync(
        _graph_to_config(app.controller.graph())
    )  # what a graph edit notifies
    drv = easy(app)
    assert not last_config_path().exists()
    drv.click_text_scrolling("Simulate optical setup", x=EASY_X)
    drv.settle()
    assert app.controller.result["detector_signals"]
    saved = load_last_config()
    assert saved and saved["lasers"] and saved["dyes"]
    # the PDA models read it as their default light path
    assert json.loads(last_config_path().read_text())["lasers"] == saved["lasers"]

    from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

    saved["lasers"] = "561:1.0"
    last_config_path().write_text(json.dumps(saved))
    other = create_app(client=in_process_client())
    try:
        laser = next(n for n in other.controller.document.nodes if n.type == "light_source")
        assert laser.config["manual_lines"] == "561:1.0"
        assert other.easy.config["lasers"] == "561:1.0"
    finally:
        other.close()


def test_kappa2_and_n_are_the_users_fret_settings(app, monkeypatch):
    from chisurf.core.settings import cs_settings
    from chisurf.emtk.optical_configuration import OpticalConfigurationWidget
    from chisurf.plugins.core.lightpath_simulator.core import easy_config

    monkeypatch.setitem(cs_settings, "fret", {"kappa2": 0.5, "n": 1.4})
    widget = OpticalConfigurationWidget()
    assert widget.config["kappa2"] == 0.5 and widget.config["n"] == 1.4
    written = []
    monkeypatch.setattr(easy_config, "persist_fret_setting", lambda k, v: written.append((k, v)))
    drv = easy(app)
    x, y, w, h = reveal(drv, "Refractive index:")
    drv.click_at(x + 200, y + 24)
    drv.draw(2)
    assert written and written[-1][0] == "n"


def test_persist_fret_setting_writes_the_user_settings_file(tmp_path, monkeypatch):
    import yaml

    from chisurf.core.settings import cs_settings
    from chisurf.plugins.core.lightpath_simulator.core.easy_config import persist_fret_setting

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setitem(cs_settings, "fret", {})
    persist_fret_setting("kappa2", 0.42)
    assert cs_settings["fret"]["kappa2"] == 0.42
    assert (
        yaml.safe_load((tmp_path / "settings_chisurf.yaml").read_text())["fret"]["kappa2"] == 0.42
    )


def test_a_simulation_without_a_dye_says_so_and_runs_nothing(app, catalogue):
    """The Qt Easy Mode refused with "Select at least one dye."; so does the window's."""
    load_catalogue(app)
    app.easy.config["dyes"] = {}
    started = []
    real_start = app.controller.start
    app.controller.start = lambda *a, **k: (started.append(a), real_start(*a, **k))
    assert app.easy.simulate() is None
    assert started == [] and app.easy.status == "Select at least one dye."


def test_the_detector_wizards_simulation_keeps_the_configuration_for_the_pda_models(catalogue):
    """The retired Qt ``LightPathEasyDialog`` (the Detector Wizard's light path) wrote the last configuration too."""
    from chisurf.emtk.optical_configuration import OpticalConfigurationWidget
    from chisurf.plugins.core.lightpath_simulator.core.easy_config import (
        last_config_path,
        load_last_config,
    )

    widget = OpticalConfigurationWidget(
        {
            "lasers": "488:1.0",
            "dyes": {str(catalogue["Atto 488"]): {"qy": 0.8, "ec": 90000}},
            "detectors": [
                {"name": "green", "qe_probe_id": catalogue["APD (flat QE)"]},
                {"name": "red", "qe_probe_id": catalogue["APD (flat QE)"]},
            ],
            "emission_splitters": [{"type": "Dichroic", "probe_id": catalogue["561LP dichroic"]}],
        },
        auto_recalculate=False,
    )
    assert not last_config_path().exists()
    widget.simulate()
    saved = load_last_config()
    assert saved["lasers"] == "488:1.0" and str(catalogue["Atto 488"]) in saved["dyes"]
    assert [d["name"] for d in saved["detectors"]] == ["green", "red"]
    assert "_cached_results" not in saved  # session state stays out of the file
