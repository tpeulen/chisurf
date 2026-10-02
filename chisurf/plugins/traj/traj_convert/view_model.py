"""Qt-free view-model backing the MD-Converter (trajectory converter) tool.

:class:`MDConverterViewModel` holds the interactive state (input topology and
trajectory paths, the output directory / base name / extension, the frame
range/stride, and the folder / split toggles) plus a running log, and performs
the actual conversion — either splitting a trajectory into one structure file
per frame, or converting it to a single file. It is deliberately free of Qt so
the logic can be unit-tested headlessly; the GUI (``sections`` + ``widget``) owns
all Qt concerns and drives this model.

Mirrors :class:`chisurf.plugins.traj.traj_save_topology.view_model.SaveTopologyViewModel`.
"""

from __future__ import annotations

import glob
import html
import logging
import os
import pathlib
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "convert_structures.view.json"

#: Output file extensions offered by the converter.
#:
#: Only what can actually be *written*. The list used to also offer ``.xtc`` and
#: ``.h5``: XTC support was dropped entirely on 2026-08-11 (DCD is lossless and
#: enough) and HDF5 trajectories were retired. Offering an unwritable format in a combo box
#: turns a wrong choice into a traceback at save time, after the user has picked
#: a directory and a name.
ENDINGS = (".dcd", ".pdb")


