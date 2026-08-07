"""The ``tttr_to_pto`` guard's persisted tri-state answers a drop with no dialog.

Dropping a vendor path through ``apply_drop_guards`` with
``data_loading.drop_guards.tttr_to_pto`` pre-set to each of the four
tri-state values must produce the right outcome without a dialog ever being
shown. The fourth value, ``"ask"``, is exercised under the test process's own
headless Qt platform -- no monkeypatching of interactivity needed -- which is
exactly the unattended-run path the guard promises never to block; its
default answer is "convert, keep original", which never deletes anything and
is therefore safe to take unattended too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.core.fio import staging
from chisurf.gui.widgets.dropguard import apply_drop_guards

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


@pytest.fixture(autouse=True)
def _no_real_settings_writes(monkeypatch):
    """Never let a test touch the user's real settings_chisurf.yaml."""
    monkeypatch.setattr(
        "chisurf.plugins.core.tttr_to_pto.gui.guard.set_data_loading_settings",
        lambda *a, **k: True,
    )


def _pre_set(monkeypatch, value: str) -> None:
    cfg = dict(staging.DEFAULTS)
    cfg["drop_guards"] = {"tttr_to_pto": value}
    monkeypatch.setattr(staging, "_settings", lambda: cfg)


def _make_source(tmp_path) -> Path:
    source = tmp_path / SPC.name
    source.write_bytes(SPC.read_bytes())
    return source


def test_always_keep_converts_and_keeps_the_source(tmp_path, monkeypatch):
    _pre_set(monkeypatch, "always_keep")
    source = _make_source(tmp_path)

    result = apply_drop_guards(None, [str(source)], ["tttr_to_pto"])

    assert result == [str(source.with_suffix(".pto"))]
    assert source.exists()


def test_always_delete_converts_and_removes_the_source(tmp_path, monkeypatch):
    _pre_set(monkeypatch, "always_delete")
    source = _make_source(tmp_path)

    result = apply_drop_guards(None, [str(source)], ["tttr_to_pto"])

    assert result == [str(source.with_suffix(".pto"))]
    assert not source.exists()


def test_never_uses_the_file_as_dropped(tmp_path, monkeypatch):
    _pre_set(monkeypatch, "never")
    source = _make_source(tmp_path)

    result = apply_drop_guards(None, [str(source)], ["tttr_to_pto"])

    assert result == [str(source)]
    assert not source.with_suffix(".pto").exists()


def test_ask_headless_defaults_to_convert_keep_original(tmp_path, monkeypatch):
    """The dialog's default answer never deletes anything, so it is headless-safe."""
    _pre_set(monkeypatch, "ask")
    source = _make_source(tmp_path)

    result = apply_drop_guards(None, [str(source)], ["tttr_to_pto"])

    assert result == [str(source.with_suffix(".pto"))]
    assert source.exists()  # "keep" never deletes


def test_a_container_that_is_already_a_pto_is_left_alone(tmp_path, monkeypatch):
    """applies() must say no to a file that is already a measurement."""
    from chisurf.plugins.core.tttr_to_pto import api

    _pre_set(monkeypatch, "always_keep")
    source = _make_source(tmp_path)
    container = api.convert(source, keep_original=True)

    result = apply_drop_guards(None, [str(container)], ["tttr_to_pto"])

    assert result == [str(container)]


@pytest.mark.skipif(not SPC2.exists(), reason="no second BH SPC test file")
def test_multiple_dropped_files_are_embedded_in_one_pto(tmp_path, monkeypatch):
    """A batch dropped together is one measurement, not one container per file."""
    _pre_set(monkeypatch, "always_keep")
    a = tmp_path / SPC.name
    a.write_bytes(SPC.read_bytes())
    b = tmp_path / SPC2.name
    b.write_bytes(SPC2.read_bytes())

    result = apply_drop_guards(None, [str(b), str(a)], ["tttr_to_pto"])

    assert result == [str(tmp_path / (SPC.stem + ".pto"))]  # lexically-first name
    assert a.exists() and b.exists()


def test_a_dropped_set_sidecar_is_never_converted_on_its_own(tmp_path, monkeypatch):
    """A .set is undecodable alone and must never be treated as its own file."""
    from chisurf.gui.widgets.dropguard import get_drop_guard

    _pre_set(monkeypatch, "always_keep")
    lone_set = tmp_path / "orphan.set"
    lone_set.write_bytes(b"not a photon stream")

    guard = get_drop_guard("tttr_to_pto")
    assert guard.applies(str(lone_set)) is False
