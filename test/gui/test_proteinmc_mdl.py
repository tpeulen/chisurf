"""ProteinMC: the pure model, its generated editor, and the plots that read it.

The 1,984-line ``ProteinMCModelWidget`` these tests used to drive is gone
(PRD-38); ``ProteinMCModel`` holds the same state, runs the sampler in a plain
thread, and is rendered from ``proteinmc.view.json``. Each test below is the
behaviour its widget-driven predecessor asserted, moved onto whatever now owns
it — which is why most of them no longer need a display at all.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.models.structure.proteinmc import ProteinMCProgress


def _fit(data=None):
    """Return a minimal fit stub the model is happy to be constructed against."""
    return SimpleNamespace(name="fit", data=data, plots=[])


def _model(data=None):
    """Return a bare :class:`ProteinMCModel` over a fit stub."""
    from chisurf.core.models.structure.proteinmc_model import ProteinMCModel

    return ProteinMCModel(fit=_fit(data))


def _progress(energy=2.0, labeling=1.0, xyz=None):
    """Return one sampler progress payload."""
    return ProteinMCProgress(
        frame_index=1,
        target_frames=2,
        iteration=1,
        accepted=1,
        rejected=0,
        energy=energy,
        labeling_energy=labeling,
        rmsd=[0.0],
        drmsd=[0.0],
        energies=[energy],
        labeling_energies=[labeling],
        xyz=np.zeros((3, 3)) if xyz is None else xyz,
        output_file="out.rmf3",
    )


def _two_ca_structure():
    """Return a structure of two Cα atoms 10 Å apart, and its labelling JSON."""
    atoms = np.zeros(
        2,
        dtype=[("xyz", float, (3,)), ("atom_name", "S2"), ("res_id", int), ("chain", "S1")],
    )
    atoms["xyz"] = np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]])
    atoms["atom_name"] = [b"CA", b"CA"]
    atoms["res_id"] = [1, 2]
    atoms["chain"] = [b"A", b"A"]
    return SimpleNamespace(atoms=atoms, xyz=atoms["xyz"])


def _labeling_file(tmp_path, score_sets=None):
    """Write an FPS JSON with one distance between the two Cα positions."""
    payload = {
        "Positions": {
            "p1": {"chain_identifier": "A", "residue_seq_number": 1, "atom_name": "CA"},
            "p2": {"chain_identifier": "A", "residue_seq_number": 2, "atom_name": "CA"},
        },
        "Distances": {"d1": {"position1_name": "p1", "position2_name": "p2", "distance": 10}},
        "χ²": score_sets if score_sets is not None else {"chi2_C1": {"distances": ["d1"]}},
    }
    path = tmp_path / "fps.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# the model
# ---------------------------------------------------------------------------
def test_proteinmc_declares_structure_and_trajectory_plots():
    """The view spec resolves to the same three plot tabs the widget listed."""
    from chisurf.emtk.fit_pages.plots import model_plot_specs

    names = [plot_class.name for plot_class, _ in model_plot_specs(_model())]
    assert names[:3] == ["Structure", "Distance Network", "Trajectory-Plot"]


def test_progress_payload_fills_the_traces_and_the_trajectory():
    """A progress callback records the energies and appends the frame."""
    model = _model()
    model._on_progress(_progress(energy=2.0, labeling=1.0))

    assert model.energy == [2.0]
    assert model.chi2r == [1.0]
    assert model.frame_count == 1
    assert model.current_frame_index == 0


def test_set_current_frame_clamps_and_follows_the_distances(tmp_path):
    """Selecting a frame re-measures the distances on *that* frame."""
    structure = _two_ca_structure()
    model = _model(structure)
    model.labeling_file = str(_labeling_file(tmp_path))
    model.score_set = "chi2_C1"
    model.proteinmc_structure = structure
    model.reload_distances()

    model.trajectory_frames = [
        np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0]]),
        np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]]),
    ]
    model.set_current_frame(1)
    assert model.current_frame_index == 1
    assert model._distance_parameters["d1"].value == pytest.approx(5.0)

    model.set_current_frame(99)
    assert model.current_frame_index == 1, "frame index was not clamped"


def test_distances_are_written_onto_the_parameters(tmp_path):
    """The distance outputs are plain parameter writes, assertable headless.

    The hand-written version published them through the GUI fitting client
    inside a bare ``except``, so they stayed NaN with no client present.
    """
    structure = _two_ca_structure()
    model = _model(structure)
    model.labeling_file = str(_labeling_file(tmp_path))
    model.score_set = "chi2_C1"
    model.proteinmc_structure = structure
    model.reload_distances()

    model.update_distance_values()
    assert model._distance_parameters["d1"].value == pytest.approx(10.0)

    model.trajectory_frames = [np.array([[0.0, 0.0, 0.0], [5.0, 0.0, 0.0]])]
    model.current_frame_index = 0
    model.update_distance_values()
    assert model._distance_parameters["d1"].value == pytest.approx(5.0)


def test_score_set_selects_which_distances_are_restrained(tmp_path):
    """The score set filters the distances, and a partial name still resolves."""
    labeling = _labeling_file(
        tmp_path,
        score_sets={"chi2_C1_20p": {"distances": ["d1"]}, "chi2_C2_33p": {"distances": []}},
    )
    model = _model(_two_ca_structure())
    model.labeling_file = str(labeling)

    assert "chi2_C1_20p" in model.score_set_names()
    assert "chi2_C2_33p" in model.score_set_names()

    # A project may store an abbreviated name; substring matching resolves it
    # rather than silently restraining nothing.
    model.score_set = "c1"
    model.reload_distances()
    assert list(model._distance_parameters) == ["d1"]

    model.score_set = "chi2_C2_33p"
    model.reload_distances()
    assert model._distance_parameters == {}

    model.score_set = ""
    model.reload_distances()
    assert model._distance_parameters == {}


def test_energy_terms_are_editable_rows(tmp_path):
    """The energy-term table's rows and cell writes reach the runner payload."""
    model = _model()
    terms = [row["term"] for row in model.potential_rows()]
    assert terms == ["H-bond", "UNRES", "Dye potential"]

    model.set_potential_field(0, "weight", 3.5)
    model.set_potential_field(0, "eval_every", 4)
    payload = model.potential_settings()[0]
    assert payload["weight"] == pytest.approx(3.5)
    assert payload["eval_interval"] == 4

    # Adding the same term twice would make the runner sum it twice.
    model.new_potential = "mj"
    model.add_potential()
    model.add_potential()
    assert [p["name"] for p in model.potential_settings()] == ["hbond", "unres", "dye", "mj"]

    model.selected_potential = {"index": 3}
    model.remove_selected_potential()
    assert [p["name"] for p in model.potential_settings()] == ["hbond", "unres", "dye"]


