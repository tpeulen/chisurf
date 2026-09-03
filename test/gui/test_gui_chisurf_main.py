from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import utils

TOPDIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')
)
utils.set_search_paths(TOPDIR)

from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtTest import QTest

import chisurf as cs
import chisurf.gui
import chisurf.gui.widgets
import chisurf.gui.widgets.experiments
import chisurf.macros

cs_app = cs.gui.get_app()


def add_fit(
        data_set_name: str,
        dataset_selector: cs.gui.widgets.experiments.ExperimentalDataSelector,
        add_fit_button: QtWidgets.QToolButton,
        model_selector: QtWidgets.QComboBox,
        model_name: str
):
    """Drive the main window's *Analysis* button to create one fit.

    Parameters
    ----------
    data_set_name : str
        Name of the dataset to select in the dataset tree.
    dataset_selector : chisurf.gui.widgets.experiments.ExperimentalDataSelector
        The main window's dataset tree.
    add_fit_button : QtWidgets.QToolButton
        The main window's *Analysis* button (``Main.toolButton``); the *Data*
        button next to it is ``toolButton_2`` and does something else.
    model_selector : QtWidgets.QComboBox
        The model combo box the fit's model is picked from.
    model_name : str
        User-facing name of the model to fit the dataset with.

    Returns
    -------
    object
        The fit created by the button click (the last entry of ``chisurf.fits``).
    """
    n_fits = len(cs.fits)
    # select data_set — scroll it into view first, the tree is only a few rows
    # tall and a click outside the viewport selects nothing at all
    for i in cs.gui.widgets.get_all_items(dataset_selector):
        if i.text(0) == data_set_name or i.text(1) == data_set_name:
            dataset_selector.scrollToItem(i)
            rect = dataset_selector.visualItemRect(i)
            QTest.mouseClick(
                dataset_selector.viewport(),
                Qt.LeftButton,
                Qt.NoModifier,
                rect.center()
            )
            break
    else:
        raise AssertionError(f"dataset {data_set_name!r} not in the dataset tree")
    assert dataset_selector.selected_dataset_idx, f"clicking {data_set_name!r} selected nothing"

    # select model
    model_idx = model_selector.findText(model_name)
    assert model_idx >= 0, f"model {model_name!r} not offered for {data_set_name!r}"
    model_selector.setCurrentIndex(model_idx)

    # click on add fit
    QTest.mouseClick(add_fit_button, Qt.LeftButton)

    assert len(cs.fits) == n_fits + 1, f"no fit was created for {model_name!r}"
    fit = cs.fits[-1]
    assert fit.name.startswith(model_name), (
        f"fit {fit.name!r} was not created with the selected model {model_name!r}"
    )
    return fit


def setup_reader(
        experiment_name: str,
        experiment_selector_combobox: QtWidgets.QComboBox,
        setup_name: str,
        setup_selector_combobox: QtWidgets.QComboBox
):
    """Pick an experiment and one of its readers in the main window.

    Parameters
    ----------
    experiment_name : str
        User-facing name of the experiment, e.g. ``"TCSPC"``.
    experiment_selector_combobox : QtWidgets.QComboBox
        The main window's experiment combo box.
    setup_name : str
        User-facing name of the reader, e.g. ``"TXT/CSV"`` — the ``name`` given
        in ``chisurf/core/settings/experiment_configs.yaml``, not the class name.
    setup_selector_combobox : QtWidgets.QComboBox
        The main window's reader combo box.
    """
    experiment_idx = experiment_selector_combobox.findText(experiment_name)
    assert experiment_idx >= 0, f"experiment {experiment_name!r} not offered"
    experiment_selector_combobox.setCurrentIndex(experiment_idx)

    setup_idx = setup_selector_combobox.findText(setup_name)
    assert setup_idx >= 0, f"reader {setup_name!r} not offered for {experiment_name!r}"
    setup_selector_combobox.setCurrentIndex(setup_idx)


class Tests(unittest.TestCase):
    """Walk the main window through "choose experiment → load data → add fit"."""

    def test_tcspc(self):
        """Open a TCSPC dataset and create a lifetime and a FRET fit."""
        gui = cs.cs
        setup_reader(
            experiment_name="TCSPC",
            experiment_selector_combobox=gui.comboBox_experimentSelect,
            setup_name="TXT/CSV",
            setup_selector_combobox=gui.comboBox_setupSelect
        )
        filename_decay = "./test/data/tcspc/ibh_sample/Decay_577D.txt"
        filename_irf = "./test/data/tcspc/ibh_sample/Prompt.txt"

        gui.current_setup.skiprows = 11
        gui.current_setup.reading_routine = 'csv'
        gui.current_setup.is_vv_vh = False
        gui.current_setup.use_header = True
        gui.current_setup.matrix_columns = []
        gui.current_setup.polarization = 'vm'
        gui.current_setup.rep_rate = 10.0
        gui.current_setup.dt = 0.0141

        cs.macros.add_dataset(
            filename=filename_decay
        )
        cs.macros.add_dataset(
            filename=filename_irf
        )
        data_set_name = "Decay_577D.txt"
        for model_name in ('Lifetime', 'FRET: FD (Gaussian)'):
            fit = add_fit(
                data_set_name=data_set_name,
                dataset_selector=gui.dataset_selector,
                add_fit_button=gui.toolButton,
                model_selector=gui.comboBox_Model,
                model_name=model_name
            )
            self.assertIsNotNone(fit.model)
            self.assertIn(data_set_name, fit.data.name)
            # parameters are discovered lazily, on the first model update
            fit.model.update()
            self.assertGreater(len(fit.model.parameters_all), 0)

    def test_fcs(self):
        """Open an FCS dataset and create a parse-model fit."""
        gui = cs.cs
        setup_reader(
            experiment_name="FCS",
            experiment_selector_combobox=gui.comboBox_experimentSelect,
            setup_name="Seidel Kristine",
            setup_selector_combobox=gui.comboBox_setupSelect
        )
        filename_fcs = "./test/data/fcs/kristine/Kristine_with_error.cor"
        cs.macros.add_dataset(
            filename=filename_fcs
        )
        model_names = [
            gui.comboBox_Model.itemText(i)
            for i in range(gui.comboBox_Model.count())
        ]
        self.assertIn('Parse-Model', model_names)
        model_name = 'Parse-Model'
        data_set_name = 'Kristine_with_error'
        fit = add_fit(
            data_set_name=data_set_name,
            dataset_selector=gui.dataset_selector,
            add_fit_button=gui.toolButton,
            model_selector=gui.comboBox_Model,
            model_name=model_name
        )
        self.assertIsNotNone(fit.model)
        # parameters are discovered lazily, on the first model update
        fit.model.update()
        self.assertGreater(len(fit.model.parameters_all), 0)

    def test_global_fit(self):
        """Create a global fit on the always-present global dataset."""
        gui = cs.cs
        model_name = 'Global fit'
        data_set_name = 'Global Dataset'
        fit = add_fit(
            data_set_name=data_set_name,
            dataset_selector=gui.dataset_selector,
            add_fit_button=gui.toolButton,
            model_selector=gui.comboBox_Model,
            model_name=model_name
        )
        self.assertIsNotNone(fit.model)


if __name__ == "__main__":
    unittest.main()
