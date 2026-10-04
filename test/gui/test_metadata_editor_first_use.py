"""Demand catalog loading and compact completer contracts in fresh interpreters."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def run_fresh(source, tmp_path):
    """Exercise cold imports without pytest's preloaded GUI or dictionary cache."""
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
               MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"))
    result = subprocess.run([sys.executable, "-c", textwrap.dedent(source)],
                            cwd=Path(__file__).resolve().parents[2], env=env,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_and_empty_editor_do_not_load_dictionary(tmp_path):
    """An unused catalog must not delay an ordinary fit or an empty metadata pane."""
    run_fresh('''
        from qtpy import QtWidgets
        from chisurf.core.fio.mmcif import pdbx_metadata as facade
        calls = []
        facade.get_pdbx_metadata_keys = lambda: calls.append('keys') or ['_custom.key']
        facade.get_pdbx_metadata_descriptions = lambda: calls.append('descriptions') or {}
        import chisurf.gui.widgets.metadata_editor as module
        assert calls == [], calls
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = module.MetadataEditor()
        editor.set_data([])
        assert calls == [], calls
        keys = module.ALL_METADATA_KEYS
        assert isinstance(keys, list) and '_custom.key' in keys
        assert calls.count('keys') == 1
        assert module.ALL_METADATA_KEYS is keys
        assert calls.count('keys') == 1
    ''', tmp_path)


def test_key_model_does_not_allocate_standard_items(tmp_path):
    """Keep all keys and descriptions without one heavyweight Qt item per key."""
    run_fresh('''
        from qtpy import QtCore, QtGui, QtWidgets
        from chisurf.core.fio.mmcif import pdbx_metadata as facade
        keys = ['_catalog.key_' + str(i) for i in range(10000)]
        facade.get_pdbx_metadata_keys = lambda: keys
        facade.get_pdbx_metadata_descriptions = lambda: {'_catalog.key_10': 'Full description'}
        import chisurf.gui.widgets.metadata_editor as module
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        def forbidden(*args, **kwargs):
            raise AssertionError('Dictionary completers must not materialize QStandardItems')
        QtGui.QStandardItem = forbidden
        editor = module.MetadataEditor()
        editor.set_data([{'key': '_catalog.key_10', 'value': 'x'},
                         {'key': '_custom.extra', 'value': 'y'}])
        first = editor.table.cellWidget(0, 0)
        second = editor.table.cellWidget(1, 0)
        assert first.model() is second.model()
        assert first.count() == len(module.ALL_METADATA_KEYS) + 1
        index = first.findText('_catalog.key_10')
        assert first.itemData(index, QtCore.Qt.UserRole + 1) == 'Full description'
        assert first.findText('_custom.extra') >= 0
        assert editor.get_data() == [{'key': '_catalog.key_10', 'value': 'x'},
                                     {'key': '_custom.extra', 'value': 'y'}]
        assert not first.model().index(-1, 0).isValid()
    ''', tmp_path)


def test_large_catalog_layout_does_not_scan_every_key(tmp_path):
    """Opening a metadata pane must not measure 10,000 labels per combobox."""
    run_fresh('''
        from qtpy import QtCore, QtWidgets
        from chisurf.core.fio.mmcif import pdbx_metadata as facade
        facade.get_pdbx_metadata_keys = lambda: ['_catalog.key_' + str(i) for i in range(10000)]
        facade.get_pdbx_metadata_descriptions = lambda: {}
        import chisurf.gui.widgets.metadata_editor as module
        calls = []
        class CountingModel(module._MetadataKeyModel):
            def data(self, index, role=QtCore.Qt.DisplayRole):
                calls.append(role)
                return super().data(index, role)
        module._MetadataKeyModel = CountingModel
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = module.MetadataEditor()
        editor.set_data([{'key': 'pH', 'value': '7'},
                         {'key': '_catalog.key_9999', 'value': 'late dictionary key'},
                         {'key': '_custom.extra', 'value': 'custom key'}])
        editor.resize(760, 320)
        editor.show()
        app.processEvents()
        assert len(calls) < 1000, len(calls)
        assert editor.table.cellWidget(0, 0).count() > 10000
    ''', tmp_path)


def test_metadata_popup_has_uniform_rows_and_keeps_catalog(tmp_path):
    """The styled popup must not request every role for every dictionary row."""
    run_fresh('''
        from qtpy import QtCore, QtWidgets
        from chisurf.core.fio.mmcif import pdbx_metadata as facade
        facade.get_pdbx_metadata_keys = lambda: ['_catalog.key_' + str(i) for i in range(10000)]
        facade.get_pdbx_metadata_descriptions = lambda: {'_catalog.key_10': 'Full description'}
        import chisurf.gui.widgets.metadata_editor as module
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        editor = module.MetadataEditor()
        editor.set_data([{'key': '_catalog.key_10', 'value': 'x'}])
        combo = editor.table.cellWidget(0, 0)
        assert combo.view().uniformItemSizes()
        editor.show()
        combo.showPopup()
        app.processEvents()
        assert combo.view().model().rowCount() == len(module.ALL_METADATA_KEYS)
        index = combo.findText('_catalog.key_10')
        assert combo.itemData(index, QtCore.Qt.UserRole + 1) == 'Full description'
        assert isinstance(combo.view().itemDelegate(), module.TooltipDelegate)
        combo.hidePopup()
    ''', tmp_path)


def test_dictionary_constant_survives_from_and_star_imports(tmp_path):
    """The historical public catalog remains a real list for explicit imports."""
    run_fresh('''
        from chisurf.gui.widgets.metadata_editor import *
        assert isinstance(ALL_METADATA_KEYS, list)
        assert MetadataEditor.__name__ == 'MetadataEditor'
        from chisurf.gui.widgets.metadata_editor import ALL_METADATA_KEYS
        assert isinstance(ALL_METADATA_KEYS, list)
        assert len(ALL_METADATA_KEYS) > 5000
        assert '_flr_sample.entity_assembly_id' in ALL_METADATA_KEYS
    ''', tmp_path)
