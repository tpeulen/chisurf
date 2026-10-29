"""Where every Record measurement came from, both ways: in the files and in the project.

A point recording must be traceable on its own -- back to the image it was picked on, the pixel,
how it was picked, the survey and tile -- and an image must find its points again. The record is
kept twice, so either half survives without the other:

* **In the files.** A point's PTU header carries the image (file name and dataset uid), the pixel
  and the image's raster (so pixel ↔ stage is reproducible), how it was picked (auto: the spot
  finder workflow and a hash of its settings; or a click) and the spot's brightness, the stage
  position aimed at and the one reached, and the survey and tile (:func:`point_tags`). A survey
  tile's PTU carries the survey, the tile, its origin and the scanner's learning
  (:func:`tile_tags`). SymPhoTime's ``ImgHdr_*`` point tags are kept as they are.
* **In the project.** Each dataset's analysis container (embedded in the ``.cs.pto``) records
  mmfdb artifacts with their operation, settings and parents: the point's ``point`` record
  (``point_measurement``: the pick and the move, the image as an external reference), its
  ``molecule`` row (``trace_segmentation``), the image's ``points`` list (``point_selection``,
  each row naming its point recording), a tile's ``survey_tile`` membership and the survey's
  ``survey_tiles`` list (``survey``, grouping the tiles). Strings that a numeric table cannot hold
  (dataset uids, file names) are lookup lists in the record's settings, indexed by a column.

:func:`backtrace` follows a point recording back (image, pixel, survey, settings);
:func:`points_of` an image forward to its points.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

_log = logging.getLogger(__name__)

__all__ = [
    "backtrace",
    "point_tags",
    "points_of",
    "settings_hash",
    "survey_of",
    "tile_tags",
    "write_image_points",
    "write_point_record",
    "write_survey_tile",
    "write_survey_tiles",
]

#: How a point was picked, as a number in a table (the name is in the header and the settings).
ORIGIN_CODES = {"click": 0, "auto": 1}


def settings_hash(settings: dict) -> str:
    """A short, stable hash of a settings document (the spot finder workflow a pick used)."""
    text = json.dumps(settings, sort_keys=True, default=str)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# -- the files ---------------------------------------------------------------------------------
def point_tags(point: dict) -> dict[str, Any]:
    """The PTU header tags of a picked point (see the module notes); *point* is a row of the
    Record tool's point list."""
    tags: dict[str, Any] = {
        "ChiSurf_Point_Origin": str(point.get("origin", "")),
        "ChiSurf_Point_SourceImage": str(point.get("image", "")),
        "ChiSurf_Point_SourceImageUID": str(point.get("image_uid", "")),
    }
    for key, tag in (("pixel_x", "ChiSurf_Point_PixelX"), ("pixel_y", "ChiSurf_Point_PixelY"),
                     ("image_x0_um", "ChiSurf_Point_ImageX0_um"),
                     ("image_y0_um", "ChiSurf_Point_ImageY0_um"),
                     ("image_pixel_um", "ChiSurf_Point_ImagePixel_um"),
                     ("brightness", "ChiSurf_Point_Brightness")):
        if point.get(key) is not None:
            tags[tag] = float(point[key])
    if point.get("workflow"):
        tags["ChiSurf_Point_PickWorkflow"] = str(point["workflow"])
        tags["ChiSurf_Point_PickSettingsHash"] = str(point.get("settings_hash", ""))
    if point.get("survey_id"):
        tags.update(survey_tags(point))
    return tags


def survey_tags(info: dict) -> dict[str, Any]:
    """The survey's tags: its id, the tile and the tile's origin (µm)."""
    return {
        "ChiSurf_Survey_ID": str(info["survey_id"]),
        "ChiSurf_Survey_Tile": int(info["tile"]),
        "ChiSurf_Survey_TileX0_um": float(info["tile_x0_um"]),
        "ChiSurf_Survey_TileY0_um": float(info["tile_y0_um"]),
    }


def tile_tags(info: dict, *, tiles: int, learning: str = "", learned_before: int | None = None
              ) -> dict[str, Any]:
    """A survey tile image's tags: the survey, tile, tile count, origin and the scanner's
    learning mode and how many times it had learned before this tile (the count after it is in
    the tile's ``survey_tile`` record: more means this tile learned)."""
    tags = {**survey_tags(info), "ChiSurf_Survey_Tiles": int(tiles)}
    if learning:
        tags["ChiSurf_Scanner_LearningMode"] = str(learning)
    if learned_before is not None:
        tags["ChiSurf_Scanner_LearnedBefore"] = int(learned_before)
    return tags


