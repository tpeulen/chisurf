"""A dropped table: linked as a table row, unless the reader chosen in Read data reads it.

A file of named columns (a burst table, a result table) enters the workspace as a ``table`` row. The
PDA readers read ``.bur`` burst tables themselves: with PDA chosen in Read data, a dropped ``.bur``
goes to the PDA reader instead of becoming a table row.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.core.fio.classify import classify
from test.native_emtk.test_emtk_shell_fits import (  # noqa: F401  (the fixture and the helpers)
    _idle,
    _settle,
    shell,
)

REPO = Path(__file__).resolve().parents[2]
BUR = (
    REPO
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15/bi4_bur/m000.bur"
)


def _rows(shell, kind):  # noqa: F811
    return [r for r in shell.data.datasets.datasets if r.get("kind") == kind]


def test_a_generic_table_is_linked_as_a_table_row(shell, tmp_path):  # noqa: F811
    table = tmp_path / "results.csv"
    table.write_text("a,b,c,d,e,f\n" + "\n".join(f"{i},1,2,3,4,5" for i in range(20)) + "\n")
    assert classify(table) == "table"
    assert shell.on_files_dropped([str(table)])
    driver = Driver(shell, (1300, 900))
    _settle(driver, lambda: _idle(shell) and _rows(shell, "table"), "the table row")
    assert [Path(r["name"]).stem for r in _rows(shell, "table")] == ["results"]


@pytest.mark.skipif(not BUR.is_file(), reason="burst-table fixture missing")
def test_with_pda_chosen_a_bur_goes_to_the_pda_reader(shell, tmp_path, monkeypatch):  # noqa: F811
    bur = tmp_path / "m000.bur"
    shutil.copy(BUR, bur)
    assert classify(bur) == "table", "the precondition: a .bur alone is a table"
    data = shell.data
    data.read.experiment = "PDA"
    data.read.experiment_changed("PDA")
    data.read.setup = "PTU/HT3/SPC"
    loaded = []
    monkeypatch.setattr(data, "load", lambda reader, path: loaded.append((reader, path)) or True)
    tables_before = len(_rows(shell, "table"))
    assert shell.on_files_dropped([str(bur)])
    assert [(getattr(r, "name", ""), Path(p).name) for r, p in loaded] == [
        ("PTU/HT3/SPC", "m000.bur")
    ]
    _idle(shell)
    assert len(_rows(shell, "table")) == tables_before
