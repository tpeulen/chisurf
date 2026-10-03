"""HydroPro without Qt: the parameters, the run, the results table and the output log.

This is the Qt tool's ``_HydroModel`` (the attributes the AutoForm reads and writes, ``indmode`` held as a string for
the combo) joined with everything ``HydroProTool`` and its two dialogs did around it: the run on a worker thread, the
output log and progress, the results table, the CSV export, the "executable required" prompt and the warnings. The
calculation itself is :func:`..core.run_hydro`, exactly as the Qt tool, the CLI and the RPC service drive it.

A window drawing this model asks the user for files, so the three actions that need a dialog (``select_files``,
``select_exe``, ``save_csv``/``save_log``) set :attr:`HydroProModel.dialog` and the window opens it; the model never
draws. :meth:`HydroProModel.poll` drains what the worker thread reported and is called once per frame.
"""

from __future__ import annotations

import csv
import queue
import threading
from pathlib import Path

from ..core import HydroProSettings, HydroResult, run_hydro

DOWNLOAD_URL = "https://leonardo.inf.um.es/macromol/programs/hydro%2B%2B/hydro%2B%2B.htm"
#: The Qt dialogs' file filters, verbatim.
STRUCT_FILTER = "Structural files (*.pdb *.txt *.bea *.*)"
EXE_FILTER = "Executables (*.exe);;All files (*.*)"
CSV_FILTER = "CSV files (*.csv)"
LOG_FILTER = "Text files (*.txt)"
CSV_HEADER = ["File", "DiffusionCoefficient(cm^2/s)"]


def format_diffusion(value: float | None) -> str:
    """The results-table cell (and CSV cell) of a diffusion coefficient: ``1.047e-06``; ``N/A`` in the table when missing."""
    return f"{value:.3e}" if value is not None else "N/A"


