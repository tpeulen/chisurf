"""Every declared analysis feature is anchored in the central vocabulary.

The general rule (owner, 2026-09-03): analysis declaration files follow
the mmfdb/flrCIF scheme. A feature either uses a term the dictionaries
define, or the term is *created in mmfdb's extension dictionary first*
(`mmfdb_flr_ext.dic`) -- freedom of definition exists, but it is exercised
centrally, so every schema drift happens at one spot. This test is the
enforcement: a declaration entry without a ``term``, or with a term the
bundled dictionaries do not define, fails here -- the fix is a dictionary
item, never a local invention.
"""

import pathlib

import pytest
import yaml

yaml_files = [
    pathlib.Path("chisurf/core/fio/fluorescence/burst_features.yaml"),
    pathlib.Path("chisurf/plugins/microscopy/img_pixel_mle/core/result_columns.yaml"),
    pathlib.Path("chisurf/plugins/microscopy/region_mle/core/result_columns.yaml"),
    pathlib.Path("chisurf/plugins/burst/accurate_fret/calibration_columns.yaml"),
]


def _entries(path):
    """Yield every column entry of one declaration file, any layout."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if "groups" in data:  # burst_features.yaml
        for group in data["groups"]:
            yield from group["columns"]
    else:  # per-model / per-list schemas
        for value in data.values():
            if isinstance(value, dict) and "columns" in value:
                yield from value["columns"]
            elif isinstance(value, list):
                yield from value


@pytest.fixture(scope="module")
def dictionary():
    mmfdb = pytest.importorskip(
        "mmfdb.schema.pdbx_metadata", reason="mmfdb (modules/mmfdb/src) not on the path"
    )
    return mmfdb.MmcifDictionary.load_bundled()


@pytest.mark.parametrize(
    "path", yaml_files, ids=[p.name + ":" + p.parent.parent.name for p in yaml_files]
)
def test_every_entry_carries_a_term(path):
    missing = [e["column"] for e in _entries(path) if "term" not in e]
    assert not missing, (
        f"{path}: entries without a `term` -- the vocabulary is central "
        f"(mmfdb_flr_ext.dic); define the item there and reference it: "
        f"{missing}"
    )


@pytest.mark.parametrize(
    "path", yaml_files, ids=[p.name + ":" + p.parent.parent.name for p in yaml_files]
)
def test_every_term_resolves_in_the_dictionaries(path, dictionary):
    unresolved = sorted(
        {
            e["term"]
            for e in _entries(path)
            if "term" in e and dictionary.get_item(e["term"]) is None
        }
    )
    assert not unresolved, (
        f"{path}: terms the mmfdb/flrCIF dictionaries do not define -- "
        f"create them in mmfdb_flr_ext.dic (the central drift spot), do "
        f"not invent them here: {unresolved}"
    )
