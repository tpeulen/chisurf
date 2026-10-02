"""EMTK micro-time shifter: align detectors on their rising edges, write shifted copies, archive them.

Files on the left (local files, a folder, or the MMFDB object store), the
controls the spec ``shifter.view.json`` declares below them (drawn by emtk's
view_form with this app as the model: its fields are the spec's attrs, its
methods the button actions, ``enabled``/``bounds`` its hooks), and the
micro-time histograms with the draggable trigger lines on the right. The
per-channel shift rows depend on the loaded file and are the spec's custom
``channel_shifts`` section. Loading, writing and archiving run on one worker
(the MMFDB connection is thread-affine), so the window keeps drawing.
"""

from __future__ import annotations

import json
import shutil
import threading
from copy import deepcopy
from pathlib import Path

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form, draw_sections

from chisurf.core.fio.staging import TTTR_EXTENSIONS
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.plugins.emtk_layout import NUMBER_WIDTH, LabelColumn, icon_label, labelled, layout_spec
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .client import MicrotimeShifterClient

HERE = Path(__file__).parent


class SampleFields:
    """The sample dialog's fields as attributes: each reads and writes one key of the app's ``sample_definition`` JSON.

    ``name`` / ``description`` / ``buffer_description`` are the sample's, the entity fields those of its first
    entity, ``donor`` / ``acceptor`` the first two probes; setting a probe also adds the FRET pair, as before.
    """

    ENTITY = {"entity_name": "name", "entity_type": "entity_type", "sequence": "sequence",
              "uniprot_accession": "uniprot_accession", "pdb_id": "pdb_id", "pdb_chain_id": "pdb_chain_id",
              "organism": "organism", "reference_sequence": "reference_sequence"}
    SAMPLE = ("name", "description", "buffer_description")
    PROBES = {"donor": 0, "acceptor": 1}

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def _data(self):
        return json.loads(self._app.sample_definition)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        data = self._data()
        if name in self.SAMPLE:
            return str(data.get(name) or "")
        if name in self.ENTITY:
            entities = data.get("entities") or [{}]
            default = "protein" if name == "entity_type" else ""
            return str(entities[0].get(self.ENTITY[name]) or default)
        if name in self.PROBES:
            probes = data.get("probes") or []
            index = self.PROBES[name]
            return str(probes[index].get("name", "")) if index < len(probes) else ""
        raise AttributeError(name)

    def __setattr__(self, name, value):
        data = self._data()
        if name in self.SAMPLE:
            data[name] = value
        elif name in self.ENTITY:
            if not data.get("entities"):
                data["entities"] = [{"name": "", "entity_type": "protein", "sequence": ""}]
            data["entities"][0][self.ENTITY[name]] = value
        elif name in self.PROBES:
            probes = list(data.get("probes") or [])
            index = self.PROBES[name]
            while len(probes) <= index:
                probes.append({"name": "", "entity_index": 0})
            probes[index]["name"] = value
            data["probes"] = [probe for probe in probes if probe.get("name")]
            if len(data["probes"]) >= 2 and not data.get("fret_pairs"):
                data["fret_pairs"] = [{"probe_1_index": 0, "probe_2_index": 1}]
        else:
            raise AttributeError(name)
        self._app.sample_definition = json.dumps(data, indent=2)

    def fetch_sample_reference(self):
        self._app.fetch_sample_reference()

    def diff_sample_reference(self):
        self._app.diff_sample_reference()


class ShiftFields:
    """The per-channel shift rows' model: ``shift_<channel>`` fields (clamped to the bin count) and ``reset_<channel>`` actions."""

    def __init__(self, app):
        object.__setattr__(self, "_app", app)

    def __getattr__(self, name):
        app = self._app
        if name.startswith("shift_") and name[6:].lstrip("-").isdigit():
            return app.channel_shifts[int(name[6:])]
        if name.startswith("reset_") and name[6:].lstrip("-").isdigit():
            return lambda channel=int(name[6:]): app.reset_shift(channel)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        app = self._app
        top = max(app.n_mt - 1, 0)
        app.channel_shifts[int(name[6:])] = max(-top, min(int(value), top))
        app.tour.notify_used("channel_shifts")

    def bounds(self, name):
        top = max(self._app.n_mt - 1, 0)
        return (-top, top)


