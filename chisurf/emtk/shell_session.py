"""The emtk shell's session menus: project files, undo and redo, settings, and the close guard.

What the Qt shell's *File*, *View*, *Macro* and *Settings* menus do, over the
same project services:

* **Project files** (:class:`ShellProject`): save, save under a new name, open,
  import, close, recent projects and the silent autosave, all as ``.cs.pto``
  through :mod:`chisurf.core.project.storage` and the session server's
  ``project.*`` RPCs (``project.capture``, ``project.load``,
  ``project.restore_payload``, ``session.restore``). The document identity and
  the "is it modified?" baseline are the Qt shell's
  :class:`~chisurf.core.project.lifecycle.ProjectDocument`; a configured MMFDB
  deployment saves versions instead, as there.
* **The close guard**: closing the window, *Quit*, *Open*, *Close Project* and
  *Reinitialize* ask **once** -- *Save* / *Don't Save* / *Cancel* when the
  session holds unsaved work, otherwise (on quit, with
  ``gui.confirm_close_program``) "Quit ChiSurf?".
* **Undo and redo**: an :class:`~chisurf.history.core.OperationHistory` of the
  session's own, whose science is captured and published through the server.
  A change the server announces (a fit updated, a model state set, a dataset
  added) records one step once the server is idle; a capture that equals the
  last one records nothing.
* **The fit window's ×** asks, then removes the fit (with
  ``gui.confirm_close_fit``), as the Qt fit window does.

Questions are :class:`emtk.message_dialog.MessageDialogs`, which tests answer
with :func:`emtk.message_dialog.auto_answer`.

Every server call runs on a worker over a connection of this module's own
(:class:`ProjectChannel`): the data docks' connection is theirs, and a ZMQ
socket must not be shared between threads. The server answers one request at a
time, so a capture asked for during a fit waits for the fit and sees its result.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from emtk.i18n import tr
from emtk.message_dialog import MessageDialogs

from chisurf.emtk.background_build import BackgroundBuild

_log = logging.getLogger("chisurf.emtk.shell.project")

#: The project file filter of the file dialogs.
PROJECT_FILTER = (("ChiSurf Project", ("*.cs.pto",)),)
#: *Load Fit*: a fit document (``<data>.fit.cs.pto``, written by *Current Fit*), or a project.
FIT_FILTER = (("ChiSurf Fit", ("*.fit.cs.pto",)), ("ChiSurf Project", ("*.cs.pto",)))
PROJECT_SUFFIX = ".cs.pto"
#: Server events after which the science may have changed (one undo step is recorded).
RECORD_TOPICS = (
    "fit.updated",
    "fit.ran",
    "fit.created",
    "fit.added",
    "fit.removed",
    "fit.cleared",
    "fit.dataset_changed",
    "fit.mask_changed",
    "fit.result_idx_changed",
    "fit.group.",
    "model.",
    "dataset.added",
    "dataset.removed",
    "dataset.cleared",
)
#: The question of the close guard.
SAVE_OPTIONS = (("save", "Save"), ("discard", "Don't Save"), ("cancel", "Cancel"))


def _setting(section: str, key: str, default: Any) -> Any:
    """``chisurf.core.settings.cs_settings[section][key]``, *default* when unset."""
    try:
        from chisurf.core.settings import cs_settings

        return (cs_settings.get(section) or {}).get(key, default)
    except Exception:  # noqa: BLE001 - a missing settings module means the defaults
        return default


def _working_path() -> Path:
    import chisurf

    return Path(getattr(chisurf, "working_path", None) or Path.home())


def display_name(path_or_name: str | Path | None) -> str:
    """A project's name from its file name, without ``.cs.pto``."""
    value = Path(str(path_or_name or "chisurf_project")).name
    return value[: -len(PROJECT_SUFFIX)] if value.lower().endswith(PROJECT_SUFFIX) else value


def escape_pressed() -> bool:
    """Whether Escape was pressed this frame: it cancels the shell's modal file dialog.

    ``DialogWindow`` closes on Escape only under the pointer (right for a tool's window
    among others); a file dialog over the whole shell is modal and, like Qt's, is
    cancelled by Escape wherever the pointer is.
    """
    from emtk import im_core
    from emtk.keys import KEY_ESCAPE

    return im_core.get_io().key == KEY_ESCAPE


@dataclass
class _Job:
    label: str
    call: Callable[[], Any]
    after: Callable[[Any], None] | None
    failed: Callable[[BaseException], None] | None
    quiet: bool
    build: BackgroundBuild | None = None


class ProjectChannel:
    """The shell's own connection to its session server, for the project services.

    Parameters
    ----------
    session : ShellSession
        The running session; its in-process server's ports are connected to.
    """

    def __init__(self, session: Any) -> None:
        from chisurf.core.api import ChiSurfAPI
        from chisurf.core.api._client import ChisurfClient
        from chisurf.emtk.session import CALL_TIMEOUT_MS

        server = session.server
        self.client = ChisurfClient(
            cmd_port=server.cmd_port,
            pub_port=server.pub_port,
            host=server.host,
            timeout_ms=CALL_TIMEOUT_MS,
        )
        self.client.connect()
        self.api = ChiSurfAPI(client=self.client, mode="server", state=server.state)

    def capture(self, name: str = "chisurf_project") -> Any:
        """The session as a detached :class:`~chisurf.core.project.Project` (``project.capture``)."""
        return self.api.capture_project(name)

    def content(self) -> bool:
        """Whether the session holds work worth protecting: a dataset of its own, a fit or a resource."""
        datasets = [d for d in self.api.list_datasets() or [] if d.get("experiment") != "Global"]
        return bool(datasets or self.api.list_fits())

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - closing must not raise into the shell's close
            _log.exception("closing the project channel failed")


