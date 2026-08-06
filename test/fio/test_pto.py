"""One measurement in one file, and the original still recoverable from it.

These are the claims the photon container is worth having for, so they are
tested against a real instrument file rather than a synthesised one: that the
bytes that went in come back out identical, that reading photons out of the
container gives the same photons as reading the vendor file, that recomputing
an analysis cannot disturb the photon stream it was computed from, and that
running the same analysis twice leaves one result rather than two.

See [the PTO.MFDB profile](/specs/pto-mfdb.md) for the rules these pin.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chisurf.core.fio.pto import (
    PROFILE,
    PROFILE_VERSION,
    Measurement,
    PtoMfdbError,
    is_measurement,
)

DATA = Path(__file__).resolve().parents[1] / "data"
PTU = DATA / "clsm" / "Leica_SP5.ptu"
SPC = DATA / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not PTU.exists(), reason="instrument test data missing")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bursts(n: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Number of Photons": np.arange(n, dtype=np.int32),
            "Tau (green)": np.linspace(1.0, 4.0, n),
        }
    )


@pytest.fixture
def measurement(tmp_path: Path) -> Path:
    """A container holding a real PTU plus a burst table derived from it."""
    raw = tmp_path / "m000.ptu"
    shutil.copy(PTU, raw)
    with Measurement.create(raw) as m:
        m.put_table(
            "bursts",
            _bursts(),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"min_photons": 60},
            derived_from=m.instrument_uid,
        )
    return tmp_path / "m000.pto"


# -- the guarantee -------------------------------------------------------------


def test_the_instrument_file_comes_back_byte_for_byte(tmp_path: Path, measurement: Path):
    """The whole reason the original may be deleted afterwards."""
    original = _sha256(tmp_path / "m000.ptu")
    with Measurement.open(measurement) as m:
        out = m.extract(m.instrument_uid, tmp_path / "restored.ptu")
    assert _sha256(out) == original


def test_extraction_refuses_a_payload_that_does_not_match_its_checksum(
    tmp_path: Path, measurement: Path
):
    """"Restorable" without verification is only "probably restorable"."""
    with Measurement.open(measurement) as m:
        uid = m.instrument_uid
        offset = m._f.object(uid).offset

    raw = bytearray(measurement.read_bytes())
    raw[offset + 1024] ^= 0xFF
    measurement.write_bytes(bytes(raw))

    with Measurement.open(measurement) as m:
        assert m.verify(), "a corrupted payload passed verification"
        with pytest.raises(PtoMfdbError, match="checksum"):
            m.extract(m.instrument_uid, tmp_path / "restored.ptu")


def test_a_clean_container_verifies(measurement: Path):
    with Measurement.open(measurement) as m:
        assert m.verify() == []


def test_a_becker_hickl_sidecar_travels_with_its_primary(tmp_path: Path):
    """An .spc keeps half its header in a .set beside it, so the two have to be
    handed to a reader together or it silently reads half a header."""
    if not SPC.exists():
        pytest.skip("no .spc test data")
    raw = tmp_path / "run.spc"
    shutil.copy(SPC, raw)
    companion = SPC.with_suffix(".set")
    if companion.exists():
        shutil.copy(companion, tmp_path / "run.set")

    with Measurement.create(raw) as m:
        pass

    with Measurement.open(tmp_path / "run.pto") as m:
        names = [o.name for o in m.artifacts()]
        assert "run.spc" in names
        out = m.extract(m.instrument_uid, tmp_path / "back.spc")
    assert _sha256(out) == _sha256(raw)


# -- transparency --------------------------------------------------------------


def test_photons_read_out_of_the_container_match_the_vendor_file(
    tmp_path: Path, measurement: Path
):
    """The point of embedding rather than decoding: the caller hands over a
    path and never learns what the payload actually is."""
    import tttrlib

    direct = tttrlib.TTTR(str(tmp_path / "m000.ptu"))
    inside = tttrlib.TTTR(str(measurement))

    np.testing.assert_array_equal(inside.macro_times, direct.macro_times)
    np.testing.assert_array_equal(inside.micro_times, direct.micro_times)
    np.testing.assert_array_equal(inside.routing_channels, direct.routing_channels)


def test_the_reading_seam_accepts_a_container_and_a_member(
    tmp_path: Path, measurement: Path
):
    """``open_tttr`` is the one seam every reader goes through, so a container
    has to work there and not only through ``tttrlib`` directly. The selector
    form is the part that needed care: only the text before the separator is a
    path, and staging must not try to copy the whole spec."""
    from chisurf.core.fio.staging import open_tttr, split_container_spec

    direct = open_tttr(str(tmp_path / "m000.ptu"))
    for spec in (str(measurement), f"{measurement}|m000.ptu"):
        got = open_tttr(spec)
        np.testing.assert_array_equal(got.macro_times, direct.macro_times)

    path, member = split_container_spec(f"{measurement}|m000.ptu")
    assert path == measurement and member == "m000.ptu"
    assert split_container_spec(measurement) == (measurement, "")


def test_it_identifies_itself(measurement: Path, tmp_path: Path):
    assert is_measurement(measurement) is True
    assert is_measurement(tmp_path / "m000.ptu") is False
    assert is_measurement(tmp_path / "absent.pto") is False


# -- the photon stream is immutable --------------------------------------------


def test_recomputing_an_analysis_does_not_move_the_photon_stream(measurement: Path):
    """The reason the instrument file is written first and never rewritten:
    recomputing a burst table beside a multi-gigabyte stream must rewrite the
    table, not the file."""
    with Measurement.open(measurement, writable=True) as m:
        before = m._f.object(m.instrument_uid).offset
        size_before = measurement.stat().st_size
        m.put_table(
            "bursts",
            _bursts(400),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"min_photons": 90},
            derived_from=m.instrument_uid,
        )
        assert m._f.object(m.instrument_uid).offset == before, "the photon stream moved"

    assert measurement.stat().st_size < size_before * 2, "the stream was rewritten"


# -- nothing accumulates -------------------------------------------------------


def test_rerunning_with_the_same_settings_replaces_the_result(measurement: Path):
    """Without this a file grows one object per run, which is the directory
    sprawl it exists to replace, moved inside a single file."""
    with Measurement.open(measurement, writable=True) as m:
        before = m._f.n_objects()
        for _ in range(5):
            m.put_table(
                "bursts",
                _bursts(41),
                artifact_kind="burst_table",
                operation_type="burst_selection",
                row_grain="burst",
                parameters={"min_photons": 60},
                derived_from=m.instrument_uid,
            )
        assert m._f.n_objects() == before

    with Measurement.open(measurement) as m:
        assert len(m.get_table("bursts")) == 41, "the replacement was not written"


def test_changing_a_setting_produces_a_new_result(measurement: Path):
    with Measurement.open(measurement, writable=True) as m:
        before = m._f.n_objects()
        m.put_table(
            "bursts",
            _bursts(),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"min_photons": 120},
            derived_from=m.instrument_uid,
        )
        assert m._f.n_objects() == before + 1


# -- grain and keys ------------------------------------------------------------


def test_a_finer_grained_table_declares_its_grain_and_its_key(
    tmp_path: Path, measurement: Path
):
    """A dwell subdivides a burst. A format that can only carry one row per
    burst has nowhere to put it, which is why H2MM results ended up in five
    files outside the companion system."""
    with Measurement.open(measurement, writable=True) as m:
        bursts = m._resolve("bursts")
        dwells = pd.DataFrame(
            {
                "burst": np.repeat(np.arange(10), 3),
                "state": np.tile([0, 1, 2], 10),
            }
        )
        uid = m.put_table(
            "dwells",
            dwells,
            artifact_kind="dwell_table",
            operation_type="photon_hmm",
            row_grain="dwell",
            parameters={"states": 3},
            derived_from=bursts,
            source_row_column="burst",
            target_row_column="Number of Photons",
        )

    with Measurement.open(measurement) as m:
        assert m.tag(uid, "_mmfdb_artifact.row_grain") == "dwell"
        assert m.tag(uid, "_mmfdb_edge.source_row_column") == "burst"
        assert m.parents(uid) == [m._resolve("bursts")]


def test_an_artifact_may_have_several_parents(measurement: Path):
    """Fusing bursts produces a row made of more than one source, so the edge
    arity has to be able to say so."""
    with Measurement.open(measurement, writable=True) as m:
        photons, bursts = m.instrument_uid, m._resolve("bursts")
        uid = m.put_table(
            "fused",
            _bursts(12),
            artifact_kind="burst_table",
            operation_type="burst_fusion",
            row_grain="burst",
            parameters={"p_same": 0.8},
            derived_from=[photons, bursts],
        )
        assert sorted(m.parents(uid)) == sorted([photons, bursts])


# -- the vocabulary is not ours ------------------------------------------------


def test_an_invented_term_is_refused(measurement: Path):
    """The profile defines no vocabulary of its own, so a word that is not in
    the dictionary is a writer inventing one. Refusing at write time is what
    keeps an unqueryable file from being produced."""
    with Measurement.open(measurement, writable=True) as m:
        with pytest.raises(PtoMfdbError, match="not a value of"):
            m.put_table(
                "x", _bursts(2),
                artifact_kind="burst_table",
                operation_type="burst_selection",
                row_grain="banana",
            )
        with pytest.raises(PtoMfdbError, match="not a value of"):
            m.put_table(
                "x", _bursts(2),
                artifact_kind="not_a_kind",
                operation_type="burst_selection",
                row_grain="burst",
            )


def test_every_written_term_resolves_in_the_dictionary(measurement: Path):
    """Walks a produced file and checks it against the dictionaries, which is
    what stops the profile drifting back into a private namespace."""
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    paths = [
        MmcifDictionary._resolve_dic(n)
        for n in (*MmcifDictionary.BUNDLED_DICTS, *MmcifDictionary.EXPORT_ONLY_DICTS)
    ]
    dic = MmcifDictionary(*paths)

    with Measurement.open(measurement) as m:
        for obj in m.artifacts():
            assert obj.kind in dic.get_enumerations("_mmfdb_artifact.artifact_kind")
            assert obj.encoding in dic.get_enumerations("_mmfdb_artifact.data_format")
        for tag in m._f.tags():
            assert dic.get_item(tag.name) is not None, f"undeclared tag name {tag.name}"


# -- versions ------------------------------------------------------------------


def test_a_file_records_what_it_was_written_against(measurement: Path):
    """Four things drift independently, so a file recording one of them cannot
    be diagnosed when it disagrees with a reader."""
    from mmfdb.schema.pdbx_metadata import extension_dictionary_version

    with Measurement.open(measurement) as m:
        assert m.tag(0, "_mmfdb_container.profile") == PROFILE
        assert m.tag(0, "_mmfdb_container.profile_version") == PROFILE_VERSION
        assert m.tag(0, "_mmfdb_container.format") == "pto"
        assert m.tag(0, "_mmfdb_container.dictionary_version") == (
            extension_dictionary_version()
        )
        assert len(m.tag(0, "_mmfdb_container.dictionary_hash")) == 64


# -- lifecycle -----------------------------------------------------------------


def test_a_read_only_container_refuses_to_be_written(measurement: Path):
    with Measurement.open(measurement) as m:
        with pytest.raises(PtoMfdbError, match="read-only"):
            m.put_table(
                "x", _bursts(2),
                artifact_kind="burst_table",
                operation_type="burst_selection",
                row_grain="burst",
            )


def test_disassembly_puts_every_object_back_on_disk(tmp_path: Path, measurement: Path):
    with Measurement.open(measurement) as m:
        written = m.disassemble(tmp_path / "apart")
    assert written
    assert (tmp_path / "apart" / "m000.ptu").exists()
    assert _sha256(tmp_path / "apart" / "m000.ptu") == _sha256(tmp_path / "m000.ptu")
