from qtpy import QtCore, QtWidgets

try:
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizard, DetectorWizardPage
except ImportError:
    DetectorWizard = DetectorWizardPage = None
import pathlib

from .. import *
from .. import _find_tttr_by_stem

# --- Simple GUI with drag-and-drop list ---
if QtWidgets is not None:

    class BidToAnalysisGUI(QtWidgets.QDialog):
        BID_EXTS = {".bid", ".bst", ".txt"}

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setWindowTitle("BID  Analysis Converter")
            self.resize(900, 520)
            self.setAcceptDrops(True)
            self._setup_ui()

        def _setup_ui(self):
            layout = QtWidgets.QVBoxLayout(self)

            # Tabbed interface: Setup and Files
            self.tabs = QtWidgets.QTabWidget(self)
            layout.addWidget(self.tabs)

            # Setup tab
            setup_widget = QtWidgets.QWidget(self)
            setup_layout = QtWidgets.QVBoxLayout(setup_widget)
            if DetectorWizardPage is not None:
                try:
                    self.detector_page = DetectorWizardPage(
                        show_help=False,
                        show_setups_file=True,
                        show_setup_selection=True,
                        show_tttr_reading=True,
                        show_tables=True,
                        show_add_inputs=True,
                    )
                except Exception:
                    self.detector_page = None
            else:
                self.detector_page = None
            if self.detector_page is not None:
                setup_layout.addWidget(self.detector_page)
            else:
                lbl = QtWidgets.QLabel(
                    "Detector setup UI not available. Default auto-detectors will be used.",
                    setup_widget,
                )
                lbl.setWordWrap(True)
                setup_layout.addWidget(lbl)
            self.tabs.addTab(setup_widget, "Setup")

            # Files tab (existing UI)
            files_widget = QtWidgets.QWidget(self)
            files_layout = QtWidgets.QVBoxLayout(files_widget)

            self.table = QtWidgets.QTableWidget(0, 4, files_widget)
            self.table.setHorizontalHeaderLabels(
                ["BID file", "TTTR file", "Output folder", "Status"]
            )
            self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            try:
                self.table.horizontalHeader().setStretchLastSection(True)
            except Exception:
                pass
            files_layout.addWidget(self.table)

            btns = QtWidgets.QHBoxLayout()
            self.btnAdd = QtWidgets.QPushButton("Add Files", files_widget)
            self.btnClear = QtWidgets.QPushButton("Clear", files_widget)
            self.btnProcess = QtWidgets.QPushButton("Process", files_widget)
            btns.addWidget(self.btnAdd)
            btns.addStretch(1)
            btns.addWidget(self.btnClear)
            btns.addWidget(self.btnProcess)
            files_layout.addLayout(btns)

            self.log = QtWidgets.QTextEdit(files_widget)
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Logs will appear here")
            files_layout.addWidget(self.log)

            self.tabs.addTab(files_widget, "Files")

            # Connect buttons
            self.btnAdd.clicked.connect(self.on_add_files)
            self.btnClear.clicked.connect(self.on_clear)
            self.btnProcess.clicked.connect(self.process_all)

        # --- Drag & Drop ---
        def dragEnterEvent(self, e):
            if getattr(QtCore, "Qt", None) is None:
                e.ignore()
                return
            if e.mimeData().hasUrls():
                for url in e.mimeData().urls():
                    p = pathlib.Path(url.toLocalFile())
                    if p.suffix.lower() in self.BID_EXTS:
                        e.acceptProposedAction()
                        return
            e.ignore()

        def dropEvent(self, e):
            paths = []
            for url in e.mimeData().urls():
                p = pathlib.Path(url.toLocalFile())
                if p.suffix.lower() in self.BID_EXTS and p.exists():
                    paths.append(p)
            if paths:
                self.add_files(paths)

        # --- UI actions ---
        def on_add_files(self):
            dlg = QtWidgets.QFileDialog(self, "Select BID files")
            dlg.setFileMode(QtWidgets.QFileDialog.ExistingFiles)
            dlg.setNameFilters(["BID files (*.bid *.bst *.txt)", "All files (*.*)"])
            if dlg.exec_() == QtWidgets.QDialog.Accepted:
                paths = [pathlib.Path(p) for p in dlg.selectedFiles()]
                self.add_files(paths)

        def on_clear(self):
            self.table.setRowCount(0)
            self.log.clear()

        def add_files(self, paths: list[pathlib.Path]):
            for p in paths:
                if p.suffix.lower() not in self.BID_EXTS:
                    continue
                self._add_row(p)

        def _add_row(self, bid: pathlib.Path):
            # prevent duplicates
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 0)
                if item and item.data(QtCore.Qt.UserRole) == str(bid):
                    return
            row = self.table.rowCount()
            self.table.insertRow(row)
            bid_item = QtWidgets.QTableWidgetItem(str(bid))
            bid_item.setData(QtCore.Qt.UserRole, str(bid))
            self.table.setItem(row, 0, bid_item)
            tttr = _find_tttr_by_stem(bid.parent, bid.stem)
            tttr_text = str(tttr) if tttr else "TTTR not found"
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(tttr_text))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(""))
            self._set_status(row, "Ready" if tttr else "Missing TTTR", error=(tttr is None))

        def _set_status(self, row: int, text: str, error: bool = False):
            it = self.table.item(row, 3)
            if it is None:
                it = QtWidgets.QTableWidgetItem("")
                self.table.setItem(row, 3, it)
            it.setText(text)

        def log_info(self, msg: str):
            try:
                logging.info(msg)
            except Exception:
                pass
            self.log.append(msg)
            self.log.ensureCursorVisible()

        def process_all(self):
            n = self.table.rowCount()
            if n == 0:
                return

            # Read detector/windows from setup page if available
            setup_windows = None
            setup_detectors = None
            setup_name = None
            if getattr(self, "detector_page", None) is not None:
                try:
                    settings = self.detector_page.get_settings()
                    setup_windows = settings.get("windows") or None
                    setup_detectors = settings.get("detectors") or None
                    setup_name = getattr(self.detector_page, "current_setup_name", None)
                except Exception:
                    setup_windows = None
                    setup_detectors = None
                    setup_name = None

            ok = 0
            for row in range(n):
                bid_item = self.table.item(row, 0)
                tttr_item = self.table.item(row, 1)
                if not bid_item:
                    continue
                bid = pathlib.Path(bid_item.data(QtCore.Qt.UserRole))
                tttr_path = (
                    pathlib.Path(tttr_item.text())
                    if tttr_item and tttr_item.text() and tttr_item.text() != "TTTR not found"
                    else None
                )
                if tttr_path is None or not tttr_path.exists():
                    self._set_status(row, "TTTR not found", error=True)
                    continue
                self._set_status(row, "Processing", error=False)
                QtWidgets.QApplication.processEvents()
                # try:
                bur_path = convert_bid_file(
                    bid,
                    windows=setup_windows,
                    detectors=setup_detectors,
                    selected_setup=setup_name,
                    bid_index=row + 1,
                )
                output_folder = None
                if isinstance(bur_path, pathlib.Path):
                    if bur_path.suffix.lower() == ".bur":
                        output_folder = bur_path.parent.parent
                    else:
                        output_folder = bur_path
                if output_folder:
                    self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(str(output_folder)))
                self._set_status(row, "Done", error=False)
                self.log_info(f"Processed {bid.name} -> {tttr_path.name}")
                ok += 1
            # except Exception as exc:
            #     self._set_status(row, f"Error: {exc}", error=True)
            #     self.log_info(f"Error processing {bid.name}: {exc}")
            self.log_info(f"Finished: {ok}/{n} files processed.")