def test_term_settings_keep_the_type_of_their_default():
    """A bool setting reaches the runner as a bool, not the string ``"True"``."""
    model = _model()
    model.new_potential = "go"
    model.add_potential()
    model.selected_potential = {"index": 3}

    names = [row["name"] for row in model.potential_setting_rows()]
    assert "native_cutoff_on" in names
    model.set_potential_setting(names.index("native_cutoff_on"), "value", "false")
    model.set_potential_setting(names.index("epsilon"), "value", "2.5")

    settings = next(p for p in model.potential_settings() if p["name"] == "go")["settings"]
    assert settings["native_cutoff_on"] is False
    assert settings["epsilon"] == pytest.approx(2.5)


def test_state_round_trips_through_a_project(tmp_path):
    """``get_state``/``set_state`` carry the whole setup, including the terms."""
    labeling = _labeling_file(tmp_path)
    model = _model(_two_ca_structure())
    model.labeling_file = str(labeling)
    model.score_set = "chi2_C1"
    model.n_iter = 4242
    model.kt = 2.25
    model.set_potential_field(0, "weight", 7.0)

    restored = _model(_two_ca_structure())
    restored.set_state(model.get_state())

    assert restored.n_iter == 4242
    assert restored.kt == pytest.approx(2.25)
    assert restored.labeling_file == str(labeling)
    assert restored.score_set == "chi2_C1"
    assert restored.potential_settings()[0]["weight"] == pytest.approx(7.0)
    assert list(restored._distance_parameters) == ["d1"]


