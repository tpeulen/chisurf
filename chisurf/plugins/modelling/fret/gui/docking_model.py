"""Qt-free backing model of the FRET docking form.

Its attributes mirror the fields of ``fret_dock.view.json``; :meth:`DockingModel.build_params`
turns them into the ``api.operations`` request. The Structure Tools docking card keeps its own
session (:mod:`chisurf.plugins.modelling.structure_tools.cards.docking_model`) and is tested
against this model's requests.
"""

from __future__ import annotations

import pathlib

from chisurf.core.dataspec import load_view_spec

_GUI_DIR = pathlib.Path(__file__).parent


class DockingModel:
    """Backing model for the FRET docking AutoForm.

    Attributes mirror the fields in ``fret_dock.view.json``; AutoForm reads and
    writes them directly. Output fields are filled in after a run.
    """

    def __init__(self) -> None:
        # inputs
        self.pdb_paths = ""
        self.fps_json = ""
        self.output_dir = ""
        self.operation = "dock"
        self.method = "minimize"
        self.score_set = ""
        # sampling
        self.n_frames = 500
        self.mc_steps = 10
        self.n_best = 20
        self.n_repeats = 1
        self.refine_av_cycles = 0
        self.fixed_body = 0
        self.sigma_da = 6.0
        self.ev_weight = 1.0
        self.simulated_annealing = False
        self.save_distributions = False
        self.av_backend = "auto"
        self.save_trajectory = False
        # FPS-style docked state (transform vectors) from the last run / loaded
        # project; when ``continue_from_poses`` is set a dock resumes from these.
        self.poses = []
        self.pose_score = None
        self.continue_from_poses = False
        # results
        self.status = ""
        self.score = 0.0
        self.n_distances = 0
        # structure(s) shown in the 3D preview (str or list of PDB paths)
        self.preview_models = []

    def view_spec(self):
        """Return the AutoForm view spec from ``fret_dock.view.json``."""
        return load_view_spec(_GUI_DIR / "fret_dock.view.json")

    # -- helpers -----------------------------------------------------------
    def pdb_list(self):
        return [p.strip() for p in self.pdb_paths.split(",") if p.strip()]

    def ensure_output_dir(self):
        """Fill ``output_dir`` with a sensible default when the user left it blank.

        Defaults to a ``dock_out`` folder next to the fps.json (or the first
        PDB) so the example runs without forcing the user to pick a directory.
        """
        if self.output_dir and self.output_dir.strip():
            return self.output_dir
        anchor = self.fps_json or (self.pdb_list()[0] if self.pdb_list() else "")
        base = pathlib.Path(anchor).parent if anchor else pathlib.Path.cwd()
        self.output_dir = str(base / "dock_out")
        return self.output_dir

    def build_params(self):
        """Build the api.operations request dict for the selected operation.

        ``dock`` with ``n_repeats > 1`` becomes an ``errors`` request (repeated
        independent docking trials), mirroring the FPS repeated-run workflow.
        """
        op = self.operation
        if op == "dock":
            req = {
                "pdb_paths": self.pdb_list(),
                "fps_json": self.fps_json,
                "output_dir": self.output_dir,
                "n_frames": self.n_frames,
                "mc_steps": self.mc_steps,
                "n_best": self.n_best,
                "fixed_body": self.fixed_body,
                "sigma_da": self.sigma_da,
                "simulated_annealing": self.simulated_annealing,
                "score_set": self.score_set,
                "method": self.method,
                "refine_av_cycles": self.refine_av_cycles,
                "ev_weight": self.ev_weight,
                "save_distributions": self.save_distributions,
                "av_backend": self.av_backend,
                "save_trajectory": self.save_trajectory,
            }
            if int(self.n_repeats) > 1:
                req["n_trials"] = int(self.n_repeats)
                return "errors", req
            # Continue a single dock from the saved docked state (FPS-style).
            if self.continue_from_poses and self.poses:
                req["initial_poses"] = list(self.poses)
            return op, req
        if op == "refine":
            return op, {
                "pdb_paths": self.pdb_list(),
                "fps_json": self.fps_json,
                "output_dir": self.output_dir,
                "score_set": self.score_set,
            }
        if op == "screen":
            return op, {
                "pdb_inputs": self.pdb_list(),
                "fps_json": self.fps_json,
                "score_set": self.score_set,
                "output_csv": str(pathlib.Path(self.output_dir) / "screen.csv")
                if self.output_dir
                else None,
            }
        # score
        return op, {
            "pdb_paths": self.pdb_list(),
            "fps_json": self.fps_json,
            "score_set": self.score_set,
            "mean_position_restraint": True,
            "sigma_da": self.sigma_da,
        }
