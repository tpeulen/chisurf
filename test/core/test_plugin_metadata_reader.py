"""The AST scan that reads plugin metadata must never drop a plugin silently.

Plugin discovery (``chisurf.plugins``) and the ``csc`` command scan every
plugin's ``__init__.py`` with :mod:`ast` instead of importing it, so a plugin
appears in the menu and on the command line without paying its import cost. Both
scanners run inside a bare ``except Exception: continue``, which means any defect
in them removes a plugin from the application without a warning. These tests pin
the two contracts that make that impossible: the readers always return their full
tuple, and they decode source the way the interpreter does.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.core.cli import _discover_plugin_metadata
from chisurf.core.cli import _read_plugin_metadata as _read_cli_metadata
from chisurf.plugins import _read_manifest_metadata, _read_plugin_metadata

#: A plugin declaring a non-UTF-8 source encoding, exactly as PEP 263 allows and
#: as the interpreter would import it.
LATIN1_PLUGIN = (
    b"# -*- coding: latin-1 -*-\n"
    b'"""Caf\xe9 plugin."""\n'
    b'name = "Spectroscopy:Caf\xe9:Tool"\n'
    b'cli_entrypoint = " cafe=chisurf.plugins.cafe.cli:main "\n'
    b"cli_only = True\n"
    b"menu_hidden = True\n"
)


@pytest.fixture
def plugin_init(tmp_path: pathlib.Path):
    """Return a factory writing a plugin ``__init__.py`` with the given bytes."""

    def _write(source: bytes, name: str = "plugin") -> pathlib.Path:
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        init_py = plugin_dir / "__init__.py"
        init_py.write_bytes(source)
        return init_py

    return _write


def test_reader_returns_five_values_for_a_plain_plugin(plugin_init):
    """A well-formed plugin yields name, description and the three flags."""
    init_py = plugin_init(
        b'"""A tool."""\n'
        b'name = "Spectroscopy:Fluorescence decay:Tool"\n'
        b'cli_entrypoint = "tool=chisurf.plugins.tool.cli:main"\n'
        b"cli_only = True\n"
        b"menu_hidden = True\n"
    )
    name, description, cli_entrypoint, cli_only, menu_hidden = _read_plugin_metadata(init_py)
    assert name == "Spectroscopy:Fluorescence decay:Tool"
    assert description == "A tool."
    assert cli_entrypoint == "tool=chisurf.plugins.tool.cli:main"
    assert cli_only is True
    assert menu_hidden is True


def test_flags_default_to_false_when_not_declared(plugin_init):
    """Omitted ``cli_only``/``menu_hidden`` mean a visible, GUI-capable plugin."""
    init_py = plugin_init(b'"""A tool."""\nname = "Tools:Tool"\n')
    name, _description, cli_entrypoint, cli_only, menu_hidden = _read_plugin_metadata(init_py)
    assert name == "Tools:Tool"
    assert cli_entrypoint is None
    assert cli_only is False
    assert menu_hidden is False


@pytest.mark.parametrize(
    "source",
    [
        pytest.param(b'name = "Tools:Tool"\ndef (\n', id="syntax-error"),
        pytest.param(b"", id="empty"),
    ],
)
def test_unparseable_source_still_returns_five_values(plugin_init, source):
    """A broken ``__init__.py`` degrades to an empty tuple, never a short one."""
    assert len(_read_plugin_metadata(plugin_init(source))) == 5


def test_missing_file_returns_five_values(tmp_path):
    """A plugin directory without ``__init__.py`` returns the empty tuple."""
    assert _read_plugin_metadata(tmp_path / "absent" / "__init__.py") == (
        None,
        None,
        None,
        False,
        False,
    )


def test_non_utf8_source_encoding_is_honoured(plugin_init):
    """A PEP 263 coding cookie decides the encoding, as it does on import.

    Reading the file as UTF-8 raised on such a plugin, and the failure branch
    returned three values where every caller unpacks five — the resulting
    ``ValueError`` was swallowed by the discovery loop and the plugin vanished
    from the menu and from ``csc``.
    """
    init_py = plugin_init(LATIN1_PLUGIN, name="cafe")
    name, description, cli_entrypoint, cli_only, menu_hidden = _read_plugin_metadata(init_py)
    assert name == "Spectroscopy:Café:Tool"
    assert description == "Café plugin."
    assert cli_entrypoint == "cafe=chisurf.plugins.cafe.cli:main"
    assert cli_only is True
    assert menu_hidden is True


def test_cli_reader_honours_non_utf8_source_encoding(plugin_init):
    """``csc``'s own scanner must decode a plugin the same way discovery does."""
    init_py = plugin_init(LATIN1_PLUGIN, name="cafe")
    name, description, cli_entrypoint = _read_cli_metadata(init_py)
    assert name == "Spectroscopy:Café:Tool"
    assert description == "Café plugin."
    assert cli_entrypoint == "cafe=chisurf.plugins.cafe.cli:main"


