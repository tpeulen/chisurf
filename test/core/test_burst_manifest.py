"""A burst folder must record how its data was read, not only what was found.

A burst table is a set of pointers back into photon streams: every row names a
file and a ``(first_photon, last_photon)`` interval. Anything that later wants
those photons — sending a gated population to FCS, a decay, PDA — has to reopen
the source, and the folder never said how it was opened.

Consumers therefore guessed from the file extension, and the guess for ``.spc``
was a container type called ``"SPC"``, which ``tttrlib`` does not have. It does
not report that as an error either: it prints to stderr and hands back an object
with **zero photons**, so the analysis ran on nothing and looked like a
measurement without signal.

These cover the manifest that closes that gap.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.fio.fluorescence.burst_manifest import (
    MANIFEST_NAME,
    describe_tttr_source,
    read_analysis_manifest,
    reading_settings_for,
    write_analysis_manifest,
)

tttrlib = pytest.importorskip("tttrlib")

#: Becker & Hickl data — the format whose extension-derived guess was wrong.
SPC = pathlib.Path(__file__).parents[1] / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


@pytest.fixture
def spc_tttr():
    """The source measurement, opened the way tttrlib itself decides."""
    if not SPC.exists():
        pytest.skip(f"missing test data: {SPC}")
    return tttrlib.TTTR(str(SPC))


def test_a_source_description_records_what_it_takes_to_reopen(spc_tttr):
    """Container type, resolutions and channels, read off the open object."""
    entry = describe_tttr_source(SPC, spc_tttr, container_type="SPC-130")

    assert entry["path"] == str(SPC)
    assert entry["container_type"] == "SPC-130"
    assert entry["macro_time_resolution"] > 0
    assert entry["n_photons"] == len(spc_tttr.macro_times)
    assert entry["routing_channels"], "no channels recorded"


def test_the_manifest_round_trips(tmp_path, spc_tttr):
    """Written into Info/, found again from the folder."""
    entry = describe_tttr_source(SPC, spc_tttr, container_type="SPC-130")
    written = write_analysis_manifest(tmp_path, [entry], settings={"threshold": 5})

    assert written == tmp_path / "Info" / MANIFEST_NAME
    manifest = read_analysis_manifest(tmp_path)
    assert manifest["version"] == 1
    assert manifest["settings"]["threshold"] == 5
    assert reading_settings_for(SPC, manifest)["container_type"] == "SPC-130"


def test_it_is_found_from_the_bur_file_and_from_below(tmp_path, spc_tttr):
    """Callers hold different things: the .bur, its folder, or the one above."""
    analysis = tmp_path / "analysis"
    bur_dir = analysis / "bi4_bur"
    bur_dir.mkdir(parents=True)
    bur = bur_dir / "m000.bur"
    bur.write_text("", encoding="utf-8")
    write_analysis_manifest(analysis, [describe_tttr_source(SPC, spc_tttr)])

    assert read_analysis_manifest(bur) is not None
    assert read_analysis_manifest(bur_dir) is not None
    assert read_analysis_manifest(analysis) is not None


def test_a_second_measurement_is_appended_not_replaced(tmp_path, spc_tttr):
    """Analysing another file into the same folder must not erase the first."""
    write_analysis_manifest(tmp_path, [describe_tttr_source("m000.spc", spc_tttr)])
    write_analysis_manifest(tmp_path, [describe_tttr_source("m001.spc", spc_tttr)])

    manifest = read_analysis_manifest(tmp_path)
    assert {pathlib.Path(s["path"]).name for s in manifest["sources"]} == {
        "m000.spc",
        "m001.spc",
    }


def test_re_running_updates_rather_than_duplicates(tmp_path, spc_tttr):
    """The same source analysed twice is one entry, the newer one."""
    write_analysis_manifest(tmp_path, [describe_tttr_source(SPC, spc_tttr, container_type="PTU")])
    write_analysis_manifest(
        tmp_path, [describe_tttr_source(SPC, spc_tttr, container_type="SPC-130")]
    )

    manifest = read_analysis_manifest(tmp_path)
    assert len(manifest["sources"]) == 1
    assert reading_settings_for(SPC, manifest)["container_type"] == "SPC-130"


def test_lookup_matches_on_name_so_a_moved_analysis_still_works(tmp_path, spc_tttr):
    """Analyses get copied off instruments and referenced through other mounts.

    A manifest that only matched absolute paths would be useless exactly when it
    is needed most.
    """
    write_analysis_manifest(
        tmp_path,
        [describe_tttr_source("/instrument/raw/m000.spc", spc_tttr, container_type="SPC-130")],
    )
    manifest = read_analysis_manifest(tmp_path)
    found = reading_settings_for("/somewhere/else/entirely/m000.spc", manifest)
    assert found["container_type"] == "SPC-130"


def test_a_folder_without_a_manifest_is_not_an_error(tmp_path):
    """Analyses written before this existed must keep working."""
    assert read_analysis_manifest(tmp_path) is None
    assert reading_settings_for("anything.spc", None) == {}


def test_a_corrupt_manifest_does_not_stop_the_next_write(tmp_path, spc_tttr):
    """A damaged file is replaced by a readable one rather than propagating."""
    info = tmp_path / "Info"
    info.mkdir()
    (info / MANIFEST_NAME).write_text("{not json", encoding="utf-8")

    assert read_analysis_manifest(tmp_path) is None
    write_analysis_manifest(tmp_path, [describe_tttr_source(SPC, spc_tttr)])
    assert read_analysis_manifest(tmp_path) is not None


def test_the_recorded_type_is_used_when_reopening(tmp_path, spc_tttr):
    """The whole point: reopening uses what was recorded, not a guess.

    Recorded as SPC-130, and read back with a deliberately wrong routine
    argument — the manifest must win and the photons must arrive.
    """
    from chisurf.server.services import bursts

    staged = tmp_path / "m000.spc"
    staged.write_bytes(SPC.read_bytes())
    write_analysis_manifest(
        tmp_path, [describe_tttr_source(staged, spc_tttr, container_type="SPC-130")]
    )

    reopened = bursts._open(str(staged), "SPC")  # the guess that used to fail
    assert len(reopened.macro_times) == len(spc_tttr.macro_times)


def test_a_decay_from_spc_bursts_is_not_empty(tmp_path, spc_tttr):
    """End to end on the format that was silently returning nothing."""
    from chisurf.server.services import bursts

    staged = tmp_path / "m000.spc"
    staged.write_bytes(SPC.read_bytes())
    write_analysis_manifest(
        tmp_path, [describe_tttr_source(staged, spc_tttr, container_type="SPC-130")]
    )

    result = bursts.from_bursts_decay(
        None,
        burst_slices={str(staged): [[0, 9999]]},
        reading_routine="SPC",
    )
    assert result["ok"], result
    assert result["result"]["n_photons"] == 10000


# --------------------------------------------------- restoring the analysis


def test_the_folder_carries_the_settings_it_ran_with(tmp_path, spc_tttr):
    """A folder must be able to repopulate the tool that produced it.

    Without this the numbers survive and the question they answer does not: an
    archive rather than a reproducible result.
    """
    from chisurf.core.fio.fluorescence.burst_manifest import restore_settings

    write_analysis_manifest(
        tmp_path,
        [describe_tttr_source(SPC, spc_tttr)],
        settings={"threshold": 5, "min_photons": 60, "method": "sliding"},
    )

    restored = restore_settings(tmp_path)
    assert restored["threshold"] == 5
    assert restored["min_photons"] == 60
    assert restored["method"] == "sliding"


def test_a_real_analysis_records_settings_that_can_be_read_back(tmp_path):
    """End to end: run an analysis, then restore what it ran with."""
    from chisurf.core.fio.fluorescence.burst_manifest import restore_settings
    from chisurf.plugins.burst.burst_selection.api import selection as sel

    staged = tmp_path / "m000.spc"
    staged.write_bytes(SPC.read_bytes())
    analysis = tmp_path / "analysis"
    analysis.mkdir()

    sel.analyze_file(str(staged), output_dir=str(analysis), mti_output_dir=str(analysis))

    restored = restore_settings(analysis)
    assert restored, "the analysis recorded no settings"
    # The burst-search parameters someone would need to repeat the run.
    assert "output_formats" in restored
    assert any(k in restored for k in ("photon_filter", "burst_filter", "gmm"))


def test_a_form_is_repopulated_from_the_folder(tmp_path, spc_tttr, qt_app_for_forms):
    """The AutoForm path: a folder restores the tool's controls, key for key."""
    from chisurf.core.dataspec import ModelView, ValueSection
    from chisurf.core.fio.fluorescence.burst_manifest import restore_form
    from chisurf.gui.autoform.auto_form import AutoForm

    class Tool:
        def __init__(self):
            self.threshold = 1
            self.min_photons = 1

        def view_spec(self):
            return ModelView(
                sections=(
                    ValueSection(label="Threshold", kind="int", attr="threshold"),
                    ValueSection(label="Min photons", kind="int", attr="min_photons"),
                )
            )

    write_analysis_manifest(
        tmp_path,
        [describe_tttr_source(SPC, spc_tttr)],
        view_state={"threshold": 5, "min_photons": 60},
    )

    form = AutoForm(Tool())
    try:
        result = restore_form(form, tmp_path)
        assert result is not None and result.ok, result
        assert form.model.threshold == 5
        assert form.model.min_photons == 60
    finally:
        form.close()


def test_restoring_from_a_folder_without_a_manifest_is_not_an_error(tmp_path):
    """Older folders must not raise; they simply have nothing to restore."""
    from chisurf.core.fio.fluorescence.burst_manifest import (
        restore_form,
        restore_settings,
    )

    assert restore_settings(tmp_path) == {}
    assert restore_form(object(), tmp_path) is None


@pytest.fixture(scope="module")
def qt_app_for_forms():
    """A QApplication for the AutoForm case (offscreen)."""
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
