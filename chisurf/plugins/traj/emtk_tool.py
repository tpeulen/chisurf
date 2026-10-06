"""The emtk app shared by the single-panel trajectory tools.

Align, Rotate/Translate, Remove Clashed, Join and Save Topology are the same
window around different view models: file rows (a read-only path, a ``…``
browse button, drag-drop), the fields their ``*.view.json`` declares, one save
action and a running log. The Qt widgets render that spec with AutoForm and a
per-tool custom section for the file rows; this app draws the same spec with
:func:`emtk.view_form.draw_form` and draws that custom section from the
:class:`PathField` / :class:`SaveAction` declarations a tool passes in.

Behaviour kept from the Qt section: a file row only takes a file that exists,
the save action asks for a trajectory first, a cancelled save dialog logs
"Save cancelled", and a failed save is reported in the window (the Qt tool
raised a message box). The work runs on a worker thread here, so a long
alignment does not freeze the window.
"""

from __future__ import annotations

import concurrent.futures
import fnmatch
import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import (
    NUMBER_WIDTH,
    LabelColumn,
    cap_widths,
    group_by_width,
    icon_label,
    labelled,
    layout_spec,
)

ERROR = (1.0, 0.45, 0.45, 1.0)
LOG_KEY = "log"
#: The log shows this many lines before it scrolls; the window below it stays empty rather than all log.
LOG_LINES = 9

TRAJECTORY_FILTERS = [("Trajectories", ["*.dcd"])]
STRUCTURE_FILTERS = [("Structures", ["*.pdb", "*.cif", "*.ent"])]


@dataclass
class PathField:
    """One file row of a tool's custom io section.

    Parameters
    ----------
    key : str
        Guide target and item key.
    label : str
        Caption in front of the path.
    attr : str
        View-model attribute holding the path.
    setter : str
        View-model method that sets the path (and logs it).
    filters : list
        ``(label, globs)`` for the browse dialog, and for routing a drop.
    placeholder, tooltip, browse_tooltip : str
        Text shown in the empty field, on the field and on ``…``.
    dialog_title : str
        Title of the browse dialog.
    folder : bool or callable
        The row takes a folder instead of a file -- always, or when
        ``folder(model)`` says so (a toggle that switches the input kind).
    """

    key: str
    label: str
    attr: str
    setter: str
    filters: list
    placeholder: str
    tooltip: str
    browse_tooltip: str
    dialog_title: str
    folder: Any = False

    def takes_folder(self, model) -> bool:
        return bool(self.folder(model) if callable(self.folder) else self.folder)


@dataclass
class SaveAction:
    """The tool's one action: pick a target file, then run the view model on it.

    ``run(model, path)`` does the work; ``missing(model)`` names what has to be
    chosen first (``None`` when the action can run); ``suggest(model)`` is the
    file name the save dialog starts with; ``failure`` heads the message a
    failed run leaves in the window (the Qt tool's error-box title) and
    ``cancelled`` is what a closed save dialog logs. Without a
    ``dialog_title`` the action runs at once (the target comes from the
    tool's own fields) and ``run`` gets ``None``; ``done`` is said in the
    window after a run that did not fail (the Qt tool's confirmation box):
    a string, or a function of what ``run`` returned (a frame count).
    """

    key: str
    label: str
    tooltip: str
    dialog_title: str | None
    filters: list
    run: Callable[[Any, str | None], Any]
    missing: Callable[[Any], str | None] = lambda model: (
        None if model.trajectory_filename else "Open a trajectory first."
    )
    suggest: Callable[[Any], str] = lambda model: ""
    failure: str = "Save failed"
    cancelled: str = "Save cancelled"
    done: Any = ""


def trajectory_field(**overrides) -> PathField:
    """The trajectory row every tool has (DCD, as the Qt sections filter)."""
    values = dict(
        key="trajectory",
        label="Trajectory",
        attr="trajectory_filename",
        setter="set_trajectory",
        filters=TRAJECTORY_FILTERS,
        placeholder="Drop a DCD trajectory here or browse…",
        tooltip="The trajectory the tool reads. Drop a .dcd here or press … to pick one.",
        browse_tooltip="Open a DCD trajectory.",
        dialog_title="Open trajectory",
    )
    values.update(overrides)
    return PathField(**values)


def topology_field(**overrides) -> PathField:
    """The topology row: the PDB that names the atoms a DCD stores coordinates for."""
    values = dict(
        key="topology",
        label="Topology",
        attr="topology_filename",
        setter="set_topology",
        filters=STRUCTURE_FILTERS,
        placeholder="PDB naming the atoms — required for DCD",
        tooltip="The structure that names the atoms; a DCD stores coordinates only.",
        browse_tooltip="Open the PDB that names the atoms. DCD stores coordinates only, so "
        "this is required for them.",
        dialog_title="Open topology",
    )
    values.update(overrides)
    return PathField(**values)


