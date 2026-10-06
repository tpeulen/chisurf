"""The in-tree .ipynb reader/writer against nbformat (the oracle)."""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.core.code_editor import ipynb

nbformat = pytest.importorskip("nbformat")

SAMPLE = {
    "nbformat": 4,
    "nbformat_minor": 5,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "orig_nbformat": 4,
        "trusted": True,
    },
    "cells": [
        {"id": "a1b2c3d4", "cell_type": "markdown", "metadata": {}, "source": ["# Title\n", "Ünïcode text"]},
        {
            "id": "e5f6a7b8",
            "cell_type": "code",
            "metadata": {"trusted": True, "tags": ["x"]},
            "execution_count": 3,
            "source": ["import numpy as np\n", "np.arange(3)"],
            "outputs": [
                {"output_type": "stream", "name": "stdout", "text": ["line 1\n", "line 2\n"]},
                {
                    "output_type": "execute_result",
                    "execution_count": 3,
                    "metadata": {},
                    "data": {
                        "text/plain": ["array([0, 1,\n", "       2])"],
                        "application/json": {"a": [1, 2]},
                        "application/vnd.custom+json": {"k": "v"},
                    },
                },
                {"output_type": "display_data", "metadata": {}, "data": {"image/png": "iVBORw0KGgo=\n"}},
            ],
        },
        {"id": "c9d0e1f2", "cell_type": "raw", "metadata": {}, "source": "raw text"},
    ],
}


def test_reads_matches_nbformat():
    text = json.dumps(SAMPLE)
    ours = ipynb.reads(text, as_version=4)
    theirs = nbformat.reads(text, as_version=4)
    assert json.loads(json.dumps(ours)) == json.loads(json.dumps(theirs))
    assert ours.cells[1].outputs[0].text == "line 1\nline 2\n"
    assert ours.metadata.kernelspec.name == "python3"


@pytest.mark.parametrize("sort_keys", [True, False])
def test_writes_is_byte_for_byte_nbformat(sort_keys):
    text = json.dumps(SAMPLE)
    ours = ipynb.writes(ipynb.reads(text), sort_keys=sort_keys, indent=1)
    theirs = nbformat.writes(nbformat.reads(text, as_version=4), sort_keys=sort_keys, indent=1)
    assert ours == theirs


def test_round_trip_through_a_file(tmp_path):
    path = tmp_path / "n.ipynb"
    path.write_text(ipynb.writes(ipynb.reads(json.dumps(SAMPLE))), encoding="utf-8")
    assert nbformat.read(str(path), as_version=4).cells[0].source == "# Title\nÜnïcode text"
    assert ipynb.read(path).cells[2].source == "raw text"


def test_new_cells_have_nbformat_fields():
    nb = ipynb.v4.new_notebook()
    nb.cells = [ipynb.v4.new_code_cell(source="x = 1"), ipynb.v4.new_markdown_cell(source="*m*")]
    nb.metadata.setdefault("language_info", {"name": "python"})
    reference = nbformat.v4.new_code_cell(source="x = 1")
    assert set(nb.cells[0]) == set(reference)
    assert len(nb.cells[0].id) == len(reference.id) == 8
    assert (nb.nbformat, nb.nbformat_minor) == (4, 5)
    nbformat.validate(nbformat.from_dict(json.loads(ipynb.writes(nb))))


def test_non_notebooks_are_rejected():
    for text in ("not json", json.dumps({"nbformat": 3, "worksheets": []}), json.dumps([1, 2])):
        with pytest.raises(ValueError):
            ipynb.reads(text)


def test_missing_and_duplicate_ids_are_repaired_like_nbformat():
    nb = json.loads(json.dumps(SAMPLE))
    del nb["cells"][0]["id"]
    nb["cells"][2]["id"] = nb["cells"][1]["id"]
    ours = ipynb.reads(json.dumps(nb))
    ids = [c.id for c in ours.cells]
    assert all(isinstance(i, str) and len(i) == 8 for i in ids) and len(set(ids)) == 3
    nbformat.validate(nbformat.from_dict(json.loads(ipynb.writes(ours))))
