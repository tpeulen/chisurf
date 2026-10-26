"""Plugin test files that pytest imports by bare basename have unique names.

A test directory without ``__init__.py`` puts its files on ``sys.path`` and
imports each under its basename, so two such plugins both shipping
``test_core.py`` cannot be collected in one run ("import file mismatch") --
the full suite errors although each passes alone. Directories that import
sibling helpers by bare name (chimol's ``native_window``) must stay that way,
so the guard checks the names, not the packaging.
"""

from __future__ import annotations

import collections
import pathlib

PLUGINS = pathlib.Path(__file__).resolve().parents[1] / "chisurf" / "plugins"


def test_rootdir_style_plugin_test_files_have_unique_basenames():
    """No basename is shared by two test files outside a package."""
    by_name = collections.defaultdict(list)
    for path in PLUGINS.rglob("test_*.py"):
        if "cookiecutter" in str(path) or (path.parent / "__init__.py").exists():
            continue
        by_name[path.name].append(str(path.relative_to(PLUGINS)))
    clashes = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    assert not clashes, clashes
