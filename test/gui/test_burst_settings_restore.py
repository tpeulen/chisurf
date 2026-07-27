"""A burst folder repopulates the tool that produced it.

Recording what an analysis ran with is only half a reproducible result; reading
it back into the tool is the other half. These drive the round trip
widgets → settings → folder → widgets and assert it returns to where it started.

A round trip is the only test that catches the failure that matters here. Every
field individually "looks applied" whether or not its units match, and the one
value read out twice in different units — ``dT_max``, in seconds via
``burst_detection.time_window`` and in milliseconds via
``delta_macro_time_filter`` — would rescale the burst search by 1000 per trip
while every isolated assertion still passed.
"""

from __future__ import annotations

import pytest

from chisurf.gui.widgets.wizard.tttr_photonfilter.filter_settings_form import (
    FilterSettings,
    FilterSettingsModel,
)
from chisurf.plugins.burst.burst_selection.api.models import AnalysisSettings
from chisurf.plugins.burst.burst_selection.gui.adapter import (
    analysis_settings_from_wizard,
    apply_analysis_folder,
    apply_analysis_settings_to_wizard,
)


class Checkbox:
    """The bit of QCheckBox this adapter uses."""

    def __init__(self, checked=False):
        self._checked = bool(checked)

    def isChecked(self):
        return self._checked

    def setChecked(self, value):
        self._checked = bool(value)


class Finder:
    """Stand-in for the photon-filter page, over the **real** settings model.

    The page's own attributes are properties over ``filter_settings``, and the
    restore now goes through the generated form's model rather than through a
    hand-written per-field mapping — so a stub with plain attributes would test
    nothing that exists. This mirrors the real page: one FilterSettings object,
    with the accessors the adapter uses defined on top of it.
    """

    def __init__(self):
        self.filter_settings = FilterSettings()
        self._filter_settings_model = FilterSettingsModel(self.filter_settings)
        self.channels = [0, 1]
        self.microtime_ranges = []
        self.tttrlib_algorithm = "maxtree"
        self.tttrlib_parameters = {}
        self.cusum_bg_rate = 2000
        self.trace_bin_width = 1.0

    # -- properties over the one settings object, as the real page has them --

    def _prop(name):  # noqa: N805 - a tiny descriptor factory, not a method
        return property(
            lambda self: getattr(self.filter_settings, name),
            lambda self, value: setattr(self.filter_settings, name, value),
        )

    used_filter = _prop("mode")
    use_gap_fill = _prop("use_gap_fill")
    min_ph = _prop("min_photons")
    ph_window = _prop("photon_window")
    dT_min = _prop("dt_min")
    dT_max = _prop("dt_max")
    use_lower = _prop("dt_min_active")
    use_upper = _prop("dt_max_active")
    kalman_q = _prop("kalman_q")
    kalman_r_scale = _prop("kalman_r_scale")
    kalman_z_thresh = _prop("kalman_z_thresh")
    kalman_min_len = _prop("kalman_min_len")
    kalman_merge_gap = _prop("kalman_merge_gap")
    cusum_sb_ratio = _prop("sb_ratio")
    cusum_alpha = _prop("alpha")
    cusum_beta = _prop("beta")
    # BOCPD has fields of its own now; its parameters used to read CUSUM's
    # background_rate while writing a shared spin box.
    bocpd_prior_count = _prop("bocpd_prior_count")
    bocpd_prior_duration = _prop("bocpd_prior_duration")
    bocpd_changepoint_prob = _prop("bocpd_changepoint_prob")
    del _prop

    @property
    def max_gap(self):
        """Zero unless gap filling is on, as the real page reports it."""
        return self.filter_settings.merge_gap if self.use_gap_fill else 0

    @max_gap.setter
    def max_gap(self, value):
        self.filter_settings.merge_gap = int(value)

    @property
    def settings(self):
        """The dict-shaped view the adapter reads the switches from."""
        return {
            "filter_active": self.filter_settings.filter_active,
            "invert_filter": self.filter_settings.invert,
            "count_rate_filter": {
                "n_ph_max": self.filter_settings.min_photons,
                "time_window": self.filter_settings.time_window,
            },
        }


class Wizard:
    """Stand-in for BurstSelectionTool, carrying only what the adapter touches."""

    def __init__(self):
        self.burst_finder = Finder()
        self.checkBox_FileMFDHDF = Checkbox(False)
        self.checkBox_ZipOutput = Checkbox(False)
        self.checkBox_RemoveFolder = Checkbox(False)
        self.checkBox_auto_components = Checkbox(False)
        self.gmm_settings = {
            "covariance_type": "full", "random_state": 42, "max_iter": 100,
            "n_init": 1, "tol": 1e-3, "max_components": 5, "reg_covar": 1e-6,
        }


