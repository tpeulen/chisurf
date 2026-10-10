"""User-visible imperative literals are measured without importing plugin code."""

from pathlib import Path

import pytest

from build_tools.dev_utils.ui_contract_audit import (
    audit_translation_python,
    audit_tree,
    baseline_delta,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "test/i18n_allowlist.txt"


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


def test_literal_allowances_reject_new_and_stale_occurrences():
    """Identical labels remain separate debt and both directions of drift fail."""
    findings = audit_translation_python('im.text("Run"); im.text("Run")', "probe.py")
    first, second = (finding.key for finding in findings)
    assert first != second
    report = {"findings": [{"key": first}, {"key": second}]}
    assert baseline_delta(report, {first, "obsolete"}) == ({second}, {"obsolete"})
    assert baseline_delta(report, {first, second}) == (set(), set())


def test_shipped_literal_contract_has_no_new_or_stale_debt():
    """Enforce the accepted production debt against committed source bytes."""
    assert BASELINE.is_file(), "Publish the accepted literal debt before enabling its guard."
    allowed = {
        line.strip()
        for line in BASELINE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    report = audit_tree(ROOT, revision="HEAD", contract="translation")
    # The accepted measurement covered 1751 production Python sources; retiring the
    # Qt plugin tools left 1627. The floor only guards against the audit collapsing.
    assert report["files"].get("python", 0) >= 1600
    new, stale = baseline_delta(report, allowed)
    assert not new, "New untranslated literals:\n" + "\n".join(sorted(new))
    assert not stale, "Remove obsolete literal allowances:\n" + "\n".join(sorted(stale))


def test_literal_line_relocation_requires_explicit_baseline_review():
    """Accepted literal keys include offsets, so a relocation is new and stale debt."""
    original = audit_translation_python('im.text("Run")', "probe.py")
    moved = audit_translation_python('\n\nim.text("Run")', "probe.py")
    assert len(original) == len(moved) == 1
    assert original[0].detail == moved[0].detail
    report = {"findings": [{"key": moved[0].key}]}
    assert baseline_delta(report, {original[0].key}) == (
        {moved[0].key},
        {original[0].key},
    )
