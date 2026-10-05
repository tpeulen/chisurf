"""Explicit structural state survives deletion of its scientific input files."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.modelling.reader import StructureReader
from chisurf.core.models.structure.proteinmc_model import ProteinMCModel


def _configured_proteinmc(tmp_path):
    """Load real 148L atoms and a restraint on its residues 47 and 86."""
    pdb = tmp_path / "148l.pdb"
    pdb.write_bytes(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes())
    experiment = Experiment(name="structure")
    experiment.add_model_class(ProteinMCModel)
    reader = StructureReader(experiment=experiment, record_provenance=False)
    data = reader.get_data(filename=str(pdb))[0]
    data.data_reader, data.experiment = reader, experiment
    labeling = tmp_path / "labeling.json"
    labeling.write_text(
        json.dumps(
            {
                "Positions": {
                    "47": {"chain_identifier": "E", "residue_seq_number": 47, "atom_name": "CA"},
                    "86": {"chain_identifier": "E", "residue_seq_number": 86, "atom_name": "CA"},
                },
                "Distances": {
                    "47-86": {
                        "position1_name": "47",
                        "position2_name": "86",
                        "distance": 30.0,
                        "error_neg": 2.0,
                        "error_pos": 3.0,
                    }
                },
                "χ²": {"selected": {"distances": ["47-86"]}},
                "FlexFit": {
                    "mobile": {
                        "Flexible residues": [
                            {"chain_identifier": "E", "residue_seq_number": residue}
                            for residue in (47, 86)
                        ]
                    }
                },
            }
        )
    )
    model = ProteinMCModel(fit=SimpleNamespace(data=data, name="structural fit", plots=[]))
    model.labeling_file = str(labeling)
    model.score_set = "selected"
    model.on_labeling_file_changed()
    model.use_flexfit = True
    model.flexfit_set = "mobile"
    model.n_iter, model.n_out, model.n_written, model.n_runs = 4, 2, 2, 3
    model.kt, model.scale = 2.25, 0.001
    model.set_potential_field(0, "weight", 3.5)
    model.set_potential_field(0, "eval_every", 2)
    model.reload_distances()
    model.update_distance_values()
    assert model._distance_parameters["47-86"].value > 0
    return model, pdb, labeling


def test_proteinmc_restores_restraints_without_original_files(tmp_path):
    """Restored atoms, restraint definitions and controls support real edits."""
    model, pdb, labeling = _configured_proteinmc(tmp_path)
    original = model._distance_parameters["47-86"].value
    state = json.loads(json.dumps(model.get_state()))
    pdb.unlink()
    labeling.unlink()
    restored = ProteinMCModel(fit=SimpleNamespace(data=None, name="fresh", plots=[]))
    restored.set_state(state)
    assert list(restored._distance_parameters) == ["47-86"]
    np.testing.assert_array_equal(restored.structure.atoms, model.structure.atoms)
    assert restored.n_runs == 3
    assert restored.potential_settings() == model.potential_settings()
    assert restored._distance_parameters["47-86"].value == original
    moved = restored.structure.xyz.copy()
    selection = (restored.structure.atoms["res_id"] == 86) & (
        restored.structure.atoms["atom_name"] == "CA"
    )
    moved[selection, 0] += 5.0
    restored.structure.xyz = moved
    restored.update()
    assert restored._distance_parameters["47-86"].value != original
    again = ProteinMCModel(fit=SimpleNamespace(data=None, name="again", plots=[]))
    again.set_state(json.loads(json.dumps(restored.get_state())))
    assert again._distance_parameters["47-86"].value == restored._distance_parameters["47-86"].value


def test_proteinmc_restores_trajectory_and_active_observable(tmp_path):
    """The selected saved frame, traces and sampling controls remain scientific state."""
    model, _, _ = _configured_proteinmc(tmp_path)
    model.trajectory_frames = [model.structure.xyz.copy(), model.structure.xyz.copy() * 1.1]
    model.current_frame_index = 1
    model.rmsd, model.drmsd = [0.0, 0.5], [0.0, 0.25]
    model.energy, model.chi2r = [2.0, 3.0], [1.0, 1.5]
    model.update()
    restored = ProteinMCModel(fit=SimpleNamespace(data=model.structure, name="fresh", plots=[]))
    restored.set_state(json.loads(json.dumps(model.get_state())))
    assert restored.current_frame_index == 1
    assert restored.frame_count == 2
    assert restored.energy == model.energy
    assert restored.chi2r == model.chi2r
    assert restored.rmsd == model.rmsd
    assert restored.drmsd == model.drmsd
    assert restored._distance_parameters["47-86"].value == model._distance_parameters["47-86"].value


def test_proteinmc_resumes_real_sampling_without_original_files(tmp_path):
    """Embedded structure and restraints drive the actual bounded native sampler."""
    model, pdb, labeling = _configured_proteinmc(tmp_path)
    state = json.loads(json.dumps(model.get_state()))
    pdb.unlink()
    labeling.unlink()
    restored = ProteinMCModel(fit=SimpleNamespace(data=None, name="fresh", plots=[]))
    restored.set_state(state)
    restored.output_directory = str(tmp_path / "sampling")
    np.random.seed(47)
    restored.start_sampling()
    restored._thread.join(timeout=30.0)
    assert not restored.is_sampling
    assert restored.sampling_status.startswith("finished:"), restored.sampling_status
    assert restored.frame_count >= 2
    assert np.isfinite(restored.energy).all()
    assert np.isfinite(restored.chi2r).all()
    assert restored._distance_parameters["47-86"].value > 0
    assert np.count_nonzero(restored.trajectory_frames[0] != restored.trajectory_frames[-1]) > 0
    again = ProteinMCModel(fit=SimpleNamespace(data=None, name="resumed", plots=[]))
    again.set_state(json.loads(json.dumps(restored.get_state())))
    np.testing.assert_array_equal(
        again.proteinmc_structure.atoms, restored.proteinmc_structure.atoms
    )
    np.testing.assert_array_equal(
        again.proteinmc_structure.internal_coordinates,
        restored.proteinmc_structure.internal_coordinates,
    )
    again.n_written = 1
    again.output_directory = str(tmp_path / "continued")
    again.start_sampling()
    again._thread.join(timeout=30.0)
    assert not again.is_sampling
    assert again.sampling_status.startswith("finished:"), again.sampling_status
    assert again.frame_count > restored.frame_count
    assert np.isfinite(again.energy).all()


def test_proteinmc_real_sampling_initializes_uninitialized_move_buffers(tmp_path, monkeypatch):
    """Reused floating-point work memory cannot inject NaNs into real coordinates."""
    from chisurf.core.models.structure.proteinmc import ProteinMCRunner

    model, _, _ = _configured_proteinmc(tmp_path)
    runner = ProteinMCRunner(
        structure_source=model.structure,
        flexfit_set=model.flexfit_set,
        settings={
            "n_iter": model.n_iter,
            "n_out": model.n_out,
            "n_written": model.n_written,
            "scale": model.scale,
            "kt": model.kt,
            "potentials": model.potential_settings(),
        },
        labeling_payload=model._labeling_payload(),
        output_file=tmp_path / "initialized-work-buffers.rmf3",
    )
    allocate = np.empty_like

    def reused_work_memory(array, *args, **kwargs):
        """Expose legal NaN contents in uninitialized floating-point scratch memory."""
        result = allocate(array, *args, **kwargs)
        if result.dtype == np.dtype(float) and result.ndim == 1:
            result.fill(np.nan)
        return result

    # Only allocation contents are controlled: atoms, potentials, random moves,
    # energy evaluation and frame writing all use the actual scientific runner.
    monkeypatch.setattr(np, "empty_like", reused_work_memory)
    np.random.seed(47)
    result = runner.run()
    assert result.n_frames >= 2
    assert np.isfinite(result.energies).all()
    assert np.isfinite(result.labeling_energies).all()
    assert np.isfinite(result.structure.xyz).all()


def test_fret_structure_embedded_atoms_support_label_recomputation(tmp_path):
    """Real accessible volumes and predictions remain available after source deletion."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.tcspc.fret_structure import FRETStructure
    from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data

    entry = next(entry for entry in CATALOGUE if entry["identity"].endswith(".FRETStructure"))
    data = _data(entry, FRETStructure)
    fit = Fit(data=data, model_class=FRETStructure)
    model = fit.model
    pdb = tmp_path / "fret-148l.pdb"
    pdb.write_bytes(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes())
    model.res_1, model.res_2 = 47, 86
    model.load_structures([str(pdb)])
    model.update()
    assert np.sum(model.source_models[0]) > 0
    assert np.isfinite(model.y).all() and np.max(model.y) > 0
    state = json.loads(json.dumps(model.get_state()))
    prediction = model.y.copy()
    pdb.unlink()
    restored_fit = Fit(data=data, model_class=FRETStructure)
    restored = restored_fit.model
    restored.set_state(state)
    restored.update()
    np.testing.assert_array_equal(restored._structures[0].atoms, model._structures[0].atoms)
    np.testing.assert_array_equal(restored.source_models[0], model.source_models[0])
    np.testing.assert_allclose(restored.y, prediction, rtol=1e-12, atol=1e-12)
    assert restored.structure_files == [str(pdb)]
    restored.linker_length_1 = 14.0
    restored.recompute_structures()
    assert np.sum(restored.source_models[0]) > 0
    assert np.isfinite(restored.y).all() and np.max(restored.y) > 0
    assert not np.array_equal(restored.source_models[0], model.source_models[0])
    again_fit = Fit(data=data, model_class=FRETStructure)
    again = again_fit.model
    again.set_state(json.loads(json.dumps(restored.get_state())))
    again.update()
    np.testing.assert_array_equal(again.source_models[0], restored.source_models[0])
    np.testing.assert_allclose(again.y, restored.y, rtol=1e-12, atol=1e-12)


