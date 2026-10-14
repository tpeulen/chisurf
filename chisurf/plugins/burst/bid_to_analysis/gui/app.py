"""Native BID conversion queue using the original scientific/provenance routines."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import action_button

from .. import _find_tttr_by_stem, convert_bid_file


class BidToAnalysisApp(ImApp, TourTarget):
    def __init__(self, setup_model=None):
        self.item_rects = {}
        super().__init__(self._draw_ui, continuous=True)
        self.rows = []
        self.messages = []
        self.running = False
        self.status = tr("Add BID files or drop them here, or press Load example.")
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
            "setup", tr("Detector setup"), lambda box: self.setup.draw(), dock="setup"
        )
        self.docks.add_window(
            "files", tr("BID files and conversion"), self.draw_files, dock="files"
        )
        self.docks.add_window("log", tr("Conversion log"), self.draw_log, dock="log")
        gui = Path(__file__).parent
        self.help_window = EmTkHelpWindow(
            title=tr("BID → Analysis help"),
            resource=gui / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=gui / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )

    def start_guide(self):
        self.help_window.hide()
        self.tour.start()

    def load_example(self):
        """Queue the shipped simulated stream with its known BID selection."""
        if self.running:
            return
        from ..demo import make_demo

        self.add_files([make_demo()])
        self.status = tr("Example queued: six simulated bursts. Press Process.")

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
        self.status = tr("{n} BID file(s) queued.").format(n=len(self.rows))

    def on_paths_dropped(self, paths):
        self.add_files(paths)

    def clear(self):
        if not self.running:
            self.rows.clear()
            self.messages.clear()
            self.status = tr("Queue cleared.")

    def process(self):
        if self.running or not self.rows:
            return
        if not self.output_types:
            self.status = tr("Choose at least one output format.")
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
        self.status = tr("Converting; current file finishes before cancellation.")

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
                self.status = tr("Finished: {done}/{total} files converted.").format(
                    done=count, total=len(self.rows)
                )
            except Exception as error:
                self.status = f"Error: {error}"
            self.messages.append(self.status)
            self.future = None
            self.running = False

    def browse(self, mode):
        from emtk.file_dialog import FileDialog

        self.dialog_mode = mode
        self.dialog = FileDialog(
            tr("BID conversion paths"),
            mode="folder" if mode in {"folder", "output"} else "open",
            filters=[(tr("BID selections"), ["*.bid", "*.bst", "*.txt"])],
            multiselect=mode == "files",
        )

    def button(self, label, tip, callback, key=None, role=None):
        """Draw one action in emtk button *role*; a keyed action is a tour target and reports its use."""
        if im.button(label, role=role):
            callback()
            if key:
                self.tour.notify_used(key)
        im.set_item_tooltip(tip)
        if key:
            self.remember(key)

    def draw_files(self, box):
        im.begin_disabled(self.running)
        if action_button(
            "example",
            tooltip=tr(
                "Queue a simulated photon stream with six known bursts and its BID selection."
            ),
        ):
            self.load_example()
            self.tour.notify_used("load_example")
        self.remember("load_example")
        im.same_line()
        for label, tip, action, key in [
            (
                tr("Add files"),
                tr("Choose BID, BST or TXT photon-index selections."),
                lambda: self.browse("files"),
                "add_files",
            ),
            (
                tr("Folder"),
                tr("Add matching selection files from one folder."),
                lambda: self.browse("folder"),
                "folder",
            ),
            (tr("Clear"), tr("Remove all queued selections and log entries."), self.clear, "clear"),
        ]:
            self.button(label, tip, action, key, role="danger" if key == "clear" else None)
            im.same_line()
        self.button(
            tr("Process"),
            tr(
                "Convert each selection with its inferred TTTR and current detector setup; "
                "preserve BID provenance."
            ),
            self.process,
            "process",
            role="primary",
        )
        for kind in ("pto", "bur", "sl5", "hdf5"):
            changed, enabled = im.checkbox(kind.upper(), kind in self.output_types)
            im.set_item_tooltip(
                {
                    "pto": tr(
                        "Measurement container with embedded original BID and derived burst table."
                    ),
                    "bur": tr("Legacy BUR burst table and MTI measurement summary."),
                    "sl5": tr("Compressed photon-selection mask."),
                    "hdf5": tr("Columnar burst table with source file provenance."),
                }[kind]
            )
            if kind == "pto":
                self.remember("formats")
            if changed:
                if enabled:
                    self.output_types.add(kind)
                else:
                    self.output_types.discard(kind)
            im.same_line()
        im.separator()
        changed, self.unique_folder = im.checkbox(tr("Unique output folder"), self.unique_folder)
        im.set_item_tooltip(
            tr("Add a numeric suffix instead of reusing an existing output folder.")
        )
        changed, self.zip_output = im.checkbox(tr("ZIP output"), self.zip_output)
        im.set_item_tooltip(tr("Archive generated analysis files while keeping the output folder."))
        im.text(tr("Output folder (empty: beside each measurement):"))
        changed, self.analysis_folder = im.input_text("##bid_output", self.analysis_folder)
        im.set_item_tooltip(
            tr("Explicit output destination; empty uses the BID stem beside its TTTR measurement.")
        )
        self.button(
            tr("Choose output folder"),
            tr("Select a destination for generated analysis files."),
            lambda: self.browse("output"),
        )
        if im.begin_table(
            "bid_queue", 4, im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_X
        ):
            for title in (tr("BID file"), tr("TTTR file"), tr("Output / remove"), tr("Status")):
                im.table_setup_column(title)
            im.table_headers_row()
            remove = None
            for index, row in enumerate(self.rows):
                im.table_next_row()
                for key in ("bid", "tttr", "output"):
                    im.table_next_column()
                    im.text_wrapped(row[key] or (tr("TTTR not found") if key == "tttr" else ""))
                    im.set_item_tooltip(row[key] or tr("Not yet generated."))
                    if key == "output":
                        if im.small_button(tr("Remove") + f"##bid{index}"):
                            remove = index
                        im.set_item_tooltip(tr("Remove this selection from the queue."))
                im.table_next_column()
                im.text_wrapped(row["status"])
            im.end_table()
            if remove is not None:
                self.rows.pop(remove)
        im.end_disabled()
        if action_button(
            "cancel",
            tooltip=tr(
                "Stop before the next file; let the current conversion finish consistently."
            ),
        ):
            self.cancel.set()
        im.same_line()
        if action_button("guide"):
            self.start_guide()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        im.text_wrapped(self.status)
        self.remember("status")

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
            if im.begin(tr("Conversion running")):
                im.text_wrapped(self.status)
                self.button(
                    tr("Cancel after current file"),
                    tr("Preserve completed output and stop the remaining queue."),
                    self.cancel.set,
                )
            im.end()
        if self.dialog is not None:
            if im.begin(tr("Choose conversion paths")):
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
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(width), float(height)))
        if self.tour.active:
            self.tour.draw(float(width), float(height))

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
