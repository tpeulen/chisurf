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

ROOT = Path(__file__).resolve().parents[4]
SPC = (
    ROOT
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)

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
