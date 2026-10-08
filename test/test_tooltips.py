"""Tooltip audits retain real omissions while excluding identifiers and reference source."""

import json
from pathlib import Path

import pytest

from build_tools.dev_utils.ui_contract_audit import (
    _kind,
    audit_json,
    audit_python,
    audit_tree,
    baseline_delta,
)

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "test/tooltip_allowlist.txt"


def codes(findings):
    """Summarize a fixture's actual missing contracts."""
    return [finding.code for finding in findings]


def test_json_nested_envelopes_and_named_templates_are_measured():
    """Controls remain covered under named templates, dock panels and tab maps."""
    spec = {
        "toolbar": {
            "sections": [{"type": "button_row", "buttons": [{"action": "run", "label": "Run"}]}]
        },
        "tabs": {
            "Settings": {
                "panels": [
                    {
                        "type": "panel",
                        "title": "Inputs",
                        "sections": [{"type": "value", "attr": "path"}],
                    }
                ]
            }
        },
    }
    findings = audit_json(json.dumps(spec), "probe.view.json")
    assert codes(findings) == ["item-tooltip", "section-tooltip", "section-tooltip"]
    assert findings[0].location == "/toolbar/sections/0/buttons/0"


def test_json_anonymous_layout_and_schema_data_are_not_controls():
    """Undrawn grouping rows and arbitrary data/schema dictionaries have no tooltip item."""
    spec = {
        "sections": [
            {
                "type": "panel",
                "sections": [{"type": "value", "attr": "gain", "tooltip": "Detector gain."}],
            }
        ],
        "$defs": {"example": {"type": "value"}},
        "data": {"record": {"type": "plot"}},
    }
    assert audit_json(json.dumps(spec), "probe.view.json") == []


def test_json_radio_options_columns_and_toggle_items_need_individual_explanations():
    """A table/section tooltip does not accidentally excuse missing column/option help."""
    spec = {
        "sections": [
            {
                "type": "choice",
                "style": "radio_list",
                "options": ["a", "b"],
                "description": "Pick mode.",
                "descriptions": ["Mode A.", " "],
            },
            {
                "type": "custom",
                "key": "data_table",
                "description": "Results.",
                "options": {"columns": [{"key": "x", "tooltip": "Coordinate."}, {"key": "y"}]},
            },
            {
                "type": "toggle_row",
                "description": "Visibility.",
                "items": [{"attr": "shown", "label": "Shown"}],
            },
        ]
    }
    assert codes(audit_json(json.dumps(spec), "probe.view.json")) == [
        "radio-tooltip",
        "column-tooltip",
        "item-tooltip",
    ]


@pytest.mark.parametrize("text", ["{oops", "null"])
def test_invalid_declarations_cannot_disappear_from_measurement(text):
    """Malformed or wrong-shaped input is a recorded failure, never an empty audit."""
    assert audit_json(text, "probe.view.json")


def test_direct_controls_assignments_conditionals_aliases_and_local_helpers():
    """A real same-block tooltip counts for a control regardless of its return-value use."""
    source = """from emtk import im as ui
def tip(text):
    ui.set_item_tooltip(text)
class Panel:
    def _item(self, text):
        ui.set_item_tooltip(text)
    def draw(self):
        if ui.button("Run"):
            self.run()
        self._item("Run analysis.")
        changed, value = ui.combo("Method", 0, ["A"])
        tip("Choose a method.")
        ui.checkbox("Enabled", True)
        ui.end_disabled()
        ui.set_item_tooltip("Enable analysis.")
"""
    assert audit_python(source, "probe.py") == []


