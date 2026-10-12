"""The form's state is the project, and nothing else.

QuEst already has one description of every input: `quest/settings/parameter_catalog.json`
names each field by its **path in the project dict** (`av_parameter.linker_length`,
`fret.dyes.1.attachment.chain`) and carries its label, type and help text. The
docs are generated from it and the web UI reads it. This module makes the
form read it too, by exposing a project dict as a flat set of attributes that
ChiSurf's AutoForm can bind to.

That removes the thing the `.ui` files existed to do — and it removes a whole
class of bug with them. The old widget kept its state in ~40 Qt controls and
converted to a project dict on the way out (`to_project_dict`) and back on the
way in (`load_project_dict`); the two directions were written by hand, and the
conversion is exactly where the GUI drifted away from the CLI before. Here there
is no conversion: :attr:`ProjectFormModel.project` *is* the state, so what the
GUI saves is byte-for-byte a project the CLI and the web UI accept.

Field names
-----------
Attribute names are the catalog paths, shortened where the path is long enough
to hurt (`av_parameter.` → `av_`, `fret.dyes.0.` → `donor_`, `fret.dyes.1.` →
`acceptor_`). :data:`FIELD_PATHS` is that map, and
`tests/test_form_model.py` fails if the catalog grows a parameter the map does
not cover — so a new input cannot appear in the docs and quietly miss the form.

Nothing here imports Qt. The model is testable, and usable, without a display.
"""

from __future__ import annotations

import copy
import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, MutableMapping

from chisurf.plugins.quenching_estimator.core.av import DEFAULT_ALLOWED_SPHERE_RADIUS
from chisurf.plugins.quenching_estimator.core.i18n import resolve_locale, translate_catalog, ui
from chisurf.plugins.quenching_estimator.core.project import (
    DEFAULT_FORSTER_RADIUS,
    REQUIRED_TOP_LEVEL_KEYS,
    ProjectValidationError,
    template_project,
    validate_project,
)

__all__ = [
    "FIELD_PATHS",
    "NON_SCALAR_PARAMETERS",
    "QUENCHER_COLUMNS",
    "ProjectFormModel",
]

#: Attribute name → path in the project dict. Every scalar the catalog
#: documents appears here; the order is the order the catalog lists them, which
#: is also the order the form shows them.
FIELD_PATHS: OrderedDict[str, str] = OrderedDict(
    (
        ("pdb", "pdb"),
        ("attachment_chain", "attachment.chain"),
        ("attachment_residue", "attachment.residue"),
        ("attachment_atom", "attachment.atom"),
        ("av_linker_length", "av_parameter.linker_length"),
        ("av_linker_width", "av_parameter.linker_width"),
        ("av_radius1", "av_parameter.radius1"),
        ("av_allowed_sphere_radius", "av_parameter.allowed_sphere_radius"),
        ("dg", "dg"),
        ("tau0", "tau0"),
        ("donor_D", "fret.dyes.0.D"),
        ("critical_distance", "critical_distance"),
        ("t_max", "t_max"),
        ("t_step", "t_step"),
        ("n_photons", "n_photons"),
        ("n_bins", "n_bins"),
        ("parallel_trajectories", "parallel_trajectories"),
        ("slow_radius", "slow_radius"),
        ("save_avs", "save_avs"),
        ("output_file", "output_file"),
        ("skip_frame", "skip_frame"),
        ("coarse_grained", "coarse_grained"),
        ("random_seed", "random_seed"),
        ("fret_enabled", "fret.enabled"),
        ("acceptor_chain", "fret.dyes.1.attachment.chain"),
        ("acceptor_residue", "fret.dyes.1.attachment.residue"),
        ("acceptor_atom", "fret.dyes.1.attachment.atom"),
        ("acceptor_linker_length", "fret.dyes.1.av_parameter.linker_length"),
        ("acceptor_linker_width", "fret.dyes.1.av_parameter.linker_width"),
        ("acceptor_radius1", "fret.dyes.1.av_parameter.radius1"),
        ("acceptor_D", "fret.dyes.1.D"),
        ("acceptor_slow_radius", "fret.dyes.1.slow_radius"),
        ("acceptor_dynamics", "fret.acceptor_dynamics"),
        ("fret_kappa2", "fret.kappa2"),
    )
)

