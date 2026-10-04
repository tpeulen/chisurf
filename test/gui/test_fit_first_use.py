"""First-use import and real-widget contracts for TCSPC fit windows."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

NATIVE_SETUP = """
import numpy as np
from qtpy import QtCore, QtWidgets
import chisurf as cs
import chisurf.gui
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.models.description import tcspc_polarized
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
chisurf.gui.initialize_gui_executors()
raw = np.loadtxt('test/data/tcspc/ibh_sample/Decay_577D.txt', skiprows=9)
prompt = np.loadtxt('test/data/tcspc/ibh_sample/Prompt.txt', skiprows=9)
x = np.arange(len(raw), dtype=float) * 0.0141
fit = FitGroup(data=DataCurveGroup([DataCurve(
    x=x, y=raw[:, 1], ey=np.sqrt(np.maximum(raw[:, 1], 1)), name='Decay_577D'
)]), model_class=tcspc_polarized)
fit.fit_range = (522, 3793)
fit.model.set_dataset('response', DataCurve(x=x, y=prompt[:, 1], name='Prompt'))
fit.update()
cs.fits.append(fit)
from chisurf.gui.widgets.fitting import FitSubWindow
host = QtWidgets.QWidget()
window = FitSubWindow(fit, QtWidgets.QVBoxLayout(host))
"""


def run_fresh(source, tmp_path):
    """Run a contract outside pytest's already-imported GUI modules."""
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        IMP_BFF_GPU="off",
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MMFDB_SETTINGS_DIR=str(tmp_path / "mmfdb"),
    )
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_native_window_leaves_code_unbuilt(tmp_path):
    """A fresh native window must leave the hidden editor and plugin unloaded."""
    run_fresh(
        NATIVE_SETUP
        + """
import sys
assert getattr(window, 'code_editor', None) is None
assert 'chisurf.plugins.core.code_editor' not in sys.modules
assert window.stack.count() == 2
""",
        tmp_path,
    )


def test_real_code_button_reuses_editor(tmp_path):
    """Qt clicks build the real editor once and keep its navigation toolbar."""
    run_fresh(
        NATIVE_SETUP
        + """
from qtpy.QtTest import QTest
window.show()
app.processEvents()
assert getattr(window, 'code_editor', None) is None
QTest.mouseClick(window.flip_to_code_btn, QtCore.Qt.LeftButton)
app.processEvents()
from chisurf.plugins.core.code_editor import CodeEditor
assert isinstance(window.code_editor, CodeEditor)
assert window.stack.currentIndex() == 1
assert window.file_combo.count() > 0
assert window.func_combo.count() > 1
editor = window.code_editor
connections = editor.receivers(editor.symbolsChanged)
QTest.mouseClick(window.flip_to_code_btn, QtCore.Qt.LeftButton)
assert window.stack.currentIndex() == 0
QTest.mouseClick(window.flip_to_code_btn, QtCore.Qt.LeftButton)
assert window.code_editor is editor
assert editor.receivers(editor.symbolsChanged) == connections
assert window.stack.count() == 2
assert window._get_current_text_editor().external_definition_callback == window._open_external_definition
""",
        tmp_path,
    )


def test_project_code_face_builds_editor(tmp_path):
    """Restoring the code face must build it even before a Code click."""
    run_fresh(
        NATIVE_SETUP
        + """
assert getattr(window, 'code_editor', None) is None
assert window.set_project_plot_state({'stack_index': 1})
assert window.code_editor is not None
assert window.stack.currentIndex() == 1
assert window.flip_to_code_btn.isChecked()
assert window.flip_to_code_btn.text() == 'Plots'
""",
        tmp_path,
    )


def test_line_plot_import_is_isolated(tmp_path):
    """Resolving LinePlot must not preload optional plot implementations."""
    run_fresh(
        """
import sys
import chisurf.gui.plots as plots
line = plots.LinePlot
assert plots.LinePlot is line
for name in ('fitinfo', 'mfd_2d', 'mfd_map', 'residual_image',
             'sampling_diagnostics', 'posterior_graph', 'global_fit', 'global_tcspc'):
    assert 'chisurf.gui.plots.' + name not in sys.modules, name
assert 'chisurf.gui.widgets.metadata_editor' not in sys.modules
""",
        tmp_path,
    )


