"""User-visible imperative literals are measured without importing plugin code."""

import pytest

from build_tools.dev_utils.ui_contract_audit import audit_translation_python


@pytest.mark.parametrize(
    "call",
    [
        "text",
        "text_wrapped",
        "text_disabled",
        "button",
        "checkbox",
        "selectable",
        "set_item_tooltip",
    ],
)
def test_bare_visible_literal_requires_translation(call):
    """Every specified text sink reports its untranslated label with a stable source location."""
    result = audit_translation_python(f'im.{call}("Open data")', "probe.py")
    assert len(result) == 1
    assert result[0].detail == "Open data"
    assert result[0].line == 1
    assert result[0].code == "untranslated-literal"


def test_hints_and_qualified_widget_calls_are_visible():
    """A keyword hint and a fully qualified text call cannot escape the audit."""
    result = audit_translation_python(
        'emtk.im.button("Run"); im.input_text("##id", value, hint="Filename")', "probe.py"
    )
    assert [f.detail for f in result] == ["Run", "Filename"]


def test_explicit_translation_identifiers_and_numeric_labels_are_exempt():
    """Translation wrappers remain calls; numeric/unit-free decoration and hidden IDs are not prose."""
    source = 'im.text(tr("Open")); im.button(i18n.tr("Run")); im.text("##private"); im.text("123.4"); im.text("…")'
    assert audit_translation_python(source, "probe.py") == []


def test_nested_calls_unicode_labels_and_repeated_source_stay_distinct():
    """Each authored occurrence is actionable, including a text sink inside another call."""
    source = 'if im.button("Données"):\n    print(im.text("Données"))\n'
    findings = audit_translation_python(source, "probe.py")
    assert [f.detail for f in findings] == ["Données", "Données"]
    assert len({f.key for f in findings}) == 2


def test_other_method_names_and_data_literals_are_not_ui_calls():
    """Unrelated application APIs and binding values are outside the declared widget sinks."""
    assert audit_translation_python('model.text("Data"); value = "Open"', "probe.py") == []


def test_malformed_shipped_python_is_an_actionable_failure():
    """A broken source cannot silently reduce the measured literal count."""
    assert audit_translation_python("def broken(:", "probe.py")[0].code == "invalid-python"


def test_import_aliases_and_direct_widget_imports_do_not_hide_literals():
    """The same toolkit sinks remain visible under local import spelling."""
    source = (
        "from emtk import im as widgets\n"
        "import emtk.im as _im\n"
        "from emtk.im import button as action\n"
        'widgets.text("Alias"); _im.button("Module"); action("Direct")\n'
    )
    assert [f.detail for f in audit_translation_python(source, "probe.py")] == [
        "Alias",
        "Module",
        "Direct",
    ]
