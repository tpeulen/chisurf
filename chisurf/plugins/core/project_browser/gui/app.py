"""Native project/version browser with the original database and archive actions."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im, overlays
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form
from emtk.widgets.menus import MenuItem, Popup

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .controller import ProjectJobs
from .model import ProjectBrowserModel
from .panel import ProjectPanel

SPEC = json.loads(Path(__file__).with_name("project_browser_emtk.view.json").read_text(encoding="utf-8"))
DETAIL_TABS = (("Summary", "summary"), ("Artifacts", "artifacts"), ("Parameters", "parameters"),
               ("Branches", "branches"), ("Version graph", "graph"))


class ProjectBrowserApp(ImApp):
    def __init__(self, model=None, autoload=True):
        self.model = model or ProjectBrowserModel()
        self.jobs = ProjectJobs(self.model)
        self.autoload = autoload
        self.loaded = False
        self.expanded = set()
        self.selected_ids = set()
        self.dialog = self.file_window = None
        self.file_action = ""
        self.modal = ""
        self.modal_window = DialogWindow("Project action", size=(520, 320), fit_height=True)
        self.pending = None
        self.context_menu = None
        self.context_actions = {}
        self.notice = ""
        self.name = self.notes = ""
        self.visibility = 0
        self.allow_name_edit = True
        self.details_tab = "Summary"
        self.help_window = EmTkHelpWindow(
            title="Project Browser — Help", resource=Path(__file__).with_name("help.md"), owner=self
        )
        self.item_rects: dict[str, tuple] = {}
        self.tour = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"),
                                   get_target_rect=lambda k: self.item_rects.get(k), owner=self,
                                   wait_for_controls=True)
        #: None until the user decides: the ID and Status columns are shown when the table is wide enough for all nine.
        self.show_id = self.show_status = None
        self.panel = ProjectPanel(self)
        self.forms = {n: FormState(on_used=self.tour.notify_used) for n in ("toolbar", "search", "browser", "details", "dialog")}
        self.docks = DockManager(Split("v", 0.58, Region("browser"), Region("details")), name="project_browser")
        self.docks.add_window("browser", "Projects and Versions", self.browser, dock="browser", closable=False)
        self.docks.add_window("details", "Selected Project Details", self.details, dock="details", closable=False)
        self.native_layouts = {"main": self.docks}
        super().__init__(self.render, continuous=False)

    def error(self, action):
        self.notice = ""  # a new action ends the last one's message
        try:
            return action()
        except Exception as exc:
            self.model.status = "Error: " + str(exc)
            return None

    def refresh(self):
        self.jobs.start("Loading projects", self.model.refresh)

    def open_selected(self):
        version = self.model.require_version(latest=True)
        self.jobs.start(
            "Restoring project",
            lambda: self.model.fetch_restore(version),
            lambda result: self.model.apply_restore(result, version["version_id"]),
        )

    def begin_save(self):
        context = self.model.context
        self.allow_name_edit = not bool(
            getattr(context, "_current_project_id", None)
            or getattr(context, "_current_project_version_id", None)
        )
        self.name = getattr(context, "_current_project_name", "")
        self.visibility = (
            1 if getattr(context, "_current_project_visibility", "private") == "public" else 0
        )
        self.notes = ""
        self.modal = "save"
        self.modal_window.title = "Save Project" if self.allow_name_edit else "Save New Version"

    def save(self):
        payload = self.model.save_snapshot(self.name)
        name, visibility, notes = self.name, ["private", "public"][self.visibility], self.notes

        def accepted(result):
            result = {
                **result,
                "project_name": name,
                "visibility": result.get("visibility", visibility),
            }
            self.model.update_current(result)
            self.notice = f"Saved '{name}' as version {result.get('version_number', '?')}."
            self.refresh()

        self.jobs.start(
            "Saving project",
            lambda: self.model.save_remote(name, visibility, notes, payload),
            accepted,
        )
        self.modal = ""

    def choose_file(self, action):
        if action == "export":
            version = self.model.require_version()
            self.pending = dict(version)
            title, mode = "Export Project as .cs.pto", "save"
            filename = f"{version.get('project_name', 'project')}_v{version.get('version_number', 1)}.cs.pto"
        else:
            title, mode, filename = "Import Project", "open", ""
        self.file_action = action
        self.dialog = FileDialog(
            title,
            mode=mode,
            filters="ChiSurf Project (*.cs.pto *.csp);;All files (*)",
            directory=self.model.last_directory or None,
        )
        if filename:
            self.dialog.filename = filename
        self.file_window = DialogWindow(title, size=(780, 560))

    def import_preview(self, path):
        def accepted(preview):
            self.pending = {"path": str(path), "preview": preview}
            self.model.status = "Archive checked: confirm to import it."
            self.modal = "import"
            self.modal_window.title = "Confirm Project Import"

        self.jobs.start(
            "Checking project archive", lambda: self.model.preview_import(path), accepted
        )

    def confirm_import(self):
        pending = self.pending
        self.jobs.start(
            "Importing project",
            lambda: self.model.import_archive(pending["path"], pending["preview"]),
            lambda result: self.import_completed(result),
        )
        self.modal = ""

    def import_completed(self, result):
        self.notice = f"Imported project {result.get('project_id', '?')}, version {result.get('version_number', '?')}."
        self.refresh()

    def begin_delete(self):
        self.pending = dict(self.model.require_version())
        self.modal = "delete"
        self.modal_window.title = "Confirm Delete"

    def confirm_delete(self):
        version = self.pending
        self.jobs.start(
            "Deleting version", lambda: self.model.delete(version), lambda result: self.refresh()
        )
        self.modal = ""

    def inspect(self):
        version = dict(self.model.require_version(latest=True))

        def accepted(result):
            self.model.artifacts = result["artifacts"]
            self.model.parameters = result["parameters"]
            self.model.branches = result["branches"]
            self.model.graph = result["graph"]
            self.model.status = "Loaded version artifacts, fit parameters and branches."

        self.jobs.start("Loading version details", lambda: self.model.details(version), accepted)


    # -- selection and the context menu ------------------------------------------------------------------ #
    def column_shown(self, name):
        """Whether the ID / Status column is shown: the user's choice, or while undecided whether the table has room for every column."""
        value = getattr(self, name)
        if value is not None:
            return bool(value)
        rect = self.item_rects.get("tree_rows")
        return bool(rect and rect[2] >= 1020.0)

    def select(self, row_id):
        """A row of the tree was selected (a project means its newest version, a version means itself)."""
        self.model.selected_id = row_id
        self.selected_ids = {row_id} if row_id else set()
        self.model.artifacts = []
        self.model.parameters = []
        self.model.branches = []
        self.model.graph = {}
        self.tour.notify_used("versions")

    def open_context_menu(self, record, position):
        """The Qt-less tree's right-click menu: restore, inspect, export, delete (a project row offers the first two)."""
        project = not record.get("parent_id")
        entries = [
            ("Open / Restore", "Restore this selection.", self.panel.open),
            ("Inspect version", "List stored artifacts, parameters and version ancestry.", self.panel.inspect),
            ("Export .cs.pto", "Export the selected exact version.", self.panel.export),
            ("Delete Version", "Request confirmation before soft deletion.", self.panel.delete),
        ]
        self.context_actions = {label: action for label, _, action in entries}
        self.context_menu = Popup([
            MenuItem(label, tooltip=tip, enabled=not project or label in ("Open / Restore", "Inspect version"))
            for label, tip, _ in entries
        ])
        self.context_menu.open_at(*(position or im.get_io().mouse_pos))

    # -- windows ----------------------------------------------------------------------------------------- #
    def _form(self, name, spec, titles=False):
        state = self.forms[name]
        state.rects.clear()
        draw_form(spec, self.panel, state, titles=titles)
        self.item_rects.update(state.rects)

    def browser(self, box):
        self._form("toolbar", SPEC["toolbar"])
        self._form("search", SPEC["search"])
        status = self.model.status
        if status.startswith("Error"):
            im.text_colored(status, (1.0, 0.45, 0.4, 1.0))
        else:
            im.text_wrapped(status)
        if self.notice:
            im.text_wrapped(self.notice)
        self._form("browser", SPEC["browser"])
        if "tree_rows" in self.item_rects:
            self.item_rects["versions"] = self.item_rects["tree_rows"]
        if not self.model.projects and not self.jobs.future:
            im.text_wrapped("No matching projects. Refresh, save the current session or import a project archive.")

    def details(self, box):
        if self.model.selected is None:
            im.text_wrapped("Select a project to restore its latest version, or expand it to select an exact version.")
            return
        if im.begin_tab_bar("project_details"):
            for title, key in DETAIL_TABS:
                opened = im.begin_tab_item(title)
                im.set_item_tooltip("Show " + title.lower() + " for the selected stored project version.")
                if opened:
                    self.details_tab = title
                    if key != "summary" and not getattr(self.model, {"artifacts": "artifacts", "parameters": "parameters",
                                                                      "branches": "branches", "graph": "graph"}[key]):
                        im.text_disabled("Press Inspect Stored Version to load this information.")
                    else:
                        self._form("details", SPEC["details"][key])
                    im.end_tab_item()
            im.end_tab_bar()

    # -- dialogs -------------------------------------------------------------------------------------------- #
    def collision_rows(self):
        preview = (self.pending or {}).get("preview", {}) if isinstance(self.pending, dict) else {}
        rows = []
        for category, ids in (preview.get("collisions") or {}).items():
            if ids:
                rows += [{"category": category, "id": str(i)} for i in ids[:20]]
                if len(ids) > 20:
                    rows.append({"category": category, "id": f"... and {len(ids) - 20} more"})
        return rows

    def draw_modal(self, box):
        close = self.modal_window.begin(box)
        done = False
        if self.modal == "save":
            signature = (self.name, self.notes, self.visibility)
            if signature != getattr(self, "_save_signature", signature) and self.model.status.startswith("Error"):
                self.model.status = ""  # the user is fixing what the message complained about
            self._save_signature = signature
            self.forms["dialog"].rects.clear()
            draw_form(SPEC["save"], self.panel, self.forms["dialog"], titles=False)
            self.item_rects.update(self.forms["dialog"].rects)
        elif self.modal == "delete":
            im.text_wrapped(
                f"Delete version {self.pending.get('version_number', '?')} of '{self.pending.get('project_name', '')}'?\n"
                f"ID: {self.pending['version_id']}\nThis soft-deletes the version and requires manage permission."
            )
            im.spacing()
            if im.button("Delete This Version"):
                self.tour.notify_used("confirm_delete")
                self.error(self.confirm_delete)
                done = True
            im.set_item_tooltip("Confirm soft deletion of this exact selected version.")
            self.item_rects["confirm_delete"] = im.get_item_rect()
            im.same_line()
            done = self._cancel_button() or done
        elif self.modal == "import":
            preview = self.pending["preview"]
            origin = preview.get("origin", {})
            counts = preview.get("entity_counts", {})
            im.text_wrapped(
                f"Original project: {origin.get('project_id', '?')} v{origin.get('version_number', '?')}.\n"
                f"Contains: {counts.get('operations', 0)} operations, {counts.get('artifacts', 0)} artifacts, "
                f"{counts.get('objects', 0)} objects."
            )
            collisions = any(preview.get("collisions", {}).values())
            im.text_wrapped(
                "The following IDs from the archive already exist in the database. On confirmation, conflicting IDs will be remapped."
                if collisions else "No ID collisions detected. Proceed with import?"
            )
            if collisions:
                self.forms["dialog"].rects.clear()
                draw_form({"sections": [{"type": "custom", "key": "data_table", "description": "The identifiers of the archive that already exist in the database, by kind.",
                                         "options": {"source": "collision_rows", "editable": False, "height": 120, "fit_columns": True,
                                                     "columns": [{"key": "category", "title": "Kind", "description": "The kind of record."},
                                                                 {"key": "id", "title": "ID", "description": "The identifier that is already in use."}]}}]},
                          self, self.forms["dialog"], titles=False)
            im.spacing()
            if im.button("Remap & Import" if collisions else "Import Archive"):
                self.tour.notify_used("confirm_import")
                self.confirm_import()
                done = True
            im.set_item_tooltip("Import this checked archive, remapping conflicting IDs when required.")
            self.item_rects["confirm_import"] = im.get_item_rect()
            im.same_line()
            done = self._cancel_button() or done
        if self.model.status.startswith("Error:"):
            im.text_colored(self.model.status, (1.0, 0.45, 0.4, 1.0))
        self.modal_window.end()
        if close or done:
            self.modal = ""

    def _cancel_button(self):
        pressed = im.button("Cancel")
        im.set_item_tooltip("Close this confirmation without changing the database.")
        self.item_rects["cancel_dialog"] = im.get_item_rect()
        return pressed

    def _release_stale_keyboard_focus(self):
        """A click ends the keyboard navigation focus (emtk keeps it on the last field, which then also takes the text a
        later field is typed into; the clicked field takes the focus again in the same frame)."""
        if self.io.mouse_clicked[0]:
            context = im.get_current_context()
            context.nav_id = None
            context.storage["__nav_id__"] = None

    def render(self):
        self._release_stale_keyboard_focus()
        self.jobs.poll()
        if self.autoload and not self.loaded:
            self.loaded = True
            self.error(self.refresh)
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        busy = self.jobs.future is not None
        self.docks.draw(box)
        if busy:
            pass
        if self.context_menu is not None:
            overlays.popup(
                "project_context",
                self.context_menu,
                on_pick=lambda item: self.error(self.context_actions[item.label]),
            )
        if self.modal:
            self.draw_modal(box)
        if self.dialog is not None:
            close = self.file_window.begin(box)
            selected = self.dialog.draw()
            self.file_window.end()
            if close or selected is False:
                self.dialog = None
            elif selected:
                path, action = selected[0], self.file_action
                version = self.pending
                self.dialog = None
                if action == "export":
                    self.error(
                        lambda: self.jobs.start(
                            "Exporting project",
                            lambda: self.model.export(version, path),
                            lambda target: setattr(self.model, "status", "Exported to " + str(target)),
                        )
                    )
                else:
                    self.error(lambda: self.import_preview(path))
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def animating(self):
        return self.jobs.future is not None or super().animating()

    def close(self):
        self.jobs.close()

    def restore_settings(self, settings):
        self.model.restore_preferences(settings)
        self.expanded = set(settings.get("expanded", []))
        self.show_id = settings.get("show_id") if isinstance(settings.get("show_id"), bool) else None
        self.show_status = settings.get("show_status") if isinstance(settings.get("show_status"), bool) else None

    def export_settings(self):
        return {**self.model.export_preferences(), "expanded": sorted(self.expanded),
                "show_id": self.show_id, "show_status": self.show_status}

    def files_dropped(self, paths):
        """A project archive dropped on the window starts the import preview (the Import Project button's flow)."""
        archive = next((str(p) for p in paths if str(p).endswith((".cs.pto", ".csp"))), "")
        if not archive or self.jobs.future is not None or self.modal:
            return False
        self.error(lambda: self.import_preview(archive))
        return True


def make_app():
    return ProjectBrowserApp()