def test_plot_public_exports_and_submodules(tmp_path):
    """All intended plot classes and historical module imports remain usable."""
    run_fresh(
        """
import importlib
import chisurf.gui.plots as plots
exports = {
    'ConditionalScanPlot': 'conditional_scan', 'DeerPrCIPlot': 'deer_pr',
    'DistributionPlot': 'distribution', 'FitInfo': 'fitinfo', 'DropTable': 'fitinfo',
    'LCurvePlot': 'lcurve', 'LinePlot': 'lineplot', 'LinePlotControl': 'lineplot',
    'Mfd2DPlot': 'mfd_2d', 'MfdMarginalPlot': 'mfd_2d', 'MfdMapPlot': 'mfd_map',
    'ParameterScanPlot': 'parameter_scan', 'Plot': 'plotbase',
    'PosteriorGraphPlot': 'posterior_graph', 'Residual2DPlot': 'residual_image',
    'SamplingDiagnosticsPlot': 'sampling_diagnostics', 'FitTablePlot': 'table_plot',
    'ResidualPlot': 'wr_plot',
}
for name, module in exports.items():
    expected = getattr(importlib.import_module('chisurf.gui.plots.' + module), name)
    assert getattr(plots, name) is expected, name
    assert getattr(plots, name) is plots.__dict__[name]
    assert name in dir(plots)
for name in ('global_fit', 'global_tcspc', 'molview', 'proteinMC', 'plotbase', 'lineplot'):
    assert getattr(plots, name) is importlib.import_module('chisurf.gui.plots.' + name)
from chisurf.gui.plots import LinePlot, FitInfo, global_fit, global_tcspc, molview, proteinMC
assert LinePlot is plots.LinePlot
try:
    plots.nonexistent_plot
except AttributeError:
    pass
else:
    raise AssertionError('unknown export accepted')
""",
        tmp_path,
    )


def shipped_registrations():
    """Derive the shipped keys and their defining objects from source ASTs."""
    import ast

    directory = Path(__file__).resolve().parents[2] / "chisurf/gui/autoform/sections"
    sections = {}
    plots = {}
    for path in directory.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    if (
                        isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Name)
                        and decorator.func.id == "register_section"
                    ):
                        sections[ast.literal_eval(decorator.args[0])] = (path.stem, node.name)
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "register_plot"
            ):
                plots[ast.literal_eval(node.args[0])] = path.stem
    return sections, plots


def test_sections_package_is_lazy(tmp_path):
    """Importing the registry must leave all optional sections unloaded."""
    run_fresh(
        """
import sys
from chisurf.gui.autoform.sections import get_section_factory, get_plot_class
for name in ('code_editor_section', 'image_browser_section', 'chimol_section',
             'node_graph_section', 'state_scheme_section', 'builtin'):
    assert 'chisurf.gui.autoform.sections.' + name not in sys.modules, name
assert get_section_factory('not_a_section') is None
assert get_plot_class('not_a_plot') is None
""",
        tmp_path,
    )


def test_native_editor_avoids_unrelated_sections(tmp_path):
    """The real TCSPC model editor must not import unused optional controls."""
    run_fresh(
        NATIVE_SETUP
        + """
import sys
from chisurf.gui.widgets.models.model_editor import build_model_editor
editor = build_model_editor(fit.model)
for name in ('code_editor_section', 'image_browser_section', 'chimol_section',
             'node_graph_section', 'state_scheme_section', 'memory_editor_section',
             'phasor_section', 'waterfall_section'):
    assert 'chisurf.gui.autoform.sections.' + name not in sys.modules, name
assert 'chisurf.plugins.core.code_editor' not in sys.modules
""",
        tmp_path,
    )


