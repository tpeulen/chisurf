"""Step 1 of the burst workflow, *Data Selection*, drawn with emtk.

:class:`BurstDataSelectionModel` holds the raw TTTR files every later step reads and the role
each is assigned to -- measurement, buffer, and per colour of the detector setup an IRF and a
reference dye (:mod:`..samples`) -- and registers each newly added local file in MMFDB (object
store + raw-data registry) through :func:`import_raw_file`. Nothing in it imports Qt.

:class:`BurstDataSelectionApp` draws a *source* -- the model, or any object that speaks the same
few methods (``paths``, ``add_paths``, ``remove_index``, ``clear``, ``mmfdb_payload``,
``import_path``) -- as four windows: the data (the Datasets workspace's photon streams on top,
the assignment table under them: one row per role, made from the setup, each listing what is
assigned to it), the selected entry's details, a summary, and the calibrations the buffer and
reference-dye files give (computed off the UI thread). A dataset dropped on a row of the
assignment table is that role; only the Measurement row goes to Burst Selection.
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form, draw_sections
from emtk.widgets.view_spec import load_view_spec

from chisurf.core.fio.staging import TTTR_EXTENSIONS
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput
from chisurf.plugins.emtk_layout import action_caption, action_tooltip, button_row

HERE = Path(__file__).resolve().parent

#: The background a host paints before the first frame.
WINDOW_BG = (30, 32, 38, 255)

#: MMFDB kinds the database picker offers for raw data.
MMFDB_KINDS = ("raw_data", "raw_measurement", "external_reference")


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def expand_paths(paths) -> list[Path]:
    """Files as given, folders replaced by the TTTR files directly inside them (sorted); resolved."""
    out: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            out.extend(
                sorted(
                    child.resolve()
                    for child in path.iterdir()
                    if child.is_file() and child.suffix.lower().lstrip(".") in _EXTENSIONS
                )
            )
        else:
            out.append(path.resolve())
    return out


_EXTENSIONS = {str(ext).lower().lstrip(".") for ext in TTTR_EXTENSIONS}

log = logging.getLogger(__name__)

#: Why a file was not registered: MMFDB stores objects only for a signed-in user, so without a session every
#: upload is refused ("Authentication required"); the file is used from disk all the same.
NOT_SIGNED_IN = (
    "Not signed in to MMFDB: the file is used from disk and not registered. "
    "Sign in (MMFDB Admin) to register it."
)


def signed_in(client: Any) -> bool:
    """Whether *client* can write to MMFDB: an MMFDB client carries a session ``token``; one that has none is
    anonymous, and MMFDB refuses an anonymous upload. A client without a ``token`` attribute authenticates
    itself (a test double, a pre-authorised transport)."""
    return client is not None and (not hasattr(client, "token") or bool(getattr(client, "token")))


def import_raw_file(client: Any, path: Path) -> dict[str, Any]:
    """Put a local file into the MMFDB object store and register it as raw TTTR data.

    The RPC object store cannot read the client's file system, so the bytes go as base64 rather than a path. A
    failing registration is kept beside the stored object (``raw_data_error``); a failing upload is the whole
    entry's ``error``. Never raises.
    """
    try:
        encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        object_result = (
            client.call(
                "mmfdb.objects.put",
                {
                    "data": encoded,
                    "filename": Path(path).name,
                    "metadata": {"source": "burst_analysis.data_selection"},
                },
            )
            or {}
        )
        payload: dict[str, Any] = {"object_result": object_result}
        try:
            raw_result = (
                client.call(
                    "raw_data.register",
                    {
                        "raw_data": {
                            "file_path": str(path),
                            "data_type": "TTTR",
                            # One of MMFDB's storage_mode vocabulary terms; "file" is not one, and every
                            # registration was rejected.
                            "storage_mode": "local_file",
                            "header_metadata": {
                                "mmfdb_object": object_result.get("object", {}),
                                "source": "burst_analysis.data_selection",
                            },
                        }
                    },
                )
                or {}
            )
            payload["raw_data_result"] = raw_result
        except Exception as raw_exc:  # noqa: BLE001 - kept beside the stored object
            payload["raw_data_error"] = str(raw_exc)
        return payload
    except Exception as exc:  # noqa: BLE001 - the entry says why
        return {"error": str(exc)}


#: A reference dye's anisotropy right after the pulse below this says its VV and VH channels are
#: swapped in the setup (``samples._g_of``'s ``r_peak``).
SWAPPED_BELOW = -0.05


class BurstDataSelectionModel:
    """The raw TTTR files of a burst workflow, what each is, and their MMFDB registration (no Qt, no emtk).

    Every file is assigned to a row of the step's assignment table (:attr:`assignments`,
    ``{path: row key}``): ``measurement`` (searched for bursts), ``buffer``, and per colour of the
    detector setup ``irf:<colour>`` and ``reference:<colour>``
    (:func:`chisurf.plugins.burst.burst_analysis.samples.row_keys`). Files that came from one
    workspace group stay one group (:attr:`groups`, :attr:`group_of`).

    Parameters
    ----------
    client : object, optional
        An MMFDB client (``call(method, params)``). Default: the shared session client of the dataset picker,
        made on the first import.
    auto_import : bool
        Register each newly added file in MMFDB, on every add.
    on_change : callable, optional
        Called after the file list or an assignment changed.
    """

    def __init__(
        self,
        client: Any = None,
        *,
        auto_import: bool = True,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._paths: list[Path] = []
        self._client = client
        self.auto_import = bool(auto_import)
        self.on_change = on_change
        self.imports: dict[str, dict[str, Any]] = {}
        self.selections: dict[str, dict[str, Any]] = {}
        self._imported: set[str] = set()
        self.selected_index: int | None = None
        self.status_text = "No TTTR files selected."
        self._told_not_signed_in = False
        #: Which workspace dataset each file came from (its burst runs go into that dataset's
        #: analysis container in the project).
        self.sources: dict[str, str] = {}
        #: ``{path: row key}``: the row each file is assigned to (as stored: a row of a colour the
        #: setup no longer has is kept, and shown as unassigned).
        self.assignments: dict[str, str] = {}
        #: ``{group uid: name}`` of the workspace groups files came from, and ``{path: group uid}``.
        self.groups: dict[str, str] = {}
        self.group_of: dict[str, str] = {}
        #: The detector setup the rows are made from (the workflow's step 0), and where the
        #: live one is read from (set by the app).
        self.setup: dict[str, Any] = {}
        self.setup_provider: Callable[[], dict] | None = None
        #: What the buffer and reference-dye files gave (:func:`..samples.calibrate`).
        self.calibration: dict[str, Any] = {}
        #: ``{colour: dye}`` of the reference-dye rows (:func:`..samples.dye_choice`: the database
        #: dye, where it came from -- ``user``, ``header``, ``file name``, ``default`` -- the
        #: temperature and a custom D). A dye the user chose is never replaced by an inference.
        self.dyes: dict[str, dict] = {}
        #: ``{detector: G}`` this step wrote into the setup last: a setup value that differs
        #: was edited by hand and is kept.
        self.applied_g: dict[str, float] = {}
        #: ``{path: measurement}`` of the buffer, IRF and reference-dye files this step found
        #: beside a measurement and put into their rows itself (:meth:`propose_references`), and
        #: the proposals the user removed: never proposed again.
        self.proposed: dict[str, str] = {}
        self.declined: set[str] = set()
        #: Propose the references beside every new measurement (:meth:`propose_references`).
        self.propose = True

    # -- the source protocol ------------------------------------------------------------------------------- #
    def paths(self) -> list[Path]:
        """Every file of the step, in order (measurements and calibration files)."""
        return list(self._paths)

    def mmfdb_payload(self) -> dict[str, Any]:
        """MMFDB import and database-selection records, by file."""
        return {"imports": self.imports, "selections": self.selections}

    def client(self) -> Any:
        if self._client is None:
            from chisurf.emtk.dataset_picker import session_client

            self._client = session_client()
        return self._client

    def add_paths(self, paths, row: str | None = None) -> int:
        """Add files and folders (expanded, de-duplicated) to *row* (default: guessed from each
        name, else ``measurement``); register new local files. A file already listed moves to
        *row* when one is given. Returns how many were added."""
        from ..samples import guess_sample_type

        added = 0
        moved = False
        for path in expand_paths(paths):
            key = str(path)
            if path in self._paths:
                if row and self.assignments.get(key) != row:
                    self.assignments[key] = row
                    moved = True
                continue
            self._paths.append(path)
            self.assignments[key] = row or guess_sample_type(path)
            added += 1
            if self.auto_import and key not in self._imported:
                self._imported.add(key)
                self.import_path(path)
        if added and self.selected_index is None:
            self.selected_index = 0
        new_measurements = [
            p for p in self._paths[len(self._paths) - added:] if self.assignments.get(str(p)) == "measurement"
        ] if added else []
        if new_measurements and self.propose:
            self.propose_references(new_measurements, notify=False)
        if added or moved:
            self._changed()
        return added

    def propose_references(self, measurements, notify: bool = True) -> list[Path]:
        """Put the buffer, IRF and reference-dye measurements found by name beside
        *measurements* (:func:`chisurf.core.fio.reference_files.find_reference_measurements`:
        their folder, else one up) into their rows -- a dye's row by its colour (Rh110 the
        green reference, Alexa 647 the red). Data Selection is the one place the workflow's
        references come from; a proposal is shown like any file, marked as found, and one the
        user removes is not proposed again. Returns the files added."""
        from chisurf.core.fio.reference_files import find_reference_measurements

        from ..samples import colour_groups, guess_colour, guess_sample_type

        measurements = [Path(p) for p in measurements]
        # a dye of a colour the setup has no detectors for is not this workflow's (Alexa 647 for
        # a green-only setup would land in the green row and give it a red dye's G)
        colours = {g["colour"] for g in colour_groups(self.current_setup())}
        if not measurements:
            return []
        try:
            found = find_reference_measurements(measurements)
        except Exception:  # noqa: BLE001 - nothing beside them: nothing proposed
            return []
        added: list[Path] = []
        for path in expand_paths([*found["dye"], *found["irf"], *found["bg"]]):
            key = str(path)
            if path in self._paths or key in self.declined:
                continue
            kind = guess_sample_type(path)
            if kind == "reference" and colours and guess_colour(path) not in colours:
                continue
            self._paths.append(path)
            self.assignments[key] = kind
            self.proposed[key] = measurements[0].name
            added.append(path)
            if self.auto_import and key not in self._imported:
                self._imported.add(key)
                self.import_path(path)
        if added and notify:
            self._changed()
        return added

    def import_path(self, path: Path) -> dict[str, Any]:
        """Register *path* in MMFDB now (again, if it was before); the record is kept in :attr:`imports`."""
        try:
            client = self.client()
        except Exception as exc:  # noqa: BLE001 - no database: the record says so
            entry = {"error": f"MMFDB unavailable: {exc}"}
        else:
            if client is None:
                entry = {"error": "MMFDB unavailable."}
            elif not signed_in(client):
                # Not a fault: no request is sent, and the notice is given once, not once per file.
                entry = {"skipped": NOT_SIGNED_IN}
                if not self._told_not_signed_in:
                    self._told_not_signed_in = True
                    log.info("Burst data selection: %s", NOT_SIGNED_IN)
            else:
                entry = import_raw_file(client, path)
        self.imports[str(path)] = entry
        self._changed(notify=False)
        return entry

    def _forget(self, path: Path) -> None:
        key = str(path)
        if self.proposed.pop(key, None) is not None:
            self.declined.add(key)  # removed by the user: not proposed again
        self.assignments.pop(key, None)
        group = self.group_of.pop(key, None)
        if group and group not in self.group_of.values():
            self.groups.pop(group, None)

    def remove_index(self, index: int) -> None:
        if 0 <= index < len(self._paths):
            self._forget(self._paths.pop(index))
            if self.selected_index is not None and self.selected_index >= len(self._paths):
                self.selected_index = len(self._paths) - 1 if self._paths else None
            self._changed()

    def remove_paths(self, paths) -> int:
        """Take *paths* out of the step; returns how many were listed."""
        wanted = {str(p) for p in paths}
        keep = [p for p in self._paths if str(p) not in wanted]
        removed = len(self._paths) - len(keep)
        for path in self._paths:
            if str(path) in wanted:
                self._forget(path)
        self._paths = keep
        if self.selected_index is not None and self.selected_index >= len(self._paths):
            self.selected_index = len(self._paths) - 1 if self._paths else None
        if removed:
            self._changed()
        return removed

    def clear(self) -> None:
        self._paths.clear()
        self.assignments.clear()
        self.groups.clear()
        self.group_of.clear()
        self.selected_index = None
        self._changed()

    def add_database_selection(self, selection: Any, local_path: str) -> None:
        """A dataset chosen in the MMFDB picker: remembered, then added as a file (not registered again)."""
        path = Path(local_path).resolve()
        self.selections[str(path)] = {
            "artifact_id": getattr(selection, "artifact_id", ""),
            "artifact_kind": getattr(selection, "artifact_kind", ""),
            "label": getattr(selection, "label", ""),
        }
        self._imported.add(str(path))
        self.add_paths([path])

    # -- rows ------------------------------------------------------------------------------------------------ #
    def assign(self, paths, row: str) -> int:
        """Move *paths* to *row*; returns how many changed."""
        changed = 0
        for path in paths:
            key = str(Path(path))
            if key in self.assignments and self.assignments[key] != row:
                self.assignments[key] = row
                changed += 1
        if changed:
            self._changed()
        return changed

    def set_group(self, paths, uid: str, name: str) -> None:
        """Keep *paths* together as the workspace group *uid* named *name*."""
        if not uid:
            return
        self.groups[str(uid)] = str(name or uid)
        for path in paths:
            if Path(path) in self._paths or str(path) in self.assignments:
                self.group_of[str(Path(path))] = str(uid)

    def row_of(self, path) -> str:
        """The row *path* is shown in with the current setup (``"unassigned"``: its row is gone)."""
        from ..samples import resolve_row

        key = str(path)
        return resolve_row(self.assignments.get(key, "measurement"), self.current_setup(), key)

    def current_setup(self) -> dict:
        """The setup the rows are made from: the workflow's live (:attr:`setup_provider`), else
        the last one the step was given (:attr:`setup`)."""
        if callable(self.setup_provider):
            try:
                self.setup = dict(self.setup_provider() or {})
            except Exception:  # noqa: BLE001 - keep the last one
                pass
        return self.setup

    def rows(self) -> dict[str, str]:
        """``{path: row}`` of every file, as the current setup shows them."""
        return {str(p): self.row_of(p) for p in self._paths}

    def measurement_paths(self) -> list[Path]:
        """The files in the Measurement row: what Burst Selection searches."""
        return [p for p in self._paths if self.row_of(p) == "measurement"]

    def paths_in(self, row: str) -> list[Path]:
        """The files shown in *row*."""
        return [p for p in self._paths if self.row_of(p) == row]

    # -- views --------------------------------------------------------------------------------------------- #
    def imported_count(self) -> int:
        return sum(1 for entry in self.imports.values() if _registered(entry))

    def _changed(self, notify: bool = True) -> None:
        if not self._paths:
            self.status_text = "No TTTR files selected."
        elif any("skipped" in (self.imports.get(str(p)) or {}) for p in self._paths):
            self.status_text = f"{len(self._paths)} TTTR file(s) selected; not signed in to MMFDB, so they are not registered."
        else:
            self.status_text = f"{len(self._paths)} TTTR file(s) selected; {self.imported_count()} imported to MMFDB."
        if notify and callable(self.on_change):
            self.on_change()

    # -- persistence --------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        paths = [str(p) for p in self._paths]
        return {
            "paths": paths,
            "assignments": {p: self.assignments.get(p, "measurement") for p in paths},
            "groups": dict(self.groups),
            "group_of": {p: g for p, g in self.group_of.items() if p in paths},
            "dyes": {k: dict(v) for k, v in self.dyes.items()},
            "applied_g": dict(self.applied_g),
            "calibration": self.calibration,
            "proposed": {p: m for p, m in self.proposed.items() if p in paths},
            "declined": sorted(self.declined),
        }

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        paths = [p for p in state.get("paths", []) if Path(p).exists()]
        self.dyes = {str(k): dict(v) for k, v in (state.get("dyes") or {}).items() if isinstance(v, dict)}
        self.applied_g = {str(k): float(v) for k, v in (state.get("applied_g") or {}).items()}
        self.calibration = dict(state.get("calibration") or {})
        self.declined = {str(p) for p in state.get("declined") or ()}
        if paths:
            auto, self.auto_import = (
                self.auto_import,
                False,
            )  # restored files were registered when first added
            propose, self.propose = self.propose, False  # the stored rows are the user's
            try:
                self.add_paths(paths)
            finally:
                self.auto_import = auto
                self.propose = propose
            self.proposed = {
                str(Path(p).resolve()): str(m) for p, m in (state.get("proposed") or {}).items()
                if str(Path(p).resolve()) in self.assignments
            }
            for path, row in (state.get("assignments") or {}).items():
                if str(Path(path).resolve()) in self.assignments:
                    self.assignments[str(Path(path).resolve())] = str(row)
            self.groups.update({str(k): str(v) for k, v in (state.get("groups") or {}).items()})
            for path, group in (state.get("group_of") or {}).items():
                if str(Path(path).resolve()) in self.assignments:
                    self.group_of[str(Path(path).resolve())] = str(group)
            self._changed()


def _registered(entry: dict | None) -> bool:
    """Whether *entry* (an :attr:`BurstDataSelectionModel.imports` record) put the file in MMFDB."""
    return entry is not None and bool(entry) and "error" not in entry and "skipped" not in entry


def _status(entry: dict | None) -> str:
    if not entry:
        return "not imported"
    if "skipped" in entry:
        return "not signed in"
    if "error" in entry:
        return "error"
    if "raw_data_error" in entry:
        return "stored (not registered)"
    return "in MMFDB"


#: What each row of the assignment table is for (shown until a result replaces it).
ROW_PURPOSE = {
    "measurement": "burst data: searched in 2. Burst Selection",
    "buffer": "the buffer without dye: background rate, scatter correction",
    "irf": "scatter / water: the IRF of Burst MLE",
    "reference": "a fast-rotating free dye: G factor and confocal volume",
    "unassigned": "its row is not in this setup: drag it to a row",
}

#: The number cells of a role table row that holds none.
_NO_NUMBERS = {k: None for k in ("g", "veff", "taud", "w0", "s", "cpm", "bg", "fwhm")}

#: The colour of the step's warning line (missing calibration files).
WARNING_COLOUR = (240, 190, 80, 255)

#: Said under the table while no setup gives the per-colour rows.
NO_SETUP_HINT = "Choose a setup in 0. Setup Selection for the IRF and reference-dye rows."


class CalibrationJob:
    """The calibrations of :func:`..samples.calibrate`, computed on a thread.

    ``busy`` and ``progress`` are what the shell's busy overlay reads (the step is blurred with a
    progress card while it runs); :meth:`take` hands the finished ``(signature, result)`` back
    once."""

    def __init__(self) -> None:
        self.busy = False
        self.progress = ""
        self._result: tuple | None = None
        self._lock = threading.Lock()

    def start(self, rows: dict, setup: dict, dyes: dict, signature: str, on_done=None) -> bool:
        if self.busy:
            return False
        from ..samples import calibrate

        self.busy = True
        self.progress = tr("Calibrating with the buffer and reference-dye files …")

        def say(text: str) -> None:
            self.progress = tr(text)

        def run() -> None:
            try:
                result = calibrate(rows, setup, dyes=dyes, progress=say)
            except Exception as exc:  # noqa: BLE001 - reported with the results
                result = {"errors": [str(exc)], "colours": {}}
            with self._lock:
                self._result = (signature, result)
            self.busy = False
            if callable(on_done):
                on_done()

        threading.Thread(target=run, name="burst-calibration", daemon=True).start()
        return True

    def take(self) -> tuple | None:
        with self._lock:
            result, self._result = self._result, None
        return result


def _workspace_listing() -> list[dict]:
    """The Datasets workspace's summaries (empty without a session)."""
    try:
        from chisurf.core.plugin.workspace_input import _api

        return list(_api().list_datasets() or [])
    except Exception:  # noqa: BLE001 - no workspace: nothing to read
        return []


