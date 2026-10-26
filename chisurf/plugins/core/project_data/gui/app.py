"""Project data: the linked files of a project, finding moved ones, making the project self-contained.

The window draws ``project_data.view.json`` over :class:`ProjectDataModel`, a
:class:`~chisurf.core.project.link_repair.LinkRepairModel` whose long actions (reading whole files
for their checksums, embedding, walking a folder) run in the background. It works on the session
open in ChiSurf (the shell registers its datasets as the ``project_links`` source) or on a project
file -- the demonstration, which *Load example* writes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.core.project.link_repair import LinkRepairModel, ProjectFileSource
from chisurf.emtk.background_build import BackgroundBuild
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

HERE = Path(__file__).resolve().parent

#: The ``session_sources`` kind the shell registers its linked datasets under.
SOURCE_KIND = "project_links"


def session_source() -> Any:
    """The open session's link source (the shell's data docks), if a shell runs."""
    from chisurf.emtk.session_sources import sources

    found = sources(SOURCE_KIND)
    return found[-1] if found else None


class ProjectDataModel(LinkRepairModel):
    """The tool's model: the repair actions, with the long ones handed to the app's worker."""

    def __init__(self, source: Any = None) -> None:
        super().__init__(source)
        #: A long action the app runs on its worker: ``"check"``, ``"self_contained"``, ``"search"``.
        self.job = ""
        self.busy = False

    @property
    def source_text(self) -> str:
        """Which project the table shows."""
        if self.source is None:
            return tr("No project: open one in ChiSurf, or press Load example.")
        if isinstance(self.source, ProjectFileSource):
            return tr("Project file: {path}").format(path=self.source.path)
        path = self.source.project_path()
        return tr("The open session ({path})").format(path=path or tr("not saved yet"))

    def enabled(self, action: str) -> bool:
        """Which buttons can act now (the view asks per button)."""
        if self.busy and action not in ("load_example",):
            return False
        return {
            "use_session": session_source() is not None and self.source is not session_source(),
            "check_checksums": bool(self.rows),
            "request_search": self.can_search(),
            "search_mmfdb": self.can_search(),
            "request_replace": self.can_replace(),
            "use_anyway": self.can_use_anyway(),
            "use_candidate": self.can_use_candidate(),
            "make_self_contained": self.can_make_self_contained(),
            "save_project": isinstance(self.source, ProjectFileSource) and self.source.dirty,
        }.get(action, True)

    # long actions: the app's worker runs them
    def check_checksums(self) -> None:
        """Compare every linked file's checksum (reads the files; in the background)."""
        self.job = "check"

    def make_self_contained(self) -> None:
        """Embed every link (each checked by its checksum first; in the background)."""
        self.job = "self_contained"

    def save_project(self) -> None:
        """Write a project file opened here back to disk."""
        if isinstance(self.source, ProjectFileSource):
            saved = self.source.save()
            self.status_text = tr("Saved {path}.").format(path=saved)
            self.refresh()

    def load_example(self) -> None:
        """Ask the app to write and open the demonstration project."""
        self.request = "example"

    def use_session(self) -> None:
        """Show the open session's linked data."""
        self.source = session_source()
        self.select_dataset(None)
        self.refresh()


