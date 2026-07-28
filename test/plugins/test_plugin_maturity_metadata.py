"""A plugin that declares itself deprecated/experimental must say so where hosts read.

The maturity flags (`experimental` / `deprecated`) are **manifest-only**:
`navigation.apply_manifest_flags()` reads
them from `manifest.json`, and the legacy AST scan in `chisurf.plugins`
(`_read_plugin_metadata`) reads only `name`, `cli_entrypoint`, `cli_only` and
`menu_hidden`. A module-level ``deprecated = True`` in a manifest-less plugin is
therefore dead text — which is exactly how `vv_vh_anisotropy` carried a
deprecation and a replacement message that nothing could ever show (RF-518).

These tests pin the rule: a flag declared in ``__init__.py`` must be mirrored in
the plugin's manifest.
"""

from __future__ import annotations

import ast
import json
import pathlib

from chisurf.core.plugin.manifest import load_manifest, validate_manifest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPO_ROOT / "chisurf" / "plugins"

#: Manifest keys carrying a maturity flag, and the module-level variable holding
#: its message in the legacy (pre-manifest) form.
MATURITY_KEYS = ("deprecated", "experimental")


def _module_level_flags(init_py: pathlib.Path) -> set[str]:
    """Return the maturity flags a plugin ``__init__.py`` assigns ``True``.

    Parameters
    ----------
    init_py : pathlib.Path
        Path to the plugin's ``__init__.py``.

    Returns
    -------
    set of str
        The subset of :data:`MATURITY_KEYS` assigned a literal ``True`` at
        module level.
    """
    try:
        tree = ast.parse(init_py.read_bytes(), filename=str(init_py))
    except Exception:
        return set()
    flags: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id in MATURITY_KEYS
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
            ):
                flags.add(target.id)
    return flags


def _plugin_inits() -> list[pathlib.Path]:
    """Return every built-in plugin ``__init__.py``, skipping the cookiecutter scaffold."""
    return [
        p
        for p in sorted(PLUGIN_ROOT.rglob("__init__.py"))
        if not any("{{" in part for part in p.parts)
    ]


def test_module_level_maturity_flags_are_mirrored_in_the_manifest():
    """A flag only hosts cannot see is a flag the user never sees."""
    unmirrored: list[str] = []
    for init_py in _plugin_inits():
        flags = _module_level_flags(init_py)
        if not flags:
            continue
        manifest = load_manifest(init_py.parent / "manifest.json")
        for flag in sorted(flags):
            if manifest is None or not getattr(manifest, flag, False):
                unmirrored.append(f"{init_py.relative_to(REPO_ROOT)}: {flag}")
    assert not unmirrored, (
        "these plugins declare a maturity flag that no host can read — "
        f"declare it in manifest.json: {unmirrored}"
    )


def test_a_deprecated_plugin_names_what_replaces_it():
    """A deprecation without a message falls back to wording that names no successor."""
    messageless: list[str] = []
    for manifest_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        if any("{{" in part for part in manifest_path.parts):
            continue
        manifest = load_manifest(manifest_path)
        if manifest is None or not manifest.deprecated:
            continue
        if not manifest.deprecation_message:
            messageless.append(str(manifest_path.relative_to(REPO_ROOT)))
    assert not messageless, (
        "deprecated without a deprecation_message — the banner then tells the user to "
        f"stop using the tool without saying what to use instead: {messageless}"
    )


def _discovery_records() -> dict[str, dict]:
    """Return every plugin discovery record, keyed by its package directory."""
    from chisurf.plugins import iter_plugins

    return {str(record["package_dir"]): record for record in iter_plugins()}


def test_discovery_record_carries_the_maturity_flags():
    """Every record has the keys, so a host never has to guess a missing one is ``False``."""
    records = _discovery_records()
    assert records, "plugin discovery found nothing"
    for path, record in records.items():
        for key in ("experimental", "deprecated"):
            assert isinstance(record.get(key), bool), f"{path}: {key} is not a bool"
        for key in ("experimental_message", "deprecation_message"):
            assert isinstance(record.get(key), str), f"{path}: {key} is not a str"


def test_every_manifest_flag_reaches_the_discovery_record():
    """A flag the discovery record drops can be rendered by no menu (RF-517).

    Before this, the record carried ``menu_hidden`` / ``manifest_id`` /
    ``state_namespace`` and nothing about maturity, so the ribbon could not mark an
    entry even if it wanted to — the flag showed only for a tool a navigation hub
    happened to embed as a panel.
    """
    records = _discovery_records()
    dropped: list[str] = []
    for manifest_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        if any("{{" in part for part in manifest_path.parts):
            continue
        manifest = load_manifest(manifest_path)
        if manifest is None:
            continue
        record = records.get(str(manifest_path.parent))
        if record is None:  # not a package (no __init__.py) — nothing discovers it
            continue
        for flag in MATURITY_KEYS:
            if getattr(manifest, flag, False) and not record.get(flag):
                dropped.append(f"{manifest_path.relative_to(REPO_ROOT)}: {flag}")
    assert not dropped, (
        "these manifests declare a maturity flag that plugin discovery drops, so no "
        f"menu can mark the tool: {dropped}"
    )


def test_the_flagged_message_travels_with_the_record():
    """The tool's own wording reaches the record, so hosts do not restate it."""
    records = _discovery_records()
    lifetime = records[str(PLUGIN_ROOT / "fluorescence_decay" / "lifetime_analysis")]
    assert lifetime["experimental"] is True
    assert "experimental" in lifetime["experimental_message"].lower()
    assert lifetime["deprecated"] is False
    assert lifetime["deprecation_message"] == ""


class TestVvVhAnisotropyDeprecation:
    """The tree's one self-declared deprecated plugin (RF-518)."""

    manifest_path = PLUGIN_ROOT / "vv_vh_anisotropy" / "manifest.json"

    def test_manifest_validates(self):
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        assert validate_manifest(data) == []

    def test_manifest_declares_the_deprecation_and_the_replacement(self):
        manifest = load_manifest(self.manifest_path)
        assert manifest is not None
        assert manifest.deprecated is True
        assert manifest.menu_hidden is True
        assert "G-Factor" in manifest.deprecation_message

    def test_the_module_does_not_restate_the_manifest_wording(self):
        """The GUI banner reads the message back rather than keeping a copy to drift."""
        source = (PLUGIN_ROOT / "vv_vh_anisotropy" / "__init__.py").read_text(encoding="utf-8")
        assert "load_manifest" in source
        assert source.count("Use the VV/VH G-Factor plugin") == 1