@pytest.fixture
def wizard():
    """A wizard with non-default values, so a no-op restore cannot pass."""
    w = Wizard()
    w.checkBox_ZipOutput.setChecked(True)
    w.checkBox_FileMFDHDF.setChecked(True)
    w.checkBox_auto_components.setChecked(True)
    w.burst_finder.min_ph = 77
    w.burst_finder.ph_window = 33
    w.burst_finder.dT_max = 7.5
    w.burst_finder.dT_min = 1.25
    w.burst_finder.max_gap = 9
    w.burst_finder.channels = [0, 1, 8, 9]
    w.burst_finder.cusum_sb_ratio = 12.5
    w.burst_finder.kalman_z_thresh = 4.5
    w.gmm_settings["max_components"] = 8
    w.gmm_settings["covariance_type"] = "diag"
    return w


def test_settings_survive_a_full_round_trip(wizard):
    """widgets → settings → widgets must return to the same values."""
    captured = analysis_settings_from_wizard(wizard)
    before = analysis_settings_from_wizard(wizard)

    # Scramble everything the restore is supposed to put back.
    wizard.burst_finder.min_ph = 1
    wizard.burst_finder.ph_window = 1
    wizard.burst_finder.dT_max = 0.1
    wizard.burst_finder.dT_min = 0.0
    wizard.burst_finder.max_gap = 0
    wizard.burst_finder.channels = []
    wizard.burst_finder.cusum_sb_ratio = 1.0
    wizard.burst_finder.kalman_z_thresh = 1.0
    wizard.gmm_settings["max_components"] = 1
    wizard.gmm_settings["covariance_type"] = "full"
    wizard.checkBox_ZipOutput.setChecked(False)
    wizard.checkBox_FileMFDHDF.setChecked(False)
    wizard.checkBox_auto_components.setChecked(False)

    skipped = apply_analysis_settings_to_wizard(wizard, captured)
    assert skipped == [], skipped

    assert analysis_settings_from_wizard(wizard) == before


def test_the_millisecond_field_is_not_rescaled_by_the_round_trip(wizard):
    """``dT_max`` is read out in two units; the raw one must win coming back.

    Deriving the widget from ``burst_detection.time_window`` (seconds) instead
    of ``delta_macro_time_filter.dT_max`` (milliseconds) divides the burst
    search by 1000 on every restore, while every field still "looks applied".
    """
    wizard.burst_finder.dT_max = 7.5
    captured = analysis_settings_from_wizard(wizard)
    assert captured.burst_detection.time_window == pytest.approx(0.0075)
    assert captured.photon_filter.delta_macro_time_filter.dT_max == pytest.approx(7.5)

    for _ in range(3):
        apply_analysis_settings_to_wizard(wizard, captured)
        captured = analysis_settings_from_wizard(wizard)

    assert wizard.burst_finder.dT_max == pytest.approx(7.5)


def test_the_stored_mapping_restores_as_well_as_the_dataclass(wizard):
    """The manifest stores plain JSON, so the mapping form has to work."""
    from dataclasses import asdict

    captured = asdict(analysis_settings_from_wizard(wizard))
    wizard.burst_finder.min_ph = 1
    wizard.gmm_settings["max_components"] = 1

    assert apply_analysis_settings_to_wizard(wizard, captured) == []
    assert wizard.burst_finder.min_ph == 77
    assert wizard.gmm_settings["max_components"] == 8


def test_an_older_settings_file_restores_what_it_shares(wizard):
    """A partial mapping must apply its fields and leave the rest alone."""
    wizard.burst_finder.min_ph = 5
    skipped = apply_analysis_settings_to_wizard(
        wizard, {"burst_detection": {"min_photons": 42}, "a_field_from_2019": 1}
    )

    assert wizard.burst_finder.min_ph == 42
    assert wizard.burst_finder.max_gap == 9, "untouched fields must survive"
    assert skipped == []


def test_restoring_from_a_real_analysis_folder(wizard, tmp_path):
    """End to end: a folder an analysis actually wrote repopulates the tool."""
    import pathlib

    from chisurf.plugins.burst.burst_selection.api import selection as sel

    spc = pathlib.Path(__file__).parents[1] / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
    if not spc.exists():
        pytest.skip(f"missing test data: {spc}")

    staged = tmp_path / "m000.spc"
    staged.write_bytes(spc.read_bytes())
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    sel.analyze_file(str(staged), output_dir=str(analysis),
                     mti_output_dir=str(analysis))

    wizard.burst_finder.min_ph = 1
    notes = apply_analysis_folder(wizard, analysis)

    assert notes == [], notes
    assert wizard.burst_finder.min_ph != 1, "the folder's settings were not applied"


def test_a_folder_without_a_manifest_says_so(wizard, tmp_path):
    """Folders written before manifests existed explain themselves."""
    notes = apply_analysis_folder(wizard, tmp_path)
    assert notes == ["this analysis folder records no settings"]


# ------------------------------------------------- the MLE wizard's loader