class FormDialog:
    """A settings form (a ``view.json`` spec over a model) in a dialog window with buttons.

    Parameters
    ----------
    title : str
        The window title.
    spec : dict
        The form's view spec.
    model : object
        The model the spec binds to.
    buttons : sequence of (str, str)
        ``(key, label)`` under the form; pressing one calls ``on_button(key)``.
    on_button : callable
        ``on_button(key) -> bool``; ``True`` closes the dialog.
    """

    #: The tooltip of each button key the shell's forms use.
    tooltips = {
        "ok": "Apply the form.",
        "cancel": "Close without applying the form.",
        "close": "Close this window.",
    }

    def __init__(self, title: str, spec: dict, model: Any, buttons, on_button) -> None:
        from emtk.dialog_window import DialogWindow
        from emtk.view_form import FormState

        self.title = title
        self.spec = spec
        self.model = model
        self.buttons = list(buttons)
        self.on_button = on_button
        self.form = FormState()
        self.rects: dict[str, tuple] = {}
        self.window = DialogWindow(title, size=(480, 260), fit_height=True)
        self.window.show()

    def draw(self, box) -> bool:
        """Draw it; ``False`` once it is closed."""
        from emtk import im
        from emtk.view_form import draw_form

        if not self.window.open:
            return False
        pressed = self.window.begin(box)
        draw_form(self.spec, self.model, self.form)
        chosen = None
        if self.buttons:
            im.separator()
        for index, (key, label) in enumerate(self.buttons):
            if index:
                im.same_line()
            if im.button(f"{tr(label)}##form.{key}"):
                chosen = key
            self.rects[key] = im.get_item_rect()
            im.set_item_tooltip(tr(self.tooltips.get(key, label)))
        self.rects.update(self.form.rects)
        self.window.end()
        if self.window.box is not None:
            self.rects["window"] = self.window.box
        if chosen is not None and self.on_button(chosen):
            self.window.hide()
        elif pressed == "close":
            self.on_button("close")
            self.window.hide()
        return self.window.open


class SaveProjectForm:
    """The model of the database *Save Project* form: name, visibility and notes."""

    def __init__(self, name: str, name_locked: bool) -> None:
        self._name = name
        self.name_locked = bool(name_locked)
        self.visibility = "private"
        self.notes = ""

    @property
    def project_name(self) -> str:
        return self._name

    @project_name.setter
    def project_name(self, value: str) -> None:
        if not self.name_locked:
            self._name = str(value)


class RdaAxisForm:
    """The model of the *FRET RDA axis* form: the live axis settings, applied by *Save axis*."""

    def __init__(self, on_saved: Callable[[], None] | None = None) -> None:
        import chisurf

        fret = getattr(chisurf.core.settings, "fret", {}) or {}
        self.rda_min = float(fret.get("rda_min", 1.0))
        self.rda_max = float(fret.get("rda_max", 130.0))
        self.rda_resolution = int(fret.get("rda_resolution", 96))
        scale = str(fret.get("rda_scale", "log")).lower()
        self.rda_scale = scale if scale in ("log", "lin") else "log"
        self.on_saved = on_saved
        self.saved: bool | None = None

    def save_axis(self) -> None:
        from chisurf.core.settings.settings_utils import apply_fret_rda_axis

        axis = apply_fret_rda_axis(self.rda_min, self.rda_max, self.rda_resolution, self.rda_scale)
        self.saved = axis is not None
        if axis is not None:
            self.rda_min, self.rda_max = float(axis[0]), float(axis[-1])
            if self.on_saved is not None:
                self.on_saved()


@dataclass
class MenuAction:
    """One item of a session menu: what it says, its shortcut and what it does."""

    key: str
    label: str
    run: Callable[[], Any]
    shortcut: str = ""
    group: str = ""
    description: str = ""
    enabled: Callable[[], bool] = field(default=lambda: True)
    checked: Callable[[], bool] | None = None
    #: nested items when this entry opens a submenu; the session menus stay flat,
    #: but the drawer reads this for any producer that nests (defaults to none).
    children: tuple["MenuAction", ...] = ()


