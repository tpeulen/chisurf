"""Background readers follow the current hosted definition without leaking corrections."""

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def private_settings(tmp_path, monkeypatch):
    """Keep detector stores and all analysis state in this test's scratch directory."""
    for name, suffix in [
        ("CHISURF_SETTINGS_DIR", "settings"),
        ("MMFDB_SETTINGS_DIR", "mmfdb"),
        ("MMFDB_DATABASE_PATH", "mmfdb.sqlite"),
        ("MMFDB_OBJECT_STORE_ROOT", "objects"),
    ]:
        monkeypatch.setenv(name, str(tmp_path / suffix))


@pytest.fixture(params=["background", "irf"])
def controller(request):
    """Construct both production controllers; IRF inherits the same reader seam."""
    if request.param == "background":
        from chisurf.plugins.burst.burst_background.gui.controller import BackgroundController
        from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

        instance = BackgroundController(BackgroundViewModel())
    else:
        from chisurf.plugins.burst.burst_irf_bg.gui.controller import IrfBackgroundController
        from chisurf.plugins.burst.burst_irf_bg.gui.view_model import IrfBackgroundViewModel

        instance = IrfBackgroundController(IrfBackgroundViewModel())
    yield instance
    instance.close()


def definition():
    """Describe the shipped BH photons with an explicit initially raw correction context."""
    return {
        "setup_name": "same-name working definition",
        "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": []}},
        "windows": {},
        "tttr_reading": {"file_type": "SPC-130", "micro_time_binning": 1},
        "channel_luts": {},
        "channel_shifts": {},
        "apply_lut": False,
    }


def measurement_path():
    """Use actual in-repository BH SPC photons, read-only and without publishing results."""
    return (
        Path(__file__).resolve().parents[2]
        / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    )


def test_hosted_reader_uses_same_name_correction_revision_and_keeps_raw_isolated(controller):
    """The captured provider follows model replacement and later LUT/shift edits by value."""
    from chisurf.core.setup_channel_definition import ChannelDefinition

    raw_definition = ChannelDefinition(definition())
    shared = ChannelDefinition(definition())
    path = measurement_path()
    assert path.is_file()
    raw = raw_definition.open_tttr(path)
    provider = controller.model.tttr_provider
    controller.channel_definition.host(shared)
    shared.data["channel_luts"] = {"0": 4095.0 * (np.arange(4096) / 4095.0) ** 1.2}
    shared.data["channel_shifts"] = {"0": 2}
    shared.data["apply_lut"] = True
    expected = shared.open_tttr(path)
    assert not np.array_equal(expected.micro_times, raw.micro_times)
    np.testing.assert_array_equal(provider(path).micro_times, expected.micro_times)
    assert controller.model.tttr_provider is provider
    assert shared.current_name == raw_definition.current_name
    np.testing.assert_array_equal(raw_definition.open_tttr(path).micro_times, raw.micro_times)
    # A second same-name revision must be read from the current shared values.
    shared.data["channel_shifts"]["0"] = 5
    revised = shared.open_tttr(path)
    assert not np.array_equal(revised.micro_times, expected.micro_times)
    np.testing.assert_array_equal(provider(path).micro_times, revised.micro_times)


def test_worker_reader_keeps_its_hosted_definition_snapshot(controller):
    """Dynamic live resolution does not alter the existing worker's frozen reader context."""
    from chisurf.core.setup_channel_definition import ChannelDefinition

    shared = ChannelDefinition(definition())
    shared.data["channel_shifts"] = {"0": 2}
    controller.channel_definition.host(shared)
    path = measurement_path()
    original = ChannelDefinition(deepcopy(shared.get_settings())).open_tttr(path)
    snapshot = controller._snapshot()
    shared.data["channel_shifts"]["0"] = 5
    current = shared.open_tttr(path)
    assert not np.array_equal(original.micro_times, current.micro_times)
    np.testing.assert_array_equal(snapshot.tttr_provider(path).micro_times, original.micro_times)
    np.testing.assert_array_equal(
        controller.model.tttr_provider(path).micro_times, current.micro_times
    )