def test_start_sampling_runs_the_runner_in_a_thread(monkeypatch, tmp_path):
    """Sampling runs headless: no Qt worker, no dialog, just the model."""
    import chisurf.core.models.structure.proteinmc_model as module

    class FakeRunner:
        def __init__(self, *, progress_callback=None, output_file=None, **kwargs):
            self.progress_callback = progress_callback
            self.output_file = output_file
            self.structure = SimpleNamespace(atoms=None, xyz=np.zeros((3, 3)))

        def run(self):
            if self.progress_callback is not None:
                self.progress_callback(_progress(energy=3.0, labeling=2.0))
            return SimpleNamespace(output_file=self.output_file, structure=self.structure)

        def stop(self):
            return None

    monkeypatch.setattr(module, "ProteinMCRunner", FakeRunner)
    model = _model()
    model.structure_file = "148l"
    model.output_directory = str(tmp_path)
    model.n_iter = model.n_out = model.n_written = 1

    model.start_sampling()
    model._thread.join(timeout=5.0)
    assert not model.is_sampling

    assert model.energy == [3.0]
    assert model.chi2r == [2.0]
    assert model.frame_count == 1
    assert "finished" in model.sampling_status


def test_start_sampling_without_an_output_directory_does_not_run():
    """A missing output folder is refused, not turned into a crash mid-run."""
    model = _model()
    model.structure_file = "148l"
    model.start_sampling()
    assert not model.is_sampling
    assert model.frame_count == 0


# ---------------------------------------------------------------------------
# the editor
# ---------------------------------------------------------------------------
def test_spec_carries_the_run_controls_and_both_term_tables():
    """The view spec carries the run controls and both term tables."""
    import json
    from pathlib import Path

    import chisurf.core.models.structure.proteinmc_model as module

    spec = json.loads(Path(module.__file__).with_name("proteinmc.view.json").read_text())
    tables, customs = [], []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "table":
                tables.append({c["label"] for c in node["columns"]})
            if node.get("type") == "custom":
                customs.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(spec)
    assert any({"Term", "Weight"} <= h for h in tables), tables
    assert any({"Setting", "Value"} <= h for h in tables), tables
    assert customs, "no run-control section in the ProteinMC spec"


def test_distance_network_plot_constructs(tmp_path):
    """The network plot reads the labelling file off the *model*, not a line edit."""
    from chisurf.emtk.fit_pages.pages.proteinMC import (
        ProteinMCDistanceNetworkPlot,
        _agreement_color,
    )

    structure = _two_ca_structure()
    xyz = structure.atoms["xyz"]
    model = SimpleNamespace(
        proteinmc_structure=structure,
        trajectory_frames=[xyz, xyz + 1.0, xyz + 2.0],
        current_frame_index=0,
        frame_count=3,
        labeling_file=str(_labeling_file(tmp_path)),
    )
    model.set_current_frame = lambda value: setattr(model, "current_frame_index", int(value))
    plot = ProteinMCDistanceNetworkPlot(SimpleNamespace(model=model))

    plot.update_all()

    # The playback is the page's settings: a spec over the page's own actions.
    assert plot.bounds("frame") == (0, 2)
    assert plot.frame_total_text() == "/ 2"
    buttons = [
        b["label"]
        for section in plot.settings_spec()["sections"][0]["sections"]
        if section.get("type") == "button_row"
        for b in section["buttons"]
    ]
    assert buttons == ["|<", "<", "▶", "■", ">", ">|"]
    plot.step = 2
    plot.goto_next()
    assert model.current_frame_index == 2
    assert _agreement_color(-3.0) == _agreement_color(3.0)


