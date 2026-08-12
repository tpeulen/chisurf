"""The application around the viewer, with no toolkit in it.

What a host actually is
-----------------------
``Cmd`` drives a *viewer* -- sixty-seven of :class:`~chimol.renderer.view.MolView`'s
methods -- and reaches past it to the surrounding application for a short,
countable list: loading a file, refreshing the object list, going full screen,
closing. On the desktop that application was ``MolViewPluginWindow``, a
``QMainWindow`` of some four thousand lines, so "run chimol" meant "start Qt".

:class:`ViewerHost` is that role and nothing else. It is what the browser page
already ran under another name, and what the Qt-free desktop window runs now, so
there is one answer to "what does ``load`` do?" rather than one per host.

It is deliberately **not** a stand-in that swallows everything. An earlier
version answered every attribute with a no-op, and ``load`` then reported
success while registering nothing -- the command delegates the actual read to
the host, and a host that silently accepts it produces a viewer with no objects
and no error.
"""
from __future__ import annotations

import contextlib
import logging
import time
import pathlib
from collections.abc import Callable

__all__ = ["ViewerHost", "sync_panel"]


logger = logging.getLogger(__name__)


#: Shortest gap between progress repaints, in seconds. A bar that updates
#: fifteen times a second reads as continuous; one that updates per record
#: spends the load drawing itself.
_PROGRESS_REDRAW_INTERVAL = 1.0 / 15.0