class HydroProModel:
    """The HydroPro window's state and actions."""

    def __init__(self, work_dir: Path | None = None) -> None:
        self.work_dir = work_dir  # run_hydro's default (~/.hydropp_gui) when None
        self.exe_path = ""
        self.struct_files = ""
        # primary model
        self.indmode = "1"
        self.aer = 2.9
        self.nsig = 6
        self.sigmin = 1.0
        self.sigmax = 2.0
        # solvent & macromolecule
        self.t = 20.0
        self.eta = 0.01
        self.rm = 100000.0
        self.vbar = 0.74
        self.rho = 1.0
        # optional calculations
        self.nq = -1
        self.qmax = 0.0
        self.ns = -1
        self.rmax = 0.0
        self.ntrials = 0
        self.idif = True
        # results
        self.status = ""
        self.results: list[HydroResult] = []
        self.cells: dict[str, str] = {}
        # output log
        self.log_lines: list[str] = []
        self.output_status = "Ready"
        self.total = 0
        self.done = 0
        self.cancelling = False
        # worker
        self.running = False
        self._cancel = False
        self._events: queue.SimpleQueue = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._pending: tuple | None = None
        # what the window must show next
        self.dialog: str | None = None  # "files", "exe", "prompt_exe", "csv", "log"
        self.notices: list[tuple[str, str]] = []
        self.exe_prompt = False
        self.prompt_path: Path | None = None
        self.opened_urls: list[str] = []
        self.open_url = None  # set by the window: callable(url)

    # -- conversions (the Qt model's) ------------------------------------------------------------------------ #
    def struct_list(self) -> list[Path]:
        return [Path(p.strip()) for p in self.struct_files.split(",") if p.strip()]

    def to_settings(self) -> HydroProSettings:
        return HydroProSettings(
            indmode=int(float(self.indmode)),
            aer=float(self.aer),
            nsig=int(self.nsig),
            sigmin=float(self.sigmin),
            sigmax=float(self.sigmax),
            t=float(self.t),
            eta=float(self.eta),
            rm=float(self.rm),
            vbar=float(self.vbar),
            rho=float(self.rho),
            nq=int(self.nq),
            qmax=float(self.qmax),
            ns=int(self.ns),
            rmax=float(self.rmax),
            ntrials=int(self.ntrials),
            idif=1 if self.idif else 0,
        )

    def load_settings(self, s: HydroProSettings) -> None:
        self.indmode = str(s.indmode)
        self.aer, self.nsig = s.aer, s.nsig
        self.sigmin, self.sigmax = s.sigmin, s.sigmax
        self.t, self.eta, self.rm = s.t, s.eta, s.rm
        self.vbar, self.rho = s.vbar, s.rho
        self.nq, self.qmax = s.nq, s.qmax
        self.ns, self.rmax = s.ns, s.rmax
        self.ntrials = s.ntrials
        self.idif = bool(s.idif)

    # -- what the window may do now ----------------------------------------------------------------------------- #
    def enabled(self, name: str) -> bool:
        if name == "run":
            return not self.running
        if name == "save_csv":
            return bool(self.results)
        if name == "cancel":
            return self.running and not self.cancelling
        if name in ("clear_log", "save_log"):
            return bool(self.log_lines)
        return True

    # -- the results table ----------------------------------------------------------------------------------------- #
    def result_rows(self) -> list[dict]:
        """One record per listed structure: its path and, after a run, its diffusion coefficient (cm²/s)."""
        rows = []
        for path in self.struct_list():
            key = str(path)
            rows.append({"key": key, "file": key, "d": self.cells.get(key, ""), "tip": key})
        return rows

    # -- output pane ------------------------------------------------------------------------------------------------- #
    @property
    def log_text(self) -> str:
        """What the Qt output dialog's ``toPlainText()`` returned: one paragraph per appended message."""
        return "\n".join(self.log_lines)

    @property
    def progress_fraction(self) -> float:
        return (self.done / self.total) if self.total else 0.0

    def progress_text(self) -> str:
        return f"{int(round(100 * self.progress_fraction))}%"

    def output_text(self) -> str:
        return self.output_status

    # -- file actions (the window opens the dialog) -------------------------------------------------------------------- #
    def select_files(self) -> None:
        self.dialog = "files"

    def select_exe(self) -> None:
        self.dialog = "exe"

    def files_chosen(self, paths) -> None:
        """Qt ``_select_files`` after the dialog: the list replaces the field and the table shows the files, empty."""
        paths = [str(p) for p in paths]
        if paths:
            self.struct_files = ", ".join(paths)
            self.cells = {}

    def exe_chosen(self, path) -> None:
        if path:
            self.exe_path = str(path)

    def download_page(self) -> None:
        self.opened_urls.append(DOWNLOAD_URL)
        if callable(self.open_url):
            self.open_url(DOWNLOAD_URL)

    def clear(self) -> None:
        """Qt ``_clear``: the file list, the status, the results and the table."""
        self.struct_files = ""
        self.status = ""
        self.results = []
        self.cells = {}

    # -- notices ---------------------------------------------------------------------------------------------------------- #
    def notify(self, title: str, text: str) -> None:
        self.notices.append((title, text))

    # -- run -------------------------------------------------------------------------------------------------------------- #
    def run(self) -> None:
        """Qt ``_on_run``: validate, make sure there is an executable (prompt), then start the worker."""
        if self.running:
            return
        files = self.struct_list()
        if not files:
            self.notify("No files", "Please select one or more files first.")
            return
        try:
            settings = self.to_settings()
            settings.validate()
        except ValueError as exc:
            self.notify("Invalid settings", str(exc))
            return
        exe = Path(self.exe_path) if self.exe_path else None
        if exe and exe.exists():
            self._begin(files, settings, exe)
            return
        self._pending = (files, settings)
        self.prompt_path = None
        self.exe_prompt = True

    def prompt_exe_chosen(self, path) -> None:
        """The prompt's "Select executable…" answer (Qt ``DownloadInfoDialog._select_exe``)."""
        if path:
            self.prompt_path = Path(path)

    def close_exe_prompt(self) -> None:
        """The prompt's Close: continue with the executable it was given, or say one is required."""
        self.exe_prompt = False
        pending, self._pending = self._pending, None
        chosen = self.prompt_path
        self.prompt_path = None
        if pending and chosen and chosen.exists():
            self.exe_path = str(chosen)
            self._begin(pending[0], pending[1], chosen)
        else:
            self.notify("Executable required", "Configure the HYDRO executable before running.")

    def _begin(self, files, settings, exe: Path) -> None:
        total = len(files)
        self.total, self.done, self.cancelling, self._cancel = total, 0, False, False
        self.log_lines = []
        self.output_status = f"Starting HYDRO for {total} file(s)…"
        self.log_lines.append(f"Executable: {exe}")
        self.running = True
        self._thread = threading.Thread(target=self._work, args=(files, settings, exe), daemon=True)
        self._thread.start()

    def _work(self, files, settings, exe) -> None:
        put = self._events.put
        try:
            results = run_hydro(
                files, settings, exe, self.work_dir,
                on_log=lambda m: put(("log", m)),
                on_progress=lambda i, n: put(("progress", i, n)),
                should_cancel=lambda: self._cancel,
            )
            put(("finished", results))
        except Exception as exc:  # surfaced to the window, as the Qt worker did
            put(("failed", str(exc)))

    def cancel(self) -> None:
        """The output pane's Cancel: the current job finishes, then the run ends."""
        if not self.running or self.cancelling:
            return
        self._cancel = True
        self.cancelling = True
        self.output_status = "Cancelling after current job finishes…"

    def poll(self) -> bool:
        """Apply what the worker reported since the last frame; True when something changed."""
        changed = False
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                return changed
            changed = True
            kind = event[0]
            if kind == "log":
                self.log_lines.append(event[1])
            elif kind == "progress":
                self.done = event[1]
            elif kind == "finished":
                self.results = list(event[1])
                self.status = f"Finished: {len(self.results)} file(s)."
                self.output_status = "Finished."
                by_file = {r.struct_file: r.diffusion_coefficient for r in self.results}
                self.cells = {str(p): format_diffusion(by_file[str(p)]) for p in self.struct_list() if str(p) in by_file}
                self._end()
            elif kind == "failed":
                self.status = f"Error: {event[1]}"
                self.log_lines.append(f"\nERROR: {event[1]}")
                self.output_status = "Failed."
                self._end()

    def _end(self) -> None:
        self.running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def wait(self, timeout: float = 60.0) -> bool:
        """Block until the worker is done and its events applied (tests and scripts)."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self.poll()
        return not self.running

    # -- files written ---------------------------------------------------------------------------------------------------- #
    def csv_name(self) -> str:
        return "hydro_results.csv"

    def log_name(self) -> str:
        return "hydro_output.txt"

    def save_csv(self) -> None:
        if not self.results:
            self.notify("No results", "There are no results to save.")
            return
        self.dialog = "csv"

    def save_log(self) -> None:
        self.dialog = "log"

    def write_csv(self, path) -> bool:
        """Qt ``_save_csv`` after the dialog: the same rows, the same message."""
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(CSV_HEADER)
                for r in self.results:
                    writer.writerow([r.struct_file, f"{r.diffusion_coefficient:.3e}"
                                     if r.diffusion_coefficient is not None else ""])
            self.notify("Saved", f"Results saved to {path}")
            return True
        except OSError as exc:
            self.notify("Error", f"Failed to save CSV: {exc}")
            return False

    def write_log(self, path) -> bool:
        """Qt ``OutputDialog._save_log``: the log as plain text; a failure is silent there, a notice here."""
        try:
            Path(path).write_text(self.log_text, encoding="utf-8")
            return True
        except OSError as exc:
            self.notify("Error", f"Failed to save the log: {exc}")
            return False

    def clear_log(self) -> None:
        self.log_lines = []

    # -- persistence (the Qt tool's QSettings: the executable and the parameters) ---------------------------------------- #
    def export_settings(self) -> dict:
        return {"exe_path": self.exe_path, **self.to_settings().to_dict(), "indmode": self.indmode}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; invalid values are ignored field by field (Qt: ``from_dict``)."""
        if isinstance(settings.get("exe_path"), str):
            self.exe_path = settings["exe_path"]
        stored = {k: v for k, v in settings.items() if k in HydroProSettings().to_dict()}
        if stored:
            self.load_settings(HydroProSettings.from_dict({**HydroProSettings().to_dict(), **self.to_settings().to_dict(), **stored}))

    def close(self) -> None:
        self._cancel = True
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
