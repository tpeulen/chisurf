"""A batch answers for every input, including the ones that went wrong.

The failure this guards against is not an exception — it is a *shorter answer*.
The loop these tests cover replaces two that dropped a file on any error and on
any empty result, so a run over a hundred fields could report ninety and look
exactly like a run over ninety. Here the invariant is asserted directly:
``len(rows) == len(files)``, whatever each file did.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.core.fio.image import imwrite
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.microscopy.spot_finder.api.models import (
    SpotFinderRequest,
    SpotFinderSettings,
)
from chisurf.plugins.microscopy.spot_finder.api.spot_finder import (
    detect_request,
    run_table,
)
from chisurf.plugins.microscopy.spot_finder.cli.main import cli

CENTRES = ((8, 9), (10, 40), (33, 20))


def _write_field(path: Path, *, spots: bool = True) -> Path:
    """Write a TIFF holding spots (or nothing), and start its container."""
    rows, cols = np.indices((48, 56))
    image = np.full((48, 56), 2.0)
    if spots:
        for cy, cx in CENTRES:
            image += 200.0 * np.exp(
                -(((rows - cy) ** 2 + (cols - cx) ** 2) / (2 * 1.6**2))
            )
    imwrite(path, image.astype(np.uint16), axes="YX")
    with Measurement.create(path, artifact_kind="image_data"):
        pass
    return path


def _settings() -> SpotFinderSettings:
    return SpotFinderSettings(method="threshold", sigma=1.0, min_area=2,
                              clear_border=False)


def test_every_input_gets_a_row_whatever_happened_to_it(tmp_path: Path):
    good = _write_field(tmp_path / "good.tif")
    empty = _write_field(tmp_path / "empty.tif", spots=False)
    broken = tmp_path / "broken.tif"
    broken.write_bytes(b"not a tiff at all")

    result = detect_request(SpotFinderRequest(
        files=[str(good), str(empty), str(broken)], settings=_settings()))

    assert len(result.rows) == 3, "a batch must answer for every input"
    assert [row.status for row in result.rows] == ["ok", "empty", "failed"]
    assert result.rows[0].n_regions == len(CENTRES)
    assert result.rows[1].n_regions == 0
    assert result.rows[2].reason, "a failed row must say why"


def test_a_blank_field_is_an_answer_not_a_failure(tmp_path: Path):
    """Otsu is undefined on a one-valued frame, and that is not the file's fault."""
    empty = _write_field(tmp_path / "empty.tif", spots=False)

    result = detect_request(SpotFinderRequest(files=[str(empty)], settings=_settings()))

    assert result.rows[0].status == "empty"
    assert "no regions" in result.rows[0].reason


def test_cancelling_marks_the_rest_skipped_rather_than_losing_them(tmp_path: Path):
    files = [str(_write_field(tmp_path / f"f{i}.tif")) for i in range(4)]
    seen: list[str] = []

    def should_stop() -> bool:
        return len(seen) >= 2

    def progress(index, total, name):
        seen.append(name)

    result = detect_request(
        SpotFinderRequest(files=files, settings=_settings()),
        progress=progress,
        should_stop=should_stop,
    )

    assert len(result.rows) == 4
    assert [row.status for row in result.rows] == ["ok", "ok", "skipped", "skipped"]


def test_the_run_table_carries_one_row_per_input(tmp_path: Path):
    from chisurf.core.datastore import column_names, row_count

    good = _write_field(tmp_path / "good.tif")
    empty = _write_field(tmp_path / "empty.tif", spots=False)

    table = run_table(detect_request(SpotFinderRequest(
        files=[str(good), str(empty)], settings=_settings())))

    assert row_count(table) == 2
    assert column_names(table) == ["input", "status", "n_regions", "container", "reason"]


