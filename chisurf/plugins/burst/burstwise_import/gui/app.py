"""Native EMTK app for importing legacy burstwise folders to PTO containers."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Event
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import (
    action_button,
    action_caption,
    window_size,
)

from .view_model import BurstwiseImportViewModel


class BurstwiseImportApp(ImApp, TourTarget):
    """EMTK application for importing legacy burstwise analysis folders into PTO containers."""

    def __init__(self, model: BurstwiseImportViewModel | None = None) -> None:
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.model = model or BurstwiseImportViewModel()

        spec = {"window": {"width": 1100, "height": 720}}
        self.window_size = window_size(spec, (1100, 720))

        super().__init__(self._draw_ui, continuous=True)

        self.running: bool = False
        self.status: str = tr("Select a legacy burstwise folder to import.")
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burstwise-importer")
        self.future: Future[Any] | None = None
        self.cancel = Event()
        self.dialog = None
        self.dialog_mode = "folder"

        self.docks = DockManager(
            Split("h", 0.50, Region("setup"), Split("v", 0.65, Region("results"), Region("log"))),
            name="burstwise_import",
        )
        self.docks.add_window(
            "setup", tr("Burstwise folder & settings"), self.draw_setup, dock="setup"
        )
        self.docks.add_window(
            "results", tr("Conversion results"), self.draw_results, dock="results"
        )
        self.docks.add_window("log", tr("Import log"), self.draw_log, dock="log")

        gui = Path(__file__).parent
        self.help_window = EmTkHelpWindow(
            title=tr("Burstwise → PTO help"),
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

    def start_guide(self) -> None:
        """Start the interactive guided tour."""
        self.help_window.hide()
        self.tour.start()

    def browse(self, mode: str) -> None:
        """Open a directory browse dialog."""
        from emtk.file_dialog import FileDialog

        self.dialog_mode = mode
        title_map = {
            "folder": tr("Choose Burstwise Folder"),
            "prefix": tr("Choose Local TTTR Root Prefix"),
            "out_dir": tr("Choose Output Directory"),
        }
        self.dialog = FileDialog(
            title_map.get(mode, tr("Choose Folder")),
            mode="folder",
            multiselect=False,
        )

    def scan(self, folder: str | Path | None = None) -> dict | None:
        """Scan target folder and populate detected tables and parameters."""
        try:
            inv = self.model.scan(folder)
            self.status = self.model.status_text
            return inv
        except Exception as exc:
            err = f"Scan failed: {exc}"
            self.model.status_text = err
            self.model.messages.append(err)
            self.status = err
            return None

    def convert(self) -> None:
        """Start conversion in background thread."""
        if self.running or not self.model.inventory:
            return
        self.running = True
        self.model.is_running = True
        self.cancel.clear()
        self.model.status_text = tr("Converting...")
        self.status = self.model.status_text
        self.future = self.executor.submit(self.model.convert)

    def cancel_conversion(self) -> None:
        """Signal cancellation of ongoing conversion."""
        self.cancel.set()
        self.model.messages.append(tr("Conversion cancelled by user."))

    def poll(self) -> None:
        """Check status of asynchronous conversion."""
        if self.future is not None and self.future.done():
            try:
                report = self.future.result()
                self.model.report = report
                self.status = report.summary()
            except Exception as exc:
                err = f"Conversion error: {exc}"
                self.model.status_text = err
                self.model.messages.append(err)
                self.status = err
            finally:
                self.future = None
                self.running = False
                self.model.is_running = False

    def on_paths_dropped(self, paths: list[str | Path]) -> None:
        """Adopt dropped directory path."""
        for p in paths:
            path = Path(p).expanduser().resolve()
            if path.is_dir():
                self.model.folder = str(path)
                self.scan()
                break

    def draw_setup(self, box) -> None:
        """Draw setup pane: folder, scan summary, resolution options, and convert action."""
        pad = 2 * im.get_style().frame_padding[0]
        im.begin_disabled(self.running)

        # Toolbar
        if action_button("guide"):
            self.start_guide()
        self.remember("guide")

        if im.get_line_avail() >= im.calc_text_size(action_caption("help"))[0] + pad:
            im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.remember("help")

        im.separator()

        # Folder selection & scan
        im.text(tr("Burstwise analysis folder:"))
        changed, self.model.folder = im.input_text("##burstwise_folder", self.model.folder)
        im.set_item_tooltip(
            tr("Legacy burstwise directory (containing bi4_bur, bg4, br4, Info, .mti).")
        )
        self.remember("folder_input")

        browse_caption = action_caption("browse")
        browse_w = im.calc_text_size(browse_caption)[0] + pad
        if im.get_line_avail() >= browse_w:
            im.same_line()
        if action_button("browse", tooltip=tr("Select burstwise analysis folder.")):
            self.browse("folder")
        self.remember("browse_folder")

        scan_caption = tr("🔍  Scan")
        scan_w = im.calc_text_size(scan_caption)[0] + pad
        if im.get_line_avail() >= scan_w:
            im.same_line()
        if im.button(scan_caption, role="primary"):
            self.scan()
        im.set_item_tooltip(tr("Scan folder for measurement tables, Info, MTI, and parameters."))
        self.remember("scan_button")

        # Inventory details
        if self.model.inventory is not None:
            inv = self.model.inventory
            stems = list(inv.get("tables", {}).keys())
            roles_count: dict[str, int] = {}
            for r_dict in inv.get("tables", {}).values():
                for r in r_dict:
                    roles_count[r] = roles_count.get(r, 0) + 1
            roles_str = ", ".join(f"{r} ({cnt})" for r, cnt in sorted(roles_count.items()))

            im.begin_child("inventory_frame", (0.0, 130.0))
            im.text_colored(
                tr("✓ Found {n} measurement stems").format(n=len(stems)), (0.3, 0.8, 0.3, 1.0)
            )
            if roles_str:
                im.text_wrapped(tr("Tables: {roles}").format(roles=roles_str))

            params = inv.get("parameters", {})
            if params:
                im.text_wrapped(
                    tr(
                        "Folder parameters: selection={sel}, threshold={th}, min_photons={mp}"
                    ).format(
                        sel=params.get("selection", "-"),
                        th=params.get("threshold", "-"),
                        mp=params.get("min_photons", "-"),
                    )
                )

            info_path = inv.get("info")
            if info_path:
                im.text_wrapped(tr("Info file: {name}").format(name=Path(info_path).name))

            mti_path = inv.get("mti")
            if mti_path:
                im.text_wrapped(
                    tr("MTI file: {name} ({n} entries)").format(
                        name=Path(mti_path).name, n=len(self.model.mti_entries)
                    )
                )
            im.end_child()
        else:
            im.text_disabled(tr("Scan a folder to view detected tables, Info, and parameters."))

        # Source resolution options
        im.separator()
        im.text(tr("Source TTTR Resolution:"))
        self.remember("resolution_mode")

        if im.radio_button(
            tr("Resolve via .mti prefix mapping"), self.model.resolver_mode == "mti"
        ):
            self.model.resolver_mode = "mti"

        if im.get_line_avail() >= im.calc_text_size(tr("Stems beside folder"))[0] + 40.0:
            im.same_line()
        if im.radio_button(tr("Stems beside folder"), self.model.resolver_mode == "beside"):
            self.model.resolver_mode = "beside"

        if self.model.resolver_mode == "mti":
            im.text(tr("Old root prefix in .mti:"))
            changed, self.model.old_prefix = im.input_text("##old_prefix", self.model.old_prefix)
            im.set_item_tooltip(tr("Original prefix recorded in .mti (e.g. N:\\)"))
            self.remember("old_prefix")

            im.text(tr("Local root prefix:"))
            changed, self.model.new_prefix = im.input_text("##new_prefix", self.model.new_prefix)
            im.set_item_tooltip(tr("Local path where raw TTTR files reside"))
            self.remember("new_prefix")

            if im.get_line_avail() >= browse_w:
                im.same_line()
            if action_button(
                "browse", id="browse_prefix", tooltip=tr("Select local root prefix directory.")
            ):
                self.browse("prefix")
        else:
            beside_path = Path(self.model.folder).parent if self.model.folder else Path(".")
            im.text_wrapped(
                tr("Matches <stem>.ht3/.spc/.ptu next to burstwise folder:\n{path}").format(
                    path=str(beside_path)
                )
            )

        # Options
        im.separator()
        changed, self.model.dry_run = im.checkbox(
            tr("Dry run (scan and validate without writing)"), self.model.dry_run
        )
        im.set_item_tooltip(
            tr("Check table mappings and TTTR source resolution without writing .mmfdb.pto.")
        )
        self.remember("dry_run")

        changed, self.model.report_unmapped = im.checkbox(
            tr("Report unmapped columns"), self.model.report_unmapped
        )
        im.set_item_tooltip(tr("Flag legacy columns not matched in the flrCIF dictionary."))
        self.remember("report_unmapped")

        im.text(tr("Output directory (empty: beside folder):"))
        changed, self.model.out_dir = im.input_text("##out_dir", self.model.out_dir)
        im.set_item_tooltip(
            tr("Explicit output directory for .mmfdb.pto containers; empty writes beside folder.")
        )
        if im.get_line_avail() >= browse_w:
            im.same_line()
        if action_button("browse", id="browse_out", tooltip=tr("Select output directory.")):
            self.browse("out_dir")

        # Convert action
        im.separator()
        can_convert = bool(self.model.inventory and not self.running)
        im.begin_disabled(not can_convert)
        if action_button(
            "run",
            id="convert_btn",
            tooltip=tr("Convert legacy burstwise folder to .mmfdb.pto containers."),
            role="primary",
        ):
            self.convert()
        self.remember("convert_button")
        im.end_disabled()

        im.end_disabled()

        if self.running:
            cancel_caption = action_caption("cancel")
            cancel_w = im.calc_text_size(cancel_caption)[0] + pad
            if im.get_line_avail() >= cancel_w:
                im.same_line()
            if action_button("cancel", id="cancel_btn", tooltip=tr("Stop conversion.")):
                self.cancel_conversion()

        im.text_wrapped(self.model.status_text)
        self.remember("status")

    def draw_results(self, box) -> None:
        """Draw results pane: list of written containers and unmapped columns."""
        rep = self.model.report
        self.remember("results_pane")
        if rep is None:
            im.text_disabled(tr("No conversion results yet. Run conversion to inspect output."))
            return

        im.text_colored(
            tr("Containers written: {c} | Measurements: {m}").format(
                c=len(rep.containers), m=len(rep.stems)
            ),
            (0.3, 0.8, 0.3, 1.0) if rep.containers else (0.8, 0.8, 0.3, 1.0),
        )
        im.separator()

        # Written containers
        if rep.containers:
            im.text(tr("Written .mmfdb.pto containers:"))
            if im.begin_table(
                "pto_results_table",
                2,
                im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_Y,
                (0.0, 160.0),
            ):
                im.table_setup_column(tr("Stem"), im.TableColumnFlags.WIDTH_FIXED, 180.0)
                im.table_setup_column(tr("PTO Container"))
                im.table_headers_row()
                for path_str in rep.containers:
                    im.table_next_row()
                    im.table_next_column()
                    stem = Path(path_str).stem.replace(".mmfdb", "")
                    im.text(stem)
                    im.table_next_column()
                    im.text_wrapped(path_str)
                im.end_table()
        else:
            im.text_disabled(tr("No containers written (dry run or missing source TTTRs)."))

        # Unmapped columns
        if self.model.report_unmapped and rep.unmapped_columns:
            im.spacing()
            im.text_colored(
                tr("⚠️ Flagged unmapped columns ({n} stems):").format(n=len(rep.unmapped_columns)),
                (0.9, 0.6, 0.2, 1.0),
            )
            if im.begin_table(
                "unmapped_cols_table",
                2,
                im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_Y,
                (0.0, 140.0),
            ):
                im.table_setup_column(tr("Stem"), im.TableColumnFlags.WIDTH_FIXED, 180.0)
                im.table_setup_column(tr("Unmapped Columns"))
                im.table_headers_row()
                for stem, cols in sorted(rep.unmapped_columns.items()):
                    im.table_next_row()
                    im.table_next_column()
                    im.text(stem)
                    im.table_next_column()
                    im.text_wrapped(", ".join(cols))
                im.end_table()

    def draw_log(self, box) -> None:
        """Draw log pane."""
        if im.button(tr("Clear log")):
            self.model.messages.clear()
        im.set_item_tooltip(tr("Clear all log messages."))
        im.separator()
        for msg in self.model.messages:
            im.text_wrapped(msg)

    def _draw_ui(self) -> None:
        """Master render callback."""
        self.poll()
        width, height = im.get_main_viewport().size
        im.begin_disabled(self.running)
        self.docks.draw((0.0, 0.0, float(width), float(height)))
        im.end_disabled()

        if self.dialog is not None:
            if im.begin(self.dialog.title):
                result = self.dialog.draw()
                if result:
                    if self.dialog_mode == "folder":
                        self.model.folder = str(result[0])
                        self.scan()
                    elif self.dialog_mode == "prefix":
                        self.model.new_prefix = str(result[0])
                    elif self.dialog_mode == "out_dir":
                        self.model.out_dir = str(result[0])
                    self.dialog = None
                elif result is False:
                    self.dialog = None
            im.end()

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(width), float(height)))
        if self.tour.active:
            self.tour.draw(float(width), float(height))

    def export_settings(self) -> dict:
        """Export current settings."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        """Restore settings from dictionary."""
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Cleanly terminate background executor."""
        self.cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)


def create_app(**kwargs) -> BurstwiseImportApp:
    """Build the Burstwise → PTO converter app (manifest entrypoints.emtk)."""
    from chisurf.emtk.i18n import install

    install()
    return BurstwiseImportApp(**kwargs)
