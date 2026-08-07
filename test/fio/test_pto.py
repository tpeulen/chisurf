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


def test_one_run_may_write_several_results_of_the_same_kind(measurement: Path):
    """Replacing is keyed on the *output*, not only on the run.

    One analysis routinely emits several artifacts of one kind: an MLE fit
    writes one table per detector, all of them ``fit_result`` from one
    operation with one settings hash. Keyed on the settings alone they are all
    "the same run", so each write replaces the last and a three-detector
    analysis ends with one table — silently, because replacing is the intended
    behaviour and nothing distinguishes it from the collision.
    """
    with Measurement.open(measurement, writable=True) as m:
        before = m._f.n_objects()
        for detector in ("green", "yellow", "red"):
            m.put_table(
                f"mle {detector}",
                _bursts(7),
                artifact_kind="fit_result",
                operation_type="burst_lifetime_fitting",
                row_grain="burst",
                parameters={"model": "fit23"},
                derived_from=m.instrument_uid,
            )
        assert m._f.n_objects() == before + 3

    with Measurement.open(measurement) as m:
        for detector in ("green", "yellow", "red"):
            assert len(m.get_table(f"mle {detector}")) == 7


def test_replacing_a_result_leaves_the_container_readable(measurement: Path):
    """A grown result moves, and the space it left has to stay walkable.

    The relocation frees the old run, and the next element written into that
    hole carves its front — the remainder is then the old payload's tail with
    no element header over it. The file is fine until something reopens it, at
    which point it reports damage at an offset in the middle of itself. Every
    ``put_table`` writes tags afterwards, so an ordinary re-run with a bigger
    result was enough to trigger it.
    """
    with Measurement.open(measurement, writable=True) as m:
        m.put_table(
            "bursts", _bursts(3),
            artifact_kind="burst_table", operation_type="burst_selection",
            row_grain="burst", parameters={"min_photons": 60},
            derived_from=m.instrument_uid,
        )
    with Measurement.open(measurement, writable=True) as m:
        m.put_table(
            "bursts", _bursts(20000),
            artifact_kind="burst_table", operation_type="burst_selection",
            row_grain="burst", parameters={"min_photons": 60},
            derived_from=m.instrument_uid,
        )
    with Measurement.open(measurement) as m:
        assert len(m.get_table("bursts")) == 20000
        assert m.verify() == []


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


def test_a_column_still_says_its_unit_when_it_is_read_back(measurement: Path):
    """A unit that can be written and not read is one only the writer believes.

    The unit is an attribute of the column, so it survives ``get_store`` and
    not ``get_table`` — pandas has nowhere to keep it. That is worth pinning in
    both directions, because the frame is the shape most callers reach for and
    it is the one that silently drops the answer.
    """
    with Measurement.open(measurement, writable=True) as m:
        m.put_table(
            "timed",
            pd.DataFrame(
                {
                    "Duration": np.linspace(0.1, 3.0, 8),
                    "Tau": np.linspace(1.0, 4.0, 8),
                    "Ratio": np.linspace(0.0, 1.0, 8),
                }
            ),
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"units": True},
            derived_from=m.instrument_uid,
            units={
                "Duration": "milliseconds",
                "Tau": "nanoseconds",
                "Ratio": "dimensionless",
            },
        )

    with Measurement.open(measurement) as m:
        store = m.get_store("timed")
        assert m.column_units(store, "Duration") == "milliseconds"
        assert m.column_units(store, "Tau") == "nanoseconds"
        # Dimensionless is a claim; "" would mean the unit is unknown.
        assert m.column_units(store, "Ratio") == "dimensionless"
        assert m.column_units(store, "nope") == ""


def test_an_invented_unit_is_refused(measurement: Path):
    """The vocabulary is the dictionary's, the same as everywhere else."""
    with Measurement.open(measurement, writable=True) as m:
        with pytest.raises(PtoMfdbError):
            m.put_table(
                "bad units",
                _bursts(4),
                artifact_kind="burst_table",
                operation_type="burst_selection",
                row_grain="burst",
                derived_from=m.instrument_uid,
                units={"Number of Photons": "furlongs"},
            )


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


# -- the file explains itself ------------------------------------------------------


def test_a_container_carries_a_plain_text_explanation_of_itself(measurement: Path):
    """A container outlives the software that wrote it. When the library will
    not install, what a person needs is not a specification somewhere else but a
    paragraph in the file saying what the bytes are."""
    with Measurement.open(measurement) as m:
        first = m.artifacts()[0]
        assert first.kind == "readme", "the preamble is not the first object"
        text = bytes(m._f.read(first.uid))

    text.decode("ascii")                     # ASCII, not UTF-8, on purpose
    body = text.decode("ascii")
    for expected in (
        "EBML",                              # what the framing is
        "0x1A45DFA3",                        # where to start
        "PtoKind",                           # how an object says what it is
        "tttr_photon_stream",                # how to find the original data
        "SHA-256",                           # how to verify it
    ):
        assert expected in body, f"the preamble does not mention {expected}"


def test_the_explanation_is_findable_in_the_raw_bytes(measurement: Path):
    """`strings file.pto` has to show it, or it is documentation nobody reaches."""
    raw = measurement.read_bytes()
    assert b"PTO.MFDB CONTAINER" in raw
    # First object, but not the first byte: the container reserves space for its
    # two indexes ahead of it, so this asserts "near the front", not "at zero".
    assert raw.index(b"PTO.MFDB CONTAINER") < 64 * 1024


# -- what the measurement is, not only what was done to it ---------------------------


def test_the_measurement_can_describe_itself(tmp_path: Path, measurement: Path):
    """Provenance says a burst table came from a photon stream. It does not say
    which sample, which dyes, which instrument -- and a file that cannot answer
    those is a record of a computation, not of a measurement."""
    with Measurement.open(measurement, writable=True) as m:
        m.put_metadata(
            {
                "flr_sample": {"sample_description": "Cy3B-Cy5 dsDNA", "num_of_probes": 2},
                "flr_instrument": {"details": "MicroTime 200"},
            }
        )

    with Measurement.open(measurement) as m:
        block = m.metadata()
        assert block.startswith("data_")
        assert "_flr_sample.sample_description   'Cy3B-Cy5 dsDNA'" in block
        assert "_flr_instrument.details" in block
        obj = [o for o in m.artifacts() if o.kind == "sample_metadata"][0]
        assert obj.encoding == "cif"


def test_metadata_the_dictionary_does_not_declare_is_refused(measurement: Path):
    """The point of mmCIF here is that the words mean something. Prose in a
    field that looks structured is worse than no field."""
    with Measurement.open(measurement, writable=True) as m:
        with pytest.raises(PtoMfdbError, match="not a declared item"):
            m.put_metadata({"flr_sample": {"invented_item": 1}})
        with pytest.raises(PtoMfdbError, match="not a category"):
            m.put_metadata({"not_a_category": {"x": 1}})


def test_a_measurement_with_nothing_to_say_says_nothing(measurement: Path):
    """An empty block would claim the measurement was described when it was not."""
    with Measurement.open(measurement) as m:
        assert m.metadata() == ""
        assert not [o for o in m.artifacts() if o.kind == "sample_metadata"]