def test_proteinmc_fresh_session_preserves_atoms_ports_and_real_sampling(tmp_path):
    """Fresh no-MMFDB restore edits an atom-backed observable and samples again."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.project.session import capture_session
    from chisurf.core.project.storage import save_file

    configured, pdb, labeling = _configured_proteinmc(tmp_path)
    fit = Fit(data=configured.structure, model_class=ProteinMCModel, xmin=0, xmax=0)
    fit.model.set_state(configured.get_state())
    port = fit.model._distance_parameters["47-86"]
    port.bounds = (0.0, 100.0)
    port.bounds_on = True
    port.error_estimate = 0.25
    path = save_file(capture_session([fit.data], [fit]), tmp_path / "structure.cs.pto")
    pdb.unlink()
    labeling.unlink()
    command = """
import json
import sys
import numpy as np
from pathlib import Path
from test.project.scientific_catalogue_probe import _BlockMMFDB
sys.meta_path.insert(0, _BlockMMFDB())
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
path = Path(sys.argv[1])
project = load_file(path)
restored = restore_session(project)
fit = restored.fits[0]
model = fit.model
assert type(fit.data).__name__ == "Structure"
assert type(model).__name__ == "ProteinMCModel"
# Every sampling control the user set comes back from the file alone.
assert (model.n_iter, model.n_out, model.n_written, model.n_runs) == (4, 2, 2, 3)
assert (model.kt, model.scale) == (2.25, .001)
assert model.score_set == "selected"
assert model.use_flexfit is True and model.flexfit_set == "mobile"
first_term = model.potential_settings()[0]
assert first_term["weight"] == 3.5 and first_term["eval_interval"] == 2, first_term
assert (fit.xmin, fit.xmax) == (0, 0)
assert len(fit.data.atoms) > 1000
assert fit.data.atoms.dtype.names and "xyz" in fit.data.atoms.dtype.names
assert not Path(model.structure_file).exists()
assert not Path(model.labeling_file).exists()
port = model._distance_parameters["47-86"]
assert port.value > 0 and np.isfinite(port.value)
assert port.error_estimate == .25 and port.bounds_on and tuple(port.bounds) == (0., 100.), (
    port.error_estimate, port.bounds_on, port.bounds)
