"""Background exports identify the exact computed run, even after revisiting settings."""

import shutil
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.core.datastore import numeric_column
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel


@pytest.fixture
def measured(tmp_path, monkeypatch):
    """Copy the actual BH observation and isolate all settings and publication."""
    for name in ("CHISURF_SETTINGS_DIR", "MMFDB_SETTINGS_DIR", "MMFDB_DATABASE_PATH"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    source = (
        Path(__file__).resolve().parents[2]
        / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    )
    path = tmp_path / "m000.spc"
    shutil.copyfile(source, path)
    return path


def _detectors(stop=4095):
    """Describe one real detector, with two physically different gates."""
    return {"green": {"chs": [0, 3, 8], "micro_time_ranges": [[0, stop]]}}


def _model(path, detectors):
    """Use the actual photon parser and production fit without a GUI."""
    model = BackgroundViewModel()
    model.files = [str(path)]
    model.channels_provider = lambda: detectors
    model.tttr_provider = lambda filename: tttrlib.TTTR(filename, "SPC-130")
    model.fit_from_ms, model.fit_to_ms = 0.5, 2.0
    return model


def _run_objects(path, detectors):
    """Find run identities through stored settings rather than ambiguous names."""
    with Measurement.open(path.with_suffix(".pto")) as measurement:
        objects = []
        for obj in measurement.artifacts(artifact_kind="background_data"):
            provenance = measurement.provenance(obj.uid)
            settings = provenance["settings"]
            if settings.get("detectors", settings) == detectors:
                objects.append((obj, provenance))
        return objects


def test_revisited_settings_keep_exact_parent_and_repeat_identity(measured):
    """A → B → A cannot attach B's rate estimate to A's histogram."""
    detectors = _detectors()
    model = _model(measured, detectors)
    model.estimate()
    initial = {obj.name: obj.uid for obj, _ in _run_objects(measured, detectors)}
    assert len(initial) == 2
    detectors["green"]["micro_time_ranges"] = [[0, 2048]]
    model.estimate()
    gated = {obj.name: obj.uid for obj, _ in _run_objects(measured, detectors)}
    assert initial["background"] != gated["background"]
    detectors["green"]["micro_time_ranges"] = [[0, 4095]]
    model.estimate()
    repeated = _run_objects(measured, detectors)
    assert {obj.name: obj.uid for obj, _ in repeated} == initial
    histogram = next(p for obj, p in repeated if obj.name.startswith("background histogram"))
    assert histogram["parents"] == [initial["background"]]
    with Measurement.open(measured.with_suffix(".pto")) as measurement:
        assert measurement.parents(initial["background"]) == measurement.instrument_uids
        np.testing.assert_array_equal(
            numeric_column(measurement.get_store(initial["background histogram green"]), "Counts"),
            model.diagnostics[str(measured)]["green"].counts,
        )


@pytest.mark.parametrize("changed", ["binsize_ms", "min_counts", "fit_from_ms", "fit_to_ms"])
def test_fit_settings_are_recorded_and_have_distinct_identity(measured, changed):
    """Each output-affecting fit setting is part of the persistent run identity."""
    model = _model(measured, _detectors())
    model.estimate()
    with Measurement.open(measured.with_suffix(".pto")) as measurement:
        initial = {obj.uid for obj in measurement.artifacts(artifact_kind="background_data")}
    setattr(
        model,
        changed,
        {"binsize_ms": 0.2, "min_counts": 3, "fit_from_ms": 0.7, "fit_to_ms": 2.3}[changed],
    )
    model.estimate()
    with Measurement.open(measured.with_suffix(".pto")) as measurement:
        artifacts = measurement.artifacts(artifact_kind="background_data")
        newer = [obj for obj in artifacts if obj.uid not in initial]
        assert len(newer) == 2
        for obj in newer:
            settings = measurement.provenance(obj.uid)["settings"]
            assert settings["detectors"] == _detectors()
            for key in ("binsize_ms", "min_counts", "tail_fraction"):
                assert settings[key] == getattr(model, key)
            assert settings["tail_range_ms"] == list(model.fit_range())


def test_cached_photons_keep_their_detector_context_when_controls_change(measured):
    """Refitting old intervals cannot relabel them as a new microtime gate."""
    detectors = _detectors()
    model = _model(measured, detectors)
    model.estimate()
    detectors["green"]["micro_time_ranges"] = [[0, 2048]]
    model.binsize_ms = 0.2
    model.refit()
    model._write_containers()
    with Measurement.open(measured.with_suffix(".pto")) as measurement:
        histograms = [
            obj
            for obj in measurement.artifacts(artifact_kind="background_data")
            if obj.name.startswith("background histogram")
        ]
        newest = measurement.provenance(histograms[-1].uid)
        settings = newest["settings"]
        assert settings.get("detectors", settings) == _detectors()


@pytest.mark.parametrize("use_lut", [False, True])
def test_worker_publication_uses_frozen_reader_and_result_context(measured, use_lut):
    """Controls edited after snapshot cannot be substituted into computed metadata."""
    from chisurf.core.setup_channel_definition import ChannelDefinition
    from chisurf.plugins.burst.burst_background.gui.controller import BackgroundController

    model = BackgroundViewModel()
    controller = BackgroundController(model)
    try:
        settings = controller.channel_definition.model.get_settings()
        settings["detectors"] = _detectors()
        settings["tttr_reading"]["file_type"] = "SPC-130"
        settings["channel_shifts"] = {"0": 3}
        lut = 4095.0 * (np.arange(4096) / 4095.0) ** 1.2
        settings["channel_luts"] = {"0": lut}
        settings["apply_lut"] = use_lut
        controller.channel_definition.host(ChannelDefinition(settings))
        model.files = [str(measured)]
        model.fit_from_ms, model.fit_to_ms = 0.5, 2.0
        expected = deepcopy(controller.channel_definition.model.get_settings())
        snapshot = controller._snapshot()
        observed = snapshot.tttr_provider(str(measured))
        raw = tttrlib.TTTR(str(measured), "SPC-130")
        if use_lut:
            assert not np.array_equal(observed.micro_times, raw.micro_times)
        snapshot.estimate()
        expected["channel_luts"] = {"0": lut.tolist()}
        current = deepcopy(expected)
        current["detectors"] = _detectors(2048)
        current["channel_shifts"] = {"0": 8}
        controller.channel_definition.model.data = deepcopy(current)
        model.binsize_ms = 0.3
        controller._publish(snapshot)
        assert model.binsize_ms == 0.3
        assert controller.channel_definition.model.get_settings() == current
        with Measurement.open(measured.with_suffix(".pto")) as measurement:
            for obj in measurement.artifacts(artifact_kind="background_data"):
                written = measurement.provenance(obj.uid)["settings"]
                assert written["detectors"] == expected["detectors"]
                assert written["input_settings"] == expected
                assert written["binsize_ms"] == snapshot.binsize_ms
    finally:
        controller.close()
