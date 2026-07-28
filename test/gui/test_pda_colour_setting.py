"""Three-colour PDA is a setting of the PDA experiment, not an experiment.

The colour count decides what a burst becomes — a cell of an S1S2 histogram or a
row of a five-column photon table — but nothing else about PDA changes with it:
the same reader reads the same files, the same burst search finds the same
windows. These tests pin the consequences of that: one experiment holds both
model families, the model list is filtered by what the loaded dataset actually
carries, and the reader panel grows a third detector row when the setting says
three.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _two_colour_curve():
    """Return a minimal dataset carrying a two-colour S1S2 payload."""
    import chisurf.core.data

    return chisurf.core.data.DataCurve(
        name="s1s2",
        load_filename_on_init=False,
        x=np.arange(4.0),
        y=np.ones(4),
        pda={"s1s2": np.ones((2, 2)), "ndim": 2},
    )


def _three_colour_curve():
    """Return a simulated three-colour burst table."""
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader

    return Pda3cSimulatorReader(n_bursts=200, seed=5).read()[0]


# ── one experiment ─────────────────────────────────────────────────────────


def test_the_configuration_holds_a_single_pda_experiment():
    import pathlib

    import yaml

    config = yaml.safe_load(
        pathlib.Path("chisurf/core/settings/experiment_configs.yaml").read_text()
    )
    pda_sections = [k for k in config if k.startswith("pda")]
    assert pda_sections == ["pda"]

    models = config["pda"]["models"]
    assert any("pda2c" in m for m in models)
    assert any("pda3c" in m for m in models)


def test_a_superseded_section_of_an_old_settings_file_is_dropped():
    """A stale user copy must not resurrect the experiment or shadow the new one.

    The user settings file is a full copy of the packaged one merged *on top* of
    it, and merging replaces lists — so an un-dropped ``pda2c`` section would
    both appear as an experiment of its own and hide every model added since.
    """
    from chisurf.core.experiments import migrate_experiment_config

    stale = {
        "experiment_types": {
            "pda2c": {"name": "PDA", "hidden": False},
            "pda3c": {"name": "PDA3c (3-colour)", "hidden": False},
            "fcs": {"name": "FCS", "hidden": False},
        },
        "pda2c": {"readers": [], "models": ["old.Model"]},
        "pda3c": {"readers": [], "models": ["old.Model3c"]},
        "fcs": {"readers": [], "models": []},
    }
    migrated = migrate_experiment_config(stale)
    assert "pda2c" not in migrated and "pda3c" not in migrated
    assert "pda2c" not in migrated["experiment_types"]
    assert "pda3c" not in migrated["experiment_types"]
    assert migrated["fcs"] == {"readers": [], "models": []}


def test_both_model_families_and_all_readers_are_registered():
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    registry = ensure_experiments_registered()
    assert [name for name in registry if name.upper().startswith("PDA")] == ["PDA"]

    pda = registry["PDA"]
    assert "PDA3c (three-colour)" in pda["models"]
    assert "PDA2c-discrete" in pda["models"]
    assert "Simulator (3-colour)" in pda["readers"]


# ── the model list follows the data ────────────────────────────────────────


def test_a_model_is_offered_only_for_the_data_it_can_fit():
    from chisurf.core.experiments.core import Experiment
    from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    experiment = Experiment(name="PDA")
    experiment.add_model_classes([Pda2cSimpleModel, Pda3cModel])

    assert experiment.get_model_names(_two_colour_curve()) == [Pda2cSimpleModel.name]
    assert experiment.get_model_names(_three_colour_curve()) == [Pda3cModel.name]
    # No selection filters nothing out.
    assert len(experiment.get_model_names()) == 2


def test_a_model_that_declares_nothing_stays_offered():
    """The filter may only remove models that would fail, never surprise ones."""
    from chisurf.core.experiments.core import Experiment
    from chisurf.core.models.tcspc.lifetime import LifetimeNewModel

    experiment = Experiment(name="TCSPC")
    experiment.add_model_class(LifetimeNewModel)
    assert experiment.get_model_names(_two_colour_curve()) == [LifetimeNewModel.name]


# ── the reader panel follows the setting ───────────────────────────────────


def _controller(n_colors: int):
    from chisurf.core.experiments.pda2c import Pda2cReader
    from chisurf.gui.widgets.experiments.pda2c.controller import Pda2cTTTRWidget

    reader = Pda2cReader(
        channels=([0], [1], [2])[:n_colors],
        micro_time_ranges=[(0, 8000), (8000, 16000)],
        n_colors=n_colors,
    )
    return Pda2cTTTRWidget(experiment_reader=reader), reader


def test_the_panel_has_one_detector_row_per_colour(qapp):
    two, _ = _controller(2)
    assert len(two.detector_combos) == 2
    assert len(two.channel_edits) == 2
    # Two colours: one photon-selection window per detector.
    assert len(two.window_edits) == 2

    three, _ = _controller(3)
    assert len(three.detector_combos) == 3
    assert len(three.channel_edits) == 3
    # Three colours: two excitation periods for three detectors.
    assert len(three.window_edits) == 2


def test_the_three_colour_panel_configures_the_reader(qapp):
    controller, reader = _controller(3)
    for edit, text in zip(controller.channel_edits, ("0", "1", "2")):
        edit.setText(text)
    for edit, text in zip(controller.window_edits, ("0-8000", "8000-16000")):
        edit.setText(text)
    controller.onParametersChanged()

    assert reader.channels == [[0], [1], [2]]
    assert reader.micro_time_ranges == [[0, 8000], [8000, 16000]]
    # Five detection combinations is what makes it a three-colour read.
    assert len(reader.detection_windows()) == 5


def test_switching_the_colour_count_rebuilds_the_panel(qapp):
    """The rebuild deletes every grabbed widget; the controller must re-adopt them."""
    controller, reader = _controller(2)
    assert len(controller.channel_edits) == 2

    reader.n_colors = 3
    controller._settings_form.rebuild()

    assert len(controller.channel_edits) == 3
    assert len(controller.window_edits) == 2
    # The re-adopted widgets are live: editing one still reaches the reader.
    controller.channel_edits[2].setText("7")
    controller.onParametersChanged()
    assert reader.channels[2] == [7]