class ShellProject:
    """The session menus' state and actions for one :class:`~chisurf.emtk.main_app.EmtkShellApp`.

    Parameters
    ----------
    shell : EmtkShellApp
        The shell: its docks, data docks (``shell.data``), frame request and close.
    """

    def __init__(self, shell: Any) -> None:
        from chisurf.core.project import recent
        from chisurf.core.project.lifecycle import Autosave, ProjectDocument
        from chisurf.history.core import OperationHistory

        self.shell = shell
        self.dialogs = MessageDialogs(wake=shell.request_frame)
        self.document = ProjectDocument()
        self.history = OperationHistory()
        config = _setting("project", "autosave", {}) or {}
        try:
            interval = max(1.0, float(config.get("interval_s", 120)))
        except (TypeError, ValueError):
            interval = 120.0
        self.autosave = Autosave(interval_s=interval, enabled=bool(config.get("enabled", True)))
        self.recent: list[str] = recent.load()
        self.channel: ProjectChannel | None = None
        self.status = ""
        self.job: _Job | None = None
        self.queue: deque[_Job] = deque()
        self.file_dialog: Any = None
        self._file_window: Any = None
        self._file_done: Callable[[str], None] | None = None
        self.form: FormDialog | None = None
        #: Whether the history has its baseline (undo is possible once it has).
        self.history_ready = False
        #: The topic of a change not recorded yet (several are recorded as one step).
        self._record_topic: str | None = None
        self._last_fingerprint: str | None = None
        self._prefetched: Any = None
        self._session: Any = None
        self._asking_fit: set[str] = set()
        self._removing_fit: list[str] = []
        #: The MMFDB client of the import under way (its preview, import and readback share it).
        self._import_client: Any = None
        self._next_autosave = time.monotonic() + self.autosave.interval_s
        #: Set once the user has agreed to quit; the window's close then goes through.
        self.quit_confirmed = False
        self._quitting = False

    # ── plumbing ──────────────────────────────────────────────────────────

    @property
    def data(self) -> Any:
        return self.shell.data

    @property
    def busy(self) -> bool:
        return self.job is not None or bool(self.queue)

    @property
    def modal(self) -> bool:
        """Whether a question, a form or a file dialog of these menus is open."""
        return self.dialogs.modal or self.form is not None or self.file_dialog is not None

    def _run(
        self,
        label: str,
        call: Callable[[], Any],
        after: Callable[[Any], None] | None = None,
        *,
        failed: Callable[[BaseException], None] | None = None,
        quiet: bool = False,
    ) -> bool:
        """Queue *call* for the worker; *after(result)* runs on the frame thread when it is done."""
        if self.channel is None:
            self.status = tr("No session: the project actions are not available yet.")
            return False
        self.queue.append(_Job(label, call, after, failed, quiet))
        self.shell.request_frame()
        return True

    def _start_next(self) -> None:
        if self.job is not None or not self.queue:
            return
        job = self.queue.popleft()
        job.build = BackgroundBuild(wake=self.shell.request_frame)
        self.job = job
        if not job.quiet:
            self.status = job.label
        job.build.start({"call": job.call}, name="chisurf-shell-project")

    def _collect(self) -> None:
        if self.job is None or self.job.build is None:
            return
        results = self.job.build.collect()
        if results is None:
            return
        job, self.job = self.job, None
        result, error = results.get("call", (None, None))
        if error is None and isinstance(result, dict) and result.get("ok") is False:
            error = RuntimeError(str(result.get("error") or "?"))
        if error is not None:
            _log.error("%s failed: %s", job.label, error)
            if job.failed is not None:
                job.failed(error)
            elif not job.quiet:
                self.status = tr("{label} failed: {error}").format(label=job.label, error=error)
            return
        if not job.quiet:
            self.status = tr("{label} done.").format(label=job.label.rstrip("…"))
        if job.after is not None:
            job.after(result)
        self.shell.request_frame()

    def _attach(self, session: Any) -> None:
        """Connect to *session*, follow its events and take the undo baseline."""
        self._session = session
        if getattr(session, "server", None) is None:
            self.status = tr(
                "This session has no local server: the project actions are not available."
            )
            return
        try:
            self.channel = ProjectChannel(session)
        except Exception as exc:  # noqa: BLE001 - the docks still work without the project menus
            _log.exception("connecting the project channel failed")
            self.status = tr("The project actions are not available: {error}").format(error=exc)
            return
        session.events.subscribe("", self._on_event)
        self._run(
            tr("Preparing undo…"),
            lambda: self.history.configure_science(self._capture_for_history, self._publish),
            lambda _result: self._history_ready(),
            quiet=True,
        )

    def _history_ready(self) -> None:
        self.history_ready = True

    @property
    def _live_channel(self) -> ProjectChannel:
        """The connected project channel; the callers only run once it exists."""
        if self.channel is None:
            raise RuntimeError("the project channel is not connected")
        return self.channel

    def _refresh_unless_none(self, result: Any) -> None:
        """Job callback: redraw the docks when the job produced something."""
        if result is not None:
            self._refresh_docks()

    def _capture_for_history(self) -> Any:
        """The project the history stores: the one a record job just captured, else a fresh capture."""
        project, self._prefetched = self._prefetched, None
        return project if project is not None else self._live_channel.capture(self.document.name)

    def _publish(self, project: Any) -> dict:
        """Replace the session's science with *project* (the history's undo and redo)."""
        return self._live_channel.api.restore_project_payload(project)

    def poll(self) -> None:
        """Once per frame, before the docks: attach, finish and start work, record, autosave."""
        session = getattr(self.data, "session", None)
        if session is not None and session is not self._session:
            self._attach(session)
        self._collect()
        if self._removing_fit and not self.data.busy:
            uid = self._removing_fit.pop(0)
            if not self.data.remove_fit(uid):
                self._removing_fit.insert(0, uid)
        if not self.busy and self._record_topic and self.history_ready:
            topic, self._record_topic = self._record_topic, None
            self._run(tr("Recording the change…"), lambda: self._record(topic), quiet=True)
        if not self.busy and self.channel is not None and time.monotonic() >= self._next_autosave:
            self._next_autosave = time.monotonic() + self.autosave.interval_s
            self._run(tr("Autosaving…"), self._autosave_tick, quiet=True)
        self._start_next()

    def next_frame_in(self) -> float | None:
        """Seconds until the next autosave is due (the shell wakes for it)."""
        if self.channel is None or not self.autosave.enabled:
            return None
        return max(0.0, self._next_autosave - time.monotonic())

    def _on_event(self, payload: dict) -> None:
        topic = str(payload.get("topic", ""))
        if any(topic == t or (t.endswith(".") and topic.startswith(t)) for t in RECORD_TOPICS):
            self._record_topic = self._record_topic or topic

    def note_command(self, summary: str) -> None:
        """A console command ran (``chisurf.run``): the next history step carries its *summary*.

        A step is recorded only when the science changed, as for every other change; a command that
        changed nothing (``print``) leaves no undo step.
        """
        self._record_topic = self._record_topic or str(summary)

    def _refresh_docks(self) -> None:
        """After the science was replaced: reopen the fit windows over the new fits and re-read."""
        for uid in list(self.data.windows):
            self.data.close_window(uid)
        self.data._dirty |= {"datasets", "fits", "windows", "current"}
        self.shell.request_frame()

    # ── undo / redo ───────────────────────────────────────────────────────

    def _record(self, topic: str) -> bool:
        """Worker: capture, and record one step when the science changed."""
        from chisurf.core.project.lifecycle import snapshot_fingerprint

        project = self._live_channel.capture(self.document.name)
        fingerprint = snapshot_fingerprint(project)
        if fingerprint == self._last_fingerprint:
            return False
        self._prefetched = project
        try:
            self.history.record(action_type=topic, summary=topic, persist=False)
        finally:
            self._prefetched = None
        self._last_fingerprint = fingerprint
        return True

    def can_undo(self) -> bool:
        return self.history_ready and self.history.step_target(-1) is not None

    def can_redo(self) -> bool:
        return self.history_ready and self.history.step_target(+1) is not None

    def undo(self) -> bool:
        """Go one step back in the history (Ctrl+Z)."""
        return self._step(-1)

    def redo(self) -> bool:
        """Go one step forward in the history (Ctrl+Y)."""
        return self._step(+1)

    def go_to_history(self, index: int) -> bool:
        """Go to step *index* of the history (the Log dock's *History*): its science is published."""
        if not self.history_ready or not self.history.can_navigate(int(index)):
            return False

        def call() -> Any:
            from chisurf.core.project.lifecycle import snapshot_fingerprint

            result = self.history.navigate(int(index))
            self._last_fingerprint = snapshot_fingerprint(self._live_channel.capture(self.document.name))
            return result

        return self._run(
            tr("Going to the history step…"),
            call,
            self._refresh_unless_none,
        )

    def clear_history(self) -> bool:
        """Forget the history's steps; what is open stays and is the new starting point."""
        if not self.history_ready:
            return False
        return self._run(tr("Clearing the history…"), self._reset_history, quiet=True)

    def _step(self, direction: int) -> bool:
        if not self.history_ready:
            return False
        # A change still being recorded is part of the history the step starts from.
        if self._record_topic:
            topic, self._record_topic = self._record_topic, None
            self._run(tr("Recording the change…"), lambda: self._record(topic), quiet=True)

        def call() -> Any:
            from chisurf.core.project.lifecycle import snapshot_fingerprint

            target = self.history.step_target(direction)
            if target is None:
                return None
            result = self.history.navigate(target)
            self._last_fingerprint = snapshot_fingerprint(self._live_channel.capture(self.document.name))
            return result

        label = tr("Undo…") if direction < 0 else tr("Redo…")
        return self._run(label, call, self._refresh_unless_none)

    # ── project files ─────────────────────────────────────────────────────

    def _unsaved(self) -> tuple[bool, bool]:
        """Worker: ``(has content, modified since the last save)``."""
        if not self._live_channel.content():
            return False, False
        try:
            project = self._live_channel.capture(self.document.name)
            return True, self.document.is_modified(project)
        except Exception:  # noqa: BLE001 - a failed dirty check must protect the user's work
            _log.exception("the unsaved-changes check failed")
            return True, True

    def guard(self, then: Callable[[], Any], *, quitting: bool = False) -> bool:
        """Run *then* once unsaved work is saved or given up -- after at most **one** question.

        *quitting* also asks "Quit ChiSurf?" for an empty session when
        ``gui.confirm_close_program`` is on (the Qt close event's second branch).
        """
        if self.channel is None:
            then()
            return True

        def decide(answer: tuple[bool, bool]) -> None:
            content, modified = answer
            if content and modified:
                self.dialogs.choice(
                    tr("Unsaved Project"),
                    tr("Save changes to the current project before continuing?"),
                    [(key, tr(label)) for key, label in SAVE_OPTIONS],
                    lambda key: self._saved_then(key, then),
                    default="cancel",
                )
            elif quitting and not content and _setting("gui", "confirm_close_program", True):
                self.dialogs.confirm(
                    tr("Quit"),
                    tr("Quit ChiSurf?"),
                    lambda yes: yes and then(),
                    default=False,
                )
            else:
                then()

        return self._run(tr("Checking for unsaved changes…"), self._unsaved, decide, quiet=True)

    def _saved_then(self, key: str | None, then: Callable[[], Any]) -> None:
        if key == "discard":
            then()
        elif key == "save":
            self.save(then=then)

    def save(self, *, then: Callable[[], Any] | None = None, save_as: bool = False) -> bool:
        """*Save Project* (Ctrl+S): to the project's file, or ask for one; a database version on MMFDB."""
        from chisurf.core.project import storage

        try:
            backend = "file" if save_as else storage.select_backend()
        except Exception as exc:  # noqa: BLE001 - a broken configuration is said, not raised
            self.dialogs.message(tr("Save Failed"), str(exc))
            return False
        if backend == "mmfdb":
            return self._ask_database_save(then)
        if not save_as and self.document.path is not None:
            return self._save_file(Path(self.document.path), then)
        title = tr("Export Project as .cs.pto") if save_as else tr("Save Project")
        name = display_name(self.document.name if self.document.name != "untitled" else None)
        self.open_file_dialog(
            title,
            "save",
            lambda path: self._save_file(Path(path), then),
            filename=f"{name}{PROJECT_SUFFIX}",
        )
        return True

    def save_as(self) -> bool:
        """*Export Project…* (Ctrl+Shift+S): save under a new file, which becomes the project's."""
        return self.save(save_as=True)

    def _save_file(self, destination: Path, then: Callable[[], Any] | None = None) -> bool:
        from chisurf.core.project import storage

        if not str(destination).lower().endswith(PROJECT_SUFFIX):
            destination = Path(f"{destination}{PROJECT_SUFFIX}")
        name = display_name(destination.name)

        def call() -> tuple[Any, Path]:
            project = self._live_channel.capture(name)
            return project, Path(storage.save_file(project, destination))

        def after(result: tuple[Any, Path]) -> None:
            project, saved = result
            before = self.document.clone()
            self.document.record_file_save(project, saved)
            self._discard_autosave(before, self.document)
            self._add_recent(saved)
            self.status = tr("Saved {path}.").format(path=saved)
            if then is not None:
                then()

        return self._run(
            tr("Saving the project…"),
            call,
            after,
            failed=lambda error: self.dialogs.message(tr("Save Failed"), str(error)),
        )

    def _ask_database_save(self, then: Callable[[], Any] | None) -> bool:
        from chisurf.emtk.fit_docks import load_view

        locked = bool(self.document.project_id)
        model = SaveProjectForm(display_name(self.document.name), name_locked=locked)

        def pressed(key: str) -> bool:
            self.form = None if key in ("ok", "cancel", "close") else self.form
            if key == "ok" and model.project_name.strip():
                self._save_database(model, then)
            return key in ("ok", "cancel", "close")

        title = tr("Save New Version") if self.document.version_id else tr("Save Project")
        self.form = FormDialog(
            title, load_view("save_project"), model, (("ok", "OK"), ("cancel", "Cancel")), pressed
        )
        return True

    def _save_database(self, model: SaveProjectForm, then: Callable[[], Any] | None) -> bool:
        from chisurf.core.project import storage

        def call() -> tuple[Any, dict]:
            project = self._live_channel.capture(model.project_name.strip())
            project.name = model.project_name.strip()
            result = storage.save_database(
                project,
                project_id=self.document.project_id,
                parent_version_id=self.document.version_id,
                notes=model.notes,
                visibility=model.visibility,
            )
            return project, result

        def after(result: tuple[Any, dict]) -> None:
            project, saved = result
            before = self.document.clone()
            self.document.record_database_save(project, saved)
            self._discard_autosave(before, self.document)
            if then is not None:
                then()

        return self._run(
            tr("Saving the project…"),
            call,
            after,
            failed=lambda error: self.dialogs.message(tr("Save Failed"), str(error)),
        )

    def open_project(self) -> bool:
        """*Open Project…*: guard, then choose a ``.cs.pto`` (the MMFDB browser on a database)."""
        from chisurf.core.project import storage

        try:
            backend = storage.select_backend()
        except Exception as exc:  # noqa: BLE001
            self.dialogs.message(tr("Open Project Failed"), str(exc))
            return False
        if backend != "file":
            if "project_browser" in self.shell.by_id:
                self.shell.open_plugin("project_browser")
                return True
            self.dialogs.message(
                tr("Open Project Failed"),
                tr(
                    "Projects in the database are opened with the project browser, which is not available here."
                ),
            )
            return False
        return self.guard(lambda: self.open_file_dialog(tr("Open Project"), "open", self.open_path))

    def open_recent(self, path: str) -> bool:
        """A *Recent Projects* entry: guard, then open it."""
        return self.guard(lambda: self.open_path(path))

    def open_path(self, path: str | Path) -> bool:
        """Replace the session with the project in *path* (no question: the caller guarded)."""
        from chisurf.core.project import recent

        path = Path(path)
        if path.is_dir():
            path = path / f"project{PROJECT_SUFFIX}"
        if not path.is_file():
            self.recent = recent.removed(self.recent, path)
            recent.store(self.recent)
            self.dialogs.message(
                tr("Open Project Failed"),
                tr("There is no ChiSurf project at {path}.").format(path=path),
            )
            return False

        def call() -> Any:
            result = self._live_channel.api.load_project(str(path))
            if not isinstance(result, dict) or result.get("ok") is not True:
                raise RuntimeError((result or {}).get("error") or tr("The project was not opened."))
            project = self._live_channel.capture(display_name(path.name))
            self._reset_history()
            return project

        def after(project: Any) -> None:
            import chisurf

            self.document.record_file_save(project, path)
            self._add_recent(path)
            chisurf.working_path = path.parent
            self._refresh_docks()
            self.status = tr("Opened {path}.").format(path=path)

        return self._run(
            tr("Opening the project…"),
            call,
            after,
            failed=lambda error: self.dialogs.message(tr("Open Project Failed"), str(error)),
        )

    def import_project(self) -> bool:
        """*Import Project…*: open a file (file storage) or import a verified copy into MMFDB."""
        from chisurf.core.project import storage

        try:
            backend = storage.select_backend()
        except Exception as exc:  # noqa: BLE001
            self.dialogs.message(tr("Import Failed"), str(exc))
            return False
        if backend == "file":
            return self.guard(
                lambda: self.open_file_dialog(tr("Import Project"), "open", self.open_path)
            )
        self.open_file_dialog(tr("Import Project"), "open", self._import_preview)
        return True

    def _import_preview(self, path: str) -> None:
        from chisurf.core.project import storage

        def ask(preview: dict) -> None:
            collisions = preview["collisions"]
            origin = preview["origin"]
            if any(ids for ids in collisions.values()):
                lines = []
                for category, ids in collisions.items():
                    if ids:
                        shown = [f"  - {i}" for i in list(ids)[:20]]
                        more = len(ids) - 20
                        lines += [f"{category} ({len(ids)}):", *shown]
                        if more > 0:
                            lines.append(tr("  ... and {n} more").format(n=more))
                self.dialogs.choice(
                    tr("Import — Collision Warning"),
                    tr(
                        "The following IDs from the archive already exist in the database. "
                        "Original project: {project} v{version}. On confirmation, conflicting IDs "
                        "will be remapped."
                    ).format(
                        project=origin.get("project_id", "?"),
                        version=origin.get("version_number", "?"),
                    ),
                    [("import", tr("Remap & Import")), ("cancel", tr("Cancel"))],
                    lambda key: key == "import" and self._import(path, True),
                    detail="\n".join(lines),
                )
            else:
                self.dialogs.confirm(
                    tr("Confirm Import"),
                    tr("No collisions detected. Original: {project}. Proceed?").format(
                        project=origin.get("project_id", "?")
                    ),
                    lambda yes: yes and self._import(path, False),
                )

        def preview() -> dict:
            self._import_client = storage.database_client()
            return storage.import_preview(path, client=self._import_client)

        self._run(
            tr("Checking the archive…"),
            preview,
            ask,
            failed=lambda error: self.dialogs.message(tr("Import Failed"), str(error)),
        )

    def _import(self, path: str, resolve: bool) -> bool:
        from chisurf.core.project import storage

        return self._run(
            tr("Importing the project…"),
            lambda: storage.import_database(
                path, resolve_collisions=resolve, client=self._import_client
            ),
            lambda result: self.dialogs.message(
                tr("Import Complete"),
                tr("Project imported. ID: {project} v{version}").format(
                    project=result["project_id"], version=result["version_number"]
                ),
            ),
            failed=lambda error: self.dialogs.message(tr("Import Failed"), str(error)),
        )

    def close_project(self, *, reinitialize: bool = False) -> bool:
        """*Close Project* (and *Reinitialize*, Ctrl+R): guard, then an empty session."""

        def clear() -> None:
            def call() -> Any:
                result = self._live_channel.api.session_restore()
                if isinstance(result, dict) and result.get("ok") is False:
                    raise RuntimeError(result.get("error") or "?")
                self._reset_history()
                return result

            def after(_result: Any) -> None:
                self.document.reset()
                self._refresh_docks()
                if reinitialize:
                    self.dialogs.message(
                        tr("Reinitialization Complete"),
                        tr("ChiSurf has been reinitialized. All scientific data has been cleared."),
                    )

            failed_title = (
                tr("Reinitialization Error") if reinitialize else tr("Close Project Failed")
            )
            self._run(
                tr("Closing the project…"),
                call,
                after,
                failed=lambda error: self.dialogs.message(failed_title, str(error)),
            )

        return self.guard(clear)

    def _reset_history(self) -> None:
        """Worker: a new document starts a new history at its current science."""
        from chisurf.core.project.lifecycle import snapshot_fingerprint

        project = self._live_channel.capture(self.document.name)
        self._prefetched = project
        try:
            self.history.clear()
        finally:
            self._prefetched = None
        self._last_fingerprint = snapshot_fingerprint(project)
        self._record_topic = None

    def _add_recent(self, path: str | Path) -> None:
        from chisurf.core.project import recent

        self.recent = recent.added(self.recent, path)
        recent.store(self.recent)

    def clear_recent(self) -> None:
        """*Clear Recent Projects*."""
        from chisurf.core.project import recent

        self.recent = []
        recent.store([])

    def _discard_autosave(self, *documents: Any) -> None:
        """Delete the autosave copies an explicit save made obsolete (never raises)."""
        from chisurf.core.project.lifecycle import Autosave

        for document in documents:
            try:
                Autosave.target(document, _working_path()).unlink(missing_ok=True)
            except OSError:
                _log.exception("could not remove the autosave copy")

    def _autosave_tick(self) -> Path | None:
        """Worker: write the silent copy when due and changed (never a question, never a history row)."""
        from chisurf.core.project import storage

        if not self.autosave.enabled or not self._live_channel.content():
            return None
        project = self._live_channel.capture(display_name(self.document.name))
        return self.autosave.run(
            project, storage.save_file, self.document, _working_path(), time.monotonic()
        )

    def autosave_now(self) -> bool:
        """Run the autosave tick at once (its interval still applies)."""
        self._next_autosave = time.monotonic() + self.autosave.interval_s
        return self._run(tr("Autosaving…"), self._autosave_tick, quiet=True)

    # ── quit and the fit window's × ───────────────────────────────────────

    def request_quit(self) -> bool:
        """*Quit* (Ctrl+Q) and the window's close button: one question at most, then close."""
        if self.quit_confirmed:
            return True
        if self._quitting:
            return False
        self._quitting = True

        def confirmed() -> None:
            self.quit_confirmed = True
            self.shell.request_close()

        if not self.guard(confirmed, quitting=True):
            self._quitting = False
            return False
        return False

    def answered_quit(self) -> None:
        """The quit question was declined: a later close asks again."""
        self._quitting = False

    def guard_fit_windows(self) -> None:
        """A fit window closed with its ×: ask, then remove the fit (Qt's fit window does this).

        Runs before the data docks see the closed window. With
        ``gui.confirm_close_fit`` off the window just closes and the fit stays.
        """
        if not _setting("gui", "confirm_close_fit", True):
            return
        docks = self.shell.docks
        for uid, window in list(self.data.windows.items()):
            dock = docks.window(window.key)
            if dock is None or dock.visible:
                continue
            docks.show(window.key)
            if uid in self._asking_fit:
                continue
            self._asking_fit.add(uid)
            name = next((r["name"] for r in self.data.datasets.fits if r["uid"] == uid), uid)
            self.dialogs.confirm(
                tr("Close fit"),
                tr(
                    "Remove the fit {name}? Its window closes and the fit leaves the session."
                ).format(name=name),
                lambda yes, u=uid: self._fit_answer(u, yes),
                default=False,
            )

    def _fit_answer(self, uid: str, yes: bool) -> None:
        self._asking_fit.discard(uid)
        if yes:
            self._removing_fit.append(uid)
            self.shell.request_frame()

    # ── fit export and import (File ▸ Fits) ───────────────────────────────

    def _fit_call(self, method: str, params: dict) -> dict:
        """Worker: one ``fit.*`` call on the project connection; a refusal raises with its reason."""
        result = self._live_channel.client.call(method, params)
        if isinstance(result, dict) and result.get("ok") is False:
            raise RuntimeError(str(result.get("error") or method))
        return result if isinstance(result, dict) else {}

    def load_fit(self) -> bool:
        """*Load Fit*: add the fits and data of a fit document (``.fit.cs.pto``) or project to the session."""
        if self.channel is None:
            return False

        def chosen(path: str) -> None:
            self._run(
                tr("Loading the fit…"),
                lambda: self._fit_call("fit.import", {"filename": str(path)}),
                lambda result: self._fits_loaded(result, path),
                failed=lambda error: self.dialogs.message(tr("Load Fit"), str(error)),
            )

        self.open_file_dialog(tr("Load Fit"), "open", chosen, filters=FIT_FILTER)
        return True

    def _fits_loaded(self, result: dict, path: str) -> None:
        count = len(result.get("fit_uids") or [])
        self.status = tr("{count} fit(s) loaded from {name}.").format(
            count=count, name=Path(path).name
        )
        self.data._dirty |= {"datasets", "fits", "windows", "current"}
        self.shell.request_frame()

    def save_current_fit(self) -> bool:
        """*Current Fit* (Ctrl+Alt+S): the current fit's curves, fit document and report, in a folder."""
        uid = self.data.current_uid
        if self.channel is None or not uid:
            return False

        def chosen(folder: str) -> None:
            self._run(
                tr("Saving the fit…"),
                lambda: self._fit_call("fit.export", {"fit_uid": uid, "target_path": str(folder)}),
                lambda result: self._fit_saved(result, folder),
                failed=lambda error: self.dialogs.message(tr("Save Fit"), str(error)),
            )

        self._open_folder_dialog(tr("Save Fit"), chosen)
        return True

    def save_all_fits(self) -> bool:
        """*All Fits*: a folder per fit and ``all_fits.docx``; folders already there are asked about once."""
        if self.channel is None or not self.data.datasets.fits:
            return False

        def write(folder: str, existing: str) -> None:
            self._run(
                tr("Saving all fits…"),
                lambda: self._fit_call(
                    "fit.export_all", {"target_path": str(folder), "existing": existing}
                ),
                lambda result: self._fit_saved(result, folder),
                failed=lambda error: self.dialogs.message(tr("Save Fits"), str(error)),
            )

        def ask(folder: str, there: list) -> None:
            if not there:
                write(folder, "skip")
                return

            def answered(key: str) -> None:
                if key in ("overwrite", "skip"):
                    write(folder, key)

            self.dialogs.choice(
                tr("Folders exist"),
                tr("{count} fit folder(s) already exist in {folder}.").format(
                    count=len(there), folder=folder
                ),
                [("overwrite", tr("Overwrite")), ("skip", tr("Skip")), ("cancel", tr("Cancel"))],
                answered,
                detail="\n".join(there),
            )

        def chosen(folder: str) -> None:
            self._run(
                tr("Checking the folder…"),
                lambda: self._fit_call("fit.export_existing", {"target_path": str(folder)}),
                lambda result: ask(folder, list(result.get("existing") or [])),
                failed=lambda error: self.dialogs.message(tr("Save Fits"), str(error)),
            )

        self._open_folder_dialog(tr("Save Fits"), chosen)
        return True

    def _fit_saved(self, result: dict, folder: str) -> None:
        skipped = len(result.get("skipped") or [])
        self.status = tr("Saved to {folder}.").format(folder=folder) + (
            " " + tr("{count} existing folder(s) skipped.").format(count=skipped) if skipped else ""
        )
        self.shell.request_frame()

    def _open_folder_dialog(self, title: str, done: Callable[[str], Any]) -> None:
        """A folder dialog over the shell, opening at the current fit's data folder when it has one."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        directory = str(_working_path())
        self.file_dialog = FileDialog(title, mode="folder", directory=directory)
        self._file_window = DialogWindow(title, size=(760, 540))
        self._file_window.show()
        self._file_done = done
        self.shell.request_frame()

    def close_fit(self) -> bool:
        """*Close Fit*: the current fit, asked as its window's × asks."""
        window = self.data.windows.get(self.data.current_uid)
        if window is None:
            return False
        self.shell.docks.hide(window.key)
        self.guard_fit_windows()
        return True

    def close_all_fits(self) -> bool:
        """*Close all fits*: every fit leaves the session (no question, as in the Qt shell)."""
        uids = [row["uid"] for row in self.data.datasets.fits]
        if not uids:
            return False
        self._removing_fit.extend(u for u in uids if u not in self._removing_fit)
        self.shell.request_frame()
        return True

    # ── settings ──────────────────────────────────────────────────────────

    def edit_settings(self) -> None:
        """*Settings ▸ Edit*: the Settings tool."""
        if "setup" in self.shell.by_id:
            self.shell.open_plugin("setup")

    def rda_axis(self) -> None:
        """*Settings ▸ FRET RDA axis…*: the distance grid, applied by *Save axis*."""
        from chisurf.emtk.fit_docks import load_view

        def updated() -> None:
            self._run(tr("Updating the fits…"), self._update_fits)
            self.status = tr("FRET RDA axis saved.")

        model = RdaAxisForm(on_saved=updated)
        self.form = FormDialog(
            tr("FRET RDA axis"),
            load_view("fret_rda_axis"),
            model,
            (("close", "Close"),),
            lambda key: self._close_form(),
        )

    def _update_fits(self) -> None:
        for row in self._live_channel.api.list_fits() or []:
            self._live_channel.client.call("fit.update", {"fit_uid": str(row.get("uid", ""))})

    def data_loading(self) -> None:
        """*Settings ▸ Data loading…*: the slow-storage staging settings (written as they change)."""
        import json

        from chisurf.core.fio.staging_settings import VIEW_JSON, DataLoadingSettingsModel

        spec = json.loads(VIEW_JSON.read_text(encoding="utf-8"))
        self.form = FormDialog(
            tr("Data loading"),
            spec,
            DataLoadingSettingsModel(),
            (("close", "Close"),),
            lambda key: self._close_form(),
        )

    def _close_form(self) -> bool:
        self.form = None
        return True

    def reset_local_settings(self) -> None:
        """*Reset local settings*: the settings folder goes back to the shipped one."""
        from chisurf.core.settings.cleanup import clear_settings_folder

        def answered(yes: bool) -> None:
            if yes:
                self._done(
                    clear_settings_folder,
                    tr("Settings Reset"),
                    tr("Local settings have been reset successfully."),
                )

        self.dialogs.confirm(
            tr("Reset local settings"),
            tr("Reset your local settings to the shipped defaults?"),
            answered,
        )

    def clear_logging_files(self) -> None:
        """*Clear logging files*."""
        from chisurf.core.settings.cleanup import clear_logging_files

        self._done(
            clear_logging_files, tr("Logging files"), tr("The logging files have been cleared.")
        )

    def clear_user_styles(self) -> None:
        """*Clear user styles*: the style files in the settings folder."""
        import chisurf

        folder = chisurf.core.settings.get_path("settings") / "styles"
        files = list(folder.glob("*.css")) if folder.is_dir() else []
        for path in files:
            try:
                path.unlink()
            except OSError as exc:
                _log.warning("could not delete style file %s: %s", path, exc)
        self.dialogs.message(
            tr("Styles Reset"),
            tr(
                "User style files have been cleared. Restart the application to apply default styles."
            )
            if files
            else tr("No user style files found."),
        )

    def clear_user_plugins(self) -> None:
        """*Clear user plugins*."""
        from chisurf.core.settings.cleanup import clear_user_plugins_folder

        self._done(
            clear_user_plugins_folder,
            tr("User Plugins Reset"),
            tr("User plugins folder has been cleared. Restart the application to apply changes."),
        )

    def _done(self, action: Callable[[], Any], title: str, message: str) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - say what failed instead of raising into a frame
            self.dialogs.message(title, str(exc))
            return
        self.dialogs.message(title, message)

    # ── drawing ───────────────────────────────────────────────────────────

    def open_file_dialog(
        self,
        title: str,
        mode: str,
        done: Callable[[str], Any],
        *,
        filename: str = "",
        filters: Any = PROJECT_FILTER,
    ) -> None:
        """A file dialog over the shell (project files unless *filters* says otherwise); *done(path)* gets the choice."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        directory = (
            str(Path(self.document.path).parent) if self.document.path else str(_working_path())
        )
        self.file_dialog = FileDialog(
            title, mode=mode, filters=filters, directory=directory, filename=filename
        )
        self._file_window = DialogWindow(title, size=(760, 540))
        self._file_window.show()
        self._file_done = done
        self.shell.request_frame()

    def choose_file(self, path: str | Path) -> bool:
        """Answer the open file dialog with *path*, as its action button does (a tour, a test)."""
        if self.file_dialog is None:
            return False
        self.file_dialog = None
        done, self._file_done = self._file_done, None
        if done is not None:
            done(str(path))
        return True

    def draw(self, box) -> None:
        """The open file dialog, form and question over the whole shell (drawn last)."""
        if self.file_dialog is not None:
            window = self._file_window
            closed = window.begin(box) or escape_pressed()
            paths = self.file_dialog.draw()
            window.end()
            if closed or paths is False:
                self.file_dialog = None
                self._file_done = None
            elif paths:
                self.file_dialog = None
                done, self._file_done = self._file_done, None
                if done is not None:
                    done(str(paths[0]))
        if self.form is not None and not self.form.draw(box):
            self.form = None
        quit_question = self._quitting and self.dialogs.modal
        self.dialogs.draw(box)
        if quit_question and not self.dialogs.modal and not self.quit_confirmed:
            self.answered_quit()

    def contains(self, x: float, y: float) -> bool:
        """Whether (x, y) is on one of the dialogs these menus have open."""
        windows = [self._file_window if self.file_dialog is not None else None]
        windows.append(self.form.window if self.form is not None else None)
        on = any(w is not None and w.contains(x, y) for w in windows)
        return on or self.dialogs.contains(x, y)

    def close(self) -> None:
        """Stop following the session and close the project channel."""
        if self._session is not None:
            try:
                self._session.events.unsubscribe("", self._on_event)
            except Exception:  # noqa: BLE001
                pass
        if self.job is not None and self.job.build is not None:
            self.job.build.collect(wait=True)
        if self.channel is not None:
            self.channel.close()
            self.channel = None


__all__ = [
    "FormDialog",
    "MenuAction",
    "PROJECT_FILTER",
    "ProjectChannel",
    "RECORD_TOPICS",
    "RdaAxisForm",
    "SaveProjectForm",
    "ShellProject",
    "display_name",
]
