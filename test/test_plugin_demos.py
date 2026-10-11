"""Shipped demos declare a stable cache API and a reachable first tour action."""

import json
import subprocess

import pytest

from build_tools.dev_utils.demo_contract_audit import audit_demo, audit_tree

GOOD = """from pathlib import Path
DEMO = {"seed": 7}
def demo_folder() -> Path:
    return Path("settings") / "demos" / "probe"
def make_demo(folder=None, *, overwrite=False) -> Path:
    return Path(folder) / "known.ptu"
"""
GUIDE = {
    "steps": [
        {"title": "Intro"},
        {"target": {"name": "load_example"}, "await": {"hint": "Press Load example"}},
    ]
}
VIEW = {
    "sections": [
        {
            "type": "button_row",
            "buttons": [
                {
                    "action": "load_example",
                    "label": "Load example",
                    "description": "Load known data.",
                }
            ],
        }
    ]
}


def test_declared_demo_and_real_control_contract_passes():
    """A folder-first producer, configuration and awaited declared action agree."""
    assert audit_demo(GOOD, GUIDE, VIEW, "probe/demo.py") == []


@pytest.mark.parametrize(
    "source, code",
    [
        (GOOD.replace("DEMO =", "OTHER ="), "demo-configuration"),
        (GOOD.replace("def demo_folder", "def old_folder"), "demo-folder"),
        (GOOD.replace("def make_demo", "def create_demo"), "demo-producer"),
        (
            GOOD.replace("folder=None, *, overwrite=False", "path=None, *, overwrite=False"),
            "demo-folder-argument",
        ),
        (
            GOOD.replace("folder=None, *, overwrite=False", "folder, *, overwrite=False"),
            "demo-optional-folder",
        ),
        (GOOD.replace("folder=None, *, overwrite=False", "folder=None"), "demo-overwrite"),
    ],
)
def test_obsolete_or_incomplete_api_is_reported(source, code):
    """An old name or signature remains actionable rather than being silently accepted."""
    assert code in [f.code for f in audit_demo(source, GUIDE, VIEW, "probe/demo.py")]


def test_tour_waits_for_the_real_example_action():
    """Changing a target or removing its await cannot turn a narration into a data lesson."""
    guide = json.loads(json.dumps(GUIDE))
    guide["steps"][1] = {"target": {"name": "old_demo"}}
    assert {f.code for f in audit_demo(GOOD, guide, VIEW, "probe/demo.py")} >= {
        "demo-tour-target",
        "demo-tour-await",
    }


def test_missing_control_and_invalid_python_are_not_empty_success():
    """Missing actions and parse errors cannot improve release counts."""
    assert "demo-control" in [
        f.code for f in audit_demo(GOOD, GUIDE, {"sections": []}, "probe/demo.py")
    ]
    assert audit_demo("def broken(:", GUIDE, VIEW, "probe/demo.py")[0].code == "invalid-python"


def test_declared_configuration_must_be_a_dictionary():
    """A scalar named DEMO is not a cache-key declaration."""
    assert "demo-configuration" in [
        f.code for f in audit_demo(GOOD.replace('{"seed": 7}', "7"), GUIDE, VIEW, "probe/demo.py")
    ]


def test_async_producer_is_not_a_synchronous_path_contract():
    """A coroutine cannot be mistaken for the primary input path."""
    assert "demo-producer" in [
        f.code
        for f in audit_demo(
            GOOD.replace("def make_demo", "async def make_demo"), GUIDE, VIEW, "probe/demo.py"
        )
    ]


LITERAL_CONTROL = """class App:
    def render(self):
        if im.button("Example"):
            self.load_example()
        self.item_rects["load_example"] = im.get_item_rect()
"""
TUPLE_CONTROL = """class App:
    def _button(self, label, key):
        pressed = im.button(label)
        self.item_rects[key] = im.get_item_rect()
        return pressed
    def render(self):
        for label, key, act in (
            ("Example", "load_example", self.load_example),
        ):
            if self._button(label, key):
                act()
"""