class _SampleInput(NamedWorkspaceInput):
    """The Input section of Data Selection: a row dropped on a row of the assignment table is
    assigned to it; right-click › *Add to* › a row does the same."""

    def workspace_input_drag(self, record, x, y, dropped, on_table=False) -> None:
        app = self.workspace_input_app
        row = app.row_at(x, y) if app is not None and not on_table else None
        if app is not None:
            # the role row the drag would land on is shown as the drop target until it is let go
            app.drop_target = None if dropped or not row else f"row:{row}"
        if not dropped or on_table:
            return
        rows = self._workspace_input_rows_of(record)
        if rows:
            self._deliver_to(rows, row)

    def workspace_input_add_to(self, record) -> list[dict]:
        """The rows of the assignment table, for the Input table's *Add to* submenu."""
        app = self.workspace_input_app
        if app is None:
            return []
        return [
            {
                "label": label,
                "group": "Add to",
                "description": tr("Assign this dataset (or the selected ones) to this row."),
                "call": lambda rec, row=row: self._deliver_to(self._workspace_input_rows_of(rec), row),
            }
            for row, label in app.row_choices()
        ]

    def _deliver_to(self, rows: list[dict], row: str | None) -> None:
        app = self.workspace_input_app
        if app is not None:
            app._drop_row = row
        try:
            self._workspace_input_deliver(rows)
        finally:
            if app is not None:
                app._drop_row = None


