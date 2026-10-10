"""The generated flrCIF vocabulary page matches the mmfdb dictionaries."""

import importlib.util
import pathlib

import pytest

pytest.importorskip("mmfdb.schema.pdbx_metadata", reason="mmfdb not on the path")

_SCRIPT = pathlib.Path("build_tools/docs/generate_flrcif_vocabulary.py")


def test_page_is_current():
    spec = importlib.util.spec_from_file_location("gen_flrcif_vocabulary", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, (
        "docs/concepts/flrcif_vocabulary.md is stale: "
        "python build_tools/docs/generate_flrcif_vocabulary.py"
    )