def test_network_playback_steps_on_drawn_frames_and_round_trips(tmp_path):
    """No timer: a playing page steps when a frame draws it, and the project keeps it."""
    from chisurf.emtk.fit_pages.pages.proteinMC import PLAY_INTERVAL, ProteinMCDistanceNetworkPlot

    structure = _two_ca_structure()
    xyz = structure.atoms["xyz"]
    model = SimpleNamespace(
        proteinmc_structure=structure,
        trajectory_frames=[xyz, xyz + 1.0, xyz + 2.0],
        current_frame_index=0,
        frame_count=3,
        labeling_file=str(_labeling_file(tmp_path)),
    )
    model.set_current_frame = lambda value: setattr(model, "current_frame_index", int(value))
    plot = ProteinMCDistanceNetworkPlot(SimpleNamespace(model=model))
    asked = []
    plot.set_refresh_target(lambda: asked.append(1))

    plot.play()
    start = plot._last_tick
    plot.tick(start + PLAY_INTERVAL / 2)
    assert model.current_frame_index == 0, "stepped before the interval"
    plot.tick(start + 1.01 * PLAY_INTERVAL)
    assert model.current_frame_index == 1
    assert asked, "a playing page must ask for the next frame"
    plot.tick(start + 2.02 * PLAY_INTERVAL)
    plot.tick(start + 3.03 * PLAY_INTERVAL)
    assert model.current_frame_index == 0, "playback wraps past the last frame"

    plot.step = 2
    state = plot.get_settings_state()
    assert state == {"frame": 0, "step": 2, "playing": True}
    plot.stop()
    assert not plot.playing
    plot.set_settings_state({"frame": 2, "step": 1, "playing": False})
    assert (model.current_frame_index, plot.step, plot.playing) == (2, 1, False)


def test_trajectory_settings_hide_panels_and_keep_the_old_keys():
    """The four curve toggles choose the panels drawn; their state uses the old keys."""
    from chisurf.emtk.fit_pages.pages.proteinMC import ProteinMCPlot

    model = SimpleNamespace(
        rmsd=[1.0, 2.0],
        drmsd=[0.5, 0.4],
        energy=[3.0, 2.0],
        chi2r=[1.0, 0.9],
        current_frame_index=1,
    )
    plot = ProteinMCPlot(SimpleNamespace(model=model, name="fit"))
    plot.update()
    assert plot._grid() is not None and len(plot._grid_key) == 4
    plot.show_energy = False
    plot.show_fret = False
    assert plot._grid() is not None and plot._grid_key == (
        id(plot.panel_items[0]),
        id(plot.panel_items[1]),
    )
    assert plot.get_settings_state() == {
        "show_rmsd": True,
        "show_drmsd": True,
        "show_energy": False,
        "show_fret": False,
    }
    plot.set_settings_state({"show_rmsd": False, "show_drmsd": False})
    assert plot._grid() is None
    plot.autoscale()


def test_sampling_without_rmf_keeps_its_frames_and_writes_no_file(monkeypatch, tmp_path):
    """An IMP.bff built without RMF (the pip wheel) still samples.

    The trajectory is the model's ``trajectory_frames``, saved in the project;
    the RMF file is only its export, so its absence costs the file, not the run.
    """
    import chisurf.core.models.structure.rmf as rmf

    monkeypatch.setattr(rmf, "rmf_unavailable_reason", lambda: "built without RMF")
    model = _model()
    model.structure_file = "148l"
    model.output_directory = str(tmp_path)
    assert model._trajectory_file(tmp_path) is None
    monkeypatch.setattr(rmf, "rmf_unavailable_reason", lambda: None)
    assert model._trajectory_file(tmp_path) == tmp_path / "proteinmc.rmf3"


def test_the_runner_without_an_output_file_writes_nothing(tmp_path, monkeypatch):
    """``output_file=None`` is an in-memory run: frames arrive, no writer is built."""
    import chisurf.core.models.structure.proteinmc as proteinmc

    def no_writer(*_args, **_kwargs):
        raise AssertionError("an in-memory run built an RMF writer")

    monkeypatch.setattr(proteinmc, "ProteinMCRmfWriter", no_writer)
    pdb = Path(__file__).resolve().parents[1] / "data/atomic_coordinates/pdb_files/148l.pdb"
    frames = []
    runner = proteinmc.ProteinMCRunner(
        str(pdb),
        settings={"n_iter": 50, "n_out": 1, "pdbOut": 2},
        progress_callback=lambda p: frames.append(p.xyz),
    )
    result = runner.run()
    assert result.output_file == ""
    assert frames and result.n_frames == len(frames)
    assert not list(tmp_path.iterdir())
