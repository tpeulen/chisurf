"""Generic behaviour of :mod:`chisurf.core.registry.tttrlib`.

The burst-search facade is exercised in the burst_selection suite; this file
covers the module's *category-agnostic* surface — categories, look-ups, the
error messages, defaults, and the no-parameters guard — using the
``file_container`` category, which every tttrlib that publishes a registry also
publishes and which (unlike a burst search) carries no ``params_schema``.
"""

from __future__ import annotations

import pytest

from chisurf.core.registry import tttrlib as registry


def test_registry_returns_a_nonempty_mapping():
    whole = registry.registry()
    assert isinstance(whole, dict)
    # Every value is itself a {name: entry} mapping.
    for category, entries in whole.items():
        assert isinstance(entries, dict), category


def test_categories_are_sorted_and_include_the_known_ones():
    categories = registry.categories()
    assert categories == sorted(categories)
    assert registry.BURST_SEARCH in categories
    assert registry.FILE_CONTAINER in categories


def test_entries_of_an_unknown_category_is_empty_not_an_error():
    # A caller can test availability without catching.
    assert registry.entries("no_such_category") == {}


def test_is_available_reflects_whether_a_category_is_published():
    assert registry.is_available(registry.FILE_CONTAINER) is True
    assert registry.is_available("no_such_category") is False
    # Defaults to the burst-search category.
    assert registry.is_available() == registry.is_available(registry.BURST_SEARCH)


def test_describe_unknown_category_names_the_alternatives():
    with pytest.raises(ValueError, match="unknown registry category") as info:
        registry.describe("no_such_category", "whatever")
    # The message lists what the caller could have asked for.
    assert registry.FILE_CONTAINER in str(info.value)


def test_describe_unknown_entry_reads_as_prose_and_lists_alternatives():
    names = registry.entries(registry.FILE_CONTAINER)
    with pytest.raises(ValueError, match="unknown file container") as info:
        registry.describe(registry.FILE_CONTAINER, "not_a_container")
    # The category is spelled out (no underscore) and a real entry is offered.
    message = str(info.value)
    assert "file_container" not in message
    assert any(name in message for name in names)


def test_describe_returns_the_entry_for_a_known_name():
    names = registry.entries(registry.FILE_CONTAINER)
    name = next(iter(names))
    entry = registry.describe(registry.FILE_CONTAINER, name)
    assert entry == names[name]
    assert entry["name"] == name


def _parameterless_container():
    for name, entry in registry.entries(registry.FILE_CONTAINER).items():
        if not (entry.get("params_schema") or {}).get("properties"):
            return name
    pytest.skip("every file container of this tttrlib declares parameters")


def test_defaults_of_a_parameterless_entry_is_empty():
    # Most file containers describe something with no parameters, so there is
    # nothing to default -- an empty dict rather than an error. (Ranged readers
    # declare first_record/n_records now, so pick one that declares nothing.)
    name = _parameterless_container()
    assert registry.defaults(registry.FILE_CONTAINER, name) == {}


def test_entry_form_view_refuses_a_parameterless_entry():
    # A container without a params_schema cannot become a form; the module says
    # so rather than building an empty one.
    name = _parameterless_container()
    with pytest.raises(ValueError, match="no parameters"):
        registry.entry_form_view(registry.FILE_CONTAINER, name)
    with pytest.raises(ValueError, match="no parameters"):
        registry.entry_form_view_auto(registry.FILE_CONTAINER, name)


def test_defaults_are_within_the_schema_bounds_for_a_parametered_entry():
    # Cross-category sanity: a burst search does carry a schema, and every
    # numeric default the registry advertises must sit inside its own range.
    name = next(iter(registry.entries(registry.BURST_SEARCH)))
    schema = registry.describe(registry.BURST_SEARCH, name)["params_schema"]
    defaults = registry.defaults(registry.BURST_SEARCH, name)
    for prop_name, value in defaults.items():
        prop = schema["properties"][prop_name]
        if prop["type"] in ("integer", "number"):
            assert prop["minimum"] <= value <= prop["maximum"], prop_name