original_uid, native_uid = port.unique_identifier, port._port.get_uid()
recaptured = capture_session(restored.datasets, restored.fits)
assert recaptured.datasets == project.datasets
assert recaptured.fits == project.fits
before = port.value
selection = (model.structure.atoms["res_id"] == 86) & (model.structure.atoms["atom_name"] == "CA")
model.structure.xyz[selection, 0] += 5.
model.update()
assert port.value != before and port.value > 0
assert port.unique_identifier == original_uid and port._port.get_uid() == native_uid
edited_path = save_file(capture_session(restored.datasets, restored.fits), path.with_name("edited.cs.pto"))
edited = restore_session(load_file(edited_path))
assert edited.fits[0].model._distance_parameters["47-86"].value == port.value
assert edited.fits[0].model._distance_parameters["47-86"].unique_identifier == original_uid
model = edited.fits[0].model
model.output_directory = str(path.parent / "fresh-sampling")
np.random.seed(47)
model.start_sampling()
model._thread.join(timeout=30.)
assert not model.is_sampling and model.sampling_status.startswith("finished:"), model.sampling_status
assert model.frame_count >= 2 and np.isfinite(model.energy).all() and np.isfinite(model.chi2r).all()
sampled = capture_session(edited.datasets, edited.fits)
sampled_path = save_file(sampled, path.with_name("sampled.cs.pto"))
again = restore_session(load_file(sampled_path))
np.testing.assert_array_equal(again.fits[0].model.proteinmc_structure.internal_coordinates,
                              model.proteinmc_structure.internal_coordinates)
assert capture_session(again.datasets, again.fits).fits == sampled.fits
print(json.dumps({"distance_before": before, "distance_after_edit": port.value,
                  "sampled_frames": model.frame_count, "energies": model.energy,
                  "labeling_energies": model.chi2r, "port_uid": original_uid,
                  "native_uid": native_uid}))
"""
    result = subprocess.run(
        [sys.executable, "-c", command, str(path)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60.0,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (tmp_path / "fresh-structure-observables.json").write_text(result.stdout.splitlines()[-1])
