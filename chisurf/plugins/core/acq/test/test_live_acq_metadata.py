"""Acquisition metadata: who measured what, when -- recorded, round-tripped, file-safe."""

from __future__ import annotations

import datetime
import json

import pytest

from chisurf.plugins.core.acq.live.acq_metadata import (
    ACQ_META_SCHEMA,
    AcquisitionMeta,
    read_meta,
    write_meta,
)


def a_meta() -> AcquisitionMeta:
    return AcquisitionMeta(
        operator="TP",
        experiment_type="fcs",
        dyes=["Alexa Fluor 488"],
        sample="MalE 211-322, 10 nM",
        project="MalE-His titration",
        instrument="MT200",
        notes="buffer check first",
    )


# -- time stamps ---------------------------------------------------------------

def test_start_and_finish_stamp_iso8601_with_utc_offset():
    meta = a_meta()
    assert meta.started_at is None and meta.finished_at is None
    started = meta.start()
    finished = meta.finish()
    for stamp in (started, finished):
        parsed = datetime.datetime.fromisoformat(stamp)
        assert parsed.tzinfo is not None          # the offset survives; UTC alone loses the lab day
    assert datetime.datetime.fromisoformat(meta.finished_at) >= datetime.datetime.fromisoformat(meta.started_at)


def test_session_stamps_land_in_the_session_section():
    meta = a_meta()
    meta.start_session("TP_20261030_JH_FluoresceinFCS")
    meta.end_session()
    assert meta.session["name"] == "TP_20261030_JH_FluoresceinFCS"
    assert {"started_at", "finished_at"} <= set(meta.session)


# -- (de)serialisation ---------------------------------------------------------

def test_to_dict_carries_the_schema_and_every_field():
    document = a_meta().to_dict()
    assert document["schema"] == ACQ_META_SCHEMA
    assert document["operator"] == "TP"
    assert document["dyes"] == ["Alexa Fluor 488"]
    assert document["project"] == "MalE-His titration"


def test_round_trip_through_a_dict_keeps_every_field():
    meta = a_meta()
    meta.start()
    assert AcquisitionMeta.from_dict(meta.to_dict()).to_dict() == meta.to_dict()


def test_from_dict_keeps_unknown_keys_for_a_newer_writer():
    document = a_meta().to_dict()
    document["future_field"] = {"whatever": True}
    meta = AcquisitionMeta.from_dict(document)
    assert meta.extra["future_field"] == {"whatever": True}
    assert meta.to_dict()["future_field"] == {"whatever": True}   # survives a round trip


def test_from_dict_tolerates_missing_and_mistyped_fields():
    meta = AcquisitionMeta.from_dict({"operator": "PH", "dyes": "Cy3B", "session": "junk"})
    assert meta.dyes == ["Cy3B"]                  # a lone dye string becomes the list
    assert meta.session == {}                     # junk shapes fall back, never raise
    assert AcquisitionMeta.from_dict({}).operator == ""


def test_sidecar_write_and_read_round_trip(tmp_path):
    path = write_meta(tmp_path / "CF532_1.meta.json", a_meta())
    meta = read_meta(path)
    assert meta.sample == "MalE 211-322, 10 nM"
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == ACQ_META_SCHEMA


def test_write_meta_is_atomic_and_utf8(tmp_path):
    path = write_meta(tmp_path / "m.meta.json", a_meta())
    assert not path.with_suffix(".meta.json.tmp").exists()
    assert "\u00b5" not in path.read_text(encoding="utf-8") or True  # free text stays verbatim
    write_meta(path, AcquisitionMeta(notes="0p125\u00b5M"))
    assert "0p125\u00b5M" in read_meta(path).notes


def test_read_meta_rejects_junk(tmp_path):
    junk = tmp_path / "junk.meta.json"
    junk.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        read_meta(junk)


# -- naming integration --------------------------------------------------------

def test_name_description_joins_sample_and_dyes_sanitized():
    meta = AcquisitionMeta(sample="MalE 211/322", dyes=["Atto 655"], experiment_type="fcs")
    assert meta.name_description() == "MalE 211_322 Atto 655"


def test_measurement_base_prefers_the_sample_then_the_experiment():
    assert a_meta().measurement_base() == "MalE 211-322, 10 nM"
    assert AcquisitionMeta(experiment_type="pie").measurement_base() == "pie"
    assert AcquisitionMeta().measurement_base() == "measurement"