class ViewerHost:
    """The application the command layer reaches past the viewer for.

    Parameters
    ----------
    viewer : chimol.renderer.view.MolView
        The viewer this host owns.
    """

    def __init__(self, viewer) -> None:
        self.viewer = viewer
        #: Called after anything that changes the object list, so the host can
        #: re-read it into the in-viewport panel.
        self.on_objects_changed: Callable[[], None] | None = None
        #: The command layer, set by whoever builds it. Scripts and demos are
        #: replayed through this, so they take exactly the route a typed line
        #: takes -- which is what keeps a demo an honest demonstration.
        self.cmd = None
        #: Where a demo's failure is reported. The Qt window raises a dialog;
        #: a toolkit-free host has the command line's error channel instead.
        self.on_error: Callable[[str], None] | None = None

    # -- what the commands actually call -------------------------------------

    @contextlib.contextmanager
    def _reporting(self, title: str, *, cancellable: bool = False):
        """Show the modal progress overlay for the duration of a block.

        Yields a ``report(fraction, message)`` callable. The overlay is torn
        down in a ``finally``: an exception mid-load must not leave a scrim
        over a viewport that no longer has anything to wait for, which would
        be a hang with no way out.

        Parameters
        ----------
        title : str
            What is happening, shown as the heading.
        cancellable : bool, optional
            Offer a Cancel button. Only pass this when the caller actually
            polls ``overlay.cancelled`` -- a button that does nothing is worse
            than none.

        Yields
        ------
        callable
            ``report(fraction=None, message=None)``. Safe to call when there is
            no chrome at all, which is the headless case.
        """
        overlay = self._progress_overlay()
        if overlay is None:
            yield lambda *_args, **_kwargs: None
            return

        overlay.begin(title, cancellable=cancellable)
        self._redraw()
        try:
            last_drawn = [0.0]

            def report(fraction=None, message=None):
                overlay.update(fraction, message)
                # Drawn synchronously: the load holds the thread, so nothing
                # else is going to pump a frame before it finishes. Without
                # this the bar would only ever be painted once, at the end,
                # which is the same as not having one.
                #
                # Throttled, because a frame is not free -- for a large scene
                # it is tens of milliseconds -- and a caller reporting per
                # record would otherwise spend the whole load redrawing the
                # thing that says how the load is going.
                now = time.monotonic()
                if now - last_drawn[0] < _PROGRESS_REDRAW_INTERVAL:
                    return
                last_drawn[0] = now
                self._redraw()

            yield report
        finally:
            overlay.end()
            self._redraw()

    def _progress_overlay(self):
        """The chrome's progress overlay, or ``None`` when there is no chrome."""
        gui = getattr(getattr(self.viewer, "_renderer", None), "_internal_gui", None)
        return getattr(gui, "progress", None)

    def _redraw(self) -> None:
        """Paint one frame now, if the host can."""
        renderer = getattr(self.viewer, "_renderer", None)
        for name in ("draw_frame", "update"):
            method = getattr(renderer, name, None)
            if callable(method):
                try:
                    method()
                except Exception:  # noqa: BLE001 - a frame is not worth the load
                    logger.debug("could not redraw during progress", exc_info=True)
                return

    def _load_structure_from_path(self, path, *, name: str | None = None) -> str:
        """Read a structure file and register it as an object.

        Parameters
        ----------
        path : str or pathlib.Path
            A file to read.
        name : str, optional
            Object name; the file's stem otherwise.

        Returns
        -------
        str
            The new object's id.

        Raises
        ------
        ValueError
            If the file yields no coordinates. Raised rather than swallowed:
            a ``load`` that reports success and shows nothing is the single
            most expensive failure mode this host has.
        """
        from ..io.structure import load_structure_payload

        source = pathlib.Path(str(path))
        label = str(name or source.stem or "molecule")

        # Reading a structure is the longest thing chimol does without saying
        # anything -- seconds for an integrative model -- so it reports. The
        # steps are named rather than numbered because the fractions are a
        # guess and the *names* are not: what takes the time is the read and
        # the scene build, in that order.
        with self._reporting(f"Opening {source.name}") as report:
            report(0.05, "reading the file")
            structure, payload = load_structure_payload(source)

            report(0.55, "building the scene")
            entry = self.viewer._create_object(name=label, source_path=str(source))
            self.viewer.set_active_object(entry.object_id)
            if structure is not None:
                self.viewer.set_structure(structure)
            else:
                if payload is None or payload.coords is None or not len(payload.coords):
                    raise ValueError(f"no coordinates in {source.name}")
                # `apply_payload` is the viewer's documented single route from a
                # file in: it is what builds the residues, the CA trace and the
                # secondary structure a cartoon needs. Going in through
                # `set_structure` instead is how a structure arrives as bare
                # points and every feature keyed on atom identity degrades
                # silently.
                self.viewer.apply_payload(payload, object_id=entry.object_id)
            report(0.95, "listing the objects")
            self._refresh_objects_from_viewer()
        # Show what just arrived. A structure carries facts nobody can read off
        # the picture -- how many atoms, its radius of gyration, which chains --
        # and the moment they are wanted is the moment it appears. Left
        # *unpinned*, so a click anywhere puts it away again; only the Info
        # button pins it open.
        try:
            self.viewer.set_system_info_text(self.system_info_text())
            self.viewer.set_system_info_visible(True)
        except Exception:  # noqa: BLE001 - a panel is not worth the load
            logger.debug("could not show the system info", exc_info=True)
        return entry.object_id

    def _refresh_objects_from_viewer(self) -> None:
        """Tell the host the object list changed."""
        if self.on_objects_changed is not None:
            self.on_objects_changed()

    def _set_object_visible(self, object_id, visible: bool) -> None:
        """Show or hide an object, then refresh the panel.

        Parameters
        ----------
        object_id : str
            The object to show or hide.
        visible : bool
            Whether it is drawn.
        """
        self.viewer.set_object_visible(object_id, bool(visible))
        self._refresh_objects_from_viewer()

    def _select_object_in_ui(self, object_id) -> None:
        """Make an object current in the host's panel.

        Parameters
        ----------
        object_id : str
            The object that became current.
        """
        self._refresh_objects_from_viewer()

    def _update_sequence_view(self, object_id=None) -> None:
        """Rebuild the sequence strip.

        Parameters
        ----------
        object_id : str, optional
            Accepted for signature parity with the Qt window; the strip is
            rebuilt from the whole object list either way.
        """
        self._refresh_objects_from_viewer()

    def system_info_text(self) -> str:
        """What the info panel says about the loaded system.

        The Qt window builds this in ``_update_system_info`` -- a hundred lines
        that touch **no Qt at all**, only the viewer -- so the toolkit-free host
        had no producer and the Info button toggled an empty panel. The panel
        draws nothing without text, so the button looked broken while the
        toggle underneath it worked perfectly.

        Returns
        -------
        str
            One block of lines, or a sentence saying nothing is loaded.
        """
        viewer = self.viewer
        active = viewer.get_active_object_id()
        entry = None
        for candidate in viewer.list_objects():
            if candidate.get("id") == active:
                entry = candidate
                break
        if entry is None:
            return "(no system loaded)"

        lines = [f"System: {entry.get('name', '?')}"]
        seq_codes, res_names = viewer.get_sequence_arrays(active)
        residues = None
        for source in (seq_codes, res_names):
            if source is not None:
                residues = len(source)
                break
        # Atoms and the radius of gyration, from the active object's own
        # coordinates. `get_atom_sphere_data` takes no object id -- it is always
        # the active one -- and passing one positionally raises, which is how
        # the atom count went missing without anything being logged.
        try:
            positions, _colours, _radii = viewer.get_atom_sphere_data()
        except Exception:  # noqa: BLE001 - not every object has atoms
            positions = None
        if positions is not None and len(positions):
            lines.append(f"Atoms: {len(positions)}")
            # Computed rather than read off the structure: the built-in PDB
            # parser is used whenever the core Structure is unavailable, and it
            # says so ("no radius of gyration"). The definition is the same
            # either way, and the coordinates are right here.
            import numpy as np  # noqa: PLC0415

            coords = np.asarray(positions, dtype=float)
            # Back to Angstrom. These are **scene** coordinates:
            # `(xyz - object_centre) * scale_factor`, and the factor is 10 by
            # default -- so a radius of gyration taken straight off them reads
            # 162 A for T4 lysozyme, which is ten times the real 16 A and just
            # plausible enough to be believed.
            scale = float(getattr(viewer, "_scale_factor", 1.0)) or 1.0
            centre = coords.mean(axis=0)
            r_g = float(np.sqrt(((coords - centre) ** 2).sum(axis=1).mean())) / scale
            lines.append(f"Radius of gyration: {r_g:.1f} A")
        if residues is not None:
            lines.append(f"Residues: {residues}")
        try:
            chains = viewer.get_chain_ids(active)
            if chains is not None and len(chains):
                unique = sorted({str(c) for c in chains})
                lines.append(f"Chains: {len(unique)} ({', '.join(unique)})")
        except Exception:  # noqa: BLE001
            pass
        # Whatever else this object is. A map and a trajectory are the two
        # things whose *content* is not visible from the atom counts, and they
        # are exactly what someone opens the panel to check.
        try:
            grid = viewer.get_volume(active)
        except Exception:  # noqa: BLE001 - not a map
            grid = None
        if grid is not None:
            shape = getattr(grid, "shape", None)
            step = getattr(grid, "step", None)
            if shape is not None:
                lines.append("Map: " + "x".join(str(int(n)) for n in shape))
            if step is not None:
                lines.append("Step: " + "/".join(f"{float(v):.3g}" for v in step))
            try:
                low, high = grid.value_range()
                lines.append(f"Values: {low:.4g} to {high:.4g}")
            except Exception:  # noqa: BLE001
                pass
            try:
                levels = viewer.get_volume_levels(active)
                if levels:
                    lines.append(
                        "Levels: " + ", ".join(f"{float(v):.4g}" for v in levels)
                    )
            except Exception:  # noqa: BLE001
                pass
        try:
            frames = int(viewer.get_frame_count(active))
            if frames > 1:
                current = int(viewer.get_active_frame_index(active)) + 1
                lines.append(f"Frames: {current} / {frames}")
        except Exception:  # noqa: BLE001 - not a trajectory
            pass

        path = entry.get("source_path")
        if path:
            lines.append(f"File: {path}")
        return "\n".join(lines)

    def update_system_info(self) -> None:
        """Refresh the info panel's text, when it is showing the system.

        Left alone while a *listing* owns the panel: `help` writes there too,
        and refreshing over it would wipe the answer the user just asked for.
        """
        gui = getattr(getattr(self.viewer, "_renderer", None), "_internal_gui", None)
        if getattr(gui, "_info_items", None):
            return
        try:
            self.viewer.set_system_info_text(self.system_info_text())
        except Exception:  # noqa: BLE001 - the panel is not worth a frame
            logger.debug("could not build the system info", exc_info=True)

    # -- scripts and demos ---------------------------------------------------

    def run_script_text(self, text: str) -> None:
        """Run chimol script text, one command per line.

        The rule ``@file`` uses: blank lines and ``#`` comments skipped, every
        other line handed to the command layer.

        Parameters
        ----------
        text : str
            The script.
        """
        run = getattr(self, "run_command", None)
        for line in str(text).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if callable(run):
                run(stripped)
            elif self.cmd is not None:
                self.cmd.do(stripped)

    def run_demo(self, key: str) -> None:
        """Run a shipped demo script by name.

        Why this lives on the host rather than on the Qt window: the ``demo``
        command asks the *host* for ``run_demo`` and reports "this host cannot
        run demo scripts" when it is missing. Only the Qt window had it, so the
        toolkit-free desktop host and the browser could list every demo from
        the menu and then run none of them -- and the message named the host,
        which reads like a limitation of the design rather than a method nobody
        had written yet.

        Nothing here needs a toolkit. ``demo_catalog`` is Qt-free (the
        ``QDialog`` lives in ``app.demos``, which merely re-exports from it),
        so the whole body is reading a file, rewriting the loader lines, and
        replaying them through the command layer.

        Parameters
        ----------
        key : str
            A demo name from ``demo_catalog.DEMOS``.
        """
        from ..app.demo_catalog import read_demo, resolve_structure
        from ..app.demo_data import DemoDataUnavailable

        text = read_demo(key)
        if not text:
            self._report(f"demo: no demo named {key!r}")
            return

        # A demo says `load 148l.pdb` so it reads like something a person would
        # type; the name is resolved here so that works from any working
        # directory. Every command whose first argument names a shipped file
        # belongs in this tuple -- `load_traj` was once missed, and the demo
        # then failed on a file sitting right there.
        loaders = ("load", "load_traj")
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            verb, _, rest = stripped.partition(" ")
            if verb in loaders and rest.strip() and "," not in stripped:
                try:
                    lines.append(f"{verb} " + resolve_structure(rest.strip()))
                except DemoDataUnavailable as exc:
                    # One demo's material is computed rather than shipped, so it
                    # can fail for a reason no file error explains. Say the
                    # reason: "cannot read file" sends the reader looking for a
                    # download that was never meant to exist.
                    self._report(f"demo: {exc}")
                    return
            else:
                lines.append(line)

        # Start from an empty viewer: without this each demo adds its structure
        # to the last one's, and by the seventh the scene is a pile of seven
        # molecules demonstrating nothing. A demo is a *scene*, not an increment.
        self.run_script_text("delete all\n" + "\n".join(lines))

    def _report(self, message: str) -> None:
        """Send a message to whatever is listening, or to the log.

        Parameters
        ----------
        message : str
            What to say.
        """
        sink = getattr(self, "on_error", None)
        if callable(sink):
            sink(message)
        else:
            logger.warning("%s", message)

    def isFullScreen(self) -> bool:  # noqa: N802 - the Qt name the commands use
        """Whether the window is full screen."""
        return False

    def showFullScreen(self) -> None:  # noqa: N802 - the Qt name
        """Go full screen."""

    def showNormal(self) -> None:  # noqa: N802 - the Qt name
        """Leave full screen."""

    def close(self) -> None:
        """Close the window."""


