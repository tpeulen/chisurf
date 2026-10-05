"""The dictionary facade supplies suggestions without owning stored metadata."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("failure", ["absent", "import_error", "assertion"])
def test_cold_facade_import_is_independent_of_mmfdb(failure, tmp_path):
    """Only a named missing optional package yields an empty cached catalog."""
    source = r"""
import importlib.abc
import sys

failure = sys.argv[1]
attempts = []
class NoMMFDB(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            attempts.append(fullname)
            if failure == "absent":
                raise ModuleNotFoundError("Optional package absent", name=fullname)
            if failure == "import_error":
                raise ImportError("Deliberate import rejection")
            raise AssertionError("Deliberate assertion rejection")
sys.meta_path.insert(0, NoMMFDB())
from chisurf.core.fio.mmcif import pdbx_metadata as facade
assert attempts == [], attempts
if failure == "absent":
    for _ in range(3):
        keys = facade.get_pdbx_metadata_keys()
        descriptions = facade.get_pdbx_metadata_descriptions()
        assert keys == [] and descriptions == {}
        keys.append("_caller.key")
        descriptions["_caller.key"] = "caller mutation"
    assert attempts == ["mmfdb"], attempts
else:
    expected = ImportError if failure == "import_error" else AssertionError
    for getter in (facade.get_pdbx_metadata_keys, facade.get_pdbx_metadata_descriptions):
        try:
            getter()
        except expected as exc:
            assert "Deliberate" in str(exc)
        else:
            raise AssertionError("Non-absence error was swallowed")
assert not any(n == "mmfdb" or n.startswith("mmfdb.") for n in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", source, failure],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(
            os.environ,
            CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
            MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
        ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_installed_catalog_keeps_exact_authority_and_one_load(monkeypatch):
    """Repeated calls return copies of the single installed dictionary's answers."""
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    from chisurf.core.fio.mmcif import pdbx_metadata

    facade = importlib.reload(pdbx_metadata)
    dictionary = MmcifDictionary.load_bundled()
    calls = []

    def load(cls):
        """Count catalog loads without changing the real authority's answers."""
        calls.append(cls)
        return dictionary

    monkeypatch.setattr(MmcifDictionary, "load_bundled", classmethod(load))
    try:
        for _ in range(3):
            keys = facade.get_pdbx_metadata_keys()
            descriptions = facade.get_pdbx_metadata_descriptions()
            assert keys == dictionary.item_names()
            assert descriptions == dictionary.item_descriptions()
            assert "_flr_sample.entity_assembly_id" in keys
            assert "entity" in descriptions["_atom_site.label_entity_id"].lower()
            keys.clear()
            descriptions.clear()
        assert calls == [MmcifDictionary]
    finally:
        importlib.reload(facade)


@pytest.mark.parametrize(
    "error",
    [
        ValueError("invalid dictionary configuration"),
        ImportError("broken installed dictionary"),
        AssertionError("invalid dictionary invariant"),
        ModuleNotFoundError("missing dictionary dependency", name="dictionary_dependency"),
        ModuleNotFoundError("missing schema module", name="mmfdb.schema.pdbx_metadata"),
        ModuleNotFoundError("package missing during parsing", name="mmfdb"),
    ],
)
def test_installed_dictionary_failures_are_not_absence(monkeypatch, error):
    """Dictionary or transitive dependency failures remain observable and uncached."""
    from mmfdb.schema.pdbx_metadata import MmcifDictionary

    from chisurf.core.fio.mmcif import pdbx_metadata

    facade = importlib.reload(pdbx_metadata)

    def fail(cls):
        """Raise the exact installed catalog failure under test."""
        raise error

    monkeypatch.setattr(MmcifDictionary, "load_bundled", classmethod(fail))
    try:
        for getter in (facade.get_pdbx_metadata_keys, facade.get_pdbx_metadata_descriptions):
            with pytest.raises(type(error)) as caught:
                getter()
            assert caught.value is error
            assert facade._cache_keys is None
            assert facade._cache_descriptions is None
    finally:
        importlib.reload(facade)
