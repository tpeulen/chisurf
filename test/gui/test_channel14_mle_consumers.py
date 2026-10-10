"""Burst MLE uses the real native detector model instead of legacy Qt table/combo fields."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import tttrlib

SOURCE = Path(__file__).resolve().parents[1] / "data/tttr/BH/132/BH_SPC132.spc"


@pytest.fixture
def mle(qapp, monkeypatch, tmp_path):
    """Build the original MLE tool with the actual native page and isolated stores."""
    from chisurf.gui.widgets import wizard as pages
    from chisurf.gui.widgets.wizard.tttr_channeldefinition.native_page import DetectorWizardPage
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setattr(pages, "DetectorWizardPage", DetectorWizardPage)
    tool = MLELifetimeAnalysisWizard()
    qapp.processEvents()
    yield tool
    tool.channel_definer.close()
    tool.close()
    qapp.processEvents()


def test_mle_detector_consumers_do_not_require_retired_qt_fields():
    """Retirement cannot retain an invisible dependency on a nonexistent native control."""
    from chisurf.plugins.burst.burst_mle_analysis import wizard

    source = Path(wizard.__file__).read_text()
    for token in ("micro_binning_combo", "setup_combo", "detectors_form"):
        assert token not in source


def test_missing_header_fallback_is_nanoseconds_for_fit_options(mle):
    """Without photon headers, the declared ps channel width must still enter the ns fit API."""
    declared_ps = mle.channel_definer.effective_micro_time_resolution
    # no header: the declared calibration stands in, so the timing is never absent
    assert mle._header_time_ns()[0] == pytest.approx(declared_ps * 1e-3)
    assert mle.dt_effective == pytest.approx(declared_ps * 1e-3)
    assert mle.excitation_period == mle.channel_definer.excitation_period


def test_real_native_mle_constructor_and_header_fallback_contract(mle, monkeypatch):
    """Existing ps/ns consumer behavior and header-first units remain exact."""
    page = mle.channel_definer
    page.model.read_tttr(SOURCE)
    assert page.host.control is page.app and page.app.page is page.editor
    assert mle.micro_time_binning == page.micro_time_binning == 1
    assert page.effective_micro_time_resolution == 3.2958984375
    assert mle.dt_effective == pytest.approx(0.0032958984375)
    assert mle.excitation_period == page.excitation_period == 13.5
    stream = tttrlib.TTTR(str(SOURCE), "SPC-130")
    monkeypatch.setattr(mle, "_current_tttr", lambda: stream)
    assert mle.dt_effective == pytest.approx(0.0032958984375)
    assert mle.excitation_period == 13.5
    page.micro_time_binning = 4
    assert mle.dt_effective == pytest.approx(0.01318359375)
    assert mle.excitation_period == 13.5


@pytest.mark.parametrize(
    ("attribute", "value"), [("g_factor", 1.314), ("l1", 0.073), ("l2", 0.042)]
)
def test_detector_calibration_setter_updates_owned_model_once(mle, attribute, value):
    """Named detector mutation preserves unknown metadata and delivers one real signal."""
    page = mle.channel_definer
    name = mle.current_detector
    page.model.data["detectors"][name]["future_metadata"] = {"retain": [1, 2]}
    previous = deepcopy(page.model.data["detectors"][name])
    spy = []
    page.detectorsChanged.connect(lambda: spy.append(True))
    setattr(mle, attribute, value)
    assert getattr(mle, attribute) == value
    stored = page.model.data["detectors"][name]
    assert stored[attribute] == value
    assert stored["future_metadata"] == previous["future_metadata"]
    assert len(spy) == 1
    setattr(mle, attribute, value)
    assert len(spy) == 1


def test_native_binning_signal_only_rebuilds_when_binning_changes(mle):
    """The actual page's binning interface replaces both old combo signal consumers."""
    page = mle.channel_definer
    spy = []
    page.micro_time_binningChanged.connect(spy.append)
    page.micro_time_binning = 4
    assert mle.micro_time_binning == 4 and len(spy) == 1
    page.micro_time_binning = 4
    assert len(spy) == 1
    assert tuple(page.binning_options) == (1, 2, 4, 8, 16, 32, 64, 128)


def test_auto_binning_uses_actual_declared_choices_and_photon_counts(mle, monkeypatch):
    """The same statistical floor chooses a legal bin without inspecting a Qt combo."""
    stream = tttrlib.TTTR(str(SOURCE), "SPC-130")
    mle.channel_definer.update_detector(mle.current_detector, {"chs": [8, 0, 3]})
    monkeypatch.setattr(mle, "_current_tttr", lambda: stream)
    monkeypatch.setattr(mle, "get_burst_indices_for_current_file", lambda: range(len(stream)))
    assert mle._auto_select_binning(target_counts_per_bin=200, irf_oversample=0) == 16
    assert mle._auto_select_binning(target_counts_per_bin=100000, irf_oversample=0) == 128


def test_native_setup_selection_is_the_actual_named_model(mle):
    """Setup-name consumers read the selected definition rather than a copied combo label."""
    page = mle.channel_definer
    settings = page.get_settings()
    settings["setup_name"] = "Validation"
    page.model.setups["Validation"] = settings
    page.select_setup("Validation")
    assert page.current_setup_name == "Validation"
    assert page.setup_name == "Validation"
    assert mle.channel_definer.get_settings()["setup_name"] == "Validation"


def test_old_wrong_unit_export_fingerprint_is_not_current(monkeypatch, tmp_path):
    """An artifact produced with the old timing fallback cannot suppress the corrected run."""
    from chisurf.core.runtime import analysis_cache
    from chisurf.plugins.burst.burst_mle_analysis import wizard

    inputs = SimpleNamespace(
        batch_input_files=lambda: [SOURCE],
        batch_settings=lambda: {"dt": 0.05, "period": 13.5},
    )
    current = wizard.MLELifetimeAnalysisWizard.batch_fingerprint(inputs)
    monkeypatch.setattr(wizard, "ALGORITHM_VERSION", 2)
    old = wizard.MLELifetimeAnalysisWizard.batch_fingerprint(inputs)
    assert old != current
    stamp = tmp_path / "cache.json"
    output = tmp_path / "old-result.dat"
    output.write_text("old incorrectly scaled fallback result\n")
    analysis_cache.write_stamp(stamp, old, outputs=[output], tool="burst_mle")
    assert analysis_cache.is_current(stamp, old)
    assert not analysis_cache.is_current(stamp, current)