def test_every_shipped_registry_key_resolves(tmp_path):
    """Every source registration must remain reachable through demand loading."""
    sections, plots = shipped_registrations()
    run_fresh(
        """
import importlib
from chisurf.gui.autoform.sections import get_section_factory, get_plot_class
"""
        + f"sections = {sections!r}\nplots = {plots!r}\n"
        + """
from chisurf.gui.autoform.sections import registry
assert registry._SECTION_MODULES == {key: module for key, (module, name) in sections.items()}
assert registry._PLOT_MODULES == plots
for key, (module, name) in sections.items():
    factory = get_section_factory(key)
    assert factory is not None, key
    assert factory is getattr(importlib.import_module(
        'chisurf.gui.autoform.sections.' + module), name), key
for key in plots:
    cls = get_plot_class(key)
    assert isinstance(cls, type), key
    assert get_plot_class(key) is cls, key
""",
        tmp_path,
    )


def test_custom_registry_overrides_survive_builtin_loading(tmp_path):
    """Loading another builtin from a module must preserve custom overrides."""
    run_fresh(
        """
from chisurf.gui.autoform.sections import (
    register_section, register_plot, get_section_factory, get_plot_class,
)
@register_section('image')
def custom_image(**kwargs):
    return kwargs
class CustomLine:
    pass
register_plot('line', lambda: CustomLine)
assert get_section_factory('fit_mixer') is not None
assert get_plot_class('residual') is not None
assert get_section_factory('image') is custom_image
assert get_plot_class('line') is CustomLine
assert get_section_factory('unknown_section') is None
assert get_plot_class('unknown_plot') is None
""",
        tmp_path,
    )


def test_explicit_section_import_errors_surface(tmp_path):
    """A failure to import an explicitly requested control cannot disappear."""
    run_fresh(
        """
from unittest.mock import patch
from chisurf.gui.autoform.sections import get_section_factory
with patch('importlib.import_module', side_effect=ImportError('broken feature')):
    try:
        get_section_factory('node_graph')
    except ImportError as exc:
        assert str(exc) == 'broken feature'
    else:
        raise AssertionError('required feature failure was hidden')
""",
        tmp_path,
    )


def test_parameter_widget_import_avoids_controller_chain(tmp_path):
    """A parameter control must not preload fit windows and controllers."""
    run_fresh(
        """
import sys
from chisurf.gui.widgets.fitting import parameter_widgets, fitting_client
from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget
assert FittingParameterWidget is parameter_widgets.FittingParameterWidget
for name in ('fit_controller', 'fit_list', 'fit_subwindow', 'widgets'):
    assert 'chisurf.gui.widgets.fitting.' + name not in sys.modules, name
""",
        tmp_path,
    )


def test_fitting_public_from_imports(tmp_path):
    """Lazy package exports must retain the actual widgets API and identities."""
    run_fresh(
        """
from chisurf.gui.widgets.fitting import (
    FittingControllerWidget, ModelDataRepresentationSelector, FitSubWindow,
    FittingParameterDetailPopup, FittingParameterGroupWidget, FittingParameterProxyController,
    FittingParameterWidget, ParameterActionsMixin, make_fitting_parameter_group_widget,
    make_fitting_parameter_widget, parameter_settings, parameter_widgets, fitting_client,
)
from chisurf.gui.widgets.fitting import widgets
import chisurf.gui.widgets.fitting as fitting
for name in widgets.__all__:
    assert getattr(fitting, name) is getattr(widgets, name), name
    assert name in dir(fitting)
assert fitting.FittingParameterWidget is parameter_widgets.FittingParameterWidget
assert fitting.fitting_client is fitting_client
""",
        tmp_path,
    )


