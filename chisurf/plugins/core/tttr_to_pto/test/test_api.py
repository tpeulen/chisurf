"""Tests for ``tttr_to_pto.api``.

Wires up a written, tested, Qt-free conversion
(``pto.Measurement.create``/``disassemble``) that nothing in the tree called
before (see the drop-guard pattern in
:mod:`chisurf.gui.widgets.dropguard`). These tests pin the contract the drop
guard and the bare drop tool both rely on: pack keeps the source untouched,
delete only happens after verification, and unpack recovers byte-identical
bytes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.plugins.core.tttr_to_pto import api

DATA = (
    Path(__file__).resolve().parents[4]
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
)
SPC = DATA / "m000.spc"
SPC2 = DATA / "m001.spc"

pytestmark = pytest.mark.skipif(not SPC.exists(), reason="no BH SPC test data")


def test_convert_keeps_original_by_default(tmp_path):
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    target = api.convert(source)

    assert target == source.with_suffix(".pto")
    assert target.exists()
    assert source.exists()  # never touched


def test_convert_deletes_original_only_after_verification(tmp_path):
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    target = api.convert(source, keep_original=False)

    assert target.exists()
    assert not source.exists()


def test_convert_keeps_source_when_verification_would_fail(tmp_path, monkeypatch):
    """A corrupted write must never cost the source.

    Simulates a container that fails its own checksum check by making
    ``Measurement.verify`` report a problem; the source must survive.
    """
    from chisurf.core.fio.pto import Measurement, PtoMfdbError

    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())

    monkeypatch.setattr(Measurement, "verify", lambda self: ["fake corruption"])

    with pytest.raises(PtoMfdbError):
        api.convert(source, keep_original=False)

    assert source.exists()


def test_extract_recovers_the_original_bytes(tmp_path):
    source = tmp_path / SPC.name
    original_bytes = SPC.read_bytes()
    source.write_bytes(original_bytes)

    container = api.convert(source, keep_original=True)
    source.unlink()  # only the container is left

    # disassemble() also writes the container's self-describing README object
    # (see chisurf.core.fio.pto.Measurement) alongside the instrument file.
    recovered = api.extract(container)
    [instrument_file] = [p for p in recovered if p.name == source.name]

    assert instrument_file.exists()
    assert instrument_file.read_bytes() == original_bytes


@pytest.mark.skipif(not SPC2.exists(), reason="no second BH SPC test file")
def test_convert_embeds_multiple_files_in_one_container(tmp_path):
    """A measurement split across several vendor files is one .pto, not several."""
    a = tmp_path / SPC.name
    a.write_bytes(SPC.read_bytes())
    b = tmp_path / SPC2.name
    b.write_bytes(SPC2.read_bytes())

    # Passed out of lexical order -- convert() must sort by name regardless.
    target = api.convert([b, a], keep_original=True)

    assert target == tmp_path / (SPC.stem + ".pto")  # named after the lexically-first file
    assert a.exists() and b.exists()

    recovered = api.extract(target)
    recovered_names = {p.name for p in recovered}
    assert {a.name, b.name} <= recovered_names


def test_convert_picks_up_the_spc_set_sidecar_automatically(tmp_path):
    """A .set beside a .spc is embedded without being named explicitly."""
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    sidecar = source.with_suffix(".set")
    sidecar.write_bytes(b"fake bh settings header")

    target = api.convert(source, keep_original=True)

    recovered = api.extract(target)
    assert any(p.name == sidecar.name for p in recovered)
