"""``data_source`` AutoForm section — one-file input, drops, and drop guards.

Covers the ``guards`` option (see ``chisurf.gui.widgets.dropguard``): a drop
guard runs only on an actual drag-and-drop, never on a browsed or
database-picked file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chisurf.gui.autoform.sections.data_source_section import DataSourceSection

_SPC = (
    Path(__file__).resolve().parents[2]
    / "chisurf"
    / "plugins"
    / "burst"
    / "burst_selection"
    / "tests"
    / "data"
    / "bh_spc132_sm_dna"
    / "m000.spc"
)


class _Model:
    def __init__(self):
        self.filename = ""


class _FakeUrl:
    def __init__(self, path: str):
        self._path = path

    def isLocalFile(self) -> bool:
        return True

    def toLocalFile(self) -> str:
        return self._path


class _FakeMimeData:
    def __init__(self, paths):
        self._urls = [_FakeUrl(p) for p in paths]

    def urls(self):
        return self._urls


class _FakeDropEvent:
    def __init__(self, paths):
        self._mime = _FakeMimeData(paths)
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True


def test_drop_with_no_guards_commits_the_path_unchanged(qapp, tmp_path):
    sample = tmp_path / "m000.ptu"
    sample.write_bytes(b"not a real container")
    model = _Model()
    section = DataSourceSection(model=model, target="filename")

    section.dropEvent(_FakeDropEvent([str(sample)]))

    assert model.filename == str(sample)
    assert not sample.with_suffix(".pto").exists()


@pytest.mark.skipif(not _SPC.exists(), reason="no BH SPC test data")
def test_drop_with_guards_converts_before_commit(qapp, tmp_path, monkeypatch):
    from chisurf.core.fio import staging

    cfg = dict(staging.DEFAULTS)
    cfg["drop_guards"] = {"tttr_to_pto": "always_keep"}
    monkeypatch.setattr(staging, "_settings", lambda: cfg)
    monkeypatch.setattr(
        "chisurf.plugins.core.tttr_to_pto.gui.guard.set_data_loading_settings",
        lambda *a, **k: True,
    )

    sample = tmp_path / _SPC.name
    sample.write_bytes(_SPC.read_bytes())
    model = _Model()
    section = DataSourceSection(model=model, target="filename", guards=["tttr_to_pto"])

    section.dropEvent(_FakeDropEvent([str(sample)]))

    assert model.filename == str(sample.with_suffix(".pto"))
    assert sample.exists()  # always_keep