def sync_panel(viewer, gui) -> None:
    """Mirror the viewer's objects and sequences into the in-viewport panel.

    The panel is a *view* of the object list, so it is fed from the list rather
    than kept in step by hand -- which is what the Qt window's
    ``sync_internal_gui`` does, for the same reason.

    Parameters
    ----------
    viewer : chimol.renderer.view.MolView
        The viewer to read from.
    gui : chimol.renderer.internal_gui.InternalGui
        The panel to fill, in place.
    """
    from ..renderer.internal_gui import GuiRow, SequenceRow

    rows = [GuiRow(name="all", is_header=True)]
    sequences = []
    for entry in viewer.list_objects():
        name = str(entry.get("name") or entry.get("id"))
        rows.append(GuiRow(name=name, enabled=bool(entry.get("visible", True))))
        codes, numbers, colours = _sequence_of(viewer, entry.get("id"))
        if codes:
            sequences.append(
                SequenceRow(
                    name=name,
                    codes=codes,
                    numbers=numbers,
                    colors=colours,
                    object_id=str(entry.get("id")),
                )
            )
    # PyMOL pins the `sele` selection object to the bottom of its object list,
    # below every real object and the `all` header.
    rows.append(GuiRow(name="sele", is_selection=True))
    gui.set_rows(rows)
    gui.set_sequences(sequences)


def _sequence_of(viewer, object_id):
    """One-letter codes, residue numbers and colours for one object.

    From the viewer's own accessors, which is what the Qt window's
    ``_sync_internal_sequences`` reads too -- deriving the sequence here from
    the payload instead is how the strip ends up disagreeing with the molecule
    about what a residue is coloured.

    Parameters
    ----------
    viewer : chimol.renderer.view.MolView
        The viewer holding the object.
    object_id : str
        Which object to describe.

    Returns
    -------
    tuple
        ``(codes, numbers, colours)``.
    """
    try:
        codes, _names = viewer.get_sequence_arrays(object_id)
        numbers = viewer.get_residue_numbers(object_id)
        colours = viewer.get_residue_colors(object_id)
    except Exception:  # noqa: BLE001 - an object with no sequence
        return "", [], []
    if codes is None or not len(codes):
        return "", [], []
    return (
        "".join(str(c) for c in codes),
        [int(n) for n in (numbers if numbers is not None else [])],
        [
            tuple(float(c) for c in rgba[:3])
            for rgba in (colours if colours is not None else [])
        ],
    )
