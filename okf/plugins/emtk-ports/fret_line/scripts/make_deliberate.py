"""Write deliberate.json from compare.json's lost list (the Qt model editor's widget text is data of a fitting editor)."""
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
lost = json.load(open(out / "compare.json"))["lost"]
named = {
    "vary": "Qt 'Vary:' caption: native choice 'Vary'", "allparams": "Qt 'all params' checkbox: native toggle 'All parameters'",
    "min": "Qt 'Min:' caption: native field 'Min'", "max": "Qt 'Max:' caption: native field 'Max'", "points": "Qt 'Points:': native field 'Points'",
    "log": "Qt 'log' checkbox: native toggle 'log'", "τ_d0(ns)": "Qt 'τ_D0 (ns):': native field 'τ_D0 (ns)'",
    "showall": "Qt 'Show all' button: native 'Show all'", "hideall": "Qt 'Hide all' button: native 'Hide all'",
    "clearall": "Qt 'Clear all' button: native 'Clear all'", "?": "Qt '?' help button: native 'Help'",
    "computedfretlines(overlaidontheplots)": "Qt caption of the lines list: the tab is titled 'FRET lines'",
    "efret": "Qt axis label E_FRET: the native plot labels it 'E_FRET'",
}
sweep = "Qt sweep-target entry or component-list text: native 'Vary' choice and component table show the same labels (test_sweep_target_labels_equal_the_qt_tools, test_the_component_list_text_and_the_add_remove_rules_equal_the_qt_tools)"
editor = ("Qt model-editor widget text (the fitting editor's groups: IRF, convolution, generic, corrections, anisotropy, window "
          "functions, and parameter names/defaults in its table): no effect on a FRET line (no decay is convolved); the native "
          "'Model parameters' table lists exactly the parameters the model uses (structure_parameter_ids) with value, fixed, bounds, "
          "limits (test_a_parameter_typed_into_the_editor_table_changes_the_model, test_the_fixed_and_bounds_boxes_...)")
res = {}
for k in lost:
    res[k] = named.get(k) or (sweep if k.startswith("c0") or k.startswith("c1") else editor)
(out / "deliberate.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
print(len(res))