# -- the project -------------------------------------------------------------------------------
def _put(source, uid: str, name: str, table: dict, *, artifact_kind: str, operation_type: str,
         row_grain: str, parameters: dict, relationship: str = "derived_from",
         units: dict | None = None) -> str:
    """One record into the analysis container of the dataset *uid* (its recording *source*):
    derived from the recording itself, the container left beside it (sidecar, never a copy)."""
    from chisurf.core.fio.fluorescence.burst_container import open_measurement
    from chisurf.core.project.analysis import container_changed, container_dir

    with open_measurement(str(source), container_dir(uid), raw_data="sidecar") as m:
        m.put_table(name, table, artifact_kind=artifact_kind, operation_type=operation_type,
                    row_grain=row_grain, parameters=parameters,
                    derived_from=m.instrument_uids or m.instrument_uid,
                    relationship_type=relationship, units=units)
        written = str(m.path)
    container_changed(written)
    return written


def _point_row(point: dict) -> dict[str, list]:
    def num(key):
        v = point.get(key)
        return [float("nan") if v is None else float(v)]

    return {
        "index": [int(point.get("index", 0))],
        "pixel_x": num("pixel_x"),
        "pixel_y": num("pixel_y"),
        "x_um": num("x_um"),
        "y_um": num("y_um"),
        "reached_x_um": num("reached_x_um"),
        "reached_y_um": num("reached_y_um"),
        "brightness": num("brightness"),
        "origin": [ORIGIN_CODES.get(str(point.get("origin", "")), -1)],
        "tile": [int(point["tile"]) if point.get("tile") is not None else -1],
    }


_POINT_UNITS = {"pixel_x": "pixels", "pixel_y": "pixels", "x_um": "micrometres",
                "y_um": "micrometres", "reached_x_um": "micrometres",
                "reached_y_um": "micrometres", "brightness": "photons"}


def _source(point: dict) -> dict:
    return {
        "image": str(point.get("image", "")),
        "image_uid": str(point.get("image_uid", "")),
        "image_raster_um": [point.get("image_x0_um"), point.get("image_y0_um"),
                            point.get("image_pixel_um")],
        "origin": str(point.get("origin", "")),
        "origin_codes": ORIGIN_CODES,
        "workflow": str(point.get("workflow", "")),
        "settings_hash": str(point.get("settings_hash", "")),
        "survey_id": str(point.get("survey_id", "")),
    }


def write_point_record(point: dict, molecule=None) -> str:
    """The point recording's own records: the ``point`` (how it was picked and measured, the
    image as an external reference) and, once analysed, its ``molecule`` row."""
    ptu, uid = point.get("ptu"), str(point.get("dataset_uid", ""))
    if not ptu or not uid:
        return ""
    written = _put(ptu, uid, "point", _point_row(point), artifact_kind="point_list",
                   operation_type="point_measurement", row_grain="spot",
                   parameters=_source(point), relationship="uses_external_reference",
                   units=_POINT_UNITS)
    if molecule is not None:
        from .molecules import molecule_rows

        written = _put(ptu, uid, "molecule", molecule_rows([molecule]),
                       artifact_kind="analysis_result", operation_type="trace_segmentation",
                       row_grain="molecule",
                       parameters={"analysis": "intensity trace, shared HMM",
                                   "point": int(point.get("index", 0))},
                       units=MOLECULE_UNITS)
    return written


MOLECULE_UNITS = {"x_um": "micrometres", "y_um": "micrometres", "photons": "photons",
                  "bleach_s": "seconds", "on_s": "seconds", "lifetime_ns": "nanoseconds",
                  "brightest_khz": "kilohertz", "efficiency": "dimensionless",
                  "stoichiometry": "dimensionless"}


def lookup(rows: list[dict], key: str) -> tuple[list[dict], np.ndarray]:
    """``(lookup list, index per row)``: the distinct ``{uid, name}`` of *key* (``point`` or
    ``image``) and each row's position in it (-1 without one) -- a numeric column that names a
    dataset, the names in the record's settings."""
    out: list[dict] = []
    where: dict[str, int] = {}
    index = []
    for r in rows:
        uid = str(r.get(f"{key}_uid", "") or "")
        if not uid:
            index.append(-1)
            continue
        if uid not in where:
            where[uid] = len(out)
            out.append({"uid": uid, "name": str(r.get(f"{key}_name", ""))})
        index.append(where[uid])
    return out, np.asarray(index, np.int64)


