"""A workflow is the run written down, and the standard one is single-molecule.

Two claims are worth more than the rest here. First, that the *defaults* and the
*standard workflow document* are the same detection — if they drift, a user who
types `spot-finder detect` and a user who runs `single_molecule.json` get
different answers to the same question and nothing says so. Second, that an
unknown key is **refused**: a document carrying `min_size` where the setting is
`min_area` must fail loudly, because the alternative is a run that succeeds, at
the default, recording a parameter that never took effect.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner

from chisurf.core.fio.image import imwrite
from chisurf.core.fio.pto import Measurement
from chisurf.plugins.microscopy.spot_finder.cli.main import cli
from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings
from chisurf.plugins.microscopy.spot_finder.core.workflow import (
    STANDARD,
    WORKFLOW_VERSION,
    builtin_workflow,
    list_workflows,
    load_workflow,
    request_from_workflow,
    workflow_from_request,
)

CENTRES = ((8, 9), (10, 40), (33, 20))


def _write_field(path: Path) -> Path:
    rows, cols = np.indices((48, 56))
    image = np.full((48, 56), 2.0)
    for cy, cx in CENTRES:
        image += 200.0 * np.exp(-(((rows - cy) ** 2 + (cols - cx) ** 2) / (2 * 1.6**2)))
    imwrite(path, image.astype(np.uint16), axes="YX")
    with Measurement.create(path, artifact_kind="image_data"):
        pass
    return path


def test_the_standard_workflow_is_single_molecule_segmentation():
    assert STANDARD == "single_molecule"
    assert list_workflows()[0] == STANDARD
    assert builtin_workflow()["settings"]["method"] == "watershed"


def test_the_defaults_are_the_standard_workflow():
    """Typing nothing and running the standard document must be one detection."""
    document = builtin_workflow(STANDARD)
    defaults = dataclasses.asdict(SpotFinderSettings())

    for key, value in document["settings"].items():
        assert defaults[key] == value, (
            f"{key}: the standard workflow says {value!r} and the dataclass "
            f"default is {defaults[key]!r} — they are the same detection or "
            "they are two answers to the same question"
        )
    assert defaults["workflow"] == STANDARD


@pytest.mark.parametrize("name", list_workflows())
def test_every_shipped_workflow_loads_and_describes_itself(name: str):
    document = load_workflow(name)

    assert document["workflow"] == name
    assert document["version"] == WORKFLOW_VERSION
    assert len(document.get("description", "")) > 40, "a workflow says what it is for"
    # And it must actually build settings — a document naming a setting the
    # detector lost would otherwise sit shipped and broken until someone ran it.
    settings = SpotFinderSettings(**document["settings"])
    settings.validated()


def test_a_document_overrides_only_what_it_names(tmp_path: Path):
    recipe = tmp_path / "mine.json"
    recipe.write_text(json.dumps({"workflow": "camera_spots", "settings": {"min_area": 9}}))

    document = load_workflow(recipe)
    base = builtin_workflow("camera_spots")

    assert document["settings"]["min_area"] == 9
    assert document["settings"]["method"] == base["settings"]["method"]
    assert document["settings"]["max_sigma"] == base["settings"]["max_sigma"]


def test_a_document_naming_no_base_gets_the_standard_one(tmp_path: Path):
    recipe = tmp_path / "mine.json"
    recipe.write_text(json.dumps({"settings": {"min_area": 5}}))

    document = load_workflow(recipe)

    assert document["workflow"] == STANDARD
    assert document["settings"]["method"] == "watershed"
    assert document["settings"]["min_area"] == 5


def test_a_misspelled_setting_is_refused_rather_than_ignored(tmp_path: Path):
    """The failure this whole strictness exists for."""
    recipe = tmp_path / "typo.json"
    recipe.write_text(json.dumps({"settings": {"min_size": 9}}))

    with pytest.raises(ValueError, match="unknown detection setting"):
        load_workflow(recipe)


def test_a_misspelled_document_key_is_refused(tmp_path: Path):
    recipe = tmp_path / "typo.json"
    recipe.write_text(json.dumps({"setings": {}, "inputs": {"file": []}}))

    with pytest.raises(ValueError, match="unknown workflow document key"):
        load_workflow(recipe)


def test_a_future_version_is_refused_rather_than_half_read(tmp_path: Path):
    recipe = tmp_path / "future.json"
    recipe.write_text(json.dumps({"version": WORKFLOW_VERSION + 1, "settings": {}}))

    with pytest.raises(ValueError, match="version"):
        load_workflow(recipe)


def test_an_unknown_workflow_name_lists_the_ones_there_are():
    with pytest.raises(FileNotFoundError) as excinfo:
        builtin_workflow("single_molecul")

    assert "single_molecule" in str(excinfo.value)


def test_a_request_round_trips_through_a_document(tmp_path: Path):
    """A run tuned by hand becomes a file that reproduces it."""
    request = request_from_workflow("camera_spots", files=["a.tif", "b.tif"])
    request.settings.min_area = 7
    request.name = "beads"

    document = workflow_from_request(request, description="my sample")
    rebuilt = request_from_workflow(document)

    assert rebuilt.name == "beads"
    assert rebuilt.files == ["a.tif", "b.tif"]
    assert dataclasses.asdict(rebuilt.settings) == dataclasses.asdict(request.settings)


def test_the_workflow_name_reaches_the_stored_detection(tmp_path: Path):
    """A container says which recipe made it, not only what the recipe evaluated to."""
    field = _write_field(tmp_path / "field.tif")

    request = request_from_workflow(STANDARD, files=[str(field)])
    from chisurf.plugins.microscopy.spot_finder.api.spot_finder import detect_request

    detect_request(request)

    with Measurement.open(field.with_suffix(".pto"), writable=False) as m:
        uid = m._resolve("spots.regions")
        parameters = m.provenance(uid).get("settings", {})

    assert parameters.get("workflow") == STANDARD, parameters


# ── the CLI surface ──
def test_the_cli_lists_the_workflows_standard_first():
    result = CliRunner().invoke(cli, ["workflows"])

    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0].startswith(STANDARD)
    assert "camera_spots" in result.output


def test_the_cli_shows_a_document_that_can_be_edited_and_run(tmp_path: Path):
    shown = CliRunner().invoke(cli, ["show", "camera_spots"])
    assert shown.exit_code == 0, shown.output

    recipe = tmp_path / "mine.json"
    recipe.write_text(shown.output)
    document = load_workflow(recipe)

    assert document["settings"]["method"] == "log"


def test_the_cli_runs_a_recipe(tmp_path: Path):
    from chisurf.core.fio.fluorescence.region_container import list_region_sets

    field = _write_field(tmp_path / "field.tif")
    recipe = tmp_path / "mine.json"
    recipe.write_text(json.dumps({
        "workflow": STANDARD,
        "name": "molecules",
        "settings": {"clear_border": False},
    }))

    result = CliRunner().invoke(cli, ["run", str(recipe), str(field)])

    assert result.exit_code == 0, result.output
    assert list_region_sets(field) == ["molecules"]


def test_a_recipe_with_no_files_says_so_rather_than_succeeding_emptily(tmp_path: Path):
    recipe = tmp_path / "mine.json"
    recipe.write_text(json.dumps({"settings": {}}))

    result = CliRunner().invoke(cli, ["run", str(recipe)])

    assert result.exit_code != 0
    assert "no files" in result.output


def test_an_untouched_option_keeps_the_workflow_value(tmp_path: Path):
    """--workflow must mean something: an option not typed does not override it."""
    field = _write_field(tmp_path / "field.tif")
    out = tmp_path / "used.json"

    result = CliRunner().invoke(cli, [
        "detect", str(field), "--workflow", "camera_spots",
        "--min-area", "3", "--dry-run", "--save-workflow", str(out),
    ])

    assert result.exit_code == 0, result.output
    document = json.loads(out.read_text())
    assert document["settings"]["min_area"] == 3          # typed, so it wins
    assert document["settings"]["method"] == "log"        # untyped, so the workflow's
    assert document["settings"]["max_sigma"] == 4.0
    assert document["workflow"] == "camera_spots"


def test_a_saved_workflow_reruns_the_same_detection(tmp_path: Path):
    from chisurf.core.fio.fluorescence.region_container import read_regions

    by_options = _write_field(tmp_path / "options.tif")
    by_recipe = _write_field(tmp_path / "recipe.tif")
    saved = tmp_path / "saved.json"

    runner = CliRunner()
    first = runner.invoke(cli, [
        "detect", str(by_options), "--threshold", "40", "--keep-border",
        "--save-workflow", str(saved),
    ])
    assert first.exit_code == 0, first.output

    second = runner.invoke(cli, ["run", str(saved), str(by_recipe)])
    assert second.exit_code == 0, second.output

    np.testing.assert_array_equal(
        read_regions(by_options).labels, read_regions(by_recipe).labels
    )


# ── the cross-plugin handoff ──
def test_prepare_resolves_files_and_channels_from_a_workflow_context(tmp_path: Path):
    from chisurf.plugins.microscopy.spot_finder.backend.services import (
        _handle_prepare_workflow,
    )

    response = _handle_prepare_workflow({
        "workflow_context": {
            "raw_files": [str(tmp_path / "a.ptu"), str(tmp_path / "b.ptu")],
            "channel_settings": {"green": {"chs": [0, 1]}, "red": {"chs": [2]}},
        }
    })

    assert response["ok"] is True, response
    data = response["result"]
    assert len(data["files"]) == 2
    assert data["channels"] == [0, 1, 2]
    assert data["workflow"]["workflow"] == STANDARD


def test_prepare_refuses_a_setting_that_does_not_exist():
    from chisurf.plugins.microscopy.spot_finder.backend.services import (
        _handle_prepare_workflow,
    )

    response = _handle_prepare_workflow({"settings": {"min_size": 3}})

    assert response["ok"] is False
    assert "min_size" in str(response)


def test_picking_a_workflow_replaces_every_setting_not_just_the_method():
    """A selector that changes one field would make the recipe decorative."""
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    vm = SpotFinderViewModel()
    vm.settings.threshold = 999.0            # a value from the previous recipe
    vm.workflow = "camera_spots"

    assert vm.settings.method == "log"
    assert vm.settings.threshold != 999.0
    assert vm.settings.max_sigma == builtin_workflow("camera_spots")["settings"]["max_sigma"]
    assert vm.workflow == "camera_spots"


def test_the_run_table_has_a_row_per_input_in_the_gui_too(tmp_path: Path):
    from chisurf.plugins.microscopy.spot_finder.gui.view_model import SpotFinderViewModel

    good = _write_field(tmp_path / "good.tif")
    broken = tmp_path / "broken.tif"
    broken.write_bytes(b"not a tiff")

    vm = SpotFinderViewModel()
    vm.files = [str(good), str(broken)]
    vm.write_results = False
    vm.run()

    rows = vm.run_entries()
    assert len(rows) == 2
    assert [r["status"] for r in rows] == ["ok", "failed"]
    assert rows[1]["reason"]