class MicrotimeShifterApp(TourTarget, ImApp):
    """The micro-time shifter window."""

    def __init__(self, client=None, mmfdb_db=None, mmfdb_session=None, mmfdb_client=None):
        self.pending_preferences = None
        self.closed = False
        self._db = mmfdb_db
        self._db_owner_thread = threading.get_ident() if mmfdb_db is not None else None
        self._session = mmfdb_session
        self._db_owned = mmfdb_db is None
        self._mmfdb_client = mmfdb_client
        self._client = client or MicrotimeShifterClient(
            mmfdb_db_provider=self.acquire_db, mmfdb_session_provider=self.acquire_session
        )
        self.files = []
        self.current_path = None
        self.n_mt = 0
        self.global_shift = 0
        self.channel_shifts = {}
        self.raw_histograms = {}
        self.trigger_level = 1
        self.trigger_position = 0
        self.trigger_drag_active = False
        self.show_trigger = True
        self.log_y = False
        self.plot_limits_signature = None
        self.message = "No file loaded."
        self.db_status = ""
        self.last_result = None
        self.output_folder = ""
        self.sample_id = ""
        self.samples = []
        self.sample_definition = None
        self.item_rects = {}
        self.spec = layout_spec(json.loads((HERE / "shifter.view.json").read_text(encoding="utf-8")))
        self.labels = LabelColumn()                  # one caption column for the fields of every panel
        for panel in self.spec["sections"]:
            for group in panel["sections"]:
                for field in group.get("sections", ()):
                    if field.get("attr") == "output_folder":
                        field.pop("width", None)
        self.form = FormState()
        self.form.custom["channel_shifts"] = self.draw_channel_shifts
        self.form.custom["sample_list"] = self.draw_sample_list
        self.sample_spec = layout_spec(json.loads((HERE / "sample.view.json").read_text(encoding="utf-8")))
        self.sample_form = FormState()
        self.sample_labels = LabelColumn()
        self.shift_fields = ShiftFields(self)
        self.shift_form = FormState()
        self.shift_channels = ()
        self.shift_sections = []
        self.sample_fields = SampleFields(self)
        self.help = EmTkHelpWindow(
            title="Micro-time shifter — Help", resource=HERE / "help.md", owner=self,
            on_start_guide=self.start_guide, size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
            owner=self, wait_for_controls=True, on_step_change=self.reveal_step,
        )
        self.form.on_used = self.shift_form.on_used = self.tour.notify_used
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_callback = None
        self.dialog_window = DialogWindow("Choose a file", size=(640.0, 420.0), key="microtime-shifter-file")
        self.sample_window = DialogWindow("New MMFDB sample", size=(620.0, 560.0), key="microtime-shifter-sample")
        self.dataset_picker = DatasetPicker(on_paths=self.add_paths)
        self.docks = DockManager(
            Split(
                "h", 0.32, Split("v", 0.4, Region("files"), Region("controls")), Region("histogram")
            )
        )
        for key, title, draw, dock in (
            ("files", icon_label("📂", "Files"), self.draw_files, "files"),
            ("controls", "↔ Micro-time shift", self.draw_controls, "controls"),
            ("status", "Status", self.draw_status, "controls"),
            ("histogram", icon_label("📊", "Micro-time histograms"), self.draw_histogram, "histogram"),
        ):
            self.docks.add_window(key, title, draw, dock=dock, closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(gui=self.render, continuous=False)

    def acquire_db(self):
        thread = threading.get_ident()
        if self._db is not None and self._db_owner_thread != thread:
            if self._db_owned:
                raise RuntimeError("MMFDB connection is owned by the TTTR worker thread.")
            target = getattr(self._db, "database_url", None) or getattr(self._db, "db_path", None)
            if not target or str(target) == ":memory:":
                raise ValueError("Background archival requires a reopenable MMFDB database target.")
            from mmfdb.repository import MFDatabase

            self._db = MFDatabase(str(target))
            self._db_owned = True
            self._db_owner_thread = thread
        if self._db is None:
            from ..api.mmfdb import active_mmfdb_connection

            self._db = active_mmfdb_connection()
            self._db_owner_thread = thread
        return self._db

    def acquire_session(self):
        db = self.acquire_db()
        if db is None:
            return None
        from chisurf.core.transform.mmfdb import runtime_session_for_database, session_from_auth

        if self._session is not None:
            if getattr(self._session, "db", None) is not db:
                self._session = session_from_auth(db, getattr(self._session, "auth", None))
            return self._session
        token = getattr(self._mmfdb_client, "token", None)
        self._session = (
            session_from_auth(db, {"token": token}) if token else runtime_session_for_database(db)
        )
        return self._session

    def button(self, label, tip, callback, key=None):
        """A button that tells the guide it was pressed, remembered under *key* (or its label)."""
        key = key or label
        pressed = im.button(label)
        im.set_item_tooltip(tip)
        self.remember(key)
        if pressed:
            self.tour.notify_used(key)
            callback()

    def start_guide(self):
        self.tour.start()

    def reveal_step(self, index, step):
        """Unfold the spec panel a guide step points into."""
        target = EmTkGuidedTour._target_key(step.get("target"))
        for panel in self.spec["sections"]:
            names = {s.get("attr") or s.get("key") for s in panel.get("sections", [])}
            names |= {b.get("action") for s in panel.get("sections", []) for b in s.get("buttons", [])}
            if target in names:
                self.form.folds[panel["title"]] = True

    # ── view_form hooks: the app is the spec's model ──────────────────────
    def enabled(self, name):
        if self.job.running:
            return name not in ("auto_align", "save_dialog", "save_batch", "register", "browse_output_folder",
                                "refresh_samples", "new_sample")
        if name in ("auto_align",):
            return self.n_mt > 0
        if name in ("save_dialog", "save_batch", "register"):
            return bool(self.files)
        return True

    def bounds(self, name):
        top = max(self.n_mt - 1, 0)
        return {"trigger_level": (1, None), "trigger_position": (0, top),
                "global_shift": (-top, top)}.get(name)

    def browse_output_folder(self):
        self.choose("Output folder", lambda paths: setattr(self, "output_folder", str(paths[0])), mode="folder")

    def save_batch(self):
        if not self.output_folder:
            self.message = "Choose an output folder first."
            return False
        return self.apply(output_dir=self.output_folder)

    def register(self):
        return self.apply(archive=True)

    def new_sample(self):
        self.sample_definition = json.dumps(
            {"name": "New sample", "description": "", "entities": [], "probes": [], "fret_pairs": []}, indent=2)
        self.sample_window.show()

    def choose(self, title, callback, mode="open", multiple=False):
        if self.job.running:
            return
        suffix = self.files[0].suffix if mode == "save" and self.files else ""
        filters = (
            [("Shifted TTTR", [f"*{suffix}"]), ("All files", ["*"])]
            if suffix
            else [("TTTR", [f"*{ext}" for ext in TTTR_EXTENSIONS]), ("All files", ["*"])]
        )
        start = self.files[0].parent if self.files else None
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=multiple,
            filters=filters,
            directory=str(start) if start else None,
            filename=(self.files[0].stem + "_shifted" + suffix) if suffix else "",
        )
        self.dialog_callback = callback
        self.dialog_window.title = title
        self.dialog_window.show()

    def add_paths(self, paths):
        if self.job.running:
            return False
        files = list(self.files)
        for path in paths:
            p = Path(path)
            candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
            for candidate in candidates:
                candidate = candidate.expanduser().resolve()
                if (
                    candidate.is_file()
                    and candidate.suffix.lower() in TTTR_EXTENSIONS
                    and candidate not in files
                ):
                    files.append(candidate)
        if not files:
            self.message = "Choose supported TTTR or PTO photon files."
            return False
        return self.load_files(files)

    def load_files(self, files, current=None):
        if self.job.running:
            return False
        paths = list(dict.fromkeys(Path(p).expanduser().resolve() for p in files))
        if not paths:
            self.clear()
            return False
        selected = Path(current).expanduser().resolve() if current else paths[0]

        def work():
            metadata = [self._client.load_metadata(path) for path in paths]
            bins = {int(item.get("n_mt", 0)) for item in metadata}
            if len(bins) != 1 or next(iter(bins)) < 1:
                raise ValueError(
                    "Queued files must have the same positive number of micro-time bins."
                )
            histogram = self._client.histogram(paths, global_shift=0, channel_shifts={})
            if not histogram.get("histograms"):
                raise ValueError("No photon histograms were read from these files.")
            try:
                info = self._client.identify(selected)
            except Exception:
                info = {"unavailable": True}
            return histogram, info

        def publish(result):
            histogram, info = result
            self.files = paths
            self.current_path = selected
            self.n_mt = int(histogram["n_mt"])
            self.raw_histograms = {
                int(ch): np.asarray(counts, dtype=np.int64)
                for ch, counts in histogram["histograms"].items()
            }
            self.global_shift = 0
            self.channel_shifts = {ch: 0 for ch in self.raw_histograms}
            peak = max(int(np.max(v)) for v in self.raw_histograms.values())
            self.trigger_level = max(1, int(peak * 0.2))
            self.trigger_position = int(self.n_mt * 0.1)
            self.db_status = (
                f"Identified artifact {info.get('artifact_id', '?')}"
                if info.get("found")
                else (
                    "MMFDB check unavailable"
                    if info.get("unavailable")
                    else "New file (not in MMFDB)"
                )
            )
            self.message = f"Loaded {len(paths)} file(s), {self.n_mt} micro-time bins."
            if self.pending_preferences is not None:
                self.restore_control_preferences(self.pending_preferences)
                self.pending_preferences = None

        self.message = "Loading TTTR histograms…"
        return self.job.start(work, publish, lambda exc: setattr(self, "message", str(exc)))

    def histograms(self):
        return (
            {
                ch: np.roll(
                    counts, (self.global_shift + self.channel_shifts.get(ch, 0)) % self.n_mt
                )
                for ch, counts in self.raw_histograms.items()
            }
            if self.n_mt
            else {}
        )

    def auto_align(self, _value=None):
        """Shift each channel so its first threshold crossing up to the peak lands on the target bin."""
        if not self.n_mt or self.job.running:
            return
        target = int(self.trigger_position)
        for ch, hist in self.histograms().items():
            peak = int(np.argmax(hist))
            crossings = np.where(hist[: peak + 1] >= int(self.trigger_level))[0]
            crossing = int(crossings[0]) if len(crossings) else peak
            self.channel_shifts[ch] = int(
                (self.channel_shifts.get(ch, 0) + target - crossing) % self.n_mt
            )

    def stop_operation(self):
        self.job.stop()
        self.message = (
            "Stopped publication; a file write or archive operation already running may finish."
        )

    def clear(self):
        self.job.stop()
        self.files = []
        self.current_path = None
        self.n_mt = 0
        self.raw_histograms = {}
        self.channel_shifts = {}
        self.global_shift = 0
        self.db_status = ""
        self.message = "No file loaded."

    def remove_selected(self):
        """Remove the selected file (the one previewed) from the queue."""
        if self.current_path in self.files:
            self.remove_file(self.files.index(self.current_path))

    def remove_file(self, index):
        if self.job.running:
            return
        paths = list(self.files)
        paths.pop(index)
        self.load_files(paths) if paths else self.clear()

    def apply(self, output_dir=None, filename=None, archive=False):
        if self.job.running:
            return False
        if not self.files:
            self.message = "Load TTTR files first."
            return False
        if archive and not self.sample_id:
            self.message = "Choose an MMFDB sample first."
            return False
        paths = [path.expanduser().resolve() for path in self.files]
        global_shift = int(self.global_shift)
        shifts = dict(self.channel_shifts)
        sample_id = str(self.sample_id)
        directory = (
            str(output_dir) if output_dir else (str(Path(filename).parent) if filename else None)
        )

        def work():
            result = self._client.apply(
                file_paths=paths,
                global_shift=global_shift,
                channel_shifts=shifts,
                output_dir=directory,
                mmfdb={"enabled": archive, "sample_id": sample_id, "register_missing_inputs": True},
            )
            if filename and len(paths) == 1:
                generated = result.get("output_paths_by_file", {}).get(str(paths[0]))
                if generated and Path(generated) != Path(filename):
                    shutil.move(generated, filename)
                    result["output_paths_by_file"][str(paths[0])] = str(filename)
            return result

        def publish(result):
            self.last_result = result
            warnings = "; ".join(result.get("warnings", []))
            count = (
                len((result.get("mmfdb_artifacts") or {}).get("output_artifacts", {}))
                if archive
                else len(result.get("output_paths_by_file", {}))
            )
            self.message = (
                f"{'Registered' if archive else 'Saved'} {count}/{len(paths)} shifted file(s)."
                + (" Warnings: " + warnings if warnings else "")
            )
            if any(
                Path(output).resolve() in paths
                for output in result.get("output_paths_by_file", {}).values()
            ):
                self.load_files(self.files, self.current_path)

        self.message = "Writing shifted files…"
        return self.job.start(
            work, publish, lambda exc: setattr(self, "message", f"Shift export failed: {exc}")
        )

    def save_dialog(self):
        if len(self.files) == 1:
            self.choose(
                "Save shifted TTTR", lambda paths: self.apply(filename=str(paths[0])), mode="save"
            )
        elif self.files:
            self.choose(
                "Shifted output folder",
                lambda paths: self.apply(output_dir=paths[0]),
                mode="folder",
            )

    def refresh_samples(self):
        if self.job.running:
            return

        def work():
            from mmfdb.samples.sample_manager import list_samples

            db = self.acquire_db()
            if db is None:
                raise ValueError("No active MMFDB database is configured.")
            return list_samples(db)

        self.job.start(
            work,
            lambda rows: setattr(self, "samples", rows),
            lambda exc: setattr(self, "message", str(exc)),
        )

    def create_sample(self):
        if self.job.running:
            return
        try:
            data = json.loads(self.sample_definition)
        except Exception as exc:
            self.message = str(exc)
            return

        def work():
            from mmfdb.models import (
                EntityDefinition,
                FretPairDefinition,
                MutationDefinition,
                ProbeDefinition,
                SampleDefinition,
            )
            from mmfdb.samples.sample_manager import create_sample

            db = self.acquire_db()
            session = self.acquire_session()
            if db is None or session is None:
                raise ValueError("An authenticated MMFDB session is required to create a sample.")
            db.session_context = session
            for entity in data.get("entities", []):
                entity["mutations"] = [
                    MutationDefinition(**mutation) for mutation in entity.get("mutations", [])
                ]
            for key, cls in (
                ("entities", EntityDefinition),
                ("probes", ProbeDefinition),
                ("fret_pairs", FretPairDefinition),
            ):
                data[key] = [cls(**item) for item in data.get(key, [])]
            return create_sample(db, SampleDefinition(**data))

        def publish(sample):
            self.sample_id = str(sample)
            self.sample_definition = None
            self.message = f"Created sample {sample}"

        self.job.start(work, publish, lambda exc: setattr(self, "message", str(exc)))

    def cancel_sample(self):
        self.job.stop()
        self.sample_definition = None

    def fetch_sample_reference(self):
        if self.job.running:
            return
        try:
            data = json.loads(self.sample_definition)
            entity = (data.get("entities") or [{}])[0]
            accession = str(entity.get("uniprot_accession") or "").strip()
            if not accession:
                raise ValueError("Enter a UniProt accession first.")
        except Exception as exc:
            self.message = str(exc)
            return

        def work():
            from mmfdb.samples.external_refs import fetch_uniprot

            result = fetch_uniprot(accession)
            if result is None:
                raise ValueError("UniProt reference could not be retrieved.")
            return result

        def publish(reference):
            data.setdefault("entities", [])
            if not data["entities"]:
                data["entities"].append({"name": "", "entity_type": "protein"})
            data["entities"][0].update(
                reference_sequence=reference.get("sequence", ""),
                organism=reference.get("organism"),
                uniprot_accession=accession,
            )
            self.sample_definition = json.dumps(data, indent=2)

        self.job.start(work, publish, lambda exc: setattr(self, "message", str(exc)))

    def diff_sample_reference(self):
        try:
            from dataclasses import asdict

            from mmfdb.samples.external_refs import diff_sequences

            data = json.loads(self.sample_definition)
            entity = data["entities"][0]
            mutations = diff_sequences(
                entity.get("sequence", ""), entity.get("reference_sequence", "")
            )
            entity["mutations"] = [asdict(item) for item in mutations]
            self.sample_definition = json.dumps(data, indent=2)
            self.message = f"Found {len(mutations)} sequence differences."
        except Exception as exc:
            self.message = str(exc)

    def draw_sample_form(self):
        """The common sample fields as a spec form over the definition JSON (the full record is under Advanced)."""
        try:
            json.loads(self.sample_definition)
        except ValueError:
            return
        if not self.sample_labels.ready:
            self.sample_labels.measure([s["label"] for s in labelled(self.sample_spec["sections"])])
            self.sample_labels.pad(self.sample_spec["sections"])
        self.sample_form.rects.clear()
        draw_form(self.sample_spec, self.sample_fields, self.sample_form)
        self.item_rects.update({f"sample_{k}": v for k, v in self.sample_form.rects.items()})

    def draw_files(self, box):
        self.button("📖  Guide", "A walk through the tool, pointing at each control.", self.start_guide, key="guide")
        im.same_line()
        self.button("❓  Help", "Shifts, alignment, what is written and the MMFDB archive.", self.help.show,
                    key="help")
        im.separator()
        im.text_wrapped(self.message)
        if self.job.running:
            self.button(
                "⏹  Stop",
                "Discard pending results; a current file write or archive may finish.",
                self.stop_operation,
                key="stop",
            )
        im.begin_disabled(self.job.running or self.dataset_picker.is_open or self.dialog is not None
                          or self.sample_definition is not None)
        buttons = (
            ("➕  Files…", "Queue TTTR files; originals are retained when saving shifts.",
             lambda: self.choose("TTTR inputs", self.add_paths, multiple=True), "add_files"),
            ("📁  Folder…", "Queue supported TTTR files recursively from a folder.",
             lambda: self.choose("TTTR folder", self.add_paths, mode="folder"), "add_folder"),
            ("🗄  Database…", "Select TTTR inputs from the MMFDB object store.", self.dataset_picker.open,
             "add_database"),
            ("➖  Remove", "Remove the selected file from the queue (it stays on disk).", self.remove_selected,
             "remove"),
            ("🧹  Clear", "Remove queued files and preview shifts.", self.clear, "clear"),
        )
        pad = 2 * im.get_style().frame_padding[0] + im.get_style().item_spacing[0]
        for i, (label, tip, callback, key) in enumerate(buttons):
            if i and im.get_line_avail() >= im.calc_text_size(label)[0] + pad:
                im.same_line()                    # wrap rather than run off a narrow dock
            self.button(label, tip, callback, key=key)
        top = im.get_cursor_screen_pos()
        for i, path in enumerate(list(self.files)):
            if im.selectable(f"{path.name}##file{i}", path == self.current_path):
                self.load_files(self.files, path)
            self.remember(f"file_{i}")
            im.set_item_tooltip(
                f"{path} — select to reload metadata and reset shifts; right-click to remove."
            )
            if im.begin_popup_context_item(f"file-menu{i}"):
                if im.menu_item("Remove from queue"):
                    self.remove_file(i)
                im.set_item_tooltip("Remove this input without deleting it from disk.")
                im.end_popup()
        self.remember("files", (top[0], top[1], max(1.0, float(box[2]) - 16.0),
                                max(im.get_text_line_height(), im.get_cursor_screen_pos()[1] - top[1])))
        im.end_disabled()

    def draw_controls(self, box):
        im.begin_disabled(self.dataset_picker.is_open or self.dialog is not None
                          or self.sample_definition is not None)
        if not self.labels.ready:
            self.labels.measure([f["label"] for f in labelled(self.spec["sections"])] + ["Channel 00"])
            self.labels.pad(self.spec["sections"])
        self.form.rects.clear()
        draw_form(self.spec, self, self.form)
        self.item_rects.update(self.form.rects)
        im.end_disabled()

    def draw_channel_shifts(self, section, model, state, width):
        """One spec row per routing channel of the loaded file: its shift (a spin field) and a reset."""
        if not self.channel_shifts:
            im.text_disabled("No file loaded.")
            self.remember("channel_shifts")
            return
        top = im.get_cursor_screen_pos()
        channels = tuple(sorted(self.channel_shifts))
        if channels != self.shift_channels:
            self.shift_channels = channels
            rows = []
            for channel in channels:
                rows.append({"type": "value", "attr": f"shift_{channel}", "label": f"Channel {channel}",
                             "kind": "int", "style": "spin", "step": 1, "width": NUMBER_WIDTH,
                             "description": "Shift micro-times cyclically; the global and routing-channel shifts "
                                            "are added modulo the bin count."})
                rows.append({"type": "button_row", "weight": 0, "buttons": [
                    {"action": f"reset_{channel}", "label": "↺",
                     "description": f"Reset the shift of channel {channel} to zero."}]})
            self.shift_sections = [{"type": "panel", "title": "", "n_col": 2, "sections": rows}]
            self.labels.pad(self.shift_sections)
        self.shift_form.rects.clear()
        draw_sections(self.shift_sections, self.shift_fields, self.shift_form)
        self.item_rects.update(self.shift_form.rects)
        self.remember("channel_shifts", (top[0], top[1], width, im.get_cursor_screen_pos()[1] - top[1]))

    def draw_sample_list(self, section, model, state, width):
        """The samples of the active database, once refreshed."""
        if not self.samples:
            return
        ids = [str(row.get("sample_id") or row.get("id") or "") for row in self.samples]
        names = [str(row.get("name") or row.get("display_name") or identifier)
                 for row, identifier in zip(self.samples, ids)]
        im.set_next_item_width(width)
        changed, index = im.combo("##sample", ids.index(self.sample_id) if self.sample_id in ids else -1, names)
        im.set_item_tooltip("Sample to own the registered shifted TTTR artifacts.")
        self.remember("sample_list")
        if changed:
            self.sample_id = ids[index]

    def reset_shift(self, channel):
        if channel is None:
            self.global_shift = 0
        else:
            self.channel_shifts[channel] = 0

    def draw_histogram(self, box):
        if implot.begin_plot("##microtime", (-1, -1)):
            implot.setup_axes("Micro-time bin", "Counts")
            if self.log_y:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            histograms = self.histograms()
            peak = max((int(np.max(hist)) for hist in histograms.values()), default=1)
            signature = (self.n_mt, self.log_y, peak)
            if not self.n_mt:                         # nothing loaded: the bin axis of a typical TCSPC card
                implot.setup_axes_limits(0, 4096, 0, 100, cond=implot.COND_ONCE)
            if self.n_mt:
                implot.setup_axes_limits(
                    0,
                    self.n_mt,
                    1 if self.log_y else 0,
                    max(2, peak * 1.2),
                    cond=implot.COND_ALWAYS
                    if signature != self.plot_limits_signature
                    else implot.COND_ONCE,
                )
                self.plot_limits_signature = signature
            for ch, hist in histograms.items():
                values = np.where(hist > 0, hist, np.nan) if self.log_y else hist
                implot.plot_stairs(f"Routing {ch}", np.arange(len(hist)), values)
            if self.show_trigger and self.n_mt:
                position = implot.drag_line_x(
                    1, float(self.trigger_position), col=(50, 200, 90, 255)
                )
                level = implot.drag_line_y(2, float(self.trigger_level), col=(255, 220, 40, 255))
                if not self.job.running and (position.modified or level.modified):
                    self.trigger_position = max(0, min(self.n_mt - 1, int(position.value)))
                    self.trigger_level = max(1, int(level.value))
                    self.trigger_drag_active = True
                if (
                    self.trigger_drag_active
                    and not position.held
                    and not level.held
                    and not self.job.running
                ):
                    self.trigger_drag_active = False
                    self.auto_align()
            implot.end_plot()
        im.set_item_tooltip(
            "Drag green target-bin and yellow threshold lines; align on release. Log Y uses actual count units."
        )
        self.remember("histogram")

    def draw_status(self, box):
        im.text_wrapped(f"File: {self.current_path or 'none'}")
        im.text_wrapped(self.db_status)
        im.text_wrapped(self.message)
        if self.last_result:
            im.text_wrapped(json.dumps(self.last_result, indent=2))

    def export_settings(self):
        return {
            "files": [str(path) for path in self.files],
            "current_path": str(self.current_path) if self.current_path else None,
            "global_shift": self.global_shift,
            "channel_shifts": dict(self.channel_shifts),
            "trigger_level": self.trigger_level,
            "trigger_position": self.trigger_position,
            "show_trigger": self.show_trigger,
            "log_y": self.log_y,
            "output_folder": self.output_folder,
        }

    def restore_control_preferences(self, state):
        self.global_shift = int(state.get("global_shift", 0))
        shifts = {int(ch): int(value) for ch, value in state.get("channel_shifts", {}).items()}
        self.channel_shifts = {ch: shifts.get(ch, 0) for ch in self.raw_histograms}
        self.trigger_level = max(1, int(state.get("trigger_level", 1)))
        self.trigger_position = max(
            0, min(max(0, self.n_mt - 1), int(state.get("trigger_position", 0)))
        )
        self.show_trigger = bool(state.get("show_trigger", True))
        self.log_y = bool(state.get("log_y", False))
        self.output_folder = str(state.get("output_folder", ""))
        self.plot_limits_signature = None

    def restore_settings(self, state):
        self.restore_control_preferences(state)
        files = [Path(path) for path in state.get("files", []) if Path(path).is_file()]
        if files:
            self.pending_preferences = deepcopy(state)
            current = state.get("current_path")
            self.load_files(files, current if current and Path(current).is_file() else files[0])

    def export_state(self):
        return {
            "files": [str(p) for p in self.files],
            "current_path": str(self.current_path) if self.current_path else None,
            "n_mt": self.n_mt,
            "global_shift": self.global_shift,
            "channel_shifts": self.channel_shifts,
            "histograms": {str(ch): hist.tolist() for ch, hist in self.raw_histograms.items()},
            "trigger_level": self.trigger_level,
            "trigger_position": self.trigger_position,
            "show_trigger": self.show_trigger,
            "log_y": self.log_y,
            "output_folder": self.output_folder,
            "sample_id": self.sample_id,
        }

    def restore_state(self, state):
        self.plot_limits_signature = None
        self.job.stop()
        self.files = [Path(p) for p in state.get("files", [])]
        self.current_path = Path(state["current_path"]) if state.get("current_path") else None
        self.n_mt = int(state.get("n_mt", 0))
        self.global_shift = int(state.get("global_shift", 0))
        self.channel_shifts = {
            int(ch): int(shift) for ch, shift in state.get("channel_shifts", {}).items()
        }
        self.raw_histograms = {
            int(ch): np.asarray(hist, dtype=np.int64)
            for ch, hist in state.get("histograms", {}).items()
        }
        self.trigger_level = int(state.get("trigger_level", 1))
        self.trigger_position = int(state.get("trigger_position", 0))
        self.show_trigger = bool(state.get("show_trigger", True))
        self.log_y = bool(state.get("log_y", False))
        self.output_folder = str(state.get("output_folder", ""))
        self.sample_id = str(state.get("sample_id", ""))

    def render(self):
        self.job.poll()
        vp = im.get_main_viewport()
        frame = (0.0, 0.0, *vp.size)
        self.docks.draw(frame)
        self.dataset_picker.render(frame)
        if self.dialog is not None:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            self.dialog_window.end()
            if result:
                callback, self.dialog = self.dialog_callback, None
                callback(result)
            elif result is False or pressed == "close":
                self.dialog = None
        if self.sample_definition is not None:
            pressed = self.sample_window.begin(frame)
            im.begin_disabled(self.job.running)
            self.draw_sample_form()
            if im.collapsing_header("Advanced sample definition"):
                _, self.sample_definition = im.input_text_multiline(
                    "##sample-json", self.sample_definition, (-1, 150)
                )
                im.set_item_tooltip(
                    "Complete sample schema: name, description, entities, probes, FRET pairs, buffer, pH, "
                    "temperature and external-reference annotations."
                )
            self.button("Create sample", "Create the defined sample in the authenticated database.",
                        self.create_sample, key="sample_create")
            im.end_disabled()
            im.same_line()
            self.button("Cancel sample", "Discard the sample definition.", self.cancel_sample, key="sample_cancel")
            self.sample_window.end()
            if pressed == "close":
                self.cancel_sample()
        self.help.draw(frame)
        self.tour.draw(*vp.size)

    def animating(self):
        return self.job.running or self.trigger_drag_active or super().animating()

    def on_paths_dropped(self, paths):
        self.add_paths(paths)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.job.stop()
        self.dataset_picker.close()

        def close_connection():
            if self._db_owned and self._db is not None:
                self._db.close()
                self._db = None
                self._session = None

        # SQLite connections are thread-affine. Queue cleanup after any current
        # operation on the same single worker, then retire the executor.
        self.job.executor.submit(close_connection)
        self.job.executor.shutdown(wait=False, cancel_futures=False)


def create_app(client=None, mmfdb_db=None, mmfdb_session=None, mmfdb_client=None):
    return MicrotimeShifterApp(
        client=client, mmfdb_db=mmfdb_db, mmfdb_session=mmfdb_session, mmfdb_client=mmfdb_client
    )