class ProjectDataApp(ImApp):
    """The *Project data* window."""

    def __init__(self, model: ProjectDataModel | None = None) -> None:
        self.model = model or ProjectDataModel(session_source())
        spec = json.loads((HERE / "project_data.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (980, 640))
        self.panels = [p for p in spec["sections"] if p.get("type") == "panel"]
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self._dialog_for = ""
        self.worker = BackgroundBuild(wake=self.request_frame)
        self.help_window = EmTkHelpWindow(
            title="Project data — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        if self.model.source is not None:
            self.model.refresh()
        super().__init__(self.render, continuous=False)

    # -- what a hand-off or a menu asks ------------------------------------------- #
    def show(self, mode: str) -> None:
        """Open on the session's data: ``"locate"``, ``"self_contained"`` (embed every link) or
        ``"check"``."""
        if session_source() is not None:
            self.model.use_session()
        if mode == "self_contained":
            self.model.make_self_contained()
        elif mode == "locate" and self.model.unresolved:
            self.model.select_dataset(self.model.unresolved[0])
            self.model.status_text = tr(
                "{n} data file(s) of this project were not found where they were linked. "
                "Select one and search a folder, or point at the file."
            ).format(n=len(self.model.unresolved))
        self.request_frame()

    def load_example(self) -> None:
        """Write the demonstration project afresh and open it."""
        from chisurf.plugins.core.project_data.demo import make_demo

        path = make_demo(overwrite=True)
        self.model.source = ProjectFileSource(path)
        self.model.select_dataset(None)
        self.model.refresh()
        missing = self.model.unresolved
        if missing:
            self.model.select_dataset(missing[0])
        self.model.status_text = tr(
            "Demonstration: {name} was moved to a backup folder. Search the folder {folder}."
        ).format(name=missing[0]["name"] if missing else "", folder=path.parent.parent / "backup")
        self.tour.notify_used("load_example")

    # -- one frame ------------------------------------------------------------------ #
    def render(self) -> None:
        self._poll_worker()
        self._requests()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin(tr("Project data"), box)
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        self.form.rects.clear()
        for panel in self.panels:
            im.separator_text(tr(panel["title"]))
            draw_sections(panel["sections"], self.model, self.form, titles=False)
        if self.model.busy:
            im.text_disabled(tr("Working…"))
        im.end()
        self._draw_dialog()
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _requests(self) -> None:
        request, self.model.request = self.model.request, ""
        if request == "example":
            self.load_example()
        elif request in ("folder", "file") and self.dialog is None:
            self._dialog_for = request
            title = tr("Search for the file in…") if request == "folder" else tr("Use this file")
            self.dialog = FileDialog(title, mode="folder" if request == "folder" else "open")
        job, self.model.job = self.model.job, ""
        if job == "check":
            self._start({"check": lambda: self.model.refresh(check_hash=True)})
        elif job == "self_contained":
            self._start({"self_contained": lambda: LinkRepairModel.make_self_contained(self.model)})

    def _start(self, jobs: dict) -> None:
        if self.worker.start(jobs, name="chisurf-project-data"):
            self.model.busy = True
            self.model.status_text = tr("Working…")

    def _poll_worker(self) -> None:
        results = self.worker.collect()
        if results is None:
            return
        self.model.busy = False
        for key, (_made, error) in results.items():
            if error is not None:
                self.model.status_text = tr("{action} failed: {error}").format(
                    action=key, error=error
                )
            elif key == "check":
                self.model.status_text = self.model.summary_text
            elif key == "self_contained":
                self.tour.notify_used("make_self_contained")
            elif key == "search":
                self.tour.notify_used("request_search")

    def _draw_dialog(self) -> None:
        if self.dialog is None:
            return
        if im.begin(self.dialog.title):
            result = self.dialog.draw()
            if result:
                chosen, self.dialog = str(result[0]), None
                if self._dialog_for == "folder":
                    self._start({"search": lambda: self.model.search(chosen)})
                else:
                    self.model.replace(chosen)
                    self.tour.notify_used("request_replace")
            elif result is False:
                self.dialog = None
        im.end()

    # -- persistence ---------------------------------------------------------------- #
    def export_settings(self) -> dict:
        """Nothing to remember beyond the folded sections."""
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        folds = (settings or {}).get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})


def receive(app: Any, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``project_data``): open on the session's data."""
    mode = str(payload.get("mode", "check"))
    if mode not in ("check", "locate", "self_contained"):
        raise ValueError(f"unknown mode {mode!r}")
    app.show(mode)


def make_app() -> ProjectDataApp:
    """Build the *Project data* window (the manifest's ``entrypoints.emtk``)."""
    return ProjectDataApp()