class MDConverterViewModel:
    """State + logic for the MD-Converter tool (no Qt)."""

    def output_formats(self) -> list:
        """Return the formats the Format combo offers.

        A method, not the literal list in the view spec it replaces: that list
        was a second copy of :data:`ENDINGS` and had already drifted from it,
        still offering `.xtc` and `.h5` after both stopped being supported. It
        must stay a *callable* -- AutoForm resolves a model-backed
        ``options_source`` by calling it, and a bare property that raises
        yields an empty combo with only a log line to say so.
        """
        return list(ENDINGS)

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``convert_structures.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self) -> None:
        #: Raw topology path as typed/picked (may not yet be an existing file).
        self.topology_path: str = ""
        #: Input trajectory: a single file, or (when :attr:`use_folder`) a folder of PDBs.
        self.trajectory: str = ""
        #: Output directory the converted file(s) are written to.
        self.target_directory: str = ""
        #: When ``True`` the input is a folder of ``*.pdb`` files instead of one file.
        self.use_folder: bool = False
        #: First frame of the processed range.
        self.first_frame: int = 0
        #: Last frame of the processed range (``-1`` = all frames).
        self.last_frame: int = -1
        #: Read every ``stride``-th frame.
        self.stride: int = 1
        #: Output base name (the extension is appended from :attr:`ending`).
        self.filename: str = "out"
        #: Output file extension (one of :data:`ENDINGS`).
        self.ending: str = ENDINGS[0]
        #: When ``True`` each frame is written to its own file instead of one file.
        self.split: bool = False
        self._log: list[str] = []
        self._observers: list[Callable[[str], None]] = []
        self.append_log("Ready")

    # ── observer plumbing ───────────────────────────────────────────────
    def add_observer(self, callback: Callable[[str], None]) -> None:
        """Register a ``callback(event)`` fired on state changes."""
        self._observers.append(callback)

    def _notify(self, event: str) -> None:
        for callback in list(self._observers):
            try:
                callback(event)
            except Exception:  # pragma: no cover - observers are best-effort
                logger.warning("MDConverter observer failed", exc_info=True)

    # ── log ─────────────────────────────────────────────────────────────
    def append_log(self, message: str) -> None:
        """Append a timestamped line to the log and notify observers."""
        timestamp = time.strftime("%H:%M:%S")
        self._log.append(f"[{timestamp}] {message}")
        self._notify("log")

    def log_html(self) -> str:
        """Render the log as a monospace HTML block (bound by the ``info`` section)."""
        lines = "<br>".join(html.escape(line) for line in self._log)
        return f"<pre style='margin:0;font-family:monospace'>{lines}</pre>"

    def log_text(self) -> list[str]:
        """Return the raw log lines (bound by the native app; no HTML)."""
        return list(self._log)

    # ── file wiring ─────────────────────────────────────────────────────
    @property
    def topology_file(self) -> str | None:
        """The topology path if it points at an existing file, else ``None``.

        Matches the legacy widget semantics: a trajectory format that carries no
        topology needs this file, and only a real file is a usable topology.
        """
        if os.path.isfile(self.topology_path):
            return self.topology_path
        return None

    @topology_file.setter
    def topology_file(self, value: str) -> None:
        """Set the raw topology path (fires observers)."""
        self.set_topology(value)

    def set_topology(self, path: str) -> None:
        """Set the topology path, log it and notify observers."""
        self.topology_path = str(path)
        self.append_log(f"Topology: {self.topology_path}")
        self._notify("topology")

    def set_trajectory(self, path: str) -> None:
        """Set the input trajectory (file or folder), log it and notify observers."""
        self.trajectory = str(path)
        self.append_log(f"Trajectory: {self.trajectory}")
        self._notify("trajectory")

    def set_target_directory(self, path: str) -> None:
        """Set the output directory, log it and notify observers."""
        self.target_directory = str(path)
        self.append_log(f"Target folder: {self.target_directory}")
        self._notify("target")

    # ── action ──────────────────────────────────────────────────────────
    def frame_selection(self, n_frames: int) -> range:
        """The frames to write: :attr:`first_frame` to :attr:`last_frame` *inclusive*, every :attr:`stride`-th.

        ``last_frame = -1`` means the last frame. The range used to be built as
        ``slice(first, last, stride)``, which left the last frame out -- and with
        ``-1`` dropped the trajectory's final frame.
        """
        last = n_frames - 1 if self.last_frame < 0 else min(int(self.last_frame), n_frames - 1)
        return range(max(0, int(self.first_frame)), last + 1, max(1, int(self.stride)))

    def input_files(self) -> list[str]:
        """The files to read: the trajectory, or (folder mode) every ``*.pdb`` in it, in name order."""
        if not self.use_folder:
            return [self.trajectory]
        files = sorted(glob.glob(os.path.join(self.trajectory, "*.pdb")))
        if not files:
            raise ValueError(f"No *.pdb files in {self.trajectory}")
        return files

    def convert(self) -> None:
        """Convert the input using the current settings.

        The input -- one trajectory, or every PDB of a folder joined in name
        order as consecutive frames -- is read, the frames of
        :meth:`frame_selection` are taken, and written either as one
        ``{filename}{ending}`` file or, with :attr:`split`, one
        ``{filename}_{frame:08d}{ending}`` file per frame (numbered by the source
        frame) in :attr:`target_directory`.

        The selection used to apply only to the single-file path: split mode
        ignored the stride and crashed on a frame range, and folder mode built
        the list of PDBs and then read the folder path itself.
        """
        from chisurf.core.structure import trajectory_data as md

        if not self.target_directory or not os.path.isdir(self.target_directory):
            raise ValueError("Choose an existing target folder first.")
        self.append_log("Starting trajectory conversion")
        inputs = self.input_files()
        parts = [md.load(path, top=self.topology_file) for path in inputs]
        whole = parts[0] if len(parts) == 1 else md.join(parts)
        if len(inputs) > 1:
            self.append_log(f"Read {len(inputs)} files as {whole.n_frames} frames")
        frames = list(self.frame_selection(whole.n_frames))
        self.append_log(f"Input frames: {self.first_frame}..{self.last_frame} stride={self.stride} "
                        f"({len(frames)} of {whole.n_frames})")
        if not frames:
            raise ValueError("The frame range selects no frames.")
        selected = whole[frames]
        if self.split:
            for frame, single in zip(frames, (selected[i] for i in range(len(frames)))):
                fn = os.path.join(self.target_directory, f"{self.filename}_{frame:08d}{self.ending}")
                single.save(fn)
            self.append_log(f"Wrote {len(frames)} files of {whole.n_atoms} atoms: "
                            f"{self.filename}_{frames[0]:08d}{self.ending} … {self.filename}_{frames[-1]:08d}{self.ending}")
        else:
            output = os.path.join(self.target_directory, self.filename + self.ending)
            self.append_log(f"Output: {output}")
            selected.save(output)
            # Say what was written: "Conversion done" over a zero-frame output
            # reads exactly like a good run.
            self.append_log(f"Wrote {selected.n_frames} frames of {selected.n_atoms} atoms")
        self.append_log("Conversion done")


__all__ = ["MDConverterViewModel", "ENDINGS"]
