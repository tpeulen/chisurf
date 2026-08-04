"""Guard: every GUI plugin ships a ``?`` help page and a **Guide** tour.

**The rule: a modern plugin has a help button and a guided tour.** They answer
two different questions and a tool needs both — ``?`` says what a control
*means*, the guide says which control to touch **first**. A dense panel of
well-documented settings is still unusable without the second one.

Neither costs a plugin any code. A tool ships ``help.md`` and ``guide.json``
beside the module its ``entrypoints.gui`` names, and
:class:`~chisurf.gui.widgets.tools.help_guide.HelpGuideMixin` — inherited by
``ChisurfDockTool`` and ``NavigationPanelTool`` alike — finds them and builds the
buttons. A tool built on neither base calls
:func:`~chisurf.gui.widgets.tools.help_guide.attach_help_and_guide` once.

``test/plugin_help_guide_allowlist.txt`` is a **shrinking** record of plugins not
yet modernised — never somewhere to add yourself to make this test pass. This
file fails when a listed plugin has been done (stale entry) and when an unlisted
one is missing its files (regression). The end state is an empty allow-list.

The checks are deliberately static — no Qt, no plugin imports — so this runs in
the fast suite and cannot be defeated by a tool that fails to construct.
"""

from __future__ import annotations

import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_PLUGINS = _ROOT / "chisurf" / "plugins"
_ALLOWLIST = _ROOT / "test" / "plugin_help_guide_allowlist.txt"

#: The cookiecutter template is a *template*, not a plugin: its manifest names a
#: module that does not exist until someone generates from it.
_SKIP_MARKERS = ("cookiecutter",)

#: A tour with two steps is a title card, not a guide. Three is the smallest
#: thing that can say where to start, what the setting means and what to check.
_MIN_STEPS = 3

#: Below this a help page is a stub — a sentence restating the tool's name.
_MIN_HELP_CHARS = 400


class GuiPlugin:
    """One plugin with a GUI entry point, and where its help files must live."""

    def __init__(self, manifest: pathlib.Path, data: dict) -> None:
        self.manifest = manifest
        self.id = str(data.get("id") or manifest.parent.name)
        self.gui = str((data.get("entrypoints") or {}).get("gui") or "")
        self.directory = self._module_directory()

    def _module_directory(self) -> pathlib.Path | None:
        """Resolve the directory the help files are looked for in.

        This mirrors what
        :func:`~chisurf.gui.widgets.tools.help_guide.resolve_tool_resource` does
        at runtime — the directory of the module holding the tool class — but by
        path arithmetic rather than by importing it, so a plugin whose import
        raises is still checked.
        """
        module = self.gui.split(":")[0]
        if not module:
            return None
        path = _ROOT / pathlib.Path(module.replace(".", "/"))
        if path.with_suffix(".py").is_file():
            return path.parent
        if path.is_dir():
            # A plugin whose entry point is the package itself anchors one level
            # above where its GUI lives. The convention is that everything
            # describing the GUI sits under ``gui/``, and the runtime resolver
            # looks there too, so accept it as the directory when it exists.
            gui = path / "gui"
            return gui if gui.is_dir() else path
        return None

    @property
    def relative(self) -> str:
        """Repo-relative directory, the spelling used in the allow-list."""
        if self.directory is None:
            return self.id
        return self.directory.relative_to(_ROOT).as_posix()

    @property
    def help_file(self) -> pathlib.Path | None:
        return self.directory / "help.md" if self.directory else None

    @property
    def guide_file(self) -> pathlib.Path | None:
        return self.directory / "guide.json" if self.directory else None

    def has_help(self) -> bool:
        return self.help_file is not None and self.help_file.is_file()

    def has_guide(self) -> bool:
        return self.guide_file is not None and self.guide_file.is_file()

    def is_modern(self) -> bool:
        return self.has_help() and self.has_guide()


def gui_plugins() -> list[GuiPlugin]:
    """Return every plugin whose manifest declares a GUI entry point."""
    found: list[GuiPlugin] = []
    for manifest in sorted(_PLUGINS.rglob("manifest.json")):
        if any(marker in manifest.as_posix() for marker in _SKIP_MARKERS):
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not (data.get("entrypoints") or {}).get("gui"):
            continue
        found.append(GuiPlugin(manifest, data))
    return found


