"""Write deliberate.json from compare.json's lost list: the Qt tree's cell texts are data, the rest is named by hand."""
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
lost = json.load(open(out / "compare.json"))["lost"] if (out / "compare.json").exists() else []
named = {
    "delay": "Qt toolbar caption 'Delay:': native field 'Delay between plugins' (0 to 5 s, step 0.1, default 0.5, arrows)",
    "chisurfplugincheck": "Qt window title label: native window and dock titles ('Plugin startup checks', 'Plugin details')",
    "selectaplugintoviewdetails": "Qt placeholder before any selection: native app selects the first plugin at start; the placeholder 'Select a plugin to inspect its details.' shows only when the list is empty",
    "ready✨134plugin(s)found": "Qt status line with a sparkle glyph: native 'Ready: N plugin(s) found' (no emoji), same count",
    "testsallpluginsforstartuperrors.✅success,❌failure,⚠️skipped.": "Qt description line with status glyphs: native status words (pass / fail / skipped / pending) explained in the Status column tooltip and the help",
}
reason = ("Qt tree cell text (a plugin's menu path or its Depends-on cell): list data, not a control; the native "
          "table shows the same cells in the same order (test_the_list_equals_the_qt_trees_rows_in_the_same_order, "
          "test_the_baseline_rows_the_qt_tool_showed_are_matched_cell_for_cell); only the rows in view are drawn")
explained = {k: named.get(k, reason) for k in lost}
(out / "deliberate.json").write_text(json.dumps(explained, indent=1, ensure_ascii=False) + "\n")
print(len(explained), "explained")