@pytest.mark.parametrize("source", [LITERAL_CONTROL, TUPLE_CONTROL])
def test_imperative_example_control_has_a_real_registered_rectangle(source):
    """A drawn button and its actual callback can teach the tour without a form spec."""
    assert (
        audit_demo(GOOD, GUIDE, [], "probe/demo.py", control_sources={"gui/app.py": source}) == []
    )


@pytest.mark.parametrize(
    "source",
    [
        'def load_example():\n    on_used("load_example")\n',
        LITERAL_CONTROL.replace("im.get_item_rect()", "(0, 0, 100, 20)"),
        LITERAL_CONTROL.replace(
            'if im.button("Example"):', 'im.button("Example")\n        if self.ready:'
        ),
        TUPLE_CONTROL.replace("self._button(label, key)", "im.button(label)"),
        TUPLE_CONTROL.replace("act()", "self.other_action()"),
    ],
)
def test_notification_or_unconnected_tuple_is_not_a_reachable_control(source):
    """Notification text, invented rectangles and unused callback rows cannot pass."""
    assert "demo-control" in [
        f.code
        for f in audit_demo(
            GOOD, GUIDE, [], "probe/demo.py", control_sources={"gui/app.py": source}
        )
    ]


def _plugin(root, name="probe"):
    """Create an authored minimal plugin tree for resource ownership checks."""
    plugin = root / "chisurf/plugins" / name
    (plugin / "gui").mkdir(parents=True)
    (plugin / "manifest.json").write_text("{}")
    (plugin / "demo.py").write_text(GOOD)
    (plugin / "gui/guide.json").write_text(json.dumps(GUIDE))
    return plugin


def test_nested_plugin_control_cannot_satisfy_parent_demo(tmp_path):
    """Nearest manifest ownership prevents borrowing a different plugin's action."""
    _plugin(tmp_path)
    nested = _plugin(tmp_path, "probe/nested")
    (nested / "gui/example.view.json").write_text(json.dumps(VIEW))
    report = audit_tree(tmp_path, revision=None)
    parent = next(record for record in report["demos"] if record["path"].endswith("probe/demo.py"))
    assert parent["views"] == []
    assert any(
        f["code"] == "demo-control" and f["path"].endswith("probe/demo.py")
        for f in report["findings"]
    )


def test_tree_uses_its_own_imperative_control(tmp_path):
    """An owned GUI source is audited without importing its renderer."""
    plugin = _plugin(tmp_path)
    (plugin / "gui/app.py").write_text(TUPLE_CONTROL)
    assert audit_tree(tmp_path, revision=None)["findings"] == []


@pytest.mark.parametrize("resource", ["gui/guide.json", "gui/example.view.json"])
def test_malformed_json_retains_the_actual_resource_identity(tmp_path, resource):
    """Malformed resource bytes remain visible alongside missing demo contracts."""
    plugin = _plugin(tmp_path)
    (plugin / resource).write_text("{broken")
    findings = audit_tree(tmp_path, revision=None)["findings"]
    assert any(f["code"] == "invalid-json" and f["path"].endswith(resource) for f in findings)


def test_async_folder_function_is_not_a_path_contract():
    """The cache folder helper must return a path synchronously too."""
    assert "demo-folder" in [
        f.code
        for f in audit_demo(
            GOOD.replace("def demo_folder", "async def demo_folder"), GUIDE, VIEW, "probe/demo.py"
        )
    ]


def test_invalid_imperative_python_is_reported_even_with_a_form_control():
    """Malformed owned GUI code cannot disappear behind a valid declarative action."""
    findings = audit_demo(
        GOOD, GUIDE, VIEW, "probe/demo.py", control_sources={"gui/app.py": "def broken(:"}
    )
    assert any(f.code == "invalid-python" and f.path == "gui/app.py" for f in findings)


def test_malformed_secondary_guide_is_not_silently_ignored(tmp_path):
    """All owned guide resources are parsed even when the first guide is valid."""
    plugin = _plugin(tmp_path)
    (plugin / "gui/example.view.json").write_text(json.dumps(VIEW))
    (plugin / "gui/guide_extra.json").write_text("{broken")
    findings = audit_tree(tmp_path, revision=None)["findings"]
    assert any(
        f["code"] == "invalid-json" and f["path"].endswith("guide_extra.json") for f in findings
    )


