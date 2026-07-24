"""Headless tests for the Settings UI language selector (offscreen Qt).

Covers language discovery, the settings-tree editor dispatch (the `_get_setting_path`
fix that makes the value-column editors fire), and that picking a language stores
the locale *code*, persists it, and switches the translation live.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("qtpy")
from qtpy import QtCore, QtWidgets  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


def test_available_languages_and_display_names(qapp):
    from chisurf.gui import i18n as gi18n

    langs = gi18n.available_languages()
    assert langs[0] == "en"  # source language first
    assert "de" in langs  # shipped German catalogue discovered
    assert "fr" in langs  # shipped French catalogue discovered (second locale)
    assert gi18n.language_display_name("en") == "English"
    assert gi18n.language_display_name("de") == "Deutsch"
    assert gi18n.language_display_name("fr") == "Français"
    assert gi18n.language_display_name("xx") == "xx"  # unknown → bare code


def test_live_apply_and_remove(qapp):
    from chisurf.core import i18n as ci18n
    from chisurf.gui import i18n as gi18n

    try:
        assert gi18n.apply_language("de") == "de"
        assert ci18n.tr("Convolution") == "Faltung"
        # switching back to English removes the catalogue (no stale translation)
        assert gi18n.apply_language("en") == "en"
        assert ci18n.tr("Convolution") == "Convolution"
    finally:
        gi18n.apply_language("en")
        ci18n.set_translation_backend(None)


def _find_value_index(model, delegate, target_path):
    def walk(item):
        for r in range(item.rowCount()):
            key_item = item.child(r, 0)
            val_item = item.child(r, 1)
            if key_item is None:
                continue
            if val_item is not None:
                idx = model.indexFromItem(val_item)
                if delegate._get_setting_path(idx) == target_path:
                    return idx
            if key_item.hasChildren():
                got = walk(key_item)
                if got is not None:
                    return got
        return None

    return walk(model.invisibleRootItem())


def test_setting_path_resolves_leaf_from_value_column(qapp):
    """Resolve a leaf setting path from its value (column-1) index.

    Regression guard: `_get_setting_path` must return the full dotted path from
    the value column, or none of the per-setting editors ever fire.
    """
    import chisurf as cs
    from chisurf.gui.widgets.settings_editor import SettingsEditor

    src = pathlib.Path(cs.__file__).parent / "core" / "settings" / "settings_chisurf.yaml"
    tmp = pathlib.Path(tempfile.mkdtemp()) / "settings_chisurf.yaml"
    shutil.copyfile(src, tmp)
    ed = SettingsEditor(filename=str(tmp))

    lang_idx = _find_value_index(ed.model, ed.delegate, "gui.language")
    theme_idx = _find_value_index(ed.model, ed.delegate, "gui.style_sheet")
    assert lang_idx is not None and lang_idx.isValid()
    assert theme_idx is not None and theme_idx.isValid()

    opt = QtWidgets.QStyleOptionViewItem()
    lang_editor = ed.delegate.createEditor(ed.tree_view, opt, lang_idx)
    assert isinstance(lang_editor, QtWidgets.QComboBox)
    assert lang_editor.property("isLanguage") is True
    codes = {lang_editor.itemData(i) for i in range(lang_editor.count())}
    assert {"en", "de"} <= codes

    theme_editor = ed.delegate.createEditor(ed.tree_view, opt, theme_idx)
    assert isinstance(theme_editor, QtWidgets.QComboBox)  # theme combo revived by the fix


def test_pick_language_stores_code_persists_and_applies(qapp, monkeypatch):
    import chisurf as cs
    from chisurf.core.settings import settings_utils
    from chisurf.gui.widgets.settings_editor import SettingsEditor

    # Do not mutate the real user settings file — capture the persisted code.
    persisted = {}
    monkeypatch.setattr(settings_utils, "set_language", lambda code: persisted.setdefault("code", code) or True)

    applied = {}
    from chisurf.gui import i18n as gi18n

    monkeypatch.setattr(gi18n, "apply_language", lambda code, app=None: applied.setdefault("code", code) or code)

    src = pathlib.Path(cs.__file__).parent / "core" / "settings" / "settings_chisurf.yaml"
    tmp = pathlib.Path(tempfile.mkdtemp()) / "settings_chisurf.yaml"
    shutil.copyfile(src, tmp)
    ed = SettingsEditor(filename=str(tmp))

    idx = _find_value_index(ed.model, ed.delegate, "gui.language")
    opt = QtWidgets.QStyleOptionViewItem()
    editor = ed.delegate.createEditor(ed.tree_view, opt, idx)
    ed.delegate.setEditorData(editor, idx)
    assert editor.currentData() == "en"

    editor.setCurrentIndex(editor.findData("de"))
    ed.delegate.setModelData(editor, ed.model, idx)

    assert idx.data(QtCore.Qt.UserRole) == "de"  # stores the code, not "Deutsch"
    assert persisted.get("code") == "de"  # persisted via set_language
    assert applied.get("code") == "de"  # live-applied

    # reopening the editor preselects the stored language
    editor2 = ed.delegate.createEditor(ed.tree_view, opt, idx)
    ed.delegate.setEditorData(editor2, idx)
    assert editor2.currentData() == "de"
