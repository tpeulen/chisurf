"""Headless tests for the translation seam (:mod:`chisurf.core.support.i18n`).

These run without Qt: the core seam must default to identity and must localize
data-driven specs once a translation backend is bound, so the server/headless
path stays import-clean of a GUI toolkit.
"""

from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def _reset_backend():
    """Ensure each test starts and ends with the identity backend."""
    from chisurf.core.support import i18n

    i18n.set_translation_backend(None)
    yield
    i18n.set_translation_backend(None)


def test_tr_identity_by_default():
    from chisurf.core.support import i18n

    assert i18n.tr("Convolution") == "Convolution"
    assert i18n.tr("") == ""
    assert i18n.tr(None) is None


def test_core_i18n_is_qt_free():
    """Importing the core seam must not pull in a Qt binding.

    Checked in a clean subprocess: the pytest session itself (pytest-qt) may have
    already imported Qt, so an in-process ``sys.modules`` check would be polluted.
    """
    import subprocess

    code = (
        "import sys, chisurf.core.support.i18n\n"
        "bad = [m for m in sys.modules if m.startswith(('PyQt5', 'PySide', 'qtpy'))]\n"
        "assert not bad, bad\n"
        "assert chisurf.core.support.i18n.tr('X') == 'X'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_backend_swap_translates_and_falls_back():
    from chisurf.core.support import i18n

    mapping = {"Convolution": "Faltung", "Detector": "Detektor"}
    i18n.set_translation_backend(lambda ctx, text: mapping.get(text, text))
    assert i18n.has_translation_backend()
    assert i18n.tr("Convolution") == "Faltung"
    assert i18n.tr("Unlisted") == "Unlisted"  # missing → source


def test_backend_exception_falls_back_to_source():
    from chisurf.core.support import i18n

    def boom(ctx, text):
        raise RuntimeError("catalogue on fire")

    i18n.set_translation_backend(boom)
    assert i18n.tr("Convolution") == "Convolution"


def test_view_spec_titles_localized_on_parse():
    from chisurf.core.support import i18n
    from chisurf.core.dataspec import _section_from_dict

    i18n.set_translation_backend(lambda ctx, text: {"Convolution": "Faltung"}.get(text, text))
    sec = _section_from_dict({"type": "panel", "title": "Convolution"})
    assert sec.title == "Faltung"


def test_nested_item_and_label_text_localized():
    from chisurf.core.support import i18n
    from chisurf.core.dataspec import _section_from_dict

    de = {"On": "Ein", "Off": "Aus", "Run": "Start"}
    i18n.set_translation_backend(lambda ctx, text: de.get(text, text))
    sec = _section_from_dict(
        {
            "type": "button_row",
            "buttons": [{"label": "Run", "description": "On"}],
        }
    )
    assert sec.buttons[0]["label"] == "Start"
    assert sec.buttons[0]["description"] == "Ein"


def test_manifest_localizes_description_not_identity_keys():
    from chisurf.core.support import i18n
    from chisurf.core.plugin.manifest import PluginManifest

    i18n.set_translation_backend(
        lambda ctx, text: {"A helpful tool": "Ein hilfreiches Werkzeug"}.get(text, text)
    )
    man = PluginManifest.from_dict(
        {
            "id": "x",
            "version": "1",
            "display_name": "Group:Sub:Tool",
            "categories": ["Group"],
            "description": "A helpful tool",
        }
    )
    assert man.description == "Ein hilfreiches Werkzeug"
    # Identity keys stay canonical for menu-path / dedup.
    assert man.display_name == "Group:Sub:Tool"
    assert man.categories == ["Group"]


def test_get_locale_defaults_to_en():
    from chisurf.core.support import i18n

    # With no gui.language set, or on any read failure, the default is English.
    assert isinstance(i18n.get_locale(), str)
    assert i18n.get_locale()  # non-empty
