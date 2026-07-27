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

from chisurf.core.cli import _read_plugin_metadata as _read_cli_metadata
from chisurf.plugins import _read_plugin_metadata

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
