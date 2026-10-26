"""Native BID conversion queue using the original scientific/provenance routines."""

import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr
from emtk.view_form import draw_form

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
        self.status = tr(
            "Pick photon streams in the Input section (their burst-ID selections are found "
            "beside them), or press Load example."
        )
        #: The one output: the measurement container (kept as state for settings parity).
        self.output_types = {"pto"}
        self.unique_folder = False
        self.zip_output = False
        self.target_path = "analysis"
        self.analysis_folder = ""
        self.setup = ChannelDefinitionWidget(model=setup_model, host_app=self)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bid-converter")
        self.future = None
        self.cancel = Event()
        # The Input section: the workspace's photon streams (manifest ``accepts`` ``photons``).
        from emtk.view_form import FormState

        from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput, input_spec

        self.input = NamedWorkspaceInput("bid_to_analysis", "photons", app=self)
        self.input.workspace_input_on_used = lambda name: self.tour.notify_used(name)
        self.input_spec = input_spec(
            Path(__file__).resolve().parents[1] / "manifest.json", "photons"
        )
        self.input_form = FormState()
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
        from chisurf.core.plugin.workspace_input import register_result

        from .. import _find_tttr_by_stem
        from ..demo import make_demo

        bid = Path(make_demo())
        tttr = _find_tttr_by_stem(bid.parent, bid.stem)
        if tttr is None:
            self.add_files([bid])
        else:  # the demo enters the workspace like any measurement, then comes in from there
            stream = register_result(str(tttr), kind="photons", name=tttr.name)
            self.take_photons([str(tttr)], [stream.unique_identifier])
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

    def take_photons(self, paths, uids=()):
        """Queue the burst-ID selection beside each photon stream of the workspace; its import is
        written into that stream's analysis container in the project."""
        from .. import find_bid_for

        if self.running:
            return 0
        existing = {row["tttr"] for row in self.rows}
        uids = list(uids) + [""] * (len(paths) - len(uids))
        added = 0
        for value, uid in zip(paths, uids):
            tttr = Path(str(value))
            if str(tttr) in existing:
                continue
            bid = find_bid_for(tttr)
            self.rows.append(
                dict(
                    bid=str(bid) if bid else "",
                    tttr=str(tttr),
                    uid=str(uid or ""),
                    output="",
                    status="Ready" if bid else "No BID selection beside it",
                )
            )
            existing.add(str(tttr))
            added += 1
        self.status = tr("{n} BID file(s) queued.").format(n=len(self.rows))
        return added

    def clear(self):
        if not self.running:
            self.rows.clear()
            self.messages.clear()
            self.status = tr("Queue cleared.")

    def process(self):
        if self.running or not self.rows:
            return
        self.running = True
        self.cancel.clear()
        settings = copy.deepcopy(self.setup.model.get_settings())
        options = dict(
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
                if not row["bid"]:
                    raise FileNotFoundError("No burst-ID selection beside the measurement")
                from chisurf.core.fio.fluorescence.burst_container import container_for
                from chisurf.core.project.analysis import container_dir

                # A workspace stream's import goes into its analysis container in the project.
                into = container_dir(row["uid"]) if row.get("uid") else None
                output = convert_bid_file(
                    row["bid"],
                    analysis_folder=folder if into is None else into / "analysis",
                    bid_index=index,
                    container_dir=into,
                    **options,
                )
                # The container is the one output: prove it holds what the
                # import promised before the row is called Done.
                from chisurf.core.datastore import row_count
                from chisurf.core.fio.pto import Measurement

                row["container"] = str(container_for(row["tttr"], into))
                with Measurement.open(row["container"]) as measurement:
                    if not row_count(measurement.get_store("bursts")):
                        raise RuntimeError("PTO output contains no burst table")
                    if measurement.get_blob(Path(row["bid"]).name) != Path(row["bid"]).read_bytes():
                        raise RuntimeError("PTO output does not contain the original BID selection")
                row["output"] = str(output)
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
                self._register_runs()
                count = sum(row["status"] == "Done" for row in self.rows)
                self.status = tr("Finished: {done}/{total} files converted.").format(
                    done=count, total=len(self.rows)
                )
            except Exception as error:
                self.status = f"Error: {error}"
            self.messages.append(self.status)
            self.future = None
            self.running = False

    def _register_runs(self):
        """Show each imported selection in the workspace: the bursts of the container written for
        a workspace stream become a child row of that stream."""
        from chisurf.core.fio.classify import container_entries
        from chisurf.core.plugin.workspace_input import register_result

        for row in self.rows:
            if row["status"] != "Done" or not row.get("uid") or not row.get("container"):
                continue
            try:
                runs = [a for kind, a in container_entries(row["container"]) if kind == "bursts"]
                if not runs:
                    # The import's table is not a burst-search run, which is all the container
                    # listing knows (chisurf.core.fio.classify.container_entries): name it.
                    from chisurf.core.fio.address import join_address

                    runs = [join_address(row["container"], "bursts")]
                for address in runs:
                    register_result(address, kind="bursts", result_of=row["uid"])
            except Exception as error:  # noqa: BLE001 - the import itself succeeded
                self.messages.append(f"{row['tttr']}: not shown in the workspace: {error}")

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
        self.input_form.rects.clear()
        draw_form(self.input_spec, self.input, self.input_form)
        self.item_rects.update(self.input_form.rects)
        for label, tip, action, key in [
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
        im.text_wrapped(
            tr(
                "Output: the measurement's container in the project -- the original BID "
                "and its burst table, with provenance; it appears under its photon stream "
                "in the Datasets workspace. Legacy formats are exported from it by the "
                "legacy export plugin."
            )
        )
        self.remember("formats")
        im.separator()
        changed, self.unique_folder = im.checkbox(tr("Unique output folder"), self.unique_folder)
        im.set_item_tooltip(
            tr("Add a numeric suffix instead of reusing an existing output folder.")
        )
        changed, self.zip_output = im.checkbox(tr("ZIP output"), self.zip_output)
        im.set_item_tooltip(tr("Archive generated analysis files while keeping the output folder."))
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
        # The container is the only output; older saved legacy formats are dropped.
        self.output_types = {"pto"}
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


def receive_photons(app: BidToAnalysisApp, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``photons``): queue the burst-ID selections beside
    the photon streams ``payload["files"]`` of the Datasets workspace."""
    from chisurf.core.plugin.workspace_input import read_address

    files = payload.get("files") or []
    files = files if isinstance(files, list) else [files]
    paths = [read_address(str(f)) for f in files]
    if not app.take_photons(paths, list(payload.get("datasets") or [])) and not set(paths) & {
        row["tttr"] for row in app.rows
    }:
        raise ValueError("nothing new to queue")