def _matches(path: str, filters: Sequence) -> bool:
    name = os.path.basename(path).lower()
    return any(fnmatch.fnmatch(name, glob.lower()) for _label, globs in filters for glob in globs)


class TrajToolApp(TourTarget, ImApp):
    """A trajectory tool's window, drawn from its view spec.

    Parameters
    ----------
    model : object
        The tool's Qt-free view model (``log_text()``, ``append_log()``, the
        setters the :class:`PathField` entries name).
    folder : pathlib.Path
        The plugin folder: the spec, ``help.md`` and ``guide.json`` live there.
    spec_name : str
        File name of the tool's ``*.view.json``.
    io_key : str
        The spec's custom section the file rows and the action are drawn into.
    title : str
        The window caption: the spec panel's title, as the Qt panel shows it.
    paths : sequence of PathField
        The file rows, in order.
    action : SaveAction
        The action button under the rows.
    action_key : str, optional
        A custom section of the spec of its own for the action button (the
        Qt converter put it under its output fields); without one the button
        closes the io section.

    A spec of one panel is drawn as that panel's sections under the window
    caption; a spec of several panels keeps them, titled.
    """

    def __init__(
        self,
        model,
        folder: pathlib.Path,
        spec_name: str,
        io_key: str,
        title: str,
        paths: Sequence[PathField],
        action: SaveAction,
        action_key: str | None = None,
    ) -> None:
        self.model = model
        self.folder = pathlib.Path(folder)
        self.title = title
        self.paths = list(paths)
        self.action = action
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.status = ""
        self.notice = ""
        self.future: concurrent.futures.Future | None = None
        self._executor = concurrent.futures.ThreadPoolExecutor(1, thread_name_prefix=io_key)
        self.dialog: FileDialog | None = None
        self.dialog_window = DialogWindow(
            "Choose a file", size=(640.0, 400.0), key=f"{io_key}-file"
        )
        self._on_pick: Callable[[str], None] | None = None
        self._log_seen = 0

        spec = json.loads((self.folder / spec_name).read_text(encoding="utf-8"))
        panel = spec["sections"][0]
        top = (
            panel.get("sections", [])
            if len(spec["sections"]) == 1
            else [
                dict(s, collapsible=True) if s.get("type") == "panel" else s
                for s in spec["sections"]
            ]
        )  # several panels fold, as the Qt AutoForm panels do
        self.spec = {"sections": [self._host_section(s) for s in top]}
        _spin_numbers(self.spec["sections"])
        self.spec = layout_spec(self.spec)
        self.labels = LabelColumn()  # the one label column every row of the window shares
        if not action_key:  # the action closes the inputs, above the log
            action_key = f"{io_key}_action"
            if not _insert_before_log(self.spec["sections"], {"type": "custom", "key": action_key}):
                self.spec["sections"].append({"type": "custom", "key": action_key})
        self.form = FormState()
        self.form.custom[io_key] = self._draw_io
        self.form.custom[LOG_KEY] = self._draw_log
        self.action_key = action_key
        self.form.custom[action_key] = lambda *args: self._draw_action()
        self.docks = DockManager(Region("main"))
        self.docks.add_window("main", title, self._draw_main, dock="main", closable=False)
        self.native_layouts = {"main": self.docks}

        self.help_window = EmTkHelpWindow(
            title=f"{panel.get('title', title)} — Help",
            resource=self.folder / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(680.0, 500.0),
        )
        self.tour = EmTkGuidedTour(
            steps=self.folder / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k) or self.form.rects.get(k),
            owner=self,
            wait_for_controls=True,
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(gui=self.render, continuous=False)

    @classmethod
    def _host_section(cls, section: dict) -> dict:
        """The log ``info`` section becomes a scrolling region; everything else draws as declared."""
        if section.get("type") == "info" and section.get("source") == "log_html":
            return {"type": "custom", "key": LOG_KEY}
        if isinstance(section.get("sections"), list):
            return dict(section, sections=[cls._host_section(s) for s in section["sections"]])
        return section

    # ── state ─────────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self.future is not None

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def set_path(self, path_field: PathField, path: str) -> bool:
        """Put *path* into a row, as the Qt row does: only a file (or folder, for a folder row) that exists."""
        folder = path_field.takes_folder(self.model)
        exists = pathlib.Path(path).is_dir() if folder else pathlib.Path(path).is_file()
        if not path or not exists:
            self.status = f"Not a {'folder' if folder else 'file'}: {path}" if path else ""
            return False
        getattr(self.model, path_field.setter)(str(path))
        self.status = ""
        return True

    def browse(self, path_field: PathField) -> None:
        """Open the row's file dialog; the pick goes into the row."""
        current = getattr(self.model, path_field.attr) or ""
        folder = path_field.takes_folder(self.model)
        start = current if folder and os.path.isdir(current) else os.path.dirname(current)
        self._open_dialog(
            FileDialog(
                path_field.dialog_title,
                mode="folder" if folder else "open",
                filters=path_field.filters,
                directory=start or None,
            ),
            lambda path: self.set_path(path_field, path),
        )

    def begin_save(self) -> None:
        """The action button: say what is missing, else ask where to write."""
        missing = self.action.missing(self.model)
        if missing:
            self.status = missing
            return
        if not self.action.dialog_title:
            self.save(None)
            return
        source = getattr(self.model, self.paths[0].attr) or ""  # the first row is the source
        self._open_dialog(
            FileDialog(
                self.action.dialog_title,
                mode="save",
                filters=self.action.filters,
                directory=os.path.dirname(source) or None,
                filename=self.action.suggest(self.model),
            ),
            self.save,
            on_cancel=lambda: self.model.append_log(self.action.cancelled),
        )

    def save(self, target: str | None) -> None:
        """Run the action on *target* on the worker; the result lands in the log and status."""
        if self.running:
            return
        self.status = self.notice = ""
        self.future = self._executor.submit(
            self.action.run, self.model, None if target is None else str(target)
        )

    def poll(self) -> None:
        if self.future is None or not self.future.done():
            return
        future, self.future = self.future, None
        try:
            result = future.result()
        except Exception as exc:  # the view model has logged it; the window says so too
            self.status = f"{self.action.failure}: {exc}"
        else:
            done = self.action.done
            self.notice = done(result) if callable(done) else done

    def _open_dialog(
        self,
        dialog: FileDialog,
        on_pick: Callable[[str], Any],
        on_cancel: Callable[[], Any] | None = None,
    ) -> None:
        self.dialog, self._on_pick, self._on_cancel = dialog, on_pick, on_cancel
        self.dialog_window.title = dialog.title
        self.dialog_window.show()

    def on_files_dropped(self, paths: Sequence[str]) -> bool:
        """The host's drop verb (the Qt and the glfw host both call it): see :meth:`on_paths_dropped`.

        Always True: a drop nothing took still has an answer (the status line) the host must repaint.
        """
        self.on_paths_dropped(paths)
        return True

    def on_paths_dropped(self, paths: Sequence[str]) -> bool:
        """A drop fills the row whose filter matches each file (an empty row first); True when one was taken."""
        taken = False
        for path in paths:
            if os.path.isdir(path):
                rows = [p for p in self.paths if p.takes_folder(self.model)]
            elif os.path.isfile(path):
                rows = [
                    p
                    for p in self.paths
                    if not p.takes_folder(self.model) and _matches(path, p.filters)
                ]
            else:
                continue
            rows.sort(key=lambda p: bool(getattr(self.model, p.attr)))
            if rows and self.set_path(rows[0], path):
                taken = True
        if not taken:
            names = " or ".join(p.label.lower() for p in self.paths)
            self.status = f"No {names} file among the dropped paths."
        return taken

    # ── drawing ───────────────────────────────────────────────────────────

    def render(self) -> None:
        self.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(box)
        im.end_disabled()
        if self.dialog is not None:
            self._draw_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _draw_dialog(self, box) -> None:
        pressed = self.dialog_window.begin(box)
        result = self.dialog.draw()
        self.dialog_window.end()
        if result:
            pick, self.dialog = self._on_pick, None
            pick(result[0])
        elif result is False or pressed == "close":
            cancel, self.dialog = self._on_cancel, None
            if cancel is not None:
                cancel()

    def _draw_main(self, box) -> None:
        if im.button(icon_label("📖", "Guide")):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool, pointing at each control.")
        self.remember("guide")
        im.same_line()
        if im.button(icon_label("❓", "Help")):
            self.show_help()
        im.set_item_tooltip("What the tool does, what it writes, and the known limits.")
        self.remember("help")
        im.separator()
        self.form.rects.clear()
        self.label_column()
        im.begin_disabled(self.running)
        draw_form(self.spec, self.model, self.form)
        im.end_disabled()
        self.item_rects.update(self.form.rects)

    def label_column(self) -> float:
        """Where the fields start: the label column every row shares (file rows, fields, editors).

        The first call measures the widest caption of the window and pads every field caption of the spec to it
        (:class:`~chisurf.plugins.emtk_layout.LabelColumn`).
        """
        if not self.labels.ready:
            captions = [p.label for p in self.paths]
            captions += [
                s["label"] for s in labelled(self.spec["sections"])
            ] + self.extra_captions()
            self.labels.measure(captions)
            self.labels.pad(self.spec["sections"])
        return self.labels.x

    def layout_spec(self, spec: dict) -> dict:
        """A spec a tool draws itself, laid out as the window's own: capped widths, one grid per kind of field."""
        return layout_spec(spec)

    def extra_captions(self) -> list[str]:
        """Captions a tool draws itself (not in its spec) in the shared label column."""
        return []

    def pad_labels(self, sections) -> None:
        """Pad the field captions of *sections* to the window's label column (see :meth:`label_column`)."""
        self.labels.pad(sections)

    def _draw_io(self, section, model, state, width) -> None:
        label_w = self.label_column()
        button_w = im.get_frame_height() + 6.0
        for path_field in self.paths:
            im.text(path_field.label)
            im.same_line(label_w)  # the paths start in one column
            im.set_next_item_width(max(80.0, width - label_w - button_w - 8.0))
            im.input_text(
                f"##{path_field.key}",
                getattr(model, path_field.attr) or "",
                hint=path_field.placeholder,
                flags=im.InputTextFlags.READ_ONLY,
                elide_start=True,
            )
            im.set_item_tooltip(path_field.tooltip)
            self.remember(path_field.key)
            im.same_line()
            if im.button(f"…##{path_field.key}.browse", (button_w, 0)):
                self.tour.notify_used(path_field.key)
                self.browse(path_field)
            im.set_item_tooltip(path_field.browse_tooltip)
            self.remember(f"{path_field.key}_browse")
        self.draw_extra_io(width)

    def _draw_action(self) -> None:
        im.spacing()
        if im.button(self.action.label):
            self.tour.notify_used(self.action.key)
            self.begin_save()
        im.set_item_tooltip(self.action.tooltip)
        self.remember(self.action.key)
        if self.running:
            im.same_line()
            im.text_disabled("Working…" + self.progress_text())
        if self.status:
            im.text_colored(ERROR, self.status)
        elif self.notice:
            im.text_wrapped(self.notice)

    def progress_text(self) -> str:
        """What follows "Working…" while the action runs (a tool that counts its frames says how many)."""
        return ""

    def draw_extra_io(self, width: float) -> None:
        """Controls a tool's io section has between the file rows and the action (none here)."""

    def _draw_log(self, section, model, state, width) -> None:
        im.text("Log")
        x, y = im.get_cursor_screen_pos()
        room = float(im.get_content_region_avail()[1])
        height = min(max(80.0, room), LOG_LINES * im.get_text_line_height_with_spacing() + 8.0)
        box = (float(x), float(y), float(width), height)
        im.begin_child("##log", box[2:])
        lines = self.model.log_text()
        for line in lines:
            im.text_wrapped(line)  # paths are long; the Qt log wrapped them too
        if len(lines) != self._log_seen:  # follow new lines, as the Qt log does
            self._log_seen = len(lines)
            im.set_scroll_here_y(1.0)
        im.end_child()
        self.remember(LOG_KEY, box)

    # ── host contract ─────────────────────────────────────────────────────

    def animating(self) -> bool:
        return self.running or super().animating()

    def export_settings(self) -> dict:
        values = {p.attr: getattr(self.model, p.attr) for p in self.paths}
        for section in _fields(self.spec["sections"]):
            values[section["attr"]] = getattr(self.model, section["attr"])
        return values

    def restore_settings(self, settings: dict) -> None:
        for path_field in self.paths:
            value = str(settings.get(path_field.attr) or "")
            if value and os.path.exists(value):
                setattr(self.model, path_field.attr, value)
        for section in _fields(self.spec["sections"]):
            if section["attr"] in settings:
                setattr(self.model, section["attr"], settings[section["attr"]])

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _insert_before_log(sections: list, node: dict) -> bool:
    """Put *node* in front of the log section wherever it nests; False when the spec has no log."""
    for i, section in enumerate(sections):
        if section.get("type") == "custom" and section.get("key") == LOG_KEY:
            sections.insert(i, node)
            return True
        if isinstance(section.get("sections"), list) and _insert_before_log(
            section["sections"], node
        ):
            return True
    return False


def _spin_numbers(sections) -> None:
    """Give every number field the arrows and wheel the Qt spin boxes had.

    The Qt AutoForm draws ``int`` / ``float`` values as spin boxes whose arrows step by the spec's
    ``step`` (Qt's default: 1). emtk's plain field takes typing only, so the spec is drawn with the
    ``spin`` style and the same step.
    """
    for section in sections:
        if (
            section.get("type") == "value"
            and section.get("kind") in ("int", "float")
            and not section.get("read_only")
        ):
            section["style"] = "spin"
            section.setdefault("step", 1)
        _spin_numbers(section.get("sections", []))


def _fields(sections):
    for section in sections:
        if section.get("attr"):
            yield section
        yield from _fields(section.get("sections", []))


__all__ = [
    "PathField",
    "SaveAction",
    "TrajToolApp",
    "icon_label",
    "topology_field",
    "trajectory_field",
]