def test_cli_reader_returns_three_values_for_broken_sources(plugin_init, tmp_path):
    """Both failure modes of the ``csc`` scanner keep the tuple shape."""
    assert _read_cli_metadata(tmp_path / "absent" / "__init__.py") == (None, None, None)
    assert _read_cli_metadata(plugin_init(b"def (\n")) == (None, None, None)


# --- The display name comes from the manifest, in ``csc`` as in the GUI --------
#
# ``manifest.json`` is the plugin contract; the module-level ``name`` literal is
# the older convention. GUI discovery has always read the manifest first, while
# ``csc`` preferred the literal, so a plugin whose manifest renamed it kept its
# stale name on the command line.

#: A user plugin whose manifest disagrees with its ``__init__.py`` literal.
RENAMED_PLUGIN_INIT = (
    b'"""A renamed tool."""\n'
    b'name = "Tools:Old Name"\n'
    b'cli_entrypoint = "renamed=chisurf.plugins.renamed.cli:main"\n'
)

RENAMED_PLUGIN_MANIFEST = (
    '{"id": "renamed", "display_name": "Tools:New Name", "version": "1.0.0",'
    ' "entrypoints": {"cli": "renamed=chisurf.plugins.renamed.cli:main"}}'
)


@pytest.fixture
def user_plugin(tmp_path: pathlib.Path, monkeypatch):
    """Return a factory writing a plugin into a throw-away user plugin directory.

    :func:`_discover_plugin_metadata` scans ``~/.chisurf/plugins`` alongside the
    built-in tree, so pointing ``Path.home()`` at ``tmp_path`` gives the scan a
    plugin whose manifest and literal we control.
    """
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

    def _write(name: str, source: bytes, manifest: str | None = None) -> pathlib.Path:
        plugin_dir = tmp_path / ".chisurf" / "plugins" / name
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "__init__.py").write_bytes(source)
        if manifest is not None:
            (plugin_dir / "manifest.json").write_text(manifest, encoding="utf-8")
        return plugin_dir

    return _write


def _discovered_user_plugins() -> dict[str, dict]:
    """Return the discovered user-plugin metadata keyed by module name."""
    return {
        str(entry["module_name"]): entry
        for entry in _discover_plugin_metadata()
        if entry["source"] == "user"
    }


def test_cli_display_name_comes_from_the_manifest(user_plugin):
    """A manifest ``display_name`` wins over a stale ``__init__.py`` literal."""
    user_plugin("renamed", RENAMED_PLUGIN_INIT, RENAMED_PLUGIN_MANIFEST)
    assert _discovered_user_plugins()["renamed"]["plugin_name"] == "Tools:New Name"


def test_cli_display_name_falls_back_to_the_literal_without_a_manifest(user_plugin):
    """A plugin shipping no manifest keeps the older AST-scanned convention."""
    user_plugin("legacy", RENAMED_PLUGIN_INIT)
    assert _discovered_user_plugins()["legacy"]["plugin_name"] == "Tools:Old Name"


def test_cli_and_gui_agree_on_every_built_in_display_name():
    """``csc`` and the menu must never label the same plugin differently.

    Eleven shipped plugins declare a ``name`` literal their manifest has since
    renamed (``Tools:mmfdb-admin`` vs ``Tools:MMFDB Admin``, ``Main:Tools:ndXplorer``
    vs ``Main:Tools:ndX``, …). Both readers now resolve to the manifest.
    """
    mismatches = []
    for entry in _discover_plugin_metadata():
        if entry["source"] != "built-in":
            continue
        gui = _read_manifest_metadata(pathlib.Path(str(entry["package_dir"])))
        if gui is None:
            continue
        if gui["plugin_name"] != entry["plugin_name"]:
            mismatches.append((entry["module_path"], entry["plugin_name"], gui["plugin_name"]))
    assert not mismatches