class BurstDataSelectionApp(TourTarget, ImApp):
    """What the workflow works on, by role, and the calibrations of the non-measurement files (emtk; no Qt).

    The Input section (top) lists the workspace's photon streams; the assignment table (bottom)
    has one row per role -- Measurement, Buffer, and per colour of the detector setup an IRF and
    a Reference dye -- and lists what is assigned to each. A dataset dropped on a row is that
    role; only the Measurement row goes to Burst Selection.

    Parameters
    ----------
    source : BurstDataSelectionModel or object, optional
        What is drawn and edited (default: a new :class:`BurstDataSelectionModel`).
    on_proceed : callable, optional
        Called by *Proceed to Burst Selection* (the workflow hub moves to the next step).
    setup_provider : callable, optional
        Returns the workflow's detector setup (the rows are made from it).
    on_apply_g : callable, optional
        ``on_apply_g({detector: G})``: write G factors into the setup (step 0's G-Factor column).
    on_calibrated : callable, optional
        Called with the calibration result once it is computed.
    """

    #: The plugin whose manifest ``accepts`` ``photons`` the Input section feeds.
    WORKSPACE_PLUGIN = "burst_analysis"
    #: The Summary dock's proceed button and its tooltip (a workflow whose next step is another one renames it).
    PROCEED_LABEL = "Proceed to Burst Selection"
    PROCEED_TIP = "Go on to 2. Burst Selection with the measurements."

    def __init__(
        self,
        source: Any = None,
        *,
        on_proceed: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
        setup_provider: Callable[[], dict] | None = None,
        on_apply_g: Callable[[dict], Any] | None = None,
        on_calibrated: Callable[[dict], Any] | None = None,
    ) -> None:
        self.source = source if source is not None else BurstDataSelectionModel()
        self.model = self.source
        self.on_proceed = on_proceed
        self._on_guide = on_guide
        self._on_help = on_help
        self.setup_provider = setup_provider
        if setup_provider is not None and hasattr(self.source, "setup_provider"):
            self.source.setup_provider = setup_provider
        self.on_apply_g = on_apply_g
        self.on_calibrated = on_calibrated
        #: Called from the calibration thread when it is done (a hub wakes its frame loop).
        self.on_wake: Callable[[], Any] | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.filter_text = ""
        self.selected_index: int | None = None
        #: The selected entry of the assignment table (its record).
        self.selected_entry: dict | None = None
        #: Rows of the assignment table shown unfolded (the role rows at first, never a group).
        self.expanded_rows: set = set()
        self._seen_rows: set = set()
        #: The row a drop or an *Add to* assigns to (``None``: guessed from the name).
        self._drop_row: str | None = None
        #: The row under the pointer: where a file dropped on the window goes.
        self._hover_row: str | None = None
        #: The role row a workspace row being dragged would land on (drawn as the drop target).
        self.drop_target: str | None = None
        self.job = CalibrationJob()
        self._calibrated_for = ""
        self.form = FormState()
        self._spec_full = load_view_spec(str(HERE / "data_selection.view.json"))
        self.spec = self._table_spec(True)
        self.message = ""
        # The Input section: the workspace's photon streams; a row dropped on a role row is that role.
        from chisurf.core.plugin.workspace_input import input_section, spec_for
        from chisurf.emtk.plugins import manifest

        self.input = _SampleInput(self.WORKSPACE_PLUGIN, "photons", app=self)
        found = spec_for(manifest(self.WORKSPACE_PLUGIN), kind="photons")
        section = input_section(found[1], title="Workspace data") if found else None
        if section is not None:
            table = next(
                (x for x in section.get("sections", []) if (x.get("options") or {}).get("source") == "workspace_input_rows"),
                None,
            )
            if table is not None:
                table["options"]["context_menu"] = list(table["options"].get("context_menu") or []) + [
                    {"label": "Add to", "items_source": "workspace_input_add_to",
                     "description": "Assign the row to one row of the table below."}
                ]
                table["description"] = (
                    "The photon streams in the workspace. Drag a row (a group is one row) onto a "
                    "row of the table below to say what it is: measurement, buffer, IRF or "
                    "reference dye; or right-click it › Add to."
                )
        self.input_spec = {"sections": [section]} if section else {"sections": []}
        self.input_form = FormState()
        self.help_window = EmTkHelpWindow(
            title="Data Selection - Help",
            resource=HERE / "data_selection_help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(680.0, 500.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "data_selection_guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        self.docks = DockManager(
            Split(
                "h",
                0.64,
                Region("files"),
                Split("v", 0.3, Region("details"), Split("v", 0.34, Region("summary"), Region("calibration"))),
            ),
            name="burst_data_selection",
        )
        self.docks.add_window("files", "Data", self._draw_files, dock="files", closable=False)
        self.docks.add_window("details", "Details", self._draw_details, dock="details", closable=False)
        self.docks.add_window("summary", "Summary", self._draw_summary, dock="summary", closable=False)
        self.docks.add_window(
            "calibration", "Calibration", self._draw_calibration, dock="calibration", closable=False
        )
        super().__init__(gui=self._render, continuous=False)

    #: The workflow's Simple / Advanced mode (standalone: everything).
    advanced = True

    def _table_spec(self, advanced: bool) -> dict:
        """The assignment table for a mode: Simple leaves out the technical columns (where a dye
        came from, size, MMFDB) and calls the result column *Status*; the Dye cell lists the dye
        database (:func:`chisurf.core.fluorescence.dyes.dye_names`) and *Other (custom D)*."""
        import copy

        from chisurf.core.fluorescence.dyes import dye_names

        from ..samples import CUSTOM_DYE

        spec = copy.deepcopy(self._spec_full)
        for section in spec["sections"]:
            options = section.get("options") or {}
            columns = []
            for column in options.get("columns") or []:
                if column.pop("advanced", False) and not advanced:
                    continue
                title = column.pop("simple_title", None)
                if title and not advanced:
                    column["title"] = title
                if column.get("key") == "dye":
                    try:
                        names = list(dye_names())
                    except Exception:  # noqa: BLE001 - no dye database: the custom D only
                        names = []
                    from ..samples import dye_label

                    # the cell shows the short name (Rh110, A647); the list too, the full one in
                    # the row's tooltip and the Calibration window
                    column["choices"] = [{"value": n, "label": dye_label(n)} for n in names] + [
                        {"value": CUSTOM_DYE, "label": CUSTOM_DYE}
                    ]
                columns.append(column)
            options["columns"] = columns
        return spec

    def set_advanced(self, advanced: bool) -> None:
        """Simple: the data, its roles with a plain status each, and the dye of each reference
        row; the G factors are applied and the volumes stored as they are computed. The details,
        the summary and the Calibration window (curves, D, temperature, Apply G) are Advanced --
        the summary stays when a workflow puts controls of its own in it."""
        changed = bool(advanced) != self.advanced
        self.advanced = bool(advanced)
        if changed:
            self.spec = self._table_spec(self.advanced)
            self.form.tables.pop("assignment_rows", None)  # bound again with the mode's columns
        keep_summary = type(self)._draw_summary_extra is not BurstDataSelectionApp._draw_summary_extra
        for key in ("details", "calibration") + (() if keep_summary else ("summary",)):
            if key in self.docks.windows:
                if advanced:
                    self.docks.show(key)
                else:
                    self.docks.hide(key)
        self.docks.focus("files")

    # -- tour / help ---------------------------------------------------------------------------------------- #
    def start_guide(self) -> None:
        if callable(self._on_guide):
            self._on_guide()
        else:
            self.tour.start()

    def show_help(self) -> None:
        if callable(self._on_help):
            self._on_help()
        else:
            self.help_window.show()

    def track(self, name: str) -> None:
        self.tour.notify_used(name)

    # -- the setup the rows come from ----------------------------------------------------------------------- #
    def setup(self) -> dict:
        """The detector setup of the workflow (``{}``: none chosen)."""
        setup = {}
        if callable(self.setup_provider):
            try:
                setup = dict(self.setup_provider() or {})
            except Exception:  # noqa: BLE001 - no setup: the rows without colours
                setup = {}
        if hasattr(self.source, "setup"):
            self.source.setup = setup
        return setup

    def row_keys(self) -> list[str]:
        """The rows of the assignment table, from the setup (plus ``unassigned`` while used)."""
        from ..samples import row_keys

        keys = row_keys(self.setup())
        rows = getattr(self.source, "rows", None)
        if callable(rows) and "unassigned" in rows().values():
            keys.append("unassigned")
        return keys

    def row_choices(self) -> list[tuple[str, str]]:
        """``[(row key, label)]`` a dataset can be assigned to."""
        from ..samples import row_keys, row_label

        setup = self.setup()
        return [(key, row_label(key, setup)) for key in row_keys(setup)]

    # -- what the assignment table binds to ----------------------------------------------------------------- #
    def _paths(self) -> list[Path]:
        return list(self.source.paths())

    def _row_of(self, path) -> str:
        row_of = getattr(self.source, "row_of", None)
        return row_of(path) if callable(row_of) else "measurement"

    def assignment_rows(self) -> list[dict]:
        """The role rows and, under each, what is assigned to it: a workspace group as one entry
        (its files under it), single files as themselves."""
        from ..samples import row_label

        setup = self.setup()
        imports = self.source.mmfdb_payload().get("imports", {})
        groups = dict(getattr(self.source, "groups", {}) or {})
        group_of = dict(getattr(self.source, "group_of", {}) or {})
        query = self.filter_text.casefold()
        paths = self._paths()
        out: list[dict] = []
        for row in self.row_keys():
            key = f"row:{row}"
            if key not in self._seen_rows:
                self._seen_rows.add(key)
                self.expanded_rows.add(key)  # a role row shows what it holds
            members = [(i, p) for i, p in enumerate(paths) if self._row_of(p) == row]
            shown = [(i, p) for i, p in members if not query or query in p.name.casefold()]
            out.append(
                {
                    "key": key,
                    "parent": "",
                    "row": row,
                    "name": row_label(row, setup, short=True),
                    **self._dye_cells(row),
                    **self.row_numbers(row, [p for _i, p in members]),
                    "files": str(len(members)) if members else "",
                    "size": _format_size(_total_size(p for _i, p in members)) if members else "",
                    "status": "",
                }
            )
            done_groups: set = set()
            for index, path in shown:
                group = group_of.get(str(path))
                parent = key
                if group:
                    gkey = f"grp:{group}@{row}"
                    parent = gkey
                    if group not in done_groups:
                        done_groups.add(group)
                        in_group = [p for _i, p in members if group_of.get(str(p)) == group]
                        out.append(
                            {
                                "key": gkey,
                                "parent": key,
                                "row": row,
                                "group": group,
                                "name": f"🗂 {groups.get(group, group)}",
                                "files": str(len(in_group)),
                                "info": "",
                                "size": _format_size(_total_size(in_group)),
                                "status": "",
                                "paths": [str(p) for p in in_group],
                                "dye": "",
                                **_NO_NUMBERS,
                                "tip": "\n".join(p.name for p in in_group),
                            }
                        )
                out.append(
                    {
                        "key": f"file:{path}",
                        "parent": parent,
                        "row": row,
                        "index": index,
                        "path": str(path),
                        "name": path.name,
                        "files": "",
                        "info": "",
                        "size": _format_size(_size(path)),
                        "status": _status(imports.get(str(path))),
                        **self._proposed_cells(path),
                        "dye": "",
                        **_NO_NUMBERS,
                    }
                )
        return out

    def _proposed_cells(self, path: Path) -> dict:
        """A file entry's info and tooltip: ``found`` for a file proposed from beside a
        measurement (where, and that Delete takes it out for good)."""
        beside = (getattr(self.source, "proposed", {}) or {}).get(str(path))
        if not beside:
            return {"info": "", "tip": str(path)}
        return {
            "info": tr("found"),
            "tip": str(tr("{path}\nFound beside {measurement} by its name and put into this row; "
                          "move it to another row, or Delete it (it is not proposed again).")).format(
                path=path, measurement=beside),
        }

    def row_numbers(self, row: str, files: list[Path]) -> dict:
        """The cells of a role row: its key numbers (G, V_eff, τ_D, w0, s, brightness of a
        reference dye; B of the buffer; the IRF's width), a one-word status and a tooltip that
        says what the status means. Empty where a number does not apply."""
        from ..samples import kind_of, row_label

        kind = kind_of(row)
        colour = row.partition(":")[2]
        calibration = getattr(self.source, "calibration", {}) or {}
        cells = dict(_NO_NUMBERS)
        label = row_label(row, self.setup())
        purpose = tr(ROW_PURPOSE.get(kind, ""))
        if not files:
            cells["info"] = "" if kind == "measurement" else tr("estimated")
            cells["tip"] = f"{label}: {purpose}. " + self._fallback_tip(row)
            return cells
        cells["info"] = tr("measured")
        cells["tip"] = f"{label}: {purpose}."
        busy = self.job.busy and kind in ("buffer", "reference", "irf")
        if kind == "buffer":
            rates = ((calibration.get("buffer") or {}).get("rates")) or {}
            if rates:
                cells["bg"] = float(sum(r["B_kHz"] for r in rates.values() if r["B_kHz"] == r["B_kHz"]))
                cells["tip"] += " " + ", ".join(f"Bg_{d} {r['B_kHz']:.2f} kHz" for d, r in rates.items())
        elif kind == "irf":
            irf = (calibration.get("irf") or {}).get(colour) or {}
            if irf.get("fwhm_ps"):
                cells["fwhm"] = float(irf["fwhm_ps"])
                cells["tip"] += f" FWHM {irf['fwhm_ps']:.0f} ps on {irf.get('detector', '')}."
        elif kind == "reference":
            entry = (calibration.get("colours") or {}).get(colour) or {}
            g = entry.get("g_factor") or {}
            volume = entry.get("volume") or {}
            if g:
                cells["g"] = float(next(iter(g.values()))["g"])
                swapped = [d for d, v in g.items() if float(v.get("r_peak", 0.0)) < SWAPPED_BELOW]
                if swapped:
                    r = float(g[swapped[0]]["r_peak"])
                    cells["info"] = tr("VV/VH swapped?")
                    cells["tip"] += " " + str(tr(
                        "The dye's anisotropy right after the pulse is {r:+.2f} on {detectors}; a free "
                        "dye's is positive: the VV and VH channels look swapped in the setup (step 0). "
                        "G and the rotation are wrong until they are swapped back."
                    )).format(r=r, detectors=", ".join(swapped))
                hand = [d for d in g if d in self.hand_edited_g()]
                if hand:
                    cells["info"] = tr("hand-edited")
                    cells["tip"] += " " + tr("The setup's G of {detectors} was edited by hand and is kept.").format(
                        detectors=", ".join(hand))
            if volume:
                cells.update(
                    veff=float(volume["veff_fl"]), taud=float(volume["tau_d_ms"]) * 1e3,
                    w0=float(volume["w0_um"]), s=float(volume["s"]),
                    cpm=float(volume.get("brightness_khz", float("nan"))),
                )
        numbers = [f"{k} {cells[k]:.3g}" for k in ("g", "veff", "taud", "w0", "s", "cpm", "bg", "fwhm")
                   if isinstance(cells.get(k), float) and cells[k] == cells[k]]
        if numbers:
            cells["tip"] += " (" + ", ".join(numbers) + ")"
        if busy:
            cells["info"] = tr("computing …")
        elif kind != "measurement" and calibration.get("errors") and not any(
            cells[k] is not None for k in ("g", "veff", "bg", "fwhm")
        ):
            cells["info"] = tr("failed")
            cells["tip"] += " " + "; ".join(calibration["errors"])
        return cells

    def _fallback_tip(self, row: str) -> str:
        """What is used for a role without a file (the row's tooltip)."""
        from ..samples import kind_of

        kind = kind_of(row)
        dets = row_detectors(row, self.setup())
        g = f"{(self.setup_g(dets[0]) if dets else None) or 1.0:.3f}"
        return {
            "buffer": tr("No buffer: the background is estimated from the photons outside the bursts."),
            "irf": tr("No IRF: estimated from the non-burst photons, else blindly from the burst decay."),
            "reference": tr("No reference dye: G from the setup ({g}); no confocal volume.").format(g=g),
            "measurement": tr("Drop the measurements here."),
        }.get(kind, "")

    def _dye_cells(self, row: str) -> dict:
        """The Dye cell of a role row (empty but on reference rows)."""
        if not row.startswith("reference:"):
            return {"dye": ""}
        from ..samples import dye_choice

        colour = row.partition(":")[2]
        choice = self.reference_dyes().get(colour) or dye_choice(
            (getattr(self.source, "dyes", {}) or {}).get(colour), colour
        )
        return {"dye": choice["dye"]}

    def cell_editable(self, record, key: str) -> bool:
        """Only a reference row's Dye cell is edited in the table."""
        return key == "dye" and isinstance(record, dict) and str(record.get("key", "")).startswith("row:reference:")

    def cell_edited(self, record, key: str, value) -> None:
        if key == "dye" and self.cell_editable(record, key):
            self.set_dye(str(record["row"]).partition(":")[2], dye=str(value))
            self.track("dye")

    def missing_references(self) -> list[str]:
        """The calibration roles nothing is assigned to (``buffer``, ``irf``, ``reference``)."""
        from ..samples import kind_of

        rows_of = getattr(self.source, "rows", None)
        used = {kind_of(r) for r in (rows_of() if callable(rows_of) else {}).values()}
        return [k for k in ("buffer", "irf", "reference") if k not in used]

    def fallback_warning(self) -> str:
        """The step's one warning line when calibration files are missing ("" when none)."""
        missing = self.missing_references()
        if not self._paths() or not missing:
            return ""
        words = {"buffer": tr("buffer"), "irf": tr("IRF"), "reference": tr("reference dye")}
        return tr("Estimated (no {missing})").format(missing=", ".join(words[k] for k in missing))

    def fallback_detail(self) -> str:
        """The warning's tooltip: what is estimated instead of each missing file."""
        parts = {
            "buffer": tr("background from the photons outside the bursts"),
            "irf": tr("IRF from the non-burst photons"),
            "reference": tr("G from the setup, no confocal volume"),
        }
        return "; ".join(parts[k] for k in self.missing_references()) + "."

    def row_at(self, x: float, y: float) -> str | None:
        """The role of the assignment-table row under ``(x, y)`` (``None``: not over a row)."""
        binding = self.form.tables.get("assignment_rows")
        if binding is None:
            return None
        control = binding.control
        position = control.row_at(x, y)
        if position is None:
            return None
        record = binding.record(control.order()[position])
        row = record.get("row") if isinstance(record, dict) else None
        return row if row and row != "unassigned" else None

    def _entry_paths(self, record) -> list[Path]:
        if not isinstance(record, dict):
            return []
        if record.get("path"):
            return [Path(record["path"])]
        if record.get("paths"):
            return [Path(p) for p in record["paths"]]
        if record.get("key", "").startswith("row:"):
            return [p for p in self._paths() if self._row_of(p) == record.get("row")]
        return []

    def select_entry(self, record) -> None:
        self.selected_entry = record if isinstance(record, dict) else None
        if isinstance(record, dict) and "index" in record:
            self.selected_index = int(record["index"])
        self.track("files")

    def remove_entry(self, record) -> None:
        """Remove (Delete, the context menu): a file, a group's files, or every file of a row."""
        paths = self._entry_paths(record)
        remove = getattr(self.source, "remove_paths", None)
        if paths and callable(remove):
            remove(paths)
        elif isinstance(record, dict) and "index" in record:
            self.source.remove_index(int(record["index"]))
        self.selected_entry = None
        self._clamp_selection()

    def move_entry(self, record, row: str) -> None:
        """Assign what *record* holds to *row*."""
        assign = getattr(self.source, "assign", None)
        paths = self._entry_paths(record)
        if paths and callable(assign) and row:
            assign(paths, row)
            self._tag_workspace(paths)
            self.track("samples")

    def assignment_menu_move(self, record) -> list[dict]:
        """The *Move to* submenu of an assignment-table row."""
        here = record.get("row") if isinstance(record, dict) else None
        return [
            {
                "label": label,
                "group": "Move to",
                "enabled": row != here,
                "description": tr("Assign it to this row instead."),
                "call": lambda rec, row=row: self.move_entry(rec, row),
            }
            for row, label in self.row_choices()
        ]

    def assignment_drag(self, record, x, y, dropped, on_table=False) -> None:
        """An entry dragged within the table: let go on another row, it moves there."""
        if not dropped or not on_table:
            return
        row = self.row_at(x, y)
        if row and isinstance(record, dict) and row != record.get("row"):
            self.move_entry(record, row)

    def _clamp_selection(self) -> None:
        n = len(self._paths())
        if self.selected_index is not None and self.selected_index >= n:
            self.selected_index = n - 1 if n else None

    # -- the workspace ------------------------------------------------------------------------------------- #
    def take_photons(self, paths, uids=()) -> int:
        """Add photon streams from the workspace -- to the row they were dropped on, else to the
        row the workspace tagged them with, else by their names; remember the dataset each came
        from and keep a workspace group together."""
        paths = [Path(str(p)) for p in paths]
        uids = [str(u or "") for u in uids]
        row = self._drop_row or self._hover_row
        listing = _workspace_listing() if any(uids) else []
        tags: dict[str, str] = {}
        parent: dict[str, tuple[str, str]] = {}
        for dto in listing:
            for member in dto.get("members") or ():
                parent[str(member.get("uid", ""))] = (str(dto.get("uid", "")), str(dto.get("name", "")))
                if (member.get("tags") or {}).get("sample"):
                    tags[str(member.get("uid"))] = str(member["tags"]["sample"])
            if (dto.get("tags") or {}).get("sample"):
                tags[str(dto.get("uid"))] = str(dto["tags"]["sample"])
        # The dataset each file came from is known before the file is added: adding it tells the
        # workflow, which makes the file's analysis container at once -- in that dataset's folder
        # (``container_dir(uid)``). Recorded after, the first container went to ``_`` and every
        # later step wrote into a second one.
        sources = getattr(self.source, "sources", None)
        if isinstance(sources, dict):
            for path, uid in zip(paths, uids):
                if uid:
                    sources[str(path)] = uid
                    sources[str(path.resolve())] = uid
        added = 0
        add = self.source.add_paths
        for path, uid in zip(paths, uids + [""] * (len(paths) - len(uids))):
            chosen = row or tags.get(uid)
            try:
                added += int(add([path], chosen) or 0)
            except TypeError:  # a source without rows
                added += int(add([path]) or 0)
        by_group: dict[str, list[Path]] = {}
        for path, uid in zip(paths, uids):
            if uid in parent:
                by_group.setdefault(parent[uid][0], []).append(path)
        set_group = getattr(self.source, "set_group", None)
        if callable(set_group):
            for gid, members in by_group.items():
                name = next(n for u, (g, n) in parent.items() if g == gid)
                set_group(members, gid, name)
        self._tag_workspace(paths)
        if row:
            self.track("samples")  # dropped on a role row (the tour waits for it)
        if self.selected_index is None and self._paths():
            self.selected_index = 0
        self.message = "" if added or row else "Nothing new to add (already in the list)."
        if callable(getattr(self.source, "on_change", None)) and by_group:
            self.source.on_change()
        return int(added or (len(paths) if row else 0))

    def _tag_workspace(self, paths) -> None:
        """Say in the workspace what each dataset is here (a ``sample`` tag on the dataset): it
        goes with the dataset into the project and comes back when it is handed in again."""
        sources = getattr(self.source, "sources", None) or {}
        assignments = getattr(self.source, "assignments", None) or {}
        uids = [(sources.get(str(p)), assignments.get(str(p))) for p in paths]
        if not any(uid for uid, _row in uids):
            return
        try:
            from chisurf.core.plugin.workspace_input import _api

            api = _api()
            for uid, row in uids:
                if uid and row:
                    api.tag_dataset(uid, "sample", row)
        except Exception:  # noqa: BLE001 - the assignment is kept with the step all the same
            log.debug("tagging the workspace datasets failed", exc_info=True)

    # -- calibration ---------------------------------------------------------------------------------------- #
    def calibration_input(self) -> tuple[dict, dict, dict, str]:
        """``(rows, setup, dyes, signature)`` of what the calibration is computed from: the
        buffer, IRF and reference-dye files, the detectors and reading of the setup, the D values."""
        setup = self.setup()
        rows_of = getattr(self.source, "rows", None)
        rows = {p: r for p, r in (rows_of() if callable(rows_of) else {}).items()
                if r == "buffer" or r.startswith(("reference:", "irf:"))}
        dyes = self.reference_dyes(setup, rows)
        signature = json.dumps(
            # the channels and gates, not the G factors the calibration itself writes
            [sorted(rows.items()),
             {d: [i.get("chs"), i.get("micro_time_ranges")] for d, i in (setup.get("detectors") or {}).items()},
             setup.get("tttr_reading"), sorted((k, sorted(v.items())) for k, v in dyes.items())],
            sort_keys=True,
            default=str,
        )
        return rows, setup, dyes, signature

    def reference_dyes(self, setup: dict | None = None, rows: dict | None = None) -> dict[str, dict]:
        """``{colour: dye}`` of every reference row with files: the user's choice, else the dye
        the files' header or names give, else the colour's default (kept in the model, so the
        table shows it)."""
        from ..samples import colour_groups, dye_choice, infer_dye

        setup = self.setup() if setup is None else setup
        if rows is None:
            rows_of = getattr(self.source, "rows", None)
            rows = rows_of() if callable(rows_of) else {}
        store = getattr(self.source, "dyes", None)
        if not isinstance(store, dict):
            return {}
        colours = [g["colour"] for g in colour_groups(setup)]
        out = {}
        for colour in colours:
            files = [p for p, r in rows.items() if r == f"reference:{colour}"]
            current = store.get(colour) or {}
            if not files and current.get("how") != "user":
                continue
            if current.get("how") != "user":
                found = tuple(current.get("_for") or ())
                if found != tuple(sorted(files)):
                    name, how = infer_dye(files, colour, colours)
                    current = {**dye_choice(current, colour), "dye": name, "how": how,
                               "_for": sorted(files)}
                    store[colour] = current
            out[colour] = {k: v for k, v in dye_choice(current, colour).items()}
        return out

    def set_dye(self, colour: str, **changes) -> None:
        """The user chose a reference row's dye, temperature or custom D: kept, never inferred over."""
        from ..samples import dye_choice

        store = getattr(self.source, "dyes", None)
        if not isinstance(store, dict):
            return
        current = dye_choice(store.get(colour), colour)
        current.update(changes)
        current["how"] = "user"
        store[colour] = current
        changed = getattr(self.source, "_changed", None)
        if callable(changed):
            changed()

    def poll_calibration(self) -> None:
        """Collect a finished calibration, and start one when its input changed (called every
        frame, by the step and by a hub while another step is on screen)."""
        done = self.job.take()
        if done is not None:
            signature, result = done
            self._calibrated_for = signature
            if hasattr(self.source, "calibration"):
                self.source.calibration = result
            self.apply_all_g()  # written as computed; a value edited by hand in the setup is kept
            if callable(self.on_calibrated):
                try:
                    self.on_calibrated(result)
                except Exception:  # noqa: BLE001 - the result is shown here all the same
                    log.exception("handing the calibration on failed")
        if self.job.busy:
            return
        rows, setup, dyes, signature = self.calibration_input()
        if signature == self._calibrated_for:
            return
        if not rows or not setup.get("detectors"):
            self._calibrated_for = signature
            if hasattr(self.source, "calibration") and self.source.calibration:
                self.source.calibration = {}
                if callable(self.on_calibrated):
                    self.on_calibrated({})
            return
        self.job.start(rows, setup, dyes, signature, on_done=self._wake)

    def _wake(self) -> None:
        self.request_frame()
        if callable(self.on_wake):
            self.on_wake()

    def computed_g(self) -> dict[str, float]:
        """``{detector: G}`` of every colour's reference dye in the last calibration."""
        calibration = getattr(self.source, "calibration", {}) or {}
        return {
            det: float(value["g"])
            for entry in (calibration.get("colours") or {}).values()
            for det, value in (entry.get("g_factor") or {}).items()
        }

    #: The G of a setup nobody calibrated. A setup at this value was not edited by hand: it was
    #: (re)loaded from the setup library, which keeps the G it was created with, while the G last
    #: written is restored with the session -- read as a hand edit, the reference dye's G was
    #: never applied again and every fit ran at G 1.0.
    UNCALIBRATED_G = 1.0

    def _edited_by_hand(self, det: str, applied: dict) -> bool:
        """Whether *det*'s setup G was changed by hand since it was last written here."""
        current, last = self.setup_g(det), applied.get(det)
        if last is None or current is None or abs(current - self.UNCALIBRATED_G) <= 5e-4:
            return False
        return abs(current - float(last)) > 5e-4

    def apply_all_g(self) -> int:
        """Write every computed G factor into the setup -- unless the setup's value is no longer
        the one written last (the user edited it by hand: kept, and said so). A setup at the
        uncalibrated G (:data:`UNCALIBRATED_G`) always takes the reference dye's."""
        applied = getattr(self.source, "applied_g", None)
        if not isinstance(applied, dict) or not callable(self.on_apply_g):
            return 0
        values = {}
        for det, g in self.computed_g().items():
            current = self.setup_g(det)
            if self._edited_by_hand(det, applied):
                continue  # edited by hand since it was written
            if current is None or abs(current - g) > 5e-4:
                values[det] = g
            applied[det] = g
        if values:
            self.on_apply_g(values)
        return len(values)

    def hand_edited_g(self) -> list[str]:
        """The detectors whose setup G differs from the one last written (edited by hand)."""
        applied = getattr(self.source, "applied_g", None) or {}
        return [d for d in applied if self._edited_by_hand(d, applied)]

    def setup_g(self, det: str) -> float | None:
        info = (self.setup().get("detectors") or {}).get(det) or {}
        value = info.get("g_factor")
        return float(value) if value is not None else None

    # -- windows -------------------------------------------------------------------------------------------- #
    def _draw_files(self, box=None) -> None:
        paths = self._paths()
        self._clamp_selection()
        selected = self.selected_entry is not None
        self.input.workspace_input_on_used = self.track
        self.input_form.rects.clear()
        draw_form(self.input_spec, self.input, self.input_form)
        for name, rect in self.input_form.rects.items():
            self.item_rects[name] = tuple(rect)
        if "workspace_input_rows" in self.input_form.rects:  # the guide's name for adding data
            self.item_rects["add_files"] = tuple(self.input_form.rects["workspace_input_rows"])
            self.item_rects["toolAction_add"] = self.item_rects["add_files"]
        im.separator()
        pressed = button_row(
            [
                {
                    "label": "Remove",
                    "key": "remove",
                    "enabled": selected,
                    "tip": "Remove the selected file, group or row's files from the step."
                    if selected
                    else "Select an entry in the table first.",
                },
                *(
                    []
                    if not self.advanced  # Simple: Remove does it, one entry at a time
                    else [
                        {
                            "label": "Clear",
                            "key": "clear",
                            "enabled": bool(paths),
                            "tip": "Remove every file from the step." if paths else "No files to remove.",
                        }
                    ]
                ),
                # in a workflow's Simple mode the hub's own Help and Guide are the ones
                *(
                    []
                    if not self.advanced
                    else [
                        {"label": action_caption("guide"), "key": "guide", "tip": action_tooltip("guide")},
                        {"label": action_caption("help"), "key": "help", "tip": action_tooltip("help")},
                    ]
                ),
            ],
            remember=self.remember,
        )
        if pressed == "remove" and selected:
            self.remove_entry(self.selected_entry)
        elif pressed == "clear":
            self.source.clear()
            self.selected_index = None
            self.selected_entry = None
        elif pressed == "guide":
            self.start_guide()
        elif pressed == "help":
            self.show_help()
        im.same_line()
        im.align_text_to_frame_padding()
        im.text(tr("Filter"))
        im.same_line()
        im.set_next_item_width(min(200.0, max(100.0, im.get_content_region_avail()[0] - 10.0)))
        _changed, self.filter_text = im.filter_field(
            "##data_filter",
            self.filter_text,
            tr("file name contains"),
            tooltip=tr("Show only files whose name contains this text."),
        )
        self.remember("filter")
        if self.message:
            im.text(self.message)
        im.text_disabled(tr("Drag data onto a role ↓"))
        im.set_item_tooltip(
            tr("Drag workspace data onto a row below to say what it is: measurement, buffer, IRF or reference dye.")
        )
        self.remember("drag_hint")
        draw_sections(self.spec["sections"], self, self.form)
        if "data_table" in self.form.rects:
            self.item_rects["files"] = tuple(self.form.rects["data_table"])
            self.item_rects["samples"] = self.item_rects["files"]
        # where a file dropped on the window goes: the row under the pointer
        mx, my = im.get_io().mouse_pos
        self._hover_row = self.row_at(mx, my)
        self._draw_sample_summary()

    def _draw_sample_summary(self) -> None:
        from ..samples import sample_summary

        warning = self.fallback_warning()
        if warning:
            from emtk.im_core import Col

            im.push_style_color(Col.TEXT, WARNING_COLOUR)
            im.text("⚠ " + warning)
            im.pop_style_color()
            im.set_item_tooltip(self.fallback_detail())
            self.remember("fallback_warning")

        rows = getattr(self.source, "rows", None)
        values = list(rows().values()) if callable(rows) else ["measurement"] * len(self._paths())
        if values:
            im.text_disabled(sample_summary(v for v in values if v != "unassigned"))
            self.remember("sample_summary")
            if "unassigned" in values:
                im.same_line()
                im.text_disabled(" · " + tr("{n} unassigned").format(n=values.count("unassigned")))
        else:
            im.text_disabled(tr("No data yet"))
            im.set_item_tooltip(
                tr(
                    "Drop photon files (.ptu, .spc, .ht3, …) on a row, or drag workspace data "
                    "from the table above onto a row."
                )
            )
        if not self.setup().get("detectors"):
            im.text_disabled(tr("No setup: no IRF / reference rows"))
            im.set_item_tooltip(tr(NO_SETUP_HINT))

    def _draw_details(self, box=None) -> None:
        record = self.selected_entry
        files = self._paths()
        if record is None and self.selected_index is not None and 0 <= self.selected_index < len(files):
            # nothing picked in the table yet: the first file (as the step showed it before)
            record = {"path": str(files[self.selected_index]), "index": self.selected_index}
        paths = self._entry_paths(record)
        if record is None:
            im.text_wrapped(tr("Nothing selected. Click an entry of the table to see its details."))
            return
        if not record.get("path"):
            im.text(str(record.get("name", "")))
            im.text_wrapped(str(self.row_numbers(str(record.get("row", "")), paths).get("tip", "")))
            im.text(tr("{n} file(s), {size}").format(n=len(paths), size=_format_size(_total_size(paths))))
            for path in paths[:12]:
                im.bullet_text(path.name)
            return
        path = Path(record["path"])
        im.text(f"Name: {path.name}")
        im.text_wrapped(f"Path: {path}")
        try:
            stat = path.stat()
            im.text(f"Size: {_format_size(stat.st_size)} ({stat.st_size:,} bytes)")
            modified = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            im.text(f"Modified: {modified}")
        except OSError as exc:
            im.text_wrapped(f"The file cannot be read: {exc}")
        im.separator()
        entry = self.source.mmfdb_payload().get("imports", {}).get(str(path))
        im.text(f"MMFDB: {_status(entry)}")
        if entry and ("error" in entry or "skipped" in entry):
            im.text_wrapped(str(entry.get("error") or entry["skipped"]))
        elif entry:
            obj = (entry.get("object_result") or {}).get("object", {}) or {}
            raw = (entry.get("raw_data_result") or {}).get("raw_data", {}) or {}
            im.text(f"Object: {obj.get('object_uuid', '-')}")
            im.text(f"Raw data: {raw.get('raw_data_id', '-')}")
            if entry.get("raw_data_error"):
                im.text_wrapped(f"Registration failed: {entry['raw_data_error']}")
        label = "Import again" if _registered(entry) else "Import now"
        if im.button(label + "##data_import"):
            self.track("import")
            self.source.import_path(path)
        im.set_item_tooltip(
            tr("Store this file in the MMFDB object store and register it as raw TTTR data.")
        )
        self.remember("import")

    def _draw_summary(self, box=None) -> None:
        paths = self._paths()
        measurements = getattr(self.source, "measurement_paths", None)
        measured = measurements() if callable(measurements) else paths
        imports = self.source.mmfdb_payload().get("imports", {})
        registered = sum(1 for p in paths if _registered(imports.get(str(p))))
        im.bullet_text(f"Files: {len(paths)} ({len(measured)} to search)")
        im.bullet_text(f"On disk: {_format_size(_total_size(paths))}")
        im.bullet_text(f"In MMFDB: {registered} of {len(paths)}")
        im.separator()
        im.begin_disabled(not measured or not callable(self.on_proceed))
        if im.button(self.PROCEED_LABEL) and self.on_proceed is not None:
            self.proceed()
        im.end_disabled()
        im.set_item_tooltip(self.PROCEED_TIP if measured else "Assign a measurement first.")
        self.remember("proceed")
        self._draw_summary_extra()

    def proceed(self) -> None:
        """On to Burst Selection -- never blocked by a missing calibration file: the first time
        without them, the step says once (not as a dialog) what is estimated instead."""
        self.track("proceed")
        warning = self.fallback_warning()
        if warning and not self._noticed:
            self._noticed = True
            self.message = "⚠ " + warning
        if callable(self.on_proceed):
            self.on_proceed()

    #: The proceed notice about missing calibration files was given (once per step).
    _noticed = False

    def _draw_summary_extra(self) -> None:
        """Below the proceed button: nothing here; a workflow adds its own controls (the ALEX Suite's demo data)."""

    def _draw_calibration(self, box=None) -> None:
        """Per colour: the dye, its temperature (or a custom D), D in one value with its source in
        the tooltip, and the fitted correlation. The numbers are in the table; everything else is
        in the analysis report (:mod:`..calibration_report`)."""
        from ..samples import CUSTOM_DYE, colour_groups, dye_choice, dye_diffusion

        self.remember("calibration", box)
        setup = self.setup()
        if not setup.get("detectors"):
            im.text_disabled(tr("No setup"))
            im.set_item_tooltip(tr(NO_SETUP_HINT))
            return
        calibration = getattr(self.source, "calibration", {}) or {}
        colours = calibration.get("colours") or {}
        rows_of = getattr(self.source, "rows", None)
        rows = rows_of() if callable(rows_of) else {}
        dyes = self.reference_dyes(setup, rows)
        shown = False
        for group in colour_groups(setup):
            colour = group["colour"]
            if not any(r == f"reference:{colour}" for r in rows.values()):
                continue
            shown = True
            choice = dyes.get(colour) or dye_choice((getattr(self.source, "dyes", {}) or {}).get(colour), colour)
            im.separator_text(f"{choice['dye']} · {tr(group['word'])}")
            im.set_next_item_width(80.0)
            changed, value = im.input_float(f"°C##T{colour}", float(choice["temperature_c"]), 0.0, 0.0, "%.1f")
            im.set_item_tooltip(
                tr(
                    "Temperature of the reference measurement: the database's D (25 °C, water) is "
                    "corrected to it with the viscosity of water (Stokes-Einstein), as in the FCS "
                    "calculator. About 2.6 % in D per °C."
                )
            )
            self.remember(f"temperature_{colour}")
            if changed and 0.0 < value < 100.0:
                self.set_dye(colour, temperature_c=float(value))
            if choice["dye"] == CUSTOM_DYE:
                im.same_line()
                im.set_next_item_width(80.0)
                changed, value = im.input_float(f"D µm²/s##D{colour}", float(choice["custom_D"]), 0.0, 0.0, "%.0f")
                im.set_item_tooltip(tr("Your own diffusion coefficient of the reference dye, at its temperature."))
                self.remember(f"diffusion_{colour}")
                if changed and value > 0:
                    self.set_dye(colour, custom_D=float(value))
            else:
                d, source = dye_diffusion(choice, colour)
                im.same_line()
                im.text(f"D {d:.0f} µm²/s" if d == d else "D —")
                im.set_item_tooltip(source)
            volume = (colours.get(colour) or {}).get("volume") or {}
            if volume:
                self._volume_plot(colour, volume)
        if not shown:
            im.text_disabled(tr("No reference dye"))
            im.set_item_tooltip(tr("Drop a reference-dye measurement on its row."))
        if calibration.get("errors"):
            im.text("⚠ " + tr("failed"))
            im.set_item_tooltip("\n".join(calibration["errors"]))

    def _volume_plot(self, colour: str, volume: dict) -> None:
        """The reference dye's correlation and the fitted 3-D diffusion model."""
        import numpy as np
        from emtk import implot

        tau = np.asarray(volume.get("tau_ms") or [], dtype=float)
        g = np.asarray(volume.get("g") or [], dtype=float)
        model = np.asarray(volume.get("model") or [], dtype=float)
        lo, hi = volume.get("fit_range_ms") or [1e-3, 1e3]
        keep = (tau >= lo) & (tau <= hi)
        if np.count_nonzero(keep) < 2:
            return
        h = max(110.0, min(170.0, im.get_content_region_avail()[1] - 30.0))
        if implot.begin_plot(f"##fcs{colour}", (-1, h)):
            implot.setup_axes("τ (ms)", "G(τ)")
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
            implot.set_next_line_style((200, 205, 220, 255), 1.5)
            implot.plot_line(tr("data"), tau[keep], g[keep])
            implot.set_next_line_style((240, 160, 60, 255), 2.0)
            implot.plot_line(tr("3-D diffusion"), tau[keep], model[keep])
            implot.end_plot()
        self.remember(f"fcs_plot_{colour}")

    # -- frame ---------------------------------------------------------------------------------------------- #
    def _render(self) -> None:
        self.poll_calibration()
        w, h = im.get_main_viewport().size
        frame = (0.0, 0.0, float(w), float(h))
        self.docks.draw(frame)
        if self.help_window.open:
            self.help_window.draw(frame)
        if self.tour.active:
            self.tour.draw(float(w), float(h))

    # -- persistence ---------------------------------------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        export = getattr(self.source, "export_settings", None)
        state = dict(export()) if callable(export) else {}
        state["filter"] = self.filter_text
        return state

    def restore_settings(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self.filter_text = str(state.get("filter", ""))
        restore = getattr(self.source, "restore_settings", None)
        if callable(restore):
            restore(state)
        # the calibration shown was computed from what is restored: not again
        self._calibrated_for = self.calibration_input()[3] if getattr(self.source, "calibration", None) else ""

    def close(self) -> None:
        pass


def row_detectors(row: str, setup: dict) -> list[str]:
    """The detectors of the colour of *row* (``irf:R`` -> ``["R|G", "R|R"]``)."""
    from ..samples import colour_groups

    colour = row.partition(":")[2]
    return next((g["detectors"] for g in colour_groups(setup) if g["colour"] == colour), [])


def _size(path: Path) -> int:
    try:
        return int(path.stat().st_size)
    except OSError:
        return 0


def _total_size(paths) -> int:
    return sum(_size(Path(p)) for p in paths)


def make_app(**kwargs) -> BurstDataSelectionApp:
    """The data-selection step alone."""
    from chisurf.emtk.i18n import install

    install()
    return BurstDataSelectionApp(**kwargs)


__all__ = [
    "BurstDataSelectionApp",
    "BurstDataSelectionModel",
    "WINDOW_BG",
    "expand_paths",
    "import_raw_file",
    "make_app",
]