def write_image_points(image_ptu, image_uid: str, points: list[dict]) -> str:
    """The image's ``points`` list: every point picked on it, each naming its recording."""
    if not image_ptu or not image_uid or not points:
        return ""
    rows = [_point_row(p) for p in points]
    table = {k: [r[k][0] for r in rows] for k in rows[0]}
    datasets, index = lookup([{"point_uid": p.get("dataset_uid"),
                               "point_name": Path(str(p.get("ptu", ""))).name} for p in points],
                             "point")
    table["point_dataset"] = index
    params = {**_source(points[0]), "point_datasets": datasets}
    params.pop("origin", None)
    return _put(image_ptu, image_uid, "points", table, artifact_kind="point_list",
                operation_type="point_selection", row_grain="spot", parameters=params,
                units=_POINT_UNITS)


def write_survey_tile(image_ptu, image_uid: str, info: dict, *, tiles: int, state: str,
                      learned_after: int | None = None) -> str:
    """A tile image's membership of its survey (grouped in it)."""
    if not image_ptu or not image_uid:
        return ""
    table = {"tile": [int(info["tile"])], "x0_um": [float(info["tile_x0_um"])],
             "y0_um": [float(info["tile_y0_um"])], "tiles": [int(tiles)],
             "learned_after": [-1 if learned_after is None else int(learned_after)]}
    return _put(image_ptu, image_uid, "survey_tile", table, artifact_kind="tile_list",
                operation_type="survey", row_grain="file",
                parameters={"survey_id": str(info["survey_id"]), "state": state},
                relationship="grouped_in",
                units={"x0_um": "micrometres", "y0_um": "micrometres"})


TILE_STATES = {"pending": 0, "current": 1, "done": 2, "empty": 3, "failed": 4}


def write_survey_tiles(image_ptu, image_uid: str, survey_id: str, tiles: list,
                       parameters: dict) -> str:
    """The survey's ``survey_tiles`` list (with its first tile's image): every tile, its state
    and its image, so a survey finds all its images and an image its survey."""
    if not image_ptu or not image_uid or not tiles:
        return ""
    datasets, index = lookup([{"image_uid": getattr(t, "image_uid", ""),
                               "image_name": getattr(t, "image_name", "")} for t in tiles],
                             "image")
    table = {
        "tile": [t.index for t in tiles], "row": [t.row for t in tiles],
        "col": [t.col for t in tiles], "x0_um": [t.x0_um for t in tiles],
        "y0_um": [t.y0_um for t in tiles], "state": [TILE_STATES.get(t.state, -1) for t in tiles],
        "found": [t.found for t in tiles], "measured": [t.measured for t in tiles],
        "image_dataset": index,
    }
    return _put(image_ptu, image_uid, "survey_tiles", table, artifact_kind="tile_list",
                operation_type="survey", row_grain="file",
                parameters={**parameters, "survey_id": survey_id, "image_datasets": datasets,
                            "state_codes": TILE_STATES},
                units={"x0_um": "micrometres", "y0_um": "micrometres"})


# -- reading it back -----------------------------------------------------------------------------
def _address_of(ref) -> tuple[str, str]:
    """``(file, dataset uid)`` of a recording given as its path or its dataset uid."""
    text = str(ref)
    try:
        from chisurf.core.api import dataset_objects

        rows = list(dataset_objects())
    except Exception:  # noqa: BLE001 - no workspace: a path only
        rows = []
    for d in rows:
        uid = str(getattr(d, "unique_identifier", "") or "")
        address = str(getattr(d, "address", "") or "")
        if text in (uid, address):
            return address, uid
    return text, ""