def test_mle_loader_accepts_a_burst_folder(tmp_path, monkeypatch):
    """The MLE wizard restores from an analysis folder, not only a file dialog.

    Its settings JSON was previously reachable only by browsing from the home
    directory, so a folder that recorded exactly what the wizard needed could
    not hand it over. Passing the folder is now equivalent to picking the file.
    """
    from chisurf.core.fio.fluorescence.burst_manifest import write_analysis_manifest
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    write_analysis_manifest(
        tmp_path, [{"path": "m000.spc", "container_type": "SPC-130"}],
        settings={"micro_time_binning": 4},
    )

    applied = {}

    def record(self, payload, source=None):
        applied.update(payload)
        applied["__source__"] = source

    monkeypatch.setattr(
        MLELifetimeAnalysisWizard, "apply_settings_payload", record, raising=True
    )
    MLELifetimeAnalysisWizard.load_settings_from(
        MLELifetimeAnalysisWizard.__new__(MLELifetimeAnalysisWizard), tmp_path
    )
    assert applied.get("micro_time_binning") == 4
    # The restore needs to know where the payload came from — it shows it in the
    # settings-file field and the status line.
    assert applied.get("__source__") == tmp_path


def test_mle_loader_still_reads_a_plain_settings_file(tmp_path, monkeypatch):
    """The existing on-disk format must keep working unchanged."""
    import json

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    path = tmp_path / "mle_wizard_settings.json"
    path.write_text(json.dumps({"micro_time_binning": 8}), encoding="utf-8")

    applied = {}
    monkeypatch.setattr(
        MLELifetimeAnalysisWizard, "apply_settings_payload",
        lambda self, payload, source=None: applied.update(payload), raising=True,
    )
    MLELifetimeAnalysisWizard.load_settings_from(
        MLELifetimeAnalysisWizard.__new__(MLELifetimeAnalysisWizard), path
    )
    assert applied.get("micro_time_binning") == 8


def test_mle_loader_reports_rather_than_raises_on_junk(tmp_path, monkeypatch):
    """A corrupt or empty source must not take the wizard down."""
    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    called = []
    monkeypatch.setattr(
        MLELifetimeAnalysisWizard, "apply_settings_payload",
        lambda self, payload, source=None: called.append(payload), raising=True,
    )
    blank = MLELifetimeAnalysisWizard.__new__(MLELifetimeAnalysisWizard)

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    MLELifetimeAnalysisWizard.load_settings_from(blank, broken)

    MLELifetimeAnalysisWizard.load_settings_from(blank, tmp_path / "no_manifest_here")

    assert called == [], "nothing should have been applied"


def test_mle_restore_actually_runs(tmp_path, qapp):
    """Run the restore for real — the other loader tests monkeypatch it away.

    ``apply_settings_payload`` was split out of the loader and kept referring to
    the loader's local ``path``, so every real restore died with ``NameError``
    right after the micro-time binning — before channel settings, detectors or
    any per-detector UI state were applied. Nothing caught it: the tests around
    it replace the method, and its two call sites sit behind a file dialog.
    """
    import json

    from chisurf.plugins.burst.burst_mle_analysis.wizard import (
        MLELifetimeAnalysisWizard,
    )

    path = tmp_path / "mle_wizard_settings.json"
    path.write_text(json.dumps({"micro_time_binning": 8}), encoding="utf-8")

    w = MLELifetimeAnalysisWizard()
    try:
        w.load_settings_from(path)
        assert w.channel_definer.micro_binning_combo.currentText() == "8"
        # The source is reported on the status line, which is what the missing
        # name was for (the old settings-file field went with the .ui).
        assert str(path) in w.statusBar().currentMessage()
        # A payload built by a caller carries no source, and must still apply.
        w.apply_settings_payload({"micro_time_binning": 4})
        assert w.channel_definer.micro_binning_combo.currentText() == "4"
    finally:
        w.close()


def test_bocpd_and_cusum_are_not_the_same_value(wizard):
    """BOCPD's prior count and CUSUM's background rate were one field.

    The page's ``bocpd_prior_count`` getter read ``filter_settings.background_rate``
    — CUSUM's parameter — while its setter wrote a shared spin box, so the two
    filters stored one number and reading a BOCPD parameter back gave a CUSUM
    one. They have separate fields now.
    """
    finder = wizard.burst_finder
    finder.cusum_bg_rate = 2000
    finder.filter_settings.background_rate = 2000.0
    finder.bocpd_prior_count = 7.5

    assert finder.bocpd_prior_count == 7.5
    assert finder.filter_settings.background_rate == 2000.0, (
        "setting a BOCPD parameter moved a CUSUM one"
    )


def test_bocpd_parameters_survive_a_round_trip(wizard):
    """They are ordinary settings now, so they restore like the rest."""
    finder = wizard.burst_finder
    finder.bocpd_prior_count = 3.25
    finder.bocpd_prior_duration = 0.45
    finder.bocpd_changepoint_prob = 2e-4

    captured = analysis_settings_from_wizard(wizard)
    finder.bocpd_prior_count = 1.0
    finder.bocpd_prior_duration = 0.1
    finder.bocpd_changepoint_prob = 1e-5

    assert apply_analysis_settings_to_wizard(wizard, captured) == []
    assert finder.bocpd_prior_count == pytest.approx(3.25)
    assert finder.bocpd_prior_duration == pytest.approx(0.45)
    assert finder.bocpd_changepoint_prob == pytest.approx(2e-4)