#: What a field shows when the project does not carry it. A project (or a dye
#: picked from the catalogue) that never set ``allowed_sphere_radius`` gets the
#: accessible volume's own default, so the form shows that number rather than
#: an empty box that reads as "off".
FIELD_DEFAULTS: dict[str, Any] = {
    "av_allowed_sphere_radius": DEFAULT_ALLOWED_SPHERE_RADIUS,
}

#: Catalog entries that are *not* a scalar field, and where they live instead.
#: Listed so the sync test can tell "deliberately not a spin box" from "someone
#: added a parameter and forgot the form".
NON_SCALAR_PARAMETERS = {
    "fret.R0_matrix": "the fret_R0 property — a 2-dye matrix is one number",
    "amino_acid_interactions": "the quencher table",
    "amino_acid_interactions.kQ": "quencher table column",
    "amino_acid_interactions.quench_radius": "quencher table column",
    "amino_acid_interactions.quench_atoms": "quencher table column",
    "amino_acid_interactions.slow_factor": "quencher table column",
    # The acceptor's own chemistry. Only `slow_factor` is read (QuEst reports
    # the donor's decay), and it defaults to the donor's table, so it is not
    # worth a second 20-row grid in the form until someone needs to edit it.
    "fret.dyes.1.amino_acid_interactions": "defaults to the donor's table",
}

#: Columns of the quencher table, in display order. `key` is also the key in the
#: per-residue `amino_acid_interactions` entry, except `residue` (the map key).
QUENCHER_COLUMNS = ("residue", "kQ", "quench_radius", "quench_atoms", "slow_factor")


def _get_path(mapping: Any, path: str) -> Any:
    """Read a dotted path; integer-looking parts index into sequences."""
    node = mapping
    for part in path.split("."):
        if node is None:
            return None
        if isinstance(node, (list, tuple)):
            index = int(part)
            node = node[index] if -len(node) <= index < len(node) else None
        else:
            node = node.get(part)
    return node


def _set_path(mapping: Any, path: str, value: Any) -> None:
    """Write a dotted path, creating the intermediate dicts it needs.

    A missing *list* element is an error rather than something to create: the
    dye list has a fixed meaning (0 = donor, 1 = acceptor) and silently growing
    it would produce a project that validates but simulates something else.
    """
    parts = path.split(".")
    node: Any = mapping
    for part in parts[:-1]:
        if isinstance(node, (list, tuple)):
            node = node[int(part)]
        else:
            if part not in node or not isinstance(node[part], (dict, list)):
                node[part] = OrderedDict()
            node = node[part]
    last = parts[-1]
    if isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value