def allowlisted() -> set[str]:
    """Return the not-yet-modernised plugin directories."""
    if not _ALLOWLIST.is_file():
        return set()
    return {
        line.strip()
        for line in _ALLOWLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_gui_plugins_are_discoverable():
    """The enumeration itself must not silently collapse to nothing.

    Every other test here is a loop over ``gui_plugins()``; if the glob or the
    manifest key ever changed, they would all pass by finding no plugins at all.
    """
    plugins = gui_plugins()
    assert len(plugins) > 50, f"only found {len(plugins)} GUI plugins — enumeration broke"
    unresolved = [p.id for p in plugins if p.directory is None]
    assert not unresolved, (
        "these manifests name a GUI module that is not on disk: " + ", ".join(unresolved)
    )


def test_every_gui_plugin_has_help_and_guide():
    """A plugin outside the allow-list ships both files."""
    missing = []
    allowed = allowlisted()
    for plugin in gui_plugins():
        if plugin.relative in allowed or plugin.is_modern():
            continue
        lacks = []
        if not plugin.has_help():
            lacks.append("help.md")
        if not plugin.has_guide():
            lacks.append("guide.json")
        missing.append(f"  {plugin.relative} ({plugin.id}) — no {' and no '.join(lacks)}")
    assert not missing, (
        "these GUI plugins have no help/guide and are not on the allow-list:\n"
        + "\n".join(missing)
        + "\n\nWrite the two files beside the tool module — no code change is "
        "needed. Do not add the plugin to test/plugin_help_guide_allowlist.txt "
        "to silence this; that list only shrinks."
    )


def test_allowlist_has_no_stale_entries():
    """A modernised plugin must be struck from the allow-list."""
    plugins = {p.relative: p for p in gui_plugins()}
    stale = []
    unknown = []
    for entry in sorted(allowlisted()):
        plugin = plugins.get(entry)
        if plugin is None:
            unknown.append(entry)
        elif plugin.is_modern():
            stale.append(entry)
    assert not stale, (
        "these plugins now ship help.md and guide.json — remove them from "
        "test/plugin_help_guide_allowlist.txt:\n  " + "\n  ".join(stale)
    )
    assert not unknown, (
        "these allow-list entries match no GUI plugin (renamed or deleted?):\n  "
        + "\n  ".join(unknown)
    )


@pytest.mark.parametrize(
    "plugin", [p for p in gui_plugins() if p.has_guide()], ids=lambda p: p.id
)
def test_guide_is_a_tour_not_a_slideshow(plugin: GuiPlugin):
    """A shipped ``guide.json`` parses, has real steps, and waits on the user.

    The last part is the point of the format: a tour that only narrates teaches
    nothing, because someone who watched a button being pressed has not learned
    where it is. At least one step must hand control back with ``await``.
    """
    raw = json.loads(plugin.guide_file.read_text(encoding="utf-8"))
    steps = raw.get("steps", []) if isinstance(raw, dict) else raw
    assert isinstance(steps, list), f"{plugin.relative}/guide.json is not a list of steps"
    assert len(steps) >= _MIN_STEPS, (
        f"{plugin.relative}/guide.json has {len(steps)} step(s); a guide needs "
        f"at least {_MIN_STEPS} to say where to start and what to check"
    )
    for index, step in enumerate(steps):
        assert isinstance(step, dict), f"{plugin.relative}/guide.json step {index} is not an object"
        assert step.get("title"), f"{plugin.relative}/guide.json step {index} has no title"
        assert step.get("text"), f"{plugin.relative}/guide.json step {index} has no text"
    assert any(step.get("await") for step in steps), (
        f"{plugin.relative}/guide.json never waits for the user — every step "
        "narrates. Give at least one step an 'await' so the user presses the "
        "button themselves."
    )


@pytest.mark.parametrize(
    "plugin", [p for p in gui_plugins() if p.has_guide()], ids=lambda p: p.id
)
def test_guide_steps_point_at_real_widgets(plugin: GuiPlugin):
    """Every ``target`` names a section that exists in the tool's view spec.

    A step whose target cannot be resolved is *shown centred* rather than
    skipped, so a typo does not fail at runtime — it silently degrades the tour
    into the slideshow it was written not to be. Checked statically against the
    view spec; a tool with no view spec (``action`` targets, hand-built widgets)
    is out of scope here.
    """
    view_specs = sorted(plugin.directory.glob("*view.json"))
    if not view_specs:
        pytest.skip(f"{plugin.relative} has no view spec to check targets against")

    # The two namespaces are kept apart on purpose. A custom section is declared
    # ``{"type": "custom", "key": "path_list", "target": "files"}`` — ``files``
    # is what the runtime resolves for ``{"attr": …}`` and ``path_list`` is what
    # it resolves for ``{"key": …}``. Pooling them into one set makes a step
    # spelled ``{"key": "files"}`` pass here and resolve to nothing at run time,
    # which is exactly the silent degradation this test exists to prevent.
    keys: set[str] = set()
    attrs: set[str] = set()
    for spec in view_specs:
        try:
            data = json.loads(spec.read_text(encoding="utf-8"))
        except Exception:
            continue
        _collect_view_names(data, keys, attrs)

    raw = json.loads(plugin.guide_file.read_text(encoding="utf-8"))
    steps = raw.get("steps", []) if isinstance(raw, dict) else raw
    unresolved = []
    for step in steps:
        target = step.get("target") or {}
        # ``action``/``name``/``tab``/``panel`` point at things that live in code
        # or in a shell, not in the view spec. Only the two that must name a spec
        # entry are checked, each against its own namespace.
        for field, known in (("attr", attrs), ("key", keys)):
            name = target.get(field)
            if name and str(name) not in known:
                other = keys if field == "attr" else attrs
                hint = (
                    f" — it is declared as {'key' if field == 'attr' else 'attr/target'}, "
                    f"so use {{'{'key' if field == 'attr' else 'attr'}': {name!r}}}"
                    if str(name) in other
                    else ""
                )
                unresolved.append(
                    f"step {step.get('title')!r} targets {field}={name!r}{hint}"
                )
    assert not unresolved, (
        f"{plugin.relative}/guide.json points at controls that are not in its "
        f"view spec — these steps will silently show centred instead of "
        f"highlighting anything:\n  " + "\n  ".join(unresolved)
    )


def _collect_view_names(node, keys: set[str], attrs: set[str]) -> None:
    """Collect a view spec's ``key`` names and its ``attr``/``target`` names.

    Separately, because the guided tour resolves them through different lookups:
    ``{"key": …}`` matches a section's ``key``, while ``{"attr": …}`` matches its
    ``attr`` **or** its ``target`` (several section types name the bound
    attribute ``target``).
    """
    if isinstance(node, dict):
        value = node.get("key")
        # Only a *section* answers ``{"key": …}`` at run time, and a section is
        # what carries a ``type``. Table columns, plot series and legend entries
        # use ``key`` too, for their own namespaces — collecting those made the
        # check accept a target the resolver would never find. It cost two
        # unresolved steps (``{"key": "correlation"}`` matched an FRC table
        # column; ``{"key": "track"}`` a tracking one) that this test passed and
        # only the tour harness caught.
        if isinstance(value, str) and isinstance(node.get("type"), str):
            keys.add(value)
        for field in ("attr", "target"):
            value = node.get(field)
            if isinstance(value, str):
                attrs.add(value)
        for value in node.values():
            _collect_view_names(value, keys, attrs)
    elif isinstance(node, list):
        for item in node:
            _collect_view_names(item, keys, attrs)


@pytest.mark.parametrize(
    "plugin", [p for p in gui_plugins() if p.has_help()], ids=lambda p: p.id
)
def test_help_is_substantive_and_links_live(plugin: GuiPlugin):
    """A shipped ``help.md`` says something, and its doc links resolve.

    The house rule is that help links are *live*: the modal routes a
    documentation page to the ChiSurf documentation browser, so a link to a page
    that is not there is a dead cross-reference the reader only discovers by
    clicking it.
    """
    import re

    text = plugin.help_file.read_text(encoding="utf-8")
    assert len(text) >= _MIN_HELP_CHARS, (
        f"{plugin.relative}/help.md is {len(text)} characters — that is a stub. "
        "Say what the method measures, which settings decide the answer, and "
        "what to check before believing the result."
    )
    broken = []
    for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", text):
        link = match.group(1).strip()
        if link.startswith(("http://", "https://", "doi:", "#", "mailto:")):
            continue
        if re.match(r"^10\.\d{4,}/", link):
            continue
        target = (_ROOT / link.split("#")[0]).resolve()
        if not target.exists():
            broken.append(link)
    assert not broken, (
        f"{plugin.relative}/help.md links to documentation that is not there:\n  "
        + "\n  ".join(broken)
    )
