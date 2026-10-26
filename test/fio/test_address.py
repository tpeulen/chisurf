"""Container addresses ``<path>[/<member>...]`` follow the shared conformance table.

The table is a byte-identical copy of ptolib's ``tests/data/address_cases.json`` (ptolib
commit 160a036; change it there first): ptolib, tttrlib and
ChiSurf each run it, so the three spell and resolve an address the same way.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from chisurf.core.fio.address import (
    container_of,
    join_address,
    split_address,
    split_address_lexical,
)

TABLE = json.loads((pathlib.Path(__file__).parents[1] / "data" / "address_cases.json").read_text())
CASES = TABLE["cases"]


def _build(root: pathlib.Path, case: dict) -> None:
    for d in case.get("dirs", []):
        (root / d).mkdir(parents=True, exist_ok=True)
    for f in case.get("files", []):
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_bytes(b"x")


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_every_case_of_the_shared_table(case, tmp_path, monkeypatch):
    """Relative addresses, resolved from the case's root, give the table's split."""
    _build(tmp_path, case)
    monkeypatch.chdir(tmp_path)
    container, member = split_address(case["address"])
    expected = case["container"]
    assert (None if container is None else container.as_posix()) == expected
    assert member == case["member"]


def test_an_absolute_address_keeps_its_root(tmp_path):
    (tmp_path / "m000.pto").write_bytes(b"x")
    container, member = split_address(tmp_path / "m000.pto" / "burstwise" / "bursts")
    assert container == tmp_path / "m000.pto"
    assert member == "burstwise/bursts"
    assert container_of(f"{tmp_path}/m000.pto/burstwise") == tmp_path / "m000.pto"
    assert container_of(tmp_path / "plain.ptu") == tmp_path / "plain.ptu"


def test_a_container_still_to_be_written_splits_lexically(tmp_path):
    """A writer names its output before the file exists; a directory is never the container."""
    assert split_address_lexical(tmp_path / "new.pto" / "run one") == (
        tmp_path / "new.pto",
        "run one",
    )
    (tmp_path / "dir.pto").mkdir()
    assert split_address_lexical(tmp_path / "dir.pto" / "x.pto" / "r") == (
        tmp_path / "dir.pto" / "x.pto",
        "r",
    )
    assert split_address_lexical(tmp_path / "plain.dat") == (None, "")


def test_join_is_the_inverse_of_split(tmp_path):
    (tmp_path / "proj.cs.pto").write_bytes(b"x")
    address = join_address(tmp_path / "proj.cs.pto", "m000.pto", "burstwise/", "bursts")
    assert address == f"{tmp_path}/proj.cs.pto/m000.pto/burstwise/bursts"
    assert split_address(address) == (tmp_path / "proj.cs.pto", "m000.pto/burstwise/bursts")
    assert join_address("run.pto") == "run.pto"