def test_code_file_navigation_and_save(tmp_path):
    """Direct code access retains real symbols, cursor navigation, and saving."""
    run_fresh(
        NATIVE_SETUP
        + r"""
from pathlib import Path
import os
from qtpy.QtTest import QTest
path = Path(os.environ['CHISURF_SETTINGS_DIR']) / 'first_use_code.py'
path.write_text('def first():\n    return 1\n\ndef second():\n    return 2\n')
assert window.code_editor is None
window.load_code_file(str(path), line_number=3)
text_editor = window._get_current_text_editor()
assert text_editor.textCursor().blockNumber() == 3
assert text_editor.file_load_callback == window.load_code_file
assert window.func_combo.count() == 3
other_path = path.with_name('other_code.py')
other_path.write_text('def other():\n    return 4\n')
window.file_combo.addItem(path.name, str(path))
window.file_combo.addItem(other_path.name, str(other_path))
window.file_combo.setCurrentIndex(1)
assert window._get_current_text_editor().current_file == str(other_path)
window.file_combo.setCurrentIndex(0)
assert window._get_current_text_editor() is text_editor
assert window.original_source_file == str(path)
window.func_combo.setCurrentIndex(1)
assert text_editor.textCursor().blockNumber() == 0
window.func_combo.setCurrentIndex(2)
assert text_editor.textCursor().blockNumber() == 3
window._open_external_definition(str(path), 2)
assert text_editor.textCursor().blockNumber() == 1
text_editor.push_nav_history(str(path), 0)
text_editor.push_nav_history(str(path), 3)
window._code_nav_back()
assert text_editor.textCursor().blockNumber() == 0
window._code_nav_forward()
assert text_editor.textCursor().blockNumber() == 3
text_editor.setText('def saved():\n    return 3\n')
from unittest.mock import patch
window.updateStatusBar('Headless code status')
cs.cs = QtWidgets.QMainWindow()
with patch('chisurf.gui.widgets.fitting.fit_subwindow.dialogs.warning') as warning:
    QTest.mouseClick(window.save_code_btn, QtCore.Qt.LeftButton)
    warning.assert_not_called()
assert cs.cs.statusBar().currentMessage() == 'Saved to ' + str(path)
assert path.read_text() == 'def saved():\n    return 3\n'
""",
        tmp_path,
    )


def test_project_front_face_restores_code_button(tmp_path):
    """Restoring the front face after Code must also restore the toggle label."""
    run_fresh(
        NATIVE_SETUP
        + """
window.show_code_view()
editor = window.code_editor
assert window.set_project_plot_state({'stack_index': 0})
assert window.stack.currentIndex() == 0
assert not window.flip_to_code_btn.isChecked()
assert window.flip_to_code_btn.text() == 'Code'
assert window.code_editor is editor
""",
        tmp_path,
    )


def test_plot_star_exports_and_configuration(tmp_path):
    """Star imports expose real classes and preserve plotting configuration."""
    run_fresh(
        """
from unittest.mock import patch
import chisurf.core.settings
from chisurf.gui import chiplot as cp
with patch.object(cp, 'configure', wraps=cp.configure) as configure:
    import chisurf.gui.plots as plots
    configure.assert_called_once_with(
        **chisurf.core.settings.cs_settings['gui']['plot']['pyqtgraph_config'])
namespace = {}
exec('from chisurf.gui.plots import *', namespace)
for name in plots.__all__:
    assert namespace[name] is getattr(plots, name), name
""",
        tmp_path,
    )


def test_real_editor_applies_model_code(tmp_path):
    """Save/Apply still executes model code from the real current editor."""
    run_fresh(
        NATIVE_SETUP
        + r"""
import os
import sys
from pathlib import Path
from unittest.mock import patch
from chisurf.gui.devtools.source_jump import resolve_compute_model_class
path = Path(os.environ['CHISURF_SETTINGS_DIR']) / 'apply_model_code.py'
path.write_text('# model code scratch\n')
window.load_code_file(str(path))
model_class = resolve_compute_model_class(fit.model) or fit.model.__class__
module = sys.modules[model_class.__module__]
module._first_use_original_class = model_class
code = model_class.__name__ + ' = _first_use_original_class\n_first_use_applied = True\n'
window._get_current_text_editor().setText(code)
cs.cs = QtWidgets.QMainWindow()
before = np.asarray(fit.model.y).copy()
with patch('inspect.getsourcefile', return_value=str(path)), patch(
        'chisurf.gui.widgets.fitting.fit_subwindow.get_fitting_client', return_value=None):
    window.save_model_code()
assert path.read_text() == code
assert module._first_use_applied is True
assert cs.cs.statusBar().currentMessage() == 'Model code applied successfully.'
np.testing.assert_array_equal(before, fit.model.y)
""",
        tmp_path,
    )
