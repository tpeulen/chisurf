"""The metadata editors' PDBx key completions come from the bundled dictionaries.

The facade used to parse a dictionary file of its own under
``chisurf/core/fio/mmcif/db/data/``. That directory does not exist, and a missing
file was answered with an empty result, so every metadata completer in the GUI
silently offered no keys at all. These tests pin that the facade reads the one
dictionary authority (``mmfdb.schema.pdbx_metadata.MmcifDictionary``) and that
its answer is non-empty.

They also pin that the deprecated ``chisurf.core.fio.mmcif.db`` package — six
dead modules re-exporting ``mmfdb`` around this one live facade — stays deleted
(INC-14).
"""

import importlib

import pytest
from mmfdb.schema.pdbx_metadata import MmcifDictionary

from chisurf.core.fio.mmcif import pdbx_metadata


@pytest.fixture(autouse=True)
def _clear_facade_cache():
    """Parse afresh in every test so the module caches cannot mask a regression."""
    pdbx_metadata._cache_keys = None
    pdbx_metadata._cache_descriptions = None
    yield
    pdbx_metadata._cache_keys = None
    pdbx_metadata._cache_descriptions = None


def test_metadata_keys_are_not_empty():
    """A completer seeded from this list must have something to complete."""
    keys = pdbx_metadata.get_pdbx_metadata_keys()
    assert len(keys) > 5000
    assert all(key.startswith("_") and "." in key for key in keys)


def test_metadata_keys_match_the_dictionary_authority():
    """The facade adds nothing of its own to the bundled dictionaries."""
    assert pdbx_metadata.get_pdbx_metadata_keys() == MmcifDictionary.load_bundled().item_names()


def test_flrcif_and_pdbx_keys_are_both_offered():
    """Both the PDBx core and the fluorescence extension reach the editors."""
    keys = set(pdbx_metadata.get_pdbx_metadata_keys())
    assert "_entity.type" in keys
    assert "_flr_sample.entity_assembly_id" in keys


def test_descriptions_are_a_subset_of_the_keys():
    """Every described key is offered; keys without a description are still offered."""
    keys = pdbx_metadata.get_pdbx_metadata_keys()
    descriptions = pdbx_metadata.get_pdbx_metadata_descriptions()
    assert descriptions
    assert set(descriptions) < set(keys)
    assert all(text.strip() for text in descriptions.values())


def test_the_caller_cannot_corrupt_the_cache():
    """Both getters hand out copies, not the module-level caches."""
    pdbx_metadata.get_pdbx_metadata_keys().clear()
    pdbx_metadata.get_pdbx_metadata_descriptions().clear()
    assert pdbx_metadata.get_pdbx_metadata_keys()
    assert pdbx_metadata.get_pdbx_metadata_descriptions()


def test_an_empty_dictionary_is_reported_not_swallowed(monkeypatch, caplog):
    """A dictionary that parses to nothing warns instead of degrading silently."""
    monkeypatch.setattr(MmcifDictionary, "load_bundled", classmethod(lambda cls: MmcifDictionary()))
    with caplog.at_level("WARNING", logger=pdbx_metadata.logger.name):
        assert pdbx_metadata.get_pdbx_metadata_keys() == []
    assert any("no metadata keys" in record.message for record in caplog.records)


@pytest.mark.parametrize(
    "module",
    [
        "chisurf.core.fio.mmcif.db",
        "chisurf.core.fio.mmcif.db.schema",
        "chisurf.core.fio.mmcif.db.repository",
        "chisurf.core.fio.mmcif.db.models",
        "chisurf.core.fio.mmcif.db.database_resolver",
        "chisurf.core.fio.mmcif.db.zmq_client",
        "chisurf.core.fio.mmcif.db.zmq_server",
    ],
)
def test_the_deprecated_db_package_stays_deleted(module):
    """Reaching for a shim must fail loudly instead of resurrecting the package."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module)


def test_the_facade_lives_beside_the_mmcif_package_not_under_db():
    """Importing the facade must not go through a deprecated package init."""
    assert pdbx_metadata.__name__ == "chisurf.core.fio.mmcif.pdbx_metadata"
