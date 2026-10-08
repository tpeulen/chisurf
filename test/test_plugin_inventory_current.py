"""Plugin inventory reports actual production ownership and remains reproducible."""

import json
from pathlib import Path

import pytest

from build_tools.dev_utils.plugin_inventory import inventory, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def plugin(folder, name="example"):
    """Write a minimal discoverable plugin declaration."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "manifest.json").write_text(json.dumps({"display_name": name, "entrypoints": {}}))


def test_nested_plugin_does_not_credit_parent(tmp_path):
    """A child's controls and imports cannot make its containing hub look ported."""
    parent = tmp_path / "hub"
    child = parent / "child"
    plugin(parent)
    plugin(child)
    (child / "gui").mkdir()
    (child / "gui" / "view.json").write_text("{}")
    (child / "gui" / "help.md").write_text("Help")
    (child / "gui" / "app.py").write_text("def start():\n    from qtpy import QtWidgets\n")
    rows = {row["plugin"]: row for row in inventory(tmp_path)}
    assert not rows["hub"]["view"]
    assert not rows["hub"]["help"]
    assert not rows["hub"]["qtimp"]
    assert rows["hub/child"]["view"] and rows["hub/child"]["qtimp"]


def test_test_and_documentation_mentions_are_not_production_imports(tmp_path):
    """Indented real imports count; test files and docstring references do not."""
    folder = tmp_path / "tool"
    plugin(folder, "Tool | name")
    (folder / "tests").mkdir()
    (folder / "tests" / "helper.py").write_text("import qtpy\n")
    (folder / "test_root.py").write_text("import pyqtgraph\n")
    (folder / "app.py").write_text('"""import qtpy; Cond.ALWAYS; object.native"""\n')
    row = inventory(tmp_path)[0]
    assert not row["qtimp"] and not row["pg"] and not row["always"]
    assert "Tool \\| name" in render_markdown([row])


@pytest.mark.parametrize("bad_file,content", [("manifest.json", "{"), ("app.py", "def broken(:")])
def test_bad_records_are_reported_instead_of_dropped(tmp_path, bad_file, content):
    """A broken record must not silently improve a release metric."""
    folder = tmp_path / "tool"
    plugin(folder)
    (folder / bad_file).write_text(content)
    with pytest.raises(ValueError, match="tool"):
        inventory(tmp_path)


def test_plugin_inventory_current():
    """The durable inventory and PRD appendix describe precisely the committed source tree."""
    rows = inventory(ROOT / "chisurf" / "plugins", revision="HEAD")
    expected = render_markdown(rows)
    record = ROOT / "okf" / "validation" / "release-readiness-w6g" / "plugin-inventory.md"
    assert record.read_text().split("\n---\n\n", 1)[1] == expected, (
        "Run plugin_inventory.py --write."
    )
    prd = (ROOT / "okf" / "prds" / "prd-154.md").read_text()
    begin = "<!-- plugin-inventory:start -->\n"
    end = "<!-- plugin-inventory:end -->"
    assert begin in prd and end in prd, "Install the generated Appendix A block."
    assert prd.split(begin, 1)[1].split(end, 1)[0] == expected


def test_first_write_anchors_real_table_outside_embedded_code(tmp_path, monkeypatch):
    """Bootstrap regeneration must retain example code and the following design section."""
    from build_tools.dev_utils import plugin_inventory as generator

    prd = tmp_path / "okf" / "prds" / "prd-154.md"
    prd.parent.mkdir(parents=True)
    sample = (
        '## Appendix A\n\n```python\nprint("| plugin | display_name |")\n```\n\n'
        "| plugin | display_name |\n|---|---|\n| old | old |\n\n---\n\n## Part E\nDesign.\n"
    )
    prd.write_text(sample)
    monkeypatch.setattr(generator, "inventory", lambda *args, **kwargs: [])
    monkeypatch.setattr("sys.argv", ["plugin_inventory", "--root", str(tmp_path), "--write"])
    generator.main()
    result = prd.read_text()
    assert 'print("| plugin | display_name |")' in result
    assert "## Part E\nDesign." in result
    assert result.count(generator.BEGIN) == 1
    assert "| old | old |" not in result