def test_each_result_lands_in_its_own_measurement_container(tmp_path: Path):
    """A batch has no output file; it has N outputs, each beside its own data."""
    from chisurf.core.fio.fluorescence.region_container import list_region_sets

    files = [str(_write_field(tmp_path / f"f{i}.tif")) for i in range(3)]

    detect_request(SpotFinderRequest(files=files, name="spots", settings=_settings()))

    for path in files:
        assert list_region_sets(path) == ["spots"]


def test_a_dry_run_writes_nothing(tmp_path: Path):
    from chisurf.core.fio.fluorescence.region_container import list_region_sets

    good = _write_field(tmp_path / "good.tif")

    result = detect_request(SpotFinderRequest(
        files=[str(good)], settings=_settings(), write=False))

    assert result.rows[0].status == "ok"
    assert result.rows[0].n_regions == len(CENTRES)
    assert result.rows[0].container == ""
    assert list_region_sets(good) == []


def test_two_detections_under_different_names_coexist(tmp_path: Path):
    """Comparing parameter sets is the point of persisting them."""
    from chisurf.core.fio.fluorescence.region_container import list_region_sets

    good = _write_field(tmp_path / "good.tif")

    detect_request(SpotFinderRequest(
        files=[str(good)], name="loose", settings=_settings()))
    tight = _settings()
    tight.threshold = 60.0     # a fixed level rather than Otsu: fewer pixels per
    detect_request(SpotFinderRequest(files=[str(good)], name="tight", settings=tight))
    # spot, same spots -- two answers to compare, which is why they are named.

    assert list_region_sets(good) == ["loose", "tight"]


# ── the CLI, which must be the same loop and not a second one ──
def test_the_cli_reports_every_file_and_exits_non_zero_when_nothing_is_found(
    tmp_path: Path,
):
    good = _write_field(tmp_path / "good.tif")
    empty = _write_field(tmp_path / "empty.tif", spots=False)

    runner = CliRunner()
    ok = runner.invoke(cli, ["detect", str(good), "--method", "threshold",
                             "--keep-border", "--min-area", "2"])
    assert ok.exit_code == 0, ok.output
    assert "ok" in ok.output

    nothing = runner.invoke(cli, ["detect", str(empty), "--method", "threshold",
                                  "--keep-border"])
    assert nothing.exit_code == 1, nothing.output
    assert "empty" in nothing.output


def test_the_cli_lists_what_a_container_holds(tmp_path: Path):
    good = _write_field(tmp_path / "good.tif")
    detect_request(SpotFinderRequest(
        files=[str(good)], name="spots", settings=_settings()))

    runner = CliRunner()
    listed = runner.invoke(cli, ["list", str(good)])

    assert listed.exit_code == 0, listed.output
    assert "spots" in listed.output
    assert str(len(CENTRES)) in listed.output


def test_the_cli_writes_the_same_thing_the_api_does(tmp_path: Path):
    """The GUI/CLI/RPC divergence this loop exists to prevent, asserted."""
    from chisurf.core.fio.fluorescence.region_container import read_regions

    by_api = _write_field(tmp_path / "api.tif")
    by_cli = _write_field(tmp_path / "cli.tif")

    detect_request(SpotFinderRequest(files=[str(by_api)], settings=_settings()))
    runner = CliRunner()
    result = runner.invoke(cli, ["detect", str(by_cli), "--method", "threshold",
                                 "--sigma", "1.0", "--min-area", "2", "--keep-border"])
    assert result.exit_code == 0, result.output

    api_regions = read_regions(by_api)
    cli_regions = read_regions(by_cli)
    np.testing.assert_array_equal(api_regions.labels, cli_regions.labels)


@pytest.mark.parametrize("method", ["watershed", "threshold", "log", "dog"])
def test_the_cli_accepts_every_detector(tmp_path: Path, method: str):
    good = _write_field(tmp_path / f"{method}.tif")

    runner = CliRunner()
    result = runner.invoke(cli, ["detect", str(good), "--method", method,
                                 "--keep-border", "--min-area", "2",
                                 "--max-sigma", "3", "--dry-run"])

    assert result.exit_code == 0, result.output