class ProjectFormModel:
    """A project dict presented as flat attributes, for AutoForm to bind to.

    Parameters
    ----------
    project : dict, optional
        The project to edit. Copied, never aliased — editing a form must not
        mutate a caller's dict behind its back. Defaults to
        :func:`quest.project.template_project`.
    locale : str, optional
        Language for labels, help and status text. Defaults to
        :func:`quest.i18n.resolve_locale` — `QUEST_LOCALE`, else the operating
        system's language, else English. Only presentation changes; the project
        the form produces is identical in every language.

    Examples
    --------
    >>> model = ProjectFormModel()
    >>> model.tau0 = 3.5
    >>> model.project["tau0"]
    3.5
    """

    def __init__(
        self, project: MutableMapping[str, Any] | None = None, locale: str | None = None
    ) -> None:
        # Bypass __setattr__: the field machinery needs _project to exist first.
        object.__setattr__(self, "_project", copy.deepcopy(project or template_project()))
        object.__setattr__(self, "_listeners", [])
        object.__setattr__(self, "locale", resolve_locale(locale))
        #: The last :class:`~quest.core.DecaySimulationResult`, or None.
        self.results = None
        #: One line of human-readable state, shown read-only in the form.
        self.status = self._t("status.idle")
        # The off-thread run (see start_simulation). __getattr__ raises for
        # anything it does not know, so these exist from the start.
        self._sim_thread: threading.Thread | None = None
        self._sim_job_id: str | None = None
        self._sim_result: Any = None
        self._sim_error: BaseException | None = None
        #: A file dialog the hosting window should open (see load_project_dialog), or None.
        self.dialog_request: dict[str, Any] | None = None

    # -- AutoForm plumbing --------------------------------------------------

    def _t(self, key: str) -> str:
        """One UI string in this model's language."""
        return ui(key, self.locale)

    def view_spec(self):
        """The generated view spec for this model's language."""
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import view_spec_path

        path = view_spec_path(self.locale)
        if not path.is_file():
            path = view_spec_path()

        try:
            from chisurf.core.dataspec import load_view_spec

            return load_view_spec(path)
        except Exception:
            return json.loads(path.read_text(encoding="utf-8"))

    def set_changed_callback(self, callback) -> None:
        """AutoForm's hook: it wants to know when the model changed."""
        self.add_listener(callback)

    # -- the flat attribute surface ---------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes not found normally, so real methods and
        # properties keep working.
        path = FIELD_PATHS.get(name)
        if path is None:
            raise AttributeError(name)
        value = _get_path(self._project, path)
        if value is None:
            return FIELD_DEFAULTS.get(name)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        path = FIELD_PATHS.get(name)
        if path is None:
            object.__setattr__(self, name, value)
            return
        _set_path(self._project, path, value)
        self._notify()

    def __dir__(self) -> Iterable[str]:
        return sorted(set(super().__dir__()) | set(FIELD_PATHS))

    # -- the project ------------------------------------------------------

    @property
    def project(self) -> dict:
        """The live project dict. Editing it edits the form."""
        return self._project

    def to_project_dict(self) -> dict:
        """A copy of the project, safe to hand to the service layer."""
        return copy.deepcopy(self._project)

    def load_project_dict(self, project: MutableMapping[str, Any]) -> None:
        """Replace the whole state with *project*, then fix attachment if needed.

        Raises
        ------
        ProjectValidationError
            When *project* is not a mapping or lacks a key every project carries
            (:data:`quest.project.REQUIRED_TOP_LEVEL_KEYS`). The state is left as it
            was: a file such as ``{}`` used to replace it, and every number field
            of the form then drew empty because the project had no value to show.
        """
        if not isinstance(project, dict):
            raise ProjectValidationError("A QuEst project is a JSON object.")
        missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in project]
        if missing:
            raise ProjectValidationError(f"Not a QuEst project: missing {', '.join(missing)}.")
        object.__setattr__(self, "_project", copy.deepcopy(project))
        self.auto_attach_to_structure()
        self._notify()

    def validate(self) -> list[str]:
        """Problems with the current project; empty when it is simulatable."""
        try:
            validate_project(self._project)
        except ProjectValidationError as error:
            return [str(error)]
        return []

    # -- FRET: one number, stored as a matrix -----------------------------

    @property
    def fret_R0(self) -> float:
        """Förster radius in **Ångström** (`fret.R0_matrix[0][1]`).

        The project stores a full donor/acceptor matrix because there may one
        day be more than two dyes. With two there is a single off-diagonal
        number, and showing a 2×2 grid of which half is `null` helps nobody.
        """
        value = _get_path(self._project, "fret.R0_matrix.0.1")
        return DEFAULT_FORSTER_RADIUS if value is None else float(value)

    @fret_R0.setter
    def fret_R0(self, value: float) -> None:
        r0 = float(value)
        _set_path(self._project, "fret.R0_matrix", [[None, r0], [r0, None]])
        self._notify()

    # -- the quencher table ------------------------------------------------

    def quencher_rows(self) -> list[dict]:
        """One row per amino acid, for the table section.

        Only residues that actually quench are worth a row by default, but the
        table shows all of them: which residues are *not* quenchers is part of
        the model, and hiding them makes a zero look like an omission.
        """
        interactions = self._project.get("amino_acid_interactions") or {}
        rows = []
        for residue in sorted(interactions):
            entry = interactions[residue] or {}
            atoms = entry.get("quench_atoms") or []
            rows.append(
                {
                    "residue": residue,
                    "kQ": entry.get("kQ", 0.0),
                    "quench_radius": entry.get("quench_radius"),
                    "quench_atoms": ", ".join(atoms),
                    "slow_factor": entry.get("slow_factor", 0.1),
                }
            )
        return rows

    def update_quencher_cell(self, row_index: int, column_key: str, value: Any) -> None:
        """Write one edited cell back into `amino_acid_interactions`.

        Bad input is dropped rather than raising: the user is mid-typing, and a
        traceback out of a cell editor is not a useful way to say "not a number".
        """
        rows = self.quencher_rows()
        if not 0 <= row_index < len(rows):
            return
        residue = rows[row_index]["residue"]
        entry = self._project.setdefault("amino_acid_interactions", {}).setdefault(residue, {})
        text = "" if value is None else str(value).strip()
        if column_key == "quench_atoms":
            entry["quench_atoms"] = [a.strip() for a in text.split(",") if a.strip()]
        elif column_key == "quench_radius":
            # Blank means "use the global critical distance", which is null in
            # the schema — not zero, which would switch quenching off.
            entry["quench_radius"] = None if not text else float(text)
        elif column_key in ("kQ", "slow_factor"):
            try:
                entry[column_key] = float(text)
            except ValueError:
                return
        else:
            return
        self._notify()

    # -- structure preview -------------------------------------------------

    @property
    def structure_label(self) -> str:
        """Human-readable name of the loaded structure, for read-only display.

        Distinct from the ``pdb`` file picker so the form never has two controls
        bound to one value.
        """
        pdb = self._project.get("pdb")
        if not pdb:
            return self._t("status.no_structure")
        return Path(str(pdb)).name

    def preview_models(self) -> list[str]:
        """Paths for the 3D viewer: the structure, when there is a readable one."""
        pdb = self._project.get("pdb")
        if pdb and Path(str(pdb)).is_file():
            return [str(pdb)]
        return []

    def auto_attach_to_structure(self) -> None:
        """Pick valid attachment sites from the loaded PDB.

        When a structure is loaded the template's default attachment (chain A,
        residue 1) may not exist. This reads the structure's chains/residues and
        selects sensible defaults: donor on the first standard residue of the
        first chain, acceptor on the last standard residue of the same chain.
        Only overwrites an attachment that is missing or invalid.
        """
        pdb = self._project.get("pdb")
        if not pdb or not Path(str(pdb)).is_file():
            return
        try:
            from chisurf.plugins.quenching_estimator.core.structure import structure_metadata

            meta = structure_metadata(pdb)
        except Exception:
            return
        chains = meta.get("chains", [])
        if not chains:
            return

        STANDARD = {
            "ALA",
            "ARG",
            "ASN",
            "ASP",
            "CYS",
            "GLN",
            "GLU",
            "GLY",
            "HIS",
            "ILE",
            "LEU",
            "LYS",
            "MET",
            "PHE",
            "PRO",
            "SER",
            "THR",
            "TRP",
            "TYR",
            "VAL",
        }

        def find_residue(chain, prefer_id=None):
            residues = chain.get("residues", [])
            std = [r for r in residues if r.get("name", "").upper() in STANDARD]
            if not std:
                return None
            if prefer_id is not None:
                for r in std:
                    if r["id"] == prefer_id:
                        return r
            return std[0]

        def first_atom(residue, fallback="CB"):
            atoms = residue.get("atoms", []) if residue else []
            for pref in ("CB", "CA", "OG", "SG"):
                if pref in atoms:
                    return pref
            return atoms[0] if atoms else fallback

        # The first chain may be a sugar or a ligand (148L's chain A is NAG);
        # attach to the first chain that has a standard residue to bind to.
        chain0 = next((c for c in chains if find_residue(c) is not None), None)
        if chain0 is None:
            return
        donor_res = find_residue(chain0)

        current_chain = _get_path(self._project, "attachment.chain")
        current_res = _get_path(self._project, "attachment.residue")
        # A site counts as valid only if it is a standard residue: the template
        # default (A:1) can name a sugar that exists but cannot take a dye.
        current_ok = any(
            c["id"] == current_chain
            and any(
                r["id"] == current_res and r.get("name", "").upper() in STANDARD
                for r in c.get("residues", [])
            )
            for c in chains
        )
        needs_fix = not current_ok

        if needs_fix or current_res is None:
            _set_path(self._project, "attachment.chain", chain0["id"])
            _set_path(self._project, "attachment.residue", donor_res["id"])
            _set_path(self._project, "attachment.atom", first_atom(donor_res))
            dyes = self._project.get("fret", {}).get("dyes", [])
            if dyes:
                dyes[0]["attachment"] = {
                    "chain": chain0["id"],
                    "residue": donor_res["id"],
                    "atom": first_atom(donor_res),
                }

        # Acceptor: last standard residue on the same chain
        if self._project.get("fret", {}).get("enabled"):
            dyes = self._project.get("fret", {}).get("dyes", [])
            if len(dyes) > 1:
                acc_chain_id = dyes[1].get("attachment", {}).get("chain")
                # The acceptor's chain only counts when it can carry a dye: 148L
                # has a chain A, but it is the NAG ligand, so a template acceptor
                # on A:2 stayed there and every FRET run failed on it.
                acc_chain = next(
                    (c for c in chains if c["id"] == acc_chain_id and find_residue(c) is not None),
                    chain0,
                )
                all_std = [
                    r
                    for r in acc_chain.get("residues", [])
                    if r.get("name", "").upper() in STANDARD
                ]
                if all_std:
                    acc_res = all_std[-1]
                    dyes[1]["attachment"] = {
                        "chain": acc_chain["id"],
                        "residue": acc_res["id"],
                        "atom": first_atom(acc_res),
                    }

        self._notify()

    # -- persistence: the saved file is a project ---------------------------

    def save_project(self, path: str | Path) -> Path:
        """Write the state as project JSON — the CLI's and web UI's format."""
        destination = Path(path)
        destination.write_text(json.dumps(self._project, indent=2, default=str), encoding="utf8")
        return destination

    def load_project(self, path: str | Path) -> None:
        """Read a project written by any surface."""
        with Path(path).open("r", encoding="utf8") as handle:
            self.load_project_dict(json.load(handle))

    # The two dialog actions are what the toolbar buttons call. The model does
    # not draw a dialog: it *requests* one (``dialog_request``) and the window
    # that hosts it opens its own emtk file dialog, then hands the choice back
    # through :meth:`finish_dialog`. So the model stays importable, and
    # testable, where there is no display, and no toolkit is imported here.

    def load_project_dialog(self) -> dict:
        """Ask the hosting window for a project file to read; returns the request."""
        return self._request_dialog(
            "load_project",
            mode="open",
            title=self._t("dialog.load_project"),
            filters=f"{self._t('filter.project')};;{self._t('filter.all')}",
        )

    def save_project_dialog(self) -> dict:
        """Ask the hosting window where to write the project; returns the request."""
        return self._request_dialog(
            "save_project",
            mode="save",
            title=self._t("dialog.save_project"),
            filters=f"{self._t('filter.project')};;{self._t('filter.all')}",
            filename="project.json",
        )

    def _request_dialog(self, kind: str, **options: Any) -> dict:
        """Record a file-dialog request for the hosting window and notify it."""
        request: dict[str, Any] = {"kind": kind, **options}
        self.dialog_request = request
        self._notify()
        return request

    def take_dialog_request(self) -> dict | None:
        """Return the pending file-dialog request and clear it (the host opens it once)."""
        request, self.dialog_request = self.dialog_request, None
        return request

    def finish_dialog(self, kind: str, path: str | Path) -> Path | None:
        """Carry out what a file dialog chose; a failure becomes the status line.

        Parameters
        ----------
        kind : str
            ``"load_project"`` or ``"save_project"``, the ``kind`` of the request.
        path : str or pathlib.Path
            The chosen file. A project saved without an extension gets ``.json``.

        Returns
        -------
        pathlib.Path or None
            The file read or written, or None when nothing was (the status says why).
        """
        path = Path(path)
        try:
            if kind == "save_project":
                if path.suffix.lower() != ".json":
                    path = path.with_name(path.name + ".json")
                done = self.save_project(path)
                self.status = self._t("status.saved").format(name=done.name)
            elif kind == "load_project":
                self.load_project(path)
                done = path
                self.status = self._t("status.loaded").format(name=path.name)
            else:
                raise ValueError(f"unknown file dialog {kind!r}")
        except (ProjectValidationError, OSError, ValueError) as error:
            # A file that is not a project leaves the form as it was and says why.
            self.status = f"{path.name}: {error}"
            self._notify()
            return None
        self._notify()
        return done

    def load_example(self) -> Path:
        """Load the plugin's demo project (T4 lysozyme, dye on E36), written by ``demo.make_demo``.

        Returns
        -------
        pathlib.Path
            The demo project file that was read.
        """
        from chisurf.plugins.quenching_estimator.demo import make_demo

        path = make_demo()
        self.load_project(path)
        self.status = self._t("status.loaded").format(name=path.name)
        self._notify()
        return path

    # -- running, and what came out ----------------------------------------

    def start_simulation(self) -> str:
        """Start a run on a worker thread and return its job id.

        The view-model calls `quest.api`, exactly as the CLI and the web
        backend do — the form contributes no physics of its own. That is the
        rule the GUI broke before, when it shipped its own quenching chemistry.

        The run is registered with :mod:`quest.tasks`, so a desktop run is
        observable through `quest.jobs.list` like any other — that mechanism
        existed from `LAY-07` but the desktop did not use it, and ran on the
        GUI thread instead.

        **Nothing here touches Qt and nothing here notifies.** A listener may
        redraw widgets, which is only safe on the GUI thread, so the worker
        only stores its outcome; :meth:`poll_simulation` applies it. That is
        the whole reason this is three methods rather than one.

        `save_outputs=False` keeps a GUI run from littering `jobs/` in whatever
        directory the app happened to start in.
        """
        from chisurf.plugins.quenching_estimator.core.tasks import default_manager

        if self._sim_thread is not None and self._sim_thread.is_alive():
            assert self._sim_job_id is not None  # set before the thread starts
            return self._sim_job_id

        manager = default_manager()
        job = manager.create("quest.simulate", {"surface": "gui"})
        manager.start(job.job_id)
        self._sim_job_id = job.job_id
        self._sim_error = None
        self._sim_result = None
        self.status = self._t("status.running")
        self._notify()

        project = copy.deepcopy(self._project)

        def worker() -> None:
            from chisurf.plugins.quenching_estimator.api.local import simulate_project
            from chisurf.plugins.quenching_estimator.rpc.contract import error_code_for

            try:
                result = simulate_project(project, save_outputs=False)
            except Exception as error:  # noqa: BLE001 — re-raised on the GUI thread
                self._sim_error = error
                manager.fail(job.job_id, str(error), error_code_for(error))
            else:
                self._sim_result = result
                manager.finish(job.job_id, result)

        self._sim_thread = threading.Thread(
            target=worker, name=f"quest-gui-simulate-{job.job_id[:8]}", daemon=True
        )
        self._sim_thread.start()
        return job.job_id

    def wait_simulation(self, timeout: float | None = None) -> bool:
        """Block until the run finishes, or *timeout* seconds pass.

        Returns whether it is finished. A GUI caller passes a short timeout in
        a loop and pumps its event queue in between; a headless caller passes
        `None`.
        """
        if self._sim_thread is None:
            return True
        self._sim_thread.join(timeout)
        return not self._sim_thread.is_alive()

    def poll_simulation(self) -> str | None:
        """Apply a finished run's outcome. **Call this on the GUI thread.**

        Returns the terminal job status (`completed`, `failed`, `cancelled`)
        once, or `None` while the run is still going. Applying the outcome —
        and therefore notifying listeners — happens here so that widgets are
        only ever touched from the thread that owns them.
        """
        from chisurf.plugins.quenching_estimator.core.tasks import default_manager

        if self._sim_job_id is None:
            return None
        if self._sim_thread is not None and self._sim_thread.is_alive():
            return None

        job = default_manager().get(self._sim_job_id)
        status = job.status.value if job is not None else "completed"
        self._sim_thread = None
        self._sim_job_id = None

        if self._sim_error is not None:
            self.results = None
            self.status = self._t("status.failed").format(error=self._sim_error)
        elif status == "cancelled":
            # The worker returned after the flag was set: its result is not the
            # one the user asked for, so it is discarded rather than displayed.
            self.results = None
            self._sim_result = None
            self.status = self._t("status.cancelled")
        else:
            self.results = self._sim_result
            self.status = self._describe(self.results)
        self._notify()
        return status

    def cancel_simulation(self) -> bool:
        """Ask a running simulation to stop. Returns whether anything was asked.

        **Honest about what this delivers**: cancellation is cooperative and a
        single simulation has essentially one checkpoint, because
        `simulate_traj` computes the whole trajectory inside one compiled
        IMP.bff call, and compiled code cannot poll a Python flag ([tasks.md]). So this
        marks the run `CANCELLING`, the form stops waiting on it, and the
        result is discarded when the kernel eventually returns — it does not
        stop the computation. A scan, which checks between sites, does stop.
        """
        from chisurf.plugins.quenching_estimator.core.tasks import default_manager

        if self._sim_job_id is None:
            return False
        return default_manager().cancel(self._sim_job_id)

    @property
    def simulation_running(self) -> bool:
        return self._sim_thread is not None and self._sim_thread.is_alive()

    def run_simulation(self) -> Any:
        """Simulate and return the result, blocking until it is done.

        The synchronous entry point, for headless callers and tests. It is the
        threaded path joined immediately, not a second implementation — a
        second one is how the GUI drifted from the CLI in the first place.
        Raises whatever the run raised, as it always did.
        """
        self.start_simulation()
        self.wait_simulation()
        self.poll_simulation()
        if self._sim_error is not None:
            error, self._sim_error = self._sim_error, None
            raise error
        return self.results

    @staticmethod
    def _describe(result: Any) -> str:
        parts = [
            f"QY = {result.quantum_yield_donor:.3f}",
            f"⟨τ⟩ = {result.lifetime_donor:.2f} ns",
        ]
        if result.fret_efficiency is not None:
            parts.append(f"E = {result.fret_efficiency:.3f}")
        return "   ".join(parts)

    def decay_series(self) -> list[dict]:
        """Donor (and FRET) decay histograms, for the decay plot."""
        result = getattr(self, "results", None)
        if result is None:
            return []
        series = [{"x": result.time, "y": result.donor_counts, "name": self._t("plot.decay.donor")}]
        if result.fret_counts is not None:
            series.append(
                {"x": result.time, "y": result.fret_counts, "name": self._t("plot.decay.fret")}
            )
        return series

    def trajectory_series(self) -> list[dict]:
        """Dye distance from the mean position over the trajectory."""
        result = getattr(self, "results", None)
        if result is None or result.trajectory_time_ns is None:
            return []
        return [
            {
                "x": result.trajectory_time_ns,
                "y": result.trajectory_distance_to_mean,
                "name": "|r − ⟨r⟩|",
            }
        ]

    def autocorrelation_series(self) -> list[dict]:
        """Autocorrelation of the dye position — how fast the dye forgets."""
        result = getattr(self, "results", None)
        if result is None or result.trajectory_autocorr is None:
            return []
        return [
            {
                "x": result.trajectory_autocorr_lag_ns,
                "y": result.trajectory_autocorr,
                "name": "ACF",
            }
        ]

    # -- change notification ------------------------------------------------

    def add_listener(self, callback) -> None:
        """Call *callback* after any field changes (the form uses this to redraw)."""
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:  # pragma: no cover - a bad listener must not
                pass  # take the form down mid-edit

    # -- help text, from the one place it is written ------------------------

    def catalog_entry(self, path: str) -> dict:
        """The catalog entry for a project path, in this model's language."""
        return dict(translate_catalog(self.locale).get("parameters", {}).get(path, {}))
