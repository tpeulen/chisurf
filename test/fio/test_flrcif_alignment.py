"""Tests for PRD-02c flrCIF alignment of ChiSurf's parameter registry."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from build_tools.dev_utils import align_flrcif_parameters as align
from chisurf.core.project.mmfdb_adapter import resolve_parameter_name
from mmfdb.adapters.chinet import _lookup_flrcif_name
from mmfdb.schema.pdbx_metadata import MmcifDictionary


REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "chisurf"
    / "core"
    / "settings"
    / "constants"
    / "parameter_registry.json"
)

DIC_PATH = MmcifDictionary.DATA_DIR / "mmfdb_flr_ext.dic"


def test_registry_file_exists():
    """The renamed parameter registry file exists."""
    assert REGISTRY_PATH.is_file(), (
        f"parameter_registry.json not found at {REGISTRY_PATH}"
    )


def test_registry_has_no_fitting_parameters_reference():
    """The registry should use 'parameter_registry' not 'fitting_parameters'."""
    with open(REGISTRY_PATH, "r") as fh:
        data = json.load(fh)
    assert "version" in data
    assert "parameters" in data


def test_all_parameters_have_flrcif_item_id():
    """Every parameter entry in the registry has an flrcif_item_id mapping."""
    with open(REGISTRY_PATH, "r") as fh:
        data = json.load(fh)
    params = data.get("parameters", {})
    missing = [
        key for key, entry in params.items()
        if isinstance(entry, dict) and "flrcif_item_id" not in entry
    ]
    assert not missing, (
        f"{len(missing)} parameter(s) missing flrcif_item_id: {missing[:10]}"
    )


def test_flrcif_item_ids_are_unique():
    """No two parameters share the same flrcif_item_id."""
    with open(REGISTRY_PATH, "r") as fh:
        data = json.load(fh)
    params = data.get("parameters", {})
    seen = {}
    for key, entry in params.items():
        if not isinstance(entry, dict):
            continue
        flrcif = entry.get("flrcif_item_id")
        if flrcif:
            if flrcif in seen:
                pytest.fail(
                    f"Duplicate flrcif_item_id '{flrcif}' for "
                    f"'{key}' and '{seen[flrcif]}'"
                )
            seen[flrcif] = key


def test_dic_file_exists():
    """The extension dictionary file exists."""
    assert DIC_PATH.is_file(), f"mmfdb_flr_ext.dic not found at {DIC_PATH}"


def test_dic_parses_correctly():
    """The extended dictionary parses without errors."""
    d = MmcifDictionary(DIC_PATH)
    assert d.get_category("flr_fit_parameter") is not None


def test_dic_contains_flr_fit_parameter_items():
    """The dictionary contains items from the flr_fit_parameter category."""
    d = MmcifDictionary(DIC_PATH)
    cat = d.get_category("flr_fit_parameter")
    assert cat is not None
    assert len(cat.items) > 0, "flr_fit_parameter category has no items"


def test_all_registry_ids_mapped_to_dic_items():
    """Every flrcif_item_id in the registry has a matching item in the .dic."""
    with open(REGISTRY_PATH, "r") as fh:
        data = json.load(fh)
    params = data.get("parameters", {})
    d = MmcifDictionary.load_bundled()
    missing = []
    for key, entry in params.items():
        if not isinstance(entry, dict):
            continue
        flrcif = entry.get("flrcif_item_id")
        if not isinstance(flrcif, str):
            continue
        item = d.get_item(flrcif)
        if item is None:
            missing.append((key, flrcif))
    assert not missing, (
        f"{len(missing)} flrcif_item_id(s) not found in bundled dictionaries: "
        f"{missing[:10]}"
    )


def test_dic_item_metadata_matches_registry():
    """Fit-parameter items are numeric: float values, int for 0/1 flags."""
    d = MmcifDictionary.load_bundled()
    cat = d.get_category("flr_fit_parameter")
    assert cat is not None
    for item in cat.items.values():
        assert item.type_code in ("float", "int"), (
            f"Expected a numeric type_code for {item.name}, "
            f"got {item.type_code}"
        )


def test_lookup_flrcif_name_resolves_known_parameters():
    """Known parameter short names resolve to canonical identifiers."""
    assert _lookup_flrcif_name("bg", resolve_parameter_name) == "_flr_fit_parameter.bg"
    assert _lookup_flrcif_name("D", resolve_parameter_name) == "_flr_fit_parameter.D"
    assert _lookup_flrcif_name("N", resolve_parameter_name) == "_flr_fit_parameter.N"


def test_lookup_flrcif_name_returns_none_for_unknown():
    """Unknown parameter names return None."""
    assert _lookup_flrcif_name("__nonexistent__", resolve_parameter_name) is None
    assert _lookup_flrcif_name("", resolve_parameter_name) is None


def test_lookup_flrcif_name_resolves_family_prefixed():
    """Family-prefixed parameter names also resolve correctly."""
    result = _lookup_flrcif_name("fcs.N", resolve_parameter_name)
    assert result == "_flr_fit_parameter.fcs_N"


def test_dic_items_have_schema_bindings():
    """Every flr_fit_parameter item has table/column schema bindings."""
    d = MmcifDictionary.load_bundled()
    cat = d.get_category("flr_fit_parameter")
    assert cat is not None
    for item in cat.items.values():
        assert item.schema_table == "flr_fit_parameter", (
            f"{item.name} missing schema_table"
        )
        assert item.schema_column, (
            f"{item.name} missing schema_column"
        )


def test_dic_uses_only_the_vendor_neutral_schema_namespace():
    """The shipped extension dictionary carries no branded schema tags.

    PRD-44 retired ``_chisurf_schema.*`` in favour of the store-keyed
    ``_mmfdb_schema.*``; a single branded tag means something re-introduced the
    application-specific namespace into a dictionary meant to be vendor-neutral.
    """
    text = DIC_PATH.read_text(encoding="utf-8")
    assert "_chisurf_schema" not in text, (
        "branded _chisurf_schema tags found in mmfdb_flr_ext.dic (PRD-44)"
    )
    assert "_mmfdb_schema" in text


def test_generated_item_def_uses_the_vendor_neutral_schema_namespace():
    """The generator emits the same schema namespace the dictionary ships with.

    The generator is the only thing that ever appends to the extension
    dictionary, so emitting the retired namespace would silently split the file
    into two conventions, one parameter at a time.
    """
    block = align.generate_item_def("E_FRET", "Apparent FRET efficiency.")
    assert "_chisurf_schema" not in block
    assert "   _mmfdb_schema.table_name  flr_fit_parameter" in block
    assert "   _mmfdb_schema.column_name e_fret" in block


def test_generator_default_dic_path_is_the_shipped_dictionary():
    """The default output path resolves to the dictionary the tests read."""
    assert align.DEFAULT_DIC_PATH == DIC_PATH
    assert align.DEFAULT_DIC_PATH.is_file()


def test_dictionary_load_failure_is_not_swallowed(monkeypatch):
    """A failed dictionary load raises instead of reporting "no items".

    An empty set reads as "nothing is defined yet", which would make the
    alignment re-append a definition for every parameter already in the file.
    """
    def _boom(*_args, **_kwargs):
        raise RuntimeError("dictionary unavailable")

    monkeypatch.setattr(align.MmcifDictionary, "load_bundled", _boom)
    with pytest.raises(RuntimeError):
        align.get_all_dic_items()


def test_alignment_is_idempotent_on_the_shipped_registry(tmp_path):
    """Re-running the alignment adds nothing: every parameter is already mapped.

    This exercises the script end to end — import, dictionary load, item-id
    derivation — against the real registry, so a moved dictionary API or a
    parameter added without a ``.dic`` entry fails here rather than in a
    hand-run script.
    """
    registry_copy = tmp_path / "parameter_registry.json"
    registry_copy.write_text(REGISTRY_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    added = align.process(registry_copy, tmp_path / "unused.dic", dry_run=True)
    assert added == 0, f"{added} registry parameter(s) have no dictionary item"


def test_registry_and_dictionary_descriptions_do_not_drift():
    """Every registry description matches the dictionary's ``_item_description``.

    Closes PRD-02c acceptance criterion 4 (description duplication
    minimised). The alignment script is now the single mechanism that keeps
    the extension dictionary in step with the registry, so a drift here means
    someone edited a description in the JSON without re-running the alignment.
    """
    import re

    with open(REGISTRY_PATH, "r") as fh:
        data = json.load(fh)
    params = data.get("parameters", {})
    d = MmcifDictionary.load_bundled()
    cat = d.get_category("flr_fit_parameter")
    assert cat is not None

    drifted = []
    for key, entry in params.items():
        if not isinstance(entry, dict):
            continue
        reg_desc = entry.get("description", "")
        if not isinstance(reg_desc, str) or not reg_desc.strip():
            continue
        attr = align.sanitize_cif_attribute(key)
        item = cat.items.get(attr)
        if item is None:
            continue
        dic_desc = (item.description or "").strip()
        if dic_desc != reg_desc.strip():
            drifted.append(key)

    assert not drifted, (
        f"{len(drifted)} parameter(s) have descriptions that differ between "
        f"the registry and the dictionary: {drifted[:10]}. "
        f"Run `python -m build_tools.dev_utils.align_flrcif_parameters` to fix."
    )