REMEMBER_CONTROL = """from chisurf.emtk.help_guide import TourTarget
class App(TourTarget):
    def render(self):
        if im.button("Example"):
            self.load_example()
        self.remember("load_example")
"""
ROW_CONTROL = """from chisurf.emtk.help_guide import TourTarget
from chisurf.plugins.emtk_layout import button_row
class App(TourTarget):
    def render(self):
        pressed = button_row([{"label": "Example", "key": "load_example"}], remember=self.remember)
        if pressed == "load_example":
            self.on_demo()
"""


@pytest.mark.parametrize("source", [REMEMBER_CONTROL, ROW_CONTROL])
def test_shared_rectangle_registration_requires_drawn_button_and_callback(source):
    """Known shared targeting APIs preserve the same real control proof."""
    assert (
        audit_demo(GOOD, GUIDE, [], "probe/demo.py", control_sources={"gui/app.py": source}) == []
    )


@pytest.mark.parametrize(
    "source",
    [
        REMEMBER_CONTROL.replace('if im.button("Example"):', "if self.ready:"),
        REMEMBER_CONTROL.replace("self.load_example()", 'self.track("load_example")'),
        REMEMBER_CONTROL.replace("class App(TourTarget):", "class App:"),
        REMEMBER_CONTROL + "\n    def remember(self, key):\n        self.on_used(key)\n",
        ROW_CONTROL.replace("remember=self.remember", "remember=self.track"),
        ROW_CONTROL.replace("self.on_demo()", 'self.track("load_example")'),
        ROW_CONTROL.replace("chisurf.plugins.emtk_layout", "unknown.helpers"),
    ],
)
def test_shared_names_without_real_registration_do_not_pass(source):
    """Shared method names cannot bless notifications or arbitrary toolbar helpers."""
    findings = audit_demo(GOOD, GUIDE, [], "probe/demo.py", control_sources={"gui/app.py": source})
    assert "demo-control" in [f.code for f in findings]


def test_shared_rectangle_mixin_can_be_inherited_through_imported_base():
    """ALEX's reused Files page traces its target storage through the actual base class."""
    source = REMEMBER_CONTROL.replace(
        "from chisurf.emtk.help_guide import TourTarget",
        "from chisurf.plugins.shared.base import FilesApp",
    ).replace("class App(TourTarget):", "class App(FilesApp):")
    base = "from chisurf.emtk.help_guide import TourTarget\nclass FilesApp(TourTarget):\n    pass\n"
    assert (
        audit_demo(
            GOOD,
            GUIDE,
            [],
            "probe/demo.py",
            control_sources={"gui/app.py": source},
            registration_sources={"chisurf/plugins/shared/base.py": base},
        )
        == []
    )


def test_prospective_tree_object_uses_only_its_authored_resource_bytes(tmp_path):
    """Root can verify an owned candidate Git tree before source publication."""
    plugin = _plugin(tmp_path)
    (plugin / "gui/example.view.json").write_text(json.dumps(VIEW))
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    paths = [path.relative_to(tmp_path).as_posix() for path in plugin.rglob("*") if path.is_file()]
    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    tree = subprocess.check_output(["git", "write-tree"], cwd=tmp_path, text=True).strip()
    (plugin / "gui/example.view.json").write_text("{broken")
    report = audit_tree(tmp_path, revision=tree)
    assert report["revision"] == tree
    assert report["findings"] == []
    assert audit_tree(tmp_path, revision=None)["counts"]["invalid-json"] == 1


def test_every_shipped_demo_has_the_standard_contract():
    """Committed demos expose the cache API and a real awaited example control."""
    from pathlib import Path

    from build_tools.dev_utils.demo_contract_audit import audit_tree

    root = Path(__file__).resolve().parents[1]
    report = audit_tree(root, revision="HEAD")
    assert report["demos"], "No committed demos were measured."
    assert not report["findings"], report["findings"]
