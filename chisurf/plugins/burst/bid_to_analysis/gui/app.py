"""Native BID conversion queue using the original scientific/provenance routines."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split

from chisurf.emtk.channel_definition import ChannelDefinitionWidget

from .. import _find_tttr_by_stem, convert_bid_file


class BidToAnalysisApp(ImApp):
    def __init__(self, setup_model=None):
        super().__init__(self._draw_ui, continuous=True)
        self.rows = []
        self.messages = []
        self.running = False
        self.status = "Add BID files or drop them here."
        self.output_types = {"pto"}
        self.unique_folder = False
        self.zip_output = False
        self.target_path = "analysis"
        self.analysis_folder = ""
        self.setup = ChannelDefinitionWidget(model=setup_model, host_app=self)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bid-converter")
        self.future = None
        self.cancel = Event()
        self.dialog = None
        self.dialog_mode = "files"
        self.docks = DockManager(
            Split("h", 0.43, Region("setup"), Split("v", 0.72, Region("files"), Region("log"))),
            name="bid_to_analysis",
        )
        self.docks.add_window(
            "setup", "Detector setup", lambda box: self.setup.draw(), dock="setup"
        )
        self.docks.add_window("files", "BID files and conversion", self.draw_files, dock="files")
        self.docks.add_window("log", "Conversion log", self.draw_log, dock="log")
        self.help_open = False

    def add_files(self, paths):
        if self.running:
            return
        existing = {row["bid"] for row in self.rows}
        for value in paths:
            path = Path(value).expanduser().resolve()
            if path.is_dir():
                self.add_files(
                    sorted(
                        p for p in path.iterdir() if p.suffix.lower() in {".bid", ".bst", ".txt"}
                    )
                )
                continue
            if (
                not path.is_file()
                or path.suffix.lower() not in {".bid", ".bst", ".txt"}
                or str(path) in existing
            ):
                continue
            tttr = _find_tttr_by_stem(path.parent, path.stem)
            self.rows.append(
                dict(
                    bid=str(path),
                    tttr=str(tttr) if tttr else "",
                    output="",
                    status="Ready" if tttr else "Missing TTTR",
                )
            )
            existing.add(str(path))
        self.status = f"{len(self.rows)} BID file(s) queued."

    def on_paths_dropped(self, paths):
        self.add_files(paths)

    def clear(self):
        if not self.running:
            self.rows.clear()
            self.messages.clear()
            self.status = "Queue cleared."

    def process(self):
        if self.running or not self.rows:
            return
        if not self.output_types:
            self.status = "Choose at least one output format."
            return
        self.running = True
        self.cancel.clear()
        settings = copy.deepcopy(self.setup.model.get_settings())
        options = dict(
            output_types=set(self.output_types),
            windows=settings.get("windows") or None,
            detectors=settings.get("detectors") or None,
            selected_setup=self.setup.model.current_name or None,
            unique_folder=self.unique_folder,
            zip_output=self.zip_output,
            target_path=self.target_path,
        )
        folder = self.analysis_folder or None
        self.future = self.executor.submit(self._convert, copy.deepcopy(self.rows), options, folder)
        self.status = "Converting; current file finishes before cancellation."

    def _convert(self, rows, options, folder):
        messages = []
        for index, row in enumerate(rows, 1):
            if self.cancel.is_set():
                if row["status"] == "Ready":
                    row["status"] = "Cancelled"
                continue
            try:
                if not row["tttr"]:
                    raise FileNotFoundError("Matching TTTR file not found")
                output = convert_bid_file(
                    row["bid"], analysis_folder=folder, bid_index=index, **options
                )
                if "pto" in options["output_types"]:
                    from chisurf.core.datastore import row_count
                    from chisurf.core.fio.pto import Measurement

                    with Measurement.open(Path(row["tttr"]).with_suffix(".pto")) as measurement:
                        if not row_count(measurement.get_store("bursts")):
                            raise RuntimeError("PTO output contains no burst table")
                        if (
                            measurement.get_blob(Path(row["bid"]).name)
                            != Path(row["bid"]).read_bytes()
                        ):
                            raise RuntimeError(
                                "PTO output does not contain the original BID selection"
                            )
                row["output"] = str(output.parent.parent if output.suffix == ".bur" else output)
                row["status"] = "Done"
                messages.append(f"Processed {row['bid']} → {output}")
            except Exception as error:
                row["status"] = f"Error: {error}"
                messages.append(f"{row['bid']}: {error}")
        return rows, messages

    def poll(self):
        if self.future is not None and self.future.done():
            try:
                self.rows, messages = self.future.result()
                self.messages.extend(messages)
                count = sum(row["status"] == "Done" for row in self.rows)
                self.status = f"Finished: {count}/{len(self.rows)} files converted."
            except Exception as error:
                self.status = f"Error: {error}"
            self.messages.append(self.status)
            self.future = None
            self.running = False

    def browse(self, mode):
        from emtk.file_dialog import FileDialog

        self.dialog_mode = mode
        self.dialog = FileDialog(
            "BID conversion paths",
            mode="folder" if mode in {"folder", "output"} else "open",
            filters=[("BID selections", ["*.bid", "*.bst", "*.txt"])],
            multiselect=mode == "files",
        )

    @staticmethod
    def button(label, tip, callback):
        if im.button(label):
            callback()
        im.set_item_tooltip(tip)

    def draw_files(self, box):
        im.begin_disabled(self.running)
        for label, tip, action in [
            (
                "Add files",
                "Choose BID, BST or TXT photon-index selections.",
                lambda: self.browse("files"),
            ),
            (
                "Folder",
                "Add matching selection files from one folder.",
                lambda: self.browse("folder"),
            ),
            ("Clear", "Remove all queued selections and log entries.", self.clear),
        ]:
            self.button(label, tip, action)
            im.same_line()
        self.button(
            "Process",
            "Convert each selection with its inferred TTTR and current detector setup; preserve BID provenance.",
            self.process,
        )
        for kind in ("pto", "bur", "sl5", "hdf5"):
            changed, enabled = im.checkbox(kind.upper(), kind in self.output_types)
            im.set_item_tooltip(
                {
                    "pto": "Measurement container with embedded original BID and derived burst table.",
                    "bur": "Legacy BUR burst table and MTI measurement summary.",
                    "sl5": "Compressed photon-selection mask.",
                    "hdf5": "Columnar burst table with source file provenance.",
                }[kind]
            )
            if changed:
                if enabled:
                    self.output_types.add(kind)
                else:
                    self.output_types.discard(kind)
            im.same_line()
        im.separator()
        changed, self.unique_folder = im.checkbox("Unique output folder", self.unique_folder)
        im.set_item_tooltip("Add a numeric suffix instead of reusing an existing output folder.")
        changed, self.zip_output = im.checkbox("ZIP output", self.zip_output)
        im.set_item_tooltip("Archive generated analysis files while keeping the output folder.")
        im.text("Output folder (empty: beside each measurement):")
        changed, self.analysis_folder = im.input_text("##bid_output", self.analysis_folder)
        im.set_item_tooltip(
            "Explicit output destination; empty uses the BID stem beside its TTTR measurement."
        )
        self.button(
            "Choose output folder",
            "Select a destination for generated analysis files.",
            lambda: self.browse("output"),
        )
        if im.begin_table(
            "bid_queue", 4, im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_X
        ):
            for title in ("BID file", "TTTR file", "Output / remove", "Status"):
                im.table_setup_column(title)
            im.table_headers_row()
            remove = None
            for index, row in enumerate(self.rows):
                im.table_next_row()
                for key in ("bid", "tttr", "output"):
                    im.table_next_column()
                    im.text_wrapped(row[key] or ("TTTR not found" if key == "tttr" else ""))
                    im.set_item_tooltip(row[key] or "Not yet generated.")
                    if key == "output":
                        if im.small_button(f"Remove##bid{index}"):
                            remove = index
                        im.set_item_tooltip("Remove this selection from the queue.")
                im.table_next_column()
                im.text_wrapped(row["status"])
            im.end_table()
            if remove is not None:
                self.rows.pop(remove)
        im.end_disabled()
        self.button(
            "Cancel",
            "Stop before the next file; let the current conversion finish consistently.",
            self.cancel.set,
        )
        im.same_line()
        self.button(
            "Help",
            "Explain input indices, detector setup, outputs and provenance.",
            lambda: setattr(self, "help_open", True),
        )
        im.text_wrapped(self.status)

    def draw_log(self, box):
        for message in self.messages:
            im.text_wrapped(message)

    def _draw_ui(self):
        self.poll()
        width, height = im.get_main_viewport().size
        im.begin_disabled(self.running)
        self.docks.draw((0.0, 0.0, float(width), float(height)))
        im.end_disabled()
        # Keep cancellation available while the queue/setup controls are locked.
        if self.running:
            if im.begin("Conversion running"):
                im.text_wrapped(self.status)
                self.button(
                    "Cancel after current file",
                    "Preserve completed output and stop the remaining queue.",
                    self.cancel.set,
                )
            im.end()
        if self.dialog is not None:
            if im.begin("Choose conversion paths"):
                result = self.dialog.draw()
                if result:
                    if self.dialog_mode == "output":
                        self.analysis_folder = str(result[0])
                    else:
                        self.add_files(result)
                    self.dialog = None
                elif result is False:
                    self.dialog = None
            im.end()
        self.setup.draw_dialogs((0.0, 0.0, float(width), float(height)))
        if self.help_open:
            if im.begin("BID → Analysis help"):
                im.text_wrapped(
                    "BID/BST/TXT selections contain two integer columns: start and stop photon indices. The TTTR measurement is inferred by stem in the current folder and three parents. Configure detector channels and PIE windows before Process. PTO retains the original BID bytes and derived-from provenance; BUR appends bursts to existing tables and records MTI duration; SL5 stores a photon mask; HDF5 stores columnar burst summaries. Cancel completes the current file and stops the remaining queue. Raw TTTR and BID inputs are preserved."
                )
                self.button(
                    "Close help",
                    "Close this workflow reference.",
                    lambda: setattr(self, "help_open", False),
                )
            im.end()

    def export_settings(self):
        return dict(
            output_types=sorted(self.output_types),
            unique_folder=self.unique_folder,
            zip_output=self.zip_output,
            analysis_folder=self.analysis_folder,
            channel_definition=self.setup.model.get_settings(),
        )

    def restore_settings(self, settings):
        self.output_types = set(settings.get("output_types", ["pto"])) & {
            "pto",
            "bur",
            "sl5",
            "hdf5",
        }
        for key in ("unique_folder", "zip_output", "analysis_folder"):
            if key in settings:
                setattr(self, key, settings[key])
        if isinstance(settings.get("channel_definition"), dict):
            self.setup.model.data = copy.deepcopy(settings["channel_definition"])

    def close(self):
        self.cancel.set()
        self.setup.close()
        self.executor.shutdown(wait=False, cancel_futures=True)


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BidToAnalysisApp(**kwargs)