def test_clicked_only_wrong_instance_and_empty_helper_tips_are_missing():
    """Help in the clicked branch, another object's helper or blank text cannot cover hover."""
    source = """from emtk import im
def tip(text):
    im.set_item_tooltip(text)
class Panel:
    def _item(self, text):
        im.set_item_tooltip(text)
    def draw(self):
        if im.button("Run"):
            im.set_item_tooltip("Only after clicking.")
        im.button("Next")
        other._item("Unrelated.")
        im.input_text("Path", "")
        tip("")
        im.slider_float("Gain", 1, 0, 2)
        im.set_item_tooltip(" ")
"""
    findings = audit_python(source, "probe.py")
    assert len(findings) == 4
    assert all(finding.line for finding in findings)


def test_reference_docstrings_and_non_gui_button_methods_are_not_controls():
    """The scanner parses code rather than matching comments, tutorial strings or Qt APIs."""
    source = '''"""im.button("example")"""
# im.checkbox("reference", False)
widget.button("Qt or application method")
'''
    assert audit_python(source, "probe.py") == []
    assert _kind("chisurf/plugins/tool/test/gui/app.py") is None
    assert _kind("chisurf/plugins/cookiecutter/gui/view.json") is None
    assert _kind("modules/ndxplorer/build/lib/example.view.json") is None
    assert _kind("chisurf/plugins/tool/gui/app.py") == "python"
    assert _kind("chisurf/plugins/tool/gui/view.json") == "json"


def test_item_rect_bookkeeping_and_conditional_style_cleanup_keep_the_last_item():
    """Real hub/editor bookkeeping does not invalidate the tooltip's target."""
    source = """from emtk import im
def draw():
    if im.button("Plot"):
        toggle()
    if plotting:
        im.pop_style_color()
    rects["plot"] = im.get_item_rect()
    tip = "Preview the data."
    if disabled:
        tip += " Currently disabled."
    im.set_item_tooltip(tip)
    callback = lambda: im.button("Not drawn at this statement")
"""
    assert audit_python(source, "probe.py") == []


def test_tooltip_after_another_item_cannot_cover_an_earlier_control():
    """Drawing a new text item ends the control's last-item contract."""
    source = """im.button("Run")
im.text("Results")
im.set_item_tooltip("About the results.")
"""
    assert len(audit_python(source, "probe.py")) == 1


def test_shared_tip_after_if_else_covers_each_drawn_branch_but_not_loop_iterations():
    """Tour enabled/disabled branches retain one last item; loops require help per item."""
    source = """if enabled:
    if im.button("Previous"):
        previous()
else:
    im.begin_disabled()
    im.button("Previous")
    im.end_disabled()
im.set_item_tooltip("Previous step.")
for label in labels:
    im.selectable(label)
im.set_item_tooltip("Only the last option.")
"""
    findings = audit_python(source, "probe.py")
    assert len(findings) == 1 and "/selectable(" in findings[0].key


def test_allowances_only_shrink_and_keys_ignore_source_line_offsets():
    """Both new debt and obsolete allowances fail; moving unchanged source is not new debt."""
    finding = audit_python('im.button("Run")', "probe.py")[0]
    moved = audit_python('\n\n im.button("Run")'.replace(" im", "im"), "probe.py")[0]
    assert finding.key == moved.key and finding.line != moved.line
    report = {"findings": [{"key": finding.key}]}
    assert baseline_delta(report, {"obsolete"}) == ({finding.key}, {"obsolete"})


def test_shipped_tooltip_contract_has_no_new_or_stale_debt():
    """Audit committed production bytes independently of concurrently dirty plugin migrations."""
    assert BASELINE.is_file(), (
        "Tooltip baseline is not published; inspect the complete audit ledger first."
    )
    allowed = {
        line.strip()
        for line in BASELINE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    report = audit_tree(ROOT, revision="HEAD")
    assert report["files"].get("json", 0) > 50
    assert report["files"].get("python", 0) > 50
    new, stale = baseline_delta(report, allowed)
    assert not new, "New tooltip omissions:\n" + "\n".join(sorted(new))
    assert not stale, "Remove obsolete tooltip allowances:\n" + "\n".join(sorted(stale))