def _container_record(uid: str, name: str) -> dict | None:
    """``{"table": {...}, "settings": {...}, "provenance": {...}}`` of the record *name* in the
    container of dataset *uid*, or ``None``."""
    if not uid:
        return None
    from chisurf.core.datastore import column_names, numeric_column
    from chisurf.core.fio.pto import Measurement
    from chisurf.core.project.analysis import container_dir

    for path in sorted(container_dir(uid).glob("*.pto")):
        try:
            with Measurement.open(path) as m:
                ref = m._f.find(name)
                if not ref:
                    continue
                store = m.get_store(ref)
                prov = m.provenance(ref)
                table = {c: numeric_column(store, c).tolist() for c in column_names(store)}
                return {"table": table, "settings": prov.get("settings") or {},
                        "provenance": prov, "container": str(path)}
        except Exception:  # noqa: BLE001 - another container, or none
            _log.debug("reading %s from %s", name, path, exc_info=True)
    return None


def backtrace(point, uid: str = "") -> dict[str, Any]:
    """Where a point recording came from: its image (file and dataset uid), the pixel and the
    image's raster, how it was picked, the stage position aimed at and reached, the survey and
    tile, its acquisition settings -- from its header, and from the project's record when the
    recording is a dataset of it (``record``).

    Parameters
    ----------
    point : str or Path
        The point's PTU file or its dataset uid.
    uid : str, optional
        The point's dataset uid when *point* is a file the workspace does not list (a project
        reopened elsewhere).
    """
    from . import settings_file

    path, found = _address_of(point)
    uid = uid or found
    tags = settings_file.read_ptu_tags(path)
    out: dict[str, Any] = {
        "point": path,
        "point_uid": uid,
        "image": tags.get("ChiSurf_Point_SourceImage", ""),
        "image_uid": tags.get("ChiSurf_Point_SourceImageUID", ""),
        "pixel": (tags.get("ChiSurf_Point_PixelX"), tags.get("ChiSurf_Point_PixelY")),
        "raster_um": (tags.get("ChiSurf_Point_ImageX0_um"), tags.get("ChiSurf_Point_ImageY0_um"),
                      tags.get("ChiSurf_Point_ImagePixel_um")),
        "origin": tags.get("ChiSurf_Point_Origin", ""),
        "workflow": tags.get("ChiSurf_Point_PickWorkflow", ""),
        "settings_hash": tags.get("ChiSurf_Point_PickSettingsHash", ""),
        "brightness": tags.get("ChiSurf_Point_Brightness"),
        "target_um": (tags.get("ChiSurf_Point_X_um"), tags.get("ChiSurf_Point_Y_um")),
        "reached_um": (tags.get("ChiSurf_Point_Reached_X_um"),
                       tags.get("ChiSurf_Point_Reached_Y_um")),
        "survey_id": tags.get("ChiSurf_Survey_ID", ""),
        "tile": tags.get("ChiSurf_Survey_Tile"),
        "tile_origin_um": (tags.get("ChiSurf_Survey_TileX0_um"),
                           tags.get("ChiSurf_Survey_TileY0_um")),
        "settings": None,
    }
    raw = tags.get(settings_file.CHISURF_SETTINGS_TAG)
    if raw:
        try:
            out["settings"] = json.loads(raw)
        except ValueError:
            out["settings"] = raw
    out["record"] = _container_record(uid, "point")
    if out["image_uid"]:
        address, _ = _address_of(out["image_uid"])
        out["image_path"] = address if address != out["image_uid"] else ""
    return out


def points_of(image, uid: str = "") -> list[dict[str, Any]]:
    """The points picked on an image: ``{"uid", "name", "pixel", "stage_um"}`` each, from the
    image's ``points`` record in the project.

    Parameters
    ----------
    image : str or Path
        The image's PTU file or its dataset uid.
    """
    _path, found = _address_of(image)
    record = _container_record(uid or found, "points")
    if record is None:
        return []
    table, datasets = record["table"], record["settings"].get("point_datasets") or []
    out = []
    for i, k in enumerate(table.get("point_dataset", [])):
        ref = datasets[int(k)] if 0 <= int(k) < len(datasets) else {}
        out.append({"uid": ref.get("uid", ""), "name": ref.get("name", ""),
                    "pixel": (table["pixel_x"][i], table["pixel_y"][i]),
                    "stage_um": (table["x_um"][i], table["y_um"][i])})
    return out


def survey_of(image, uid: str = "") -> dict[str, Any] | None:
    """The survey a tile image belongs to: ``{"survey_id", "tile", ...}`` from its record."""
    _path, found = _address_of(image)
    record = _container_record(uid or found, "survey_tile")
    if record is None:
        return None
    return {"survey_id": record["settings"].get("survey_id", ""),
            "tile": int(record["table"]["tile"][0]), "state": record["settings"].get("state")}
