"""Every Record measurement traces both ways, in its file and in the project.

A survey of four tiles on the simulator (molecules planted in two of them): every tile image is a
dataset and names its survey and tile; every point recording names its image, pixel, pick and
survey in its header; the project's containers link point → image → survey and back; the
backtrace helpers round-trip, also after the project was saved and opened elsewhere.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from chisurf.core.project import analysis
from chisurf.plugins.core.acq.gui.record_app import RecordModel
from chisurf.plugins.core.acq.live import provenance, settings_file
from chisurf.plugins.core.acq.live.scanner import ImagingSample, ScanSettings

PLANTED = [(12.0, 12.0, 0), (14.0, 14.5, 1), (19.0, 19.0, 0), (20.5, 17.5, 1)]


@pytest.fixture(autouse=True)
def fresh_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setattr(analysis, "_SESSION", None)
    logging.getLogger("chisurf.core.math.hmm").setLevel(logging.ERROR)


@pytest.fixture
def surveyed(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.mode = "image"
    model.mode_changed()
    model.load_example()
    model.set_scan(ScanSettings(pixels_x=32, pixels_y=32, area_x_um=6.4, area_y_um=6.4,
                                x0_um=10.0, y0_um=10.0, dwell_ms=0.1, frames=2))
    model.imaging_sample = lambda: ImagingSample(positions=PLANTED, bead_brightness=80.0,
                                                 cell=False)
    model.survey_area_kind = "custom"
    model.survey_x0_um = model.survey_y0_um = 10.0
    model.survey_w_um = model.survey_h_um = 12.8
    model.point_time_s, model.img_bleach_s = 1.0, 0.3
    assert model.survey_start()
    model.wait_survey(300)
    assert len(model.survey_rows) == len(PLANTED)
    return model


def _workspace_images() -> dict[str, str]:
    from chisurf.core.api import dataset_objects

    return {str(d.address): str(d.unique_identifier) for d in dataset_objects()
            if str(getattr(d, "data_kind", "")) == "image"}


def test_every_tile_image_is_a_dataset_naming_its_survey(surveyed):
    tiles = surveyed.survey_tiles
    images = _workspace_images()
    assert {t.state for t in tiles} == {"done", "empty"}
    for t in tiles:  # the empty tiles too
        assert t.image_uid and t.image_uid in images.values()
        path = next(a for a, u in images.items() if u == t.image_uid)
        tags = settings_file.read_ptu_tags(path)
        assert tags["ChiSurf_Survey_Tile"] == t.index
        assert tags["ChiSurf_Survey_Tiles"] == len(tiles)
        assert tags["ChiSurf_Survey_TileX0_um"] == pytest.approx(t.x0_um)
        found = provenance.survey_of(t.image_uid)
        assert found["tile"] == t.index and found["survey_id"] == tags["ChiSurf_Survey_ID"]


def test_every_point_names_its_image_pixel_and_survey(surveyed):
    for row in surveyed.survey_rows:
        point = row["point"]
        tags = settings_file.read_ptu_tags(point["ptu"])
        tile = surveyed.survey_tiles[row["tile"]]
        assert tags["ChiSurf_Point_SourceImageUID"] == tile.image_uid
        assert tags["ChiSurf_Point_SourceImage"] == tile.image_name
        # the pixel and the raster give the stage position back
        x = tags["ChiSurf_Point_ImageX0_um"] + tags["ChiSurf_Point_PixelX"] * \
            tags["ChiSurf_Point_ImagePixel_um"]
        assert x == pytest.approx(tags["ChiSurf_Point_X_um"], abs=1e-6)
        assert tags["ChiSurf_Point_Origin"] == "auto"
        assert tags["ChiSurf_Point_PickWorkflow"] == "single_molecule"
        assert len(tags["ChiSurf_Point_PickSettingsHash"]) == 16
        assert tags["ChiSurf_Point_Reached_X_um"] == pytest.approx(tags["ChiSurf_Point_X_um"])
        assert tags["ChiSurf_Survey_Tile"] == row["tile"]
        assert tags["ImgHdr_Ident"] == 6  # SymPhoTime's point header kept


def test_the_backtrace_round_trips(surveyed):
    by_image: dict[str, set] = {}
    for row in surveyed.survey_rows:
        point = row["point"]
        back = provenance.backtrace(point["ptu"])
        assert back["point_uid"] == point["dataset_uid"]
        assert back["image_uid"] == point["image_uid"]
        assert back["image_path"] and Path(back["image_path"]).name == point["image"]
        assert back["tile"] == row["tile"] and back["survey_id"]
        assert back["settings"]["schema"].startswith("chisurf.acquisition/")
        record = back["record"]
        assert record["settings"]["image_uid"] == point["image_uid"]
        assert record["provenance"]["operation"] == "point_measurement"
        by_image.setdefault(point["image_uid"], set()).add(point["dataset_uid"])
    for image_uid, points in by_image.items():
        assert {p["uid"] for p in provenance.points_of(image_uid)} == points


def test_the_survey_and_molecule_tables_name_their_datasets(surveyed):
    first = surveyed.survey_tiles[0]
    tiles = provenance._container_record(first.image_uid, "survey_tiles")
    images = [d["uid"] for d in tiles["settings"]["image_datasets"]]
    assert sorted(images) == sorted(t.image_uid for t in surveyed.survey_tiles)
    assert tiles["provenance"]["operation"] == "survey"
    table = provenance._container_record(first.image_uid, "survey_molecules.table")
    points = table["settings"]["point_datasets"]
    named = {points[int(k)]["uid"] for k in table["table"]["point_dataset"]}
    assert named == {r["point"]["dataset_uid"] for r in surveyed.survey_rows}
    molecule = provenance._container_record(surveyed.survey_rows[0]["point"]["dataset_uid"],
                                            "molecule")
    assert molecule["provenance"]["operation"] == "trace_segmentation"


def test_the_provenance_travels_in_the_project(surveyed, tmp_path, monkeypatch):
    from chisurf.core.fio.pto import Measurement
    from chisurf.core.project.project import Project

    point = surveyed.survey_rows[0]["point"]
    saved = Project(name="p").save(tmp_path / "p.cs.pto")
    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(analysis, "_SESSION", None)
    project = Project.load(saved)
    kept = project.extra[analysis.EXTRA_KEY]
    assert point["dataset_uid"] in {k for k in kept} | set(analysis.containers())
    back = provenance.backtrace(point["ptu"], uid=point["dataset_uid"])
    assert back["record"]["settings"]["image_uid"] == point["image_uid"]
    assert provenance.points_of(point["image"], uid=point["image_uid"])
    for paths in analysis.containers().values():
        for path in paths:
            with Measurement.open(path) as m:
                assert m.untraceable() == [], path
