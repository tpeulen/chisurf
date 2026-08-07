"""A `.pto` is addressed like a folder, and the scheme is not about bursts.

The grammar (``m000.pto/<run>``), the listing, the read, the write and the
unpack all live in one module so that a tool taking a folder path takes a
container path without knowing it does. Before it there was a `.pto` branch per
plugin — one in the shared burst reader, another in BVA's copy of it, a third in
the workflow's handoff — each with its own idea of which analysis it meant.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.datastore import row_count
from chisurf.core.fio.fluorescence.burst_tree import read_burst_table
from chisurf.core.fio.analysis_path import (
    artifact_name,
    export_tree,
    is_container_path,
    list_runs,
    read_tables,
    split_artifact_name,
    split_container_path,
)

DATA = (
    Path(__file__).resolve().parents[2]
    / "chisurf" / "plugins" / "burst" / "burst_selection"
    / "tests" / "data" / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"


# -- the grammar, which needs no files -----------------------------------------


@pytest.mark.parametrize(
    ("path", "run"),
    [
        ("a/m000.pto", ""),
        ("a/m000.pto/countrate_All 0.2000#60", "countrate_All 0.2000#60"),
        # A path copied from a folder analysis still resolves: `bi4_bur` is a
        # directory the folder layout needs and the container does not.
        ("a/m000.pto/countrate_All 0.2000#60/bi4_bur", "countrate_All 0.2000#60"),
        ("a/M000.PTO/run", "run"),
    ],
)
def test_a_container_path_splits_into_container_and_run(path, run):
    container, got = split_container_path(path)
    assert container is not None
    assert got == run
    assert is_container_path(path)


def test_an_ordinary_folder_is_left_alone():
    assert split_container_path("/data/countrate_All 0.2000#60") == (None, "")
    assert not is_container_path("/data/countrate_All 0.2000#60")


def test_a_name_round_trips_through_the_artifact_form():
    assert split_artifact_name(artifact_name("run one", "bursts")) == ("run one", "bursts")
    # A container written before runs were named stores the table at the top
    # level, and must stay addressable rather than become invisible.
    assert split_artifact_name(artifact_name("", "bursts")) == ("", "bursts")


def test_listing_a_container_that_is_not_there_is_empty_not_an_error():
    """Asking what is in a file that does not exist is a question, not a fault."""
    assert list_runs("/nowhere/m000.pto") == []
    assert list_runs("/nowhere/plain-folder") == []


# -- and the same grammar over a real container --------------------------------

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def _analyse(container, min_photons: int) -> str:
    from chisurf.plugins.burst.burst_selection.api.models import (
        AnalysisRequest,
        AnalysisSettings,
        BurstDetectionSettings,
        DeltaMacroTimeFilterSettings,
        PhotonFilterSettings,
    )
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_request

    settings = AnalysisSettings()
    settings.output_formats = ["pto"]
    settings.photon_filter = PhotonFilterSettings(
        channels=[], filter_active=True, used_filter="count_rate",
        delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
    )
    settings.burst_detection = BurstDetectionSettings(
        min_photons=min_photons, photon_window=10, time_window=1e-3
    )
    result = analyze_request(
        AnalysisRequest(files=[str(container)], settings=settings, legacy_output=False)
    )
    return result.output_paths["output_folder"]


@pytest.fixture
def analysed(tmp_path: Path):
    """A container holding three analyses of one measurement."""
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)
    paths = [_analyse(container, n) for n in (30, 60, 120)]
    return container, paths


def test_several_analyses_of_one_measurement_are_separately_addressable(analysed):
    """The reason the scheme exists: `bursts` was ambiguous three times over."""
    container, paths = analysed

    runs = list_runs(container)
    assert len(runs) == 3
    assert runs == sorted(runs, key=lambda r: paths.index(f"{container}/{r}"))

    counts = [row_count(read_burst_table(p)) for p in paths]
    assert counts == sorted(counts, reverse=True), "a higher minimum kept more bursts"
    assert len(set(counts)) == 3


def test_without_a_run_the_most_recent_analysis_is_read(analysed):
    container, paths = analysed
    assert row_count(read_burst_table(container)) == row_count(
        read_burst_table(paths[-1])
    )


def test_naming_an_analysis_that_is_not_there_lists_the_ones_that_are(analysed):
    """"Not found" without a listing is the unhelpful half of an error."""
    container, _paths = analysed
    with pytest.raises(FileNotFoundError) as caught:
        read_tables(f"{container}/no such run")
    message = str(caught.value)
    assert "no such run" in message
    for run in list_runs(container):
        assert run in message


def test_unpacking_gives_the_original_and_the_analysis_folders(analysed, tmp_path: Path):
    """What a session working in folders would have had on disk.

    The container stores its tables as binary columns — that is what makes
    opening one cheap. Text is for leaving.
    """
    import hashlib

    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    container, _paths = analysed
    out = tmp_path / "unpacked"
    written = pto_api.extract(container, out_dir=out)

    recovered = out / SPC.name
    assert recovered in written
    assert hashlib.sha256(recovered.read_bytes()).hexdigest() == (
        hashlib.sha256(SPC.read_bytes()).hexdigest()
    ), "the original did not come back byte for byte"

    for run in list_runs(container):
        csv = out / run / "bi4_bur" / f"{container.stem}.bur"
        assert csv.exists(), f"no folder unpacked for {run!r}"
        assert csv.read_text().splitlines()[0].startswith("First Photon")

    # The binary tables themselves are not dumped beside the vendor file: a
    # blob named `bursts` next to an `.spc` is a file nothing can open.
    assert not (out / "bursts").exists()


def test_export_is_a_no_op_for_a_container_with_no_analysis(tmp_path: Path):
    """The ordinary state of a freshly converted measurement, not a problem."""
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    assert export_tree(container, tmp_path / "out") == []


# -- the container mirrors the folder, 1:1 -------------------------------------


def test_the_container_holds_the_bur_byte_for_byte(tmp_path: Path):
    """The claim `.pto` has to be able to make about the folder it replaces.

    Not "the same bursts" — the same *file*. The container stores the `.bur` as
    that file holds it, interleave and all, under the name it would have had
    (`<run>/bi4_bur/<stem>.bur`), so unpacking reproduces the folder rather than
    an approximation of it. Anything less and the two layouts are two formats
    that have to be kept in step by hand.

    Checked against a folder run of the *same* measurement and settings, not
    against a stored expectation — an expectation would only pin that the
    analysis never changes.
    """
    from chisurf.plugins.burst.burst_selection.api.models import (
        AnalysisRequest,
        AnalysisSettings,
        BurstDetectionSettings,
        DeltaMacroTimeFilterSettings,
        PhotonFilterSettings,
    )
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_request
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    def _settings(formats):
        s = AnalysisSettings()
        s.output_formats = formats
        s.photon_filter = PhotonFilterSettings(
            channels=[], filter_active=True, used_filter="count_rate",
            delta_macro_time_filter=DeltaMacroTimeFilterSettings(dT_min=0.0, dT_max=0.2),
        )
        s.burst_detection = BurstDetectionSettings(
            min_photons=60, photon_window=10, time_window=1e-3
        )
        return s

    # The folder way, on the vendor file.
    folder_dir = tmp_path / "folder"
    folder_dir.mkdir()
    (folder_dir / SPC.name).write_bytes(SPC.read_bytes())
    folder = analyze_request(
        AnalysisRequest(
            files=[str(folder_dir / SPC.name)],
            settings=_settings(["bur"]),
            legacy_output=True,
        )
    )

    # The container way, on the same measurement packed into a `.pto`.
    pto_dir = tmp_path / "container"
    pto_dir.mkdir()
    (pto_dir / SPC.name).write_bytes(SPC.read_bytes())
    container = pto_api.convert(pto_dir / SPC.name)
    result = analyze_request(
        AnalysisRequest(
            files=[str(container)], settings=_settings(["pto"]), legacy_output=True
        )
    )
    assert result.metadata["n_bursts"] == folder.metadata["n_bursts"]

    unpacked = tmp_path / "unpacked"
    pto_api.extract(container, out_dir=unpacked)

    want = Path(folder.output_paths["bur"])
    got = unpacked / want.relative_to(folder_dir)
    assert got.exists(), f"the container did not unpack to {want.relative_to(folder_dir)}"
    assert got.read_text() == want.read_text()


def test_the_burst_table_names_the_measurement_not_the_box(tmp_path: Path):
    """`First File` is what a burst was found in, and that is the `.spc`.

    A reader resolving `tttrs[row["First File"]]` against an unpacked folder
    would otherwise look for an `m000.pto` that is not there beside the
    `m000.spc` it just recovered.
    """
    import numpy as np

    from chisurf.core.fio.fluorescence.burst_tree import read_burst_table
    from chisurf.plugins.burst.burst_selection.api.models import (
        AnalysisRequest,
        AnalysisSettings,
        BurstDetectionSettings,
        PhotonFilterSettings,
    )
    from chisurf.plugins.burst.burst_selection.api.selection import analyze_request
    from chisurf.plugins.core.tttr_to_pto import api as pto_api

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    container = pto_api.convert(source)

    settings = AnalysisSettings()
    settings.output_formats = ["pto"]
    settings.photon_filter = PhotonFilterSettings(channels=[], filter_active=False)
    settings.burst_detection = BurstDetectionSettings(
        min_photons=60, photon_window=10, time_window=1e-3
    )
    analyze_request(
        AnalysisRequest(files=[str(container)], settings=settings, legacy_output=False)
    )

    named = {str(v) for v in np.asarray(read_burst_table(container)["First File"])}
    assert named == {SPC.name}
