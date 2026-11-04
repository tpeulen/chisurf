"""The instrument reference-history store, headlessly.

The store keeps historical reference measurements of the MT200 -- diffusion time and
background-corrected molecular brightness at the laser power they were measured with -- so a
later measurement can be judged against what the same instrument did before. The rules the
tests pin:

* comparability is keyed on explicit experimental conditions: laser wavelength, the verified
  calibrated isolated laser power (a total-diode reading with several lasers on establishes no
  individual laser's power), excitation pulse mode/timing and rep rate, optical configuration,
  detector, dye, temperature and any extra conditions the user records;
* spec or reference bounds come from the user (or are derived from the user's own stored
  records, labelled as derived). The module ships no thresholds;
* a deviation is a maintenance/inspection recommendation, never scientific proof of a fault;
* missing metadata or an unverified power reading gets no spec verdict at all;
* invalid values are rejected; the user's records are preserved on every failure; writes are
  atomic; there is no cap on how many records a history may hold.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from chisurf.plugins.core.acq.live import reference_history as rh


# -- helpers -----------------------------------------------------------------------------------
def rec(**over):
    """A valid reference measurement (MT200, 640 nm branch), overridden per test."""
    base = dict(
        timestamp_utc="2026-10-30T12:00:00+00:00",
        laser_nm=640.0,
        power_uw=25.0,
        power_verified=True,
        excitation_mode="pulsed",
        rep_rate_mhz=40.0,
        optical_configuration="MT200 confocal, 640 branch",
        detector="SPAD-1",
        dye="Rhodamine 6G",
        tau_diff_s=4.2e-4,
        brightness_cps=2.1e4,
        temperature_c=23.0,
    )
    base.update(over)
    return base


BOUNDS = {
    "tau_diff_s": {"min": 3.0e-4, "max": 5.0e-4},
    "brightness_cps": {"min": 1.0e4, "max": 3.0e4},
}


@pytest.fixture
def store(tmp_path):
    return rh.ReferenceHistory(tmp_path / "references.json")


# -- storing and retrieving --------------------------------------------------------------------
def test_add_stores_and_returns_record_with_uid_and_utc_timestamp(store):
    out = store.add(**rec())
    assert out["uid"]
    assert out["timestamp_utc"] == "2026-10-30T12:00:00+00:00"
    assert out["stored_at_utc"].endswith("+00:00")
    assert [r["uid"] for r in store.records()] == [out["uid"]]


def test_records_round_trip_all_fields_including_conditions_and_provenance(tmp_path):
    path = tmp_path / "references.json"
    fields = rec(
        conditions={"waist_um": 0.5, "filter_set": "HQ700/80"},
        provenance={"background_correction": "measured dark rate", "operator": "mt200"},
        background_cps=2100.0,
        notes="fresh stock solution",
    )
    rh.ReferenceHistory(path).add(**fields)
    (out,) = rh.ReferenceHistory(path).records()
    for key, value in fields.items():
        assert out[key] == value, key
    assert out["key"] == rh.conditions_key({
        "laser_nm": 640.0, "power_uw": 25.0, "power_verified": True,
        "excitation_mode": "pulsed",
        "rep_rate_mhz": 40.0, "optical_configuration": "MT200 confocal, 640 branch",
        "detector": "SPAD-1", "dye": "Rhodamine 6G", "temperature_c": 23.0,
        "waist_um": 0.5, "filter_set": "HQ700/80",
    })


def test_timestamp_accepts_timezone_offset_and_datetime_and_normalises_to_utc(store):
    a = store.add(**rec(timestamp_utc="2026-10-30T14:00:00+02:00"))
    b = store.add(**rec(timestamp_utc=datetime(2026, 10, 30, 9, 30, tzinfo=timezone(-5 * timedelta(hours=1)))))
    assert a["timestamp_utc"] == "2026-10-30T12:00:00+00:00"
    assert b["timestamp_utc"] == "2026-10-30T14:30:00+00:00"


def test_naive_timestamp_is_rejected(store):
    with pytest.raises(rh.InvalidMeasurement, match="timezone"):
        store.add(**rec(timestamp_utc="2026-10-30T12:00:00"))
    with pytest.raises(rh.InvalidMeasurement):
        store.add(**rec(timestamp_utc=datetime(2026, 10, 30, 12)))
    assert store.records() == []


def test_uid_is_unique_per_record(store):
    uids = {store.add(**rec(timestamp_utc=f"2026-10-30T12:00:{s:02d}+00:00"))["uid"] for s in range(5)}
    assert len(uids) == 5


def test_empty_store_reads_as_no_records_and_creates_no_file(tmp_path):
    path = tmp_path / "references.json"
    assert rh.ReferenceHistory(path).records() == []
    assert not path.exists()


# -- rejecting invalid values ------------------------------------------------------------------
@pytest.mark.parametrize(
    "over",
    [
        {"tau_diff_s": 0.0}, {"tau_diff_s": -1e-4}, {"tau_diff_s": float("nan")},
        {"tau_diff_s": float("inf")}, {"tau_diff_s": None},
        {"brightness_cps": 0.0}, {"brightness_cps": -1.0}, {"brightness_cps": float("nan")},
        {"brightness_cps": None},
        {"laser_nm": 0.0}, {"laser_nm": float("nan")}, {"laser_nm": None},
        {"power_uw": 0.0}, {"power_uw": -1.0}, {"power_uw": None},
        {"power_verified": "yes"},
        {"dye": ""}, {"dye": "   "}, {"detector": ""},
        {"excitation_mode": ""}, {"excitation_mode": "pulsed", "rep_rate_mhz": None},
        {"excitation_mode": "pulsed", "rep_rate_mhz": 0.0},
        {"excitation_mode": "cw", "rep_rate_mhz": 20.0},
        {"optical_configuration": ""},
        {"background_cps": -1.0}, {"background_cps": float("nan")},
        {"temperature_c": "warm"}, {"temperature_c": float("nan")},
        {"timestamp_utc": "yesterday"},
        {"conditions": {"laser_nm": 488.0}},  # shadows a core condition
        {"conditions": {"tags": ["a", "b"]}},  # non-scalar condition value
        {"conditions": {"thing": object()}},  # not JSON-serialisable
        {"provenance": {"stuff": {1, 2}}},  # not JSON-serialisable
        {"unknown_field": 1},
    ],
)
def test_invalid_values_are_rejected_and_nothing_is_written(store, over):
    with pytest.raises(rh.InvalidMeasurement):
        store.add(**rec(**over))
    assert store.records() == []
    assert not store.path.exists() or store.path.read_text() == ""


# -- the store preserves the user's records ----------------------------------------------------
def test_corrupt_store_is_reported_explicitly_and_never_overwritten(tmp_path):
    path = tmp_path / "references.json"
    path.write_text("{not json")
    before = path.read_bytes()
    for action in (
        lambda s: s.records(),
        lambda s: s.add(**rec()),
        lambda s: s.set_bounds({"laser_nm": 640.0}, BOUNDS),
    ):
        with pytest.raises(rh.StoreError):
            action(rh.ReferenceHistory(path))
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("doc", [{"schema": "something-else"}, {"schema": rh.SCHEMA, "version": 999}])
def test_foreign_or_newer_store_is_reported_and_never_overwritten(tmp_path, doc):
    path = tmp_path / "references.json"
    path.write_text(json.dumps(doc))
    before = path.read_bytes()
    with pytest.raises(rh.StoreError):
        rh.ReferenceHistory(path).add(**rec())
    assert path.read_bytes() == before


def test_failed_write_preserves_existing_records(tmp_path, monkeypatch):
    path = tmp_path / "references.json"
    store = rh.ReferenceHistory(path)
    first = store.add(**rec())
    before = path.read_bytes()

    def boom(*a, **kw):
        raise OSError("disk gone")

    monkeypatch.setattr(rh.tempfile, "mkstemp", boom)
    with pytest.raises(rh.StoreError):
        store.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00"))
    monkeypatch.undo()
    assert path.read_bytes() == before
    assert [r["uid"] for r in rh.ReferenceHistory(path).records()] == [first["uid"]]
    assert not list(tmp_path.glob("*.tmp"))


def test_successful_writes_leave_no_temporary_files(store, tmp_path):
    for s in range(3):
        store.add(**rec(timestamp_utc=f"2026-10-30T12:00:0{s}+00:00"))
    assert {p.name for p in store.path.parent.iterdir()} == {store.path.name}
    doc = json.loads(store.path.read_text())
    assert doc["schema"] == rh.SCHEMA and len(doc["records"]) == 3


def test_two_instances_share_one_file(tmp_path):
    path = tmp_path / "references.json"
    a, b = rh.ReferenceHistory(path), rh.ReferenceHistory(path)
    a.add(**rec())
    assert len(b.records()) == 1
    b.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00"))
    assert len(a.records()) == 2


def test_no_arbitrary_limit_on_record_count(store):
    n = 500
    for i in range(n):
        store.add(**rec(timestamp_utc=f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}+00:00"))
    assert len(store.records()) == n


# -- comparability ------------------------------------------------------------------------------
def test_conditions_key_normalises_numbers_and_drops_none():
    assert rh.conditions_key({"a": 1, "b": None}) == rh.conditions_key({"a": 1.0})
    assert rh.conditions_key({"p": 25}) == rh.conditions_key({"p": 25.0})


def test_comparability_is_gated_on_the_full_condition_set(store):
    same = rec()
    store.add(**same)
    for differing in [
        {"power_uw": 30.0},
        {"laser_nm": 530.0},
        {"rep_rate_mhz": 20.0},
        {"excitation_mode": "cw", "rep_rate_mhz": None},
        {"optical_configuration": "MT200 confocal, 530 branch"},
        {"detector": "SPAD-2"},
        {"dye": "Atto 655"},
        {"temperature_c": 25.0},
        {"conditions": {"waist_um": 0.5}},  # an extra condition only one side records
        {"power_verified": False},
    ]:
        store.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00", **differing))
        assert len(store.comparable(**same)) == 1, differing


def test_identical_conditions_are_comparable(store):
    store.add(**rec(temperature_c=None))
    store.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00", temperature_c=None))
    assert len(store.comparable(**rec(temperature_c=None))) == 2


def test_comparable_normalises_int_and_float_conditions(store):
    store.add(**rec(power_uw=25))
    assert len(store.comparable(**rec())) == 1


# -- bounds: user-established, never fabricated --------------------------------------------------
def test_set_bounds_round_trip_and_overwrite(store):
    conditions = {"laser_nm": 640.0}
    store.set_bounds(conditions, BOUNDS, kind="spec", note="vendor datasheet")
    entry = store.get_bounds(conditions)
    assert entry["bounds"] == BOUNDS and entry["kind"] == "spec" and entry["note"] == "vendor datasheet"
    assert entry["set_at_utc"].endswith("+00:00")
    store.set_bounds(conditions, {"tau_diff_s": {"max": 4e-4}}, kind="reference")
    assert list(store.all_bounds()) == [rh.conditions_key(conditions)]
    assert store.get_bounds(conditions)["bounds"] == {"tau_diff_s": {"max": 4e-4}}


def test_a_fresh_history_has_no_bounds(store):
    assert store.get_bounds({"laser_nm": 640.0}) is None
    assert store.all_bounds() == {}


@pytest.mark.parametrize(
    "bounds",
    [
        {},
        {"count_rate_hz": {"max": 1e6}},  # not a tracked metric
        {"tau_diff_s": {}},  # neither min nor max
        {"tau_diff_s": {"min": 5e-4, "max": 3e-4}},  # min >= max
        {"tau_diff_s": {"min": 5e-4, "max": 5e-4}},
        {"brightness_cps": {"min": float("nan")}},
        {"brightness_cps": {"min": -1.0}},
        {"tau_diff_s": "loose"},
        {"tau_diff_s": {"min": "small"}},
    ],
)
def test_nonsense_bounds_are_rejected(store, bounds):
    with pytest.raises(rh.InvalidBounds):
        store.set_bounds({"laser_nm": 640.0}, bounds)


def test_derived_reference_bounds_come_from_the_stored_records_only(store):
    for i in range(8):
        store.add(**rec(
            timestamp_utc=f"2026-10-30T12:00:{i:02d}+00:00",
            tau_diff_s=4.0e-4 + i * 1.0e-6,
            brightness_cps=2.0e4 + i * 100.0,
        ))
    out = store.reference_bounds(rec())
    assert out["info"]["source"] == "derived_from_history" and out["info"]["n"] == 8
    assert "MAD" in out["info"]["method"]
    tau = out["bounds"]["tau_diff_s"]
    b = BOUNDS["tau_diff_s"]
    assert b["min"] < tau["min"] <= 4.0e-4 <= tau["max"] < b["max"]
    assert out["bounds"]["brightness_cps"]["min"] >= 0.0


def test_derived_reference_bounds_need_sufficient_comparable_history(store):
    store.add(**rec())
    with pytest.raises(rh.InsufficientHistory, match="1 comparable"):
        store.reference_bounds(rec())
    store.reference_bounds(rec(), min_history=1)  # an explicit, smaller minimum is the user's call


# -- the verdict ---------------------------------------------------------------------------------
def test_within_bounds_verdict_reports_history_shortfall_explicitly(store):
    store.set_bounds(rec(), BOUNDS, kind="spec")
    verdict = store.evaluate(rec())
    assert verdict["status"] == "within_reference"
    assert all(c["level"] == "within" for c in verdict["checks"])
    assert verdict["history"]["sufficiency"] == "none"
    assert verdict["history"]["why"]
    assert "not" in verdict["caveat"] and "fault" in verdict["caveat"]
    assert verdict["bounds_provenance"]["kind"] == "spec"


def test_outside_bounds_recommends_inspection_and_is_never_proof_of_fault(store):
    store.set_bounds(rec(), BOUNDS)
    for over, level in [
        ({"tau_diff_s": 6.0e-4}, "above_max"),
        ({"tau_diff_s": 2.0e-4}, "below_min"),
        ({"brightness_cps": 5.0e4}, "above_max"),
    ]:
        verdict = store.evaluate(rec(**over))
        assert verdict["status"] == "recommend_inspection", over
        bad = [c for c in verdict["checks"] if c["level"] != "within"]
        assert [c["level"] for c in bad] == [level]
        assert bad[0]["deviation"] > 0
        text = (verdict["recommendation"] + verdict["caveat"]).lower()
        assert "inspect" in text or "maintenance" in text
        assert "not" in text and "fault" in text


def test_a_deviation_from_history_free_bounds_is_labelled_as_derived(store):
    for i in range(8):
        store.add(**rec(timestamp_utc=f"2026-10-30T12:00:{i:02d}+00:00",
                        tau_diff_s=4.0e-4 + i * 1.0e-6, brightness_cps=2.0e4 + i * 100.0))
    derived = store.reference_bounds(rec())
    store.set_bounds(rec(), derived["bounds"], kind="reference",
                     note=f"derived from {derived['info']['n']} stored records")
    verdict = store.evaluate(rec(tau_diff_s=9.0e-4))
    assert verdict["status"] == "recommend_inspection"
    assert verdict["bounds_provenance"]["kind"] == "reference"


def test_explicit_bounds_argument_is_used_and_labelled(store):
    verdict = store.evaluate(rec(), bounds=BOUNDS)
    assert verdict["status"] == "within_reference"
    assert verdict["bounds_provenance"]["source"] == "call"


def test_no_bounds_means_no_verdict_and_no_invented_thresholds(store):
    verdict = store.evaluate(rec())
    assert verdict["status"] == "no_bounds"
    assert verdict["checks"] == []
    assert verdict["bounds"] is None
    assert "set_bounds" in verdict["why"]


def test_unverified_power_gets_no_spec_verdict(store):
    store.set_bounds(rec(), BOUNDS)
    verdict = store.evaluate(rec(power_verified=False))
    assert verdict["status"] == "unverified"
    assert verdict["checks"] == []
    assert "isolated" in verdict["why"]


def test_missing_metadata_gets_no_spec_verdict_and_names_the_gaps(store):
    store.set_bounds(rec(), BOUNDS)
    incomplete = rec()
    del incomplete["optical_configuration"], incomplete["rep_rate_mhz"]
    verdict = store.evaluate(incomplete)
    assert verdict["status"] == "unverifiable"
    assert set(verdict["missing"]) == {"optical_configuration", "rep_rate_mhz"}
    assert verdict["checks"] == []


def test_evaluate_reports_insufficient_history_explicitly(store):
    store.set_bounds(rec(), BOUNDS)
    store.add(**rec())
    verdict = store.evaluate(rec())
    assert verdict["history"]["sufficiency"] == "insufficient"
    assert "1" in verdict["history"]["why"] and "3" in verdict["history"]["why"]


def test_evaluate_reports_incomparable_history_explicitly(store):
    store.set_bounds(rec(), BOUNDS)
    store.add(**rec(power_uw=30.0))
    store.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00", power_uw=35.0))
    verdict = store.evaluate(rec())
    assert verdict["history"]["sufficiency"] == "none"
    assert "2" in verdict["history"]["why"]
    assert any("power_uw" in ex["differs_on"] for ex in verdict["history"]["incomparable_examples"])


def test_evaluate_excludes_the_stored_record_itself(store):
    stored = store.add(**rec())
    verdict = store.evaluate({**rec(), "uid": stored["uid"]})
    assert verdict["history"]["n_comparable"] == 0
    other = store.add(**rec(timestamp_utc="2026-10-30T12:00:01+00:00"))
    # without the uid the evaluated measurement is a new one: both stored records are comparable
    assert store.evaluate(rec())["history"]["n_comparable"] == 2
    assert other["uid"] != stored["uid"]


def test_history_summary_carries_the_comparable_spread(store):
    store.set_bounds(rec(), BOUNDS)
    for i in range(3):
        store.add(**rec(timestamp_utc=f"2026-10-30T12:00:{i:02d}+00:00",
                        tau_diff_s=4.0e-4 + i * 1.0e-5))
    stats = store.evaluate(rec())["history"]["metrics"]["tau_diff_s"]
    assert stats["n"] == 3 and stats["min"] == pytest.approx(4.0e-4) and stats["max"] == pytest.approx(4.2e-4)
    assert math.isfinite(stats["median"])
