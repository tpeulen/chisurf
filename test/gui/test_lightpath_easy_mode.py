from chisurf.plugins.core.lightpath_simulator.gui.easy_mode import LightPathEasyWidget


def test_two_detector_template_populates_filtered_probe_tables(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "chisurf.plugins.core.lightpath_simulator.gui.easy_mode.EASY_LAST_CONFIG_PATH",
        tmp_path / "missing-last-config.json",
    )
    probes = [
        {"probe_id": 1, "name": "Excitation", "category": "dichroic"},
        {"probe_id": 2, "name": "Splitter", "category": "dichroic"},
        {"probe_id": 3, "name": "Green filter", "category": "filter"},
        {"probe_id": 4, "name": "Green detector", "category": "detector"},
        {"probe_id": 5, "name": "Red filter", "category": "filter"},
        {"probe_id": 6, "name": "Red detector", "category": "detector"},
    ]
    config = {
        "excitation_dichroic_probe_id": 1,
        "emission_splitters": [{"type": "Dichroic", "probe_id": 2}],
        "detectors": [
            {"name": "Green", "bandpass_probe_id": 3, "qe_probe_id": 4},
            {"name": "Red", "bandpass_probe_id": 5, "qe_probe_id": 6},
        ],
    }

    widget = LightPathEasyWidget(probes)
    widget.set_optical_config(config)

    assert len(widget._splitter_tables) == 1
    assert widget._splitter_tables[0]._splitter_type == "Dichroic"
    assert (
        widget._exci_table.filtered_table.table.horizontalHeaderItem(0).text() == "Exci. Dichroic"
    )
    assert (
        widget._splitter_tables[0].filtered_table.table.horizontalHeaderItem(0).text()
        == "Splitter 1"
    )
    assert (
        widget._detector_widgets[0]["bp"].filtered_table.table.horizontalHeaderItem(0).text()
        == "C1"
    )

    widget.close()
