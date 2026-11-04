"""Safe per-measurement names: Windows sanitization, the MT200 naming scheme, reservations."""

from __future__ import annotations

import datetime
import json
import re

import pytest

from chisurf.plugins.core.acq.live.naming import (
    DEFAULT_MAX_COMPONENT,
    MEASUREMENT_META_SUFFIX,
    MeasurementSlot,
    initials,
    measurement_stem,
    next_available,
    sanitize_component,
    session_dir_name,
    unique_session_dir,
)

MORNING = datetime.datetime(2026, 10, 30, 9, 30, 15)


# -- Windows-safe components ---------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("buffer_APO_0d_60b", "buffer_APO_0d_60b"),
    ("a<b>c:d\"e/f\\g|h|i?j*k", "a_b_c_d_e_f_g_h_i_j_k"),
    ("Green dye", "Green dye"),                    # spaces are legal on Windows and observed
    ("trailing dot.", "trailing dot"),             # Windows silently drops it
    ("trailing space ", "trailing space"),
    (".hidden", "hidden"),
    ("0p125\u00b5M", "0p125uM"),                   # the µ actually found in MT200 file names
    ("caf\u00e9 cr\u00e8me", "cafe creme"),        # accents fold
    ("control\x01char", "control_char"),
    ("tab\tand\nnewline", "tab and newline"),
    ("", "measurement"),                           # never empty
    ("???", "___"),
])
def test_sanitize_component_known_transformations(raw, expected):
    assert sanitize_component(raw) == expected


@pytest.mark.parametrize("reserved", ["CON", "con", "Nul", "COM1", "lpt4", "aux", "nul.txt"])
def test_sanitize_component_avoids_windows_device_names(reserved):
    assert sanitize_component(reserved) != reserved
    assert not re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$",
                        sanitize_component(reserved), re.IGNORECASE)


def test_sanitize_component_caps_length_and_never_ends_on_a_dot():
    long = "x" * 500 + "."
    cleaned = sanitize_component(long)
    assert len(cleaned) <= DEFAULT_MAX_COMPONENT
    assert not cleaned.endswith(".")
    assert cleaned  # never empty


def test_sanitize_component_keeps_ascii_fold_off_when_asked():
    assert sanitize_component("caf\u00e9", fold=False) == "caf\u00e9"


# -- the observed MT200 conventions --------------------------------------------

def test_initials_follow_the_session_directory_scheme():
    assert initials("Thomas Peulen") == "TP"
    assert initials("dm") == "DM"                  # the DM_/TP_/PH_ prefixes on C:\Measurements
    assert initials("M. Random") == "MR"
    assert initials("") == "OP"


def test_session_dir_name_matches_the_observed_pattern():
    name = session_dir_name("Thomas Peulen", MORNING, "JH FluoresceinFCS")
    assert name == "TP_20261030_JH FluoresceinFCS"
    assert re.match(r"^[A-Z]{2}_\d{8}_.+$", name)


def test_session_dir_name_without_description_stays_two_parts():
    assert session_dir_name("dm", MORNING, "") == "DM_20261030"


def test_session_dir_name_sanitizes_the_description():
    name = session_dir_name("TP", MORNING, "MalE_211/322 \u00b5M??")
    assert "/" not in name and "?" not in name and "\u00b5" not in name


# -- collision-free names ------------------------------------------------------

def test_next_available_returns_a_free_stem_unchanged():
    assert next_available("CF532", []) == "CF532"


def test_next_available_counts_up_like_symphotime_does():
    # The counter goes before the extension: FCS_Fitting.pqres -> FCS_Fitting_1.pqres.
    existing = ["FCS_Fitting.pqres", "FCS_Fitting_1.pqres", "FCS_Fitting_2.pqres"]
    assert next_available("FCS_Fitting.pqres", existing) == "FCS_Fitting_3.pqres"


def test_next_available_without_extension_keeps_the_whole_stem():
    assert next_available("CF532", ["CF532", "CF532_1"]) == "CF532_2"


def test_next_available_compares_case_insensitively():
    # NTFS folds case: Test_1 and test_1 are the same file.
    assert next_available("Test", ["test", "Test_1"]) == "Test_2"


