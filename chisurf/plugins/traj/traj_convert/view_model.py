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
#: enough) and HDF5 trajectories were retired with
#: :doc:`PRD-80 </prds/prd-80>`. Offering an unwritable format in a combo box
#: turns a wrong choice into a traceback at save time, after the user has picked
#: a directory and a name.
ENDINGS = (".dcd", ".pdb")


class Object:
    """Plain argument holder for the conversion parameters.

    The conversion parameters were assembled for an external converter that took
    an ``argparse``-style namespace. The shell-out is gone -- it was this same
    read/write loop with an ``argv`` in the middle -- but the holder is kept as
    the one place the parameters are gathered and validated before the loop runs.
    """

    pass


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
    def convert(self) -> None:
        """Convert the input trajectory using the current settings.

        When :attr:`split` is set, every frame is iterated and written to its own
        ``{filename}_%08d{ending}`` file in :attr:`target_directory`; otherwise the
        whole trajectory is read and written as a single ``{filename}{ending}``
        file. A non-default :attr:`first_frame` /
        :attr:`last_frame` range switches the reader from chunked/strided reads to
        an index slice, mirroring the legacy tool.
        """
        from chisurf.core.structure import trajectory_data as md

        self.append_log("Starting trajectory conversion")
        args = Object()
        args.topology = self.topology_file
        args.input = (
            [self.trajectory]
            if not self.use_folder
            else glob.glob(os.path.join(self.trajectory, "*.pdb"))
        )
        args.index = None
        args.chunk = 1000
        args.stride = self.stride

        if self.first_frame != 0 or self.last_frame != -1:
            args.index = slice(self.first_frame, self.last_frame, self.stride)
            args.stride = None
            args.chunk = None

        args.force = True
        args.atom_indices = None
        self.append_log(f"Input frames: {self.first_frame}:{self.last_frame} stride={self.stride}")

        if self.split:
            i = 0
            for chunk in md.iterload(self.trajectory, chunk=args.chunk, top=self.topology_file):
                for s in chunk:
                    try:
                        fn = os.path.join(
                            self.target_directory,
                            self.filename + f"_{i:08d}" + self.ending,
                        )
                        self.append_log(f"Saving frame {i}: {fn}")
                        s.save(fn)
                    except Exception as exc:  # noqa: BLE001
                        self.append_log(f"Frame {i} failed: {exc}")
                    i += 1
        else:
            args.output = os.path.join(self.target_directory, self.filename + self.ending)
            self.append_log(f"Output: {args.output}")
            # One file: read the whole trajectory and write it out. This used
            # to shell out to an external converter, which is the same loop
            # with an argv in the middle.
            whole = md.load(self.trajectory, top=self.topology_file or None, stride=args.stride)
            if args.index is not None:
                whole = whole[args.index]
            whole.save(args.output)
            # Say what was written. "Conversion done" over a zero-frame output
            # reads exactly like a good run -- and a stride or an index that
            # selects nothing is the easy way to get one.
            self.append_log(f"Wrote {whole.n_frames} frames of {whole.n_atoms} atoms")
        self.append_log("Conversion done")


__all__ = ["MDConverterViewModel", "Object", "ENDINGS"]