@pytest.mark.parametrize("sep, expected", [
    ("_", "H2O_181_2"),
    ("", "H2O_1812"),
    ("r", "H2O_181r2"),
])
def test_next_available_separator_styles(sep, expected):
    assert next_available("H2O_181", ["H2O_181", f"H2O_181{sep}1"], sep=sep) == expected


def test_measurement_stem_styles():
    assert measurement_stem("CF532", MORNING, style="plain") == "CF532"
    assert measurement_stem("CF532", MORNING, style="datetime") == "CF532_093015"
    assert measurement_stem("CF532", MORNING, style="date") == "CF532_20261030"
    with pytest.raises(ValueError):
        measurement_stem("CF532", style="hour")


# -- reservations --------------------------------------------------------------

def test_slot_create_reserves_a_family_with_the_sidecar(tmp_path):
    slot = MeasurementSlot.create(tmp_path, "buffer_APO_0d_60b")
    assert slot.stem == "buffer_APO_0d_60b"
    assert slot.meta_path.name == "buffer_APO_0d_60b.meta.json"
    assert slot.ptu_path.name == "buffer_APO_0d_60b.ptu"
    assert slot.meta_path.exists() and slot.placeholder
    assert json.loads(slot.meta_path.read_text())["reserved_at"]


def test_slot_create_never_reuses_a_taken_name(tmp_path):
    first = MeasurementSlot.create(tmp_path, "CF532")
    second = MeasurementSlot.create(tmp_path, "CF532")
    assert first.stem != second.stem
    assert second.stem == "CF532_1"                # the observed _1 suffixing


def test_slot_create_resolves_same_second_datetime_collisions(tmp_path):
    when = datetime.datetime(2026, 10, 30, 14, 46, 10)
    first = MeasurementSlot.create(tmp_path, "CF532", when=when, style="datetime")
    second = MeasurementSlot.create(tmp_path, "CF532", when=when, style="datetime")
    assert first.stem == "CF532_144610"
    assert second.stem == "CF532_144610_1"         # same second must not collide
    assert MeasurementSlot.create(tmp_path, "CF532", when=when, style="datetime").stem \
        == "CF532_144610_2"


def test_slot_create_is_case_insensitive_against_existing_files(tmp_path):
    (tmp_path / "CF532.ptu").write_bytes(b"existing measurement")
    slot = MeasurementSlot.create(tmp_path, "cf532")
    assert slot.stem == "cf532_1"
    (tmp_path / "cf532_1.ptu").write_bytes(b"x")
    assert MeasurementSlot.create(tmp_path, "CF532").stem == "CF532_2"


def test_slot_write_meta_replaces_the_placeholder(tmp_path):
    slot = MeasurementSlot.create(tmp_path, "CF532")
    slot.write_meta({"operator": "TP", "sample": "CF532 10 nM"})
    assert not slot.placeholder
    assert json.loads(slot.meta_path.read_text())["operator"] == "TP"


def test_slot_abandon_removes_only_an_untouched_empty_reservation(tmp_path):
    slot = MeasurementSlot.create(tmp_path, "never_ran")
    assert slot.abandon() is True
    assert not slot.meta_path.exists()


def test_slot_abandon_never_touches_a_measurement_with_data(tmp_path):
    slot = MeasurementSlot.create(tmp_path, "CF532")
    slot.ptu_path.write_bytes(b"photon stream")
    assert slot.abandon() is False
    assert slot.meta_path.exists() and slot.ptu_path.exists()
    slot.write_meta({"operator": "TP"})
    assert slot.abandon() is False                 # real metadata is data too


def test_unique_session_dir_resolves_collisions(tmp_path):
    first = unique_session_dir(tmp_path, "TP_20261030_FCS")
    second = unique_session_dir(tmp_path, "TP_20261030_FCS")
    assert first.name == "TP_20261030_FCS"
    assert second.name == "TP_20261030_FCS_1"


def test_unique_session_dir_refuses_a_missing_root(tmp_path):
    with pytest.raises(NotADirectoryError):
        unique_session_dir(tmp_path / "Z_missing", "TP_20261030")
    assert not (tmp_path / "Z_missing").exists()   # the root is never auto-created


def test_reservation_suffix_constant_is_the_sidecar(tmp_path):
    slot = MeasurementSlot.create(tmp_path, "x")
    assert slot.meta_path.name.endswith(MEASUREMENT_META_SUFFIX)
