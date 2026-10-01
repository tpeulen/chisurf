"""Native project/version browser with the original database and archive actions."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im, overlays
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.widgets.menus import MenuItem, Popup

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .controller import ProjectJobs
from .model import ProjectBrowserModel

FIELDS = [
    ("Project / Version", "project_name", 0.23),
    ("ID", "id", 0.18),
    ("Owner", "owner_user_id", 0.10),
    ("Status", "status", 0.08),
    ("Visibility", "visibility", 0.07),
    ("Datasets", "dataset_count", 0.06),
    ("Fits", "fit_count", 0.05),
    ("Created", "created_at", 0.12),
    ("Notes", "notes", 0.11),
]


class ProjectBrowserApp(ImApp):
    def __init__(self, model=None, autoload=True):
        self.model = model or ProjectBrowserModel()
        self.jobs = ProjectJobs(self.model)
        self.autoload = autoload
        self.loaded = False
        self.expanded = set()
        self.selected_ids = set()
        self.row_rects = {}
        self.dialog = self.file_window = None
        self.file_action = ""
        self.modal = ""
        self.modal_window = DialogWindow("Project action", size=(700, 520))
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
        self.docks = DockManager(Split("v", 0.75, Region("browser"), Region("details")))
        self.docks.add_window(
            "browser", "Projects and versions", self.browser, dock="browser", closable=False
        )
        self.docks.add_window(
            "details", "Selected project details", self.details, dock="details", closable=False
        )
        super().__init__(self.render, continuous=False)

    def error(self, action):
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

    #: The guide's key for each action button.
    ACTION_KEYS = {"Open / Restore": "open", "Save Current Project": "save", "Export .cs.pto": "export",
                   "Import Project": "import", "Delete Version": "delete", "Refresh": "refresh",
                   "Inspect stored version": "inspect", "Guide": "guide", "Help": "help"}

    def action(self, label, tip, callback):
        key = self.ACTION_KEYS.get(label)
        if im.button(label):
            if key:
                self.tour.notify_used(key)
            self.error(callback)
        im.set_item_tooltip(tip)
        if key:
            self.item_rects[key] = im.get_item_rect()

    def browser(self, box):
        actions = [
            (
                "Open / Restore",
                "Restore a selected version, or the newest version of the selected project.",
                self.open_selected,
            ),
            (
                "Save Current Project",
                "Save all current datasets, fits and instrument state as a new database version.",
                self.begin_save,
            ),
            (
                "Export .cs.pto",
                "Export the selected exact version as a portable project archive.",
                lambda: self.choose_file("export"),
            ),
            (
                "Import Project",
                "Preview an archive, check IDs and import after confirmation.",
                lambda: self.choose_file("import"),
            ),
            (
                "Delete Version",
                "Soft-delete the selected version; database manage permission is required.",
                self.begin_delete,
            ),
            ("Refresh", "Reload projects from the database.", self.refresh),
            ("Guide", "Walk through finding, inspecting, restoring and saving projects.", self.tour.start),
            (
                "Help",
                "Explain project versions, restoration, permissions and archives.",
                self.help_window.show,
            ),
        ]
        for index, (label, tip, callback) in enumerate(actions):
            if index:
                im.same_line()
            self.action(label, tip, callback)
        changed, self.model.search = im.input_text(
            "Search projects", self.model.search, "Name, ID, owner or notes"
        )
        im.set_item_tooltip("Search stored project names, identifiers, owners and version notes.")
        self.item_rects["search"] = im.get_item_rect()
        toggled, self.model.show_public = im.checkbox("Show public", self.model.show_public)
        im.set_item_tooltip("Include projects made readable to other authenticated users.")
        if changed or toggled:
            self.error(self.refresh)
        im.text_wrapped(self.model.status)
        if self.notice:
            im.text_wrapped(self.notice)
        flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.RESIZABLE
            | im.TableFlags.REORDERABLE
            | im.TableFlags.HIDEABLE
            | im.TableFlags.SORTABLE
            | im.TableFlags.SCROLL_X
        )
        tx, ty = im.get_cursor_screen_pos()
        tw, th = im.get_content_region_avail()
        self.item_rects["versions"] = (tx, ty, tw, max(40.0, min(th, 240.0)))
        if im.begin_table("project_versions", len(FIELDS), flags):
            # Fixed widths that fit header and contents (capped), scrolled sideways when the
            # pane is narrow: stretched to 800 px the columns overlapped their own text.
            for title, width in zip((f[0] for f in FIELDS), self._column_widths()):
                im.table_setup_column(title, im.TableColumnFlags.WIDTH_FIXED, width)
            im.table_next_row()
            for title, _, _ in FIELDS:
                im.table_next_column()
                im.table_header(title)
                im.set_item_tooltip(
                    "Sort by " + title.lower() + "; drag the header edge to resize this column."
                )
            specs = im.table_get_sort_specs()
            column, reverse = (
                (specs.specs[0].column_index, not specs.specs[0].ascending)
                if specs and specs.specs
                else (7, True)
            )
            key = FIELDS[column][1]

            def value(row):
                if key == "id":
                    return row.get("version_id", row.get("project_id", ""))
                if key in ("dataset_count", "fit_count"):
                    return int(row.get(key) or 0)
                return str(row.get(key) or "").casefold()

            for project in sorted(self.model.projects, key=value, reverse=reverse):
                self.row(project, project=True)
                if project.get("project_id") in self.expanded:
                    for version in sorted(project.get("versions", []), key=value, reverse=reverse):
                        self.row(
                            {
                                **version,
                                "visibility": version.get(
                                    "visibility", project.get("visibility", "private")
                                ),
                            }
                        )
            im.end_table()
        if not self.model.projects:
            im.text_wrapped(
                "No matching projects. Refresh, save the current session or import a project archive."
            )

    def _cell_text(self, row, key, project):
        if key == "project_name":
            return (f"{row.get('project_name', '(unnamed)')} ({row.get('version_count', 0)} versions)" if project
                    else f"  v{row.get('version_number', '?')} {row.get('project_name', '')}")
        if key == "id":
            return row.get("project_id" if project else "version_id", "")
        value = row.get(key, "")
        return str(value)[:19].replace("T", " ") if key == "created_at" else str(value)

    def _column_widths(self):
        """Per column: the widest of header and cells, plus padding (the expander on the first)."""
        rows = [(p, True) for p in self.model.projects]
        rows += [(v, False) for p in self.model.projects if p.get("project_id") in self.expanded
                 for v in p.get("versions", [])]
        widths = []
        for index, (title, key, _) in enumerate(FIELDS):
            texts = [title] + [self._cell_text(r, key, project) for r, project in rows]
            widest = max(im.calc_text_size(t)[0] for t in texts)
            widths.append(min(widest + (40.0 if index == 0 else 14.0), 320.0))
        return widths

    def row(self, row, project=False):
        identifier = row.get("project_id" if project else "version_id", "")
        im.push_id(identifier)
        im.table_next_row()
        for index, (_, key, _) in enumerate(FIELDS):
            im.table_next_column()
            if index == 0:
                if project:
                    if im.small_button(("−" if identifier in self.expanded else "+") + "##expand"):
                        self.expanded.symmetric_difference_update({identifier})
                    im.set_item_tooltip("Expand or collapse this project's stored versions.")
                    im.same_line()
                label = (
                    f"{row.get('project_name', '(unnamed)')} ({row.get('version_count', 0)} versions)"
                    if project
                    else f"  v{row.get('version_number', '?')} {row.get('project_name', '')}"
                )
                clicked = im.selectable(
                    label + "##select",
                    self.model.selected_id == identifier or identifier in self.selected_ids,
                )
                self.row_rects[identifier] = im.get_item_rect()
                if clicked or (im.is_item_hovered() and im.is_mouse_clicked(1)):
                    if im.get_io().key_ctrl and clicked:
                        self.selected_ids.symmetric_difference_update({identifier})
                        self.model.selected_id = (
                            identifier
                            if identifier in self.selected_ids
                            else next(iter(self.selected_ids), "")
                        )
                    elif not (im.is_mouse_clicked(1) and identifier in self.selected_ids):
                        self.selected_ids = {identifier}
                        self.model.selected_id = identifier
                    else:
                        self.model.selected_id = identifier
                    self.tour.notify_used("versions")
                    self.model.artifacts = []
                    self.model.parameters = []
                    self.model.branches = []
                    self.model.graph = {}
                im.set_item_tooltip(
                    f"{'Project' if project else 'Version'}: {identifier}\nOwner: {row.get('owner_user_id', '')}\n{row.get('notes', '')}"
                )
                if im.is_item_hovered() and im.is_mouse_double_clicked(0):
                    self.error(self.open_selected)
                if im.is_item_hovered() and im.is_mouse_clicked(1):
                    entries = [
                        ("Open / Restore", "Restore this selection.", self.open_selected),
                        (
                            "Inspect version",
                            "List stored artifacts, parameters and version ancestry.",
                            self.inspect,
                        ),
                        (
                            "Export .cs.pto",
                            "Export the selected exact version.",
                            lambda: self.choose_file("export"),
                        ),
                        (
                            "Delete Version",
                            "Request confirmation before soft deletion.",
                            self.begin_delete,
                        ),
                    ]
                    self.context_actions = {label: action for label, _, action in entries}
                    self.context_menu = Popup(
                        [
                            MenuItem(
                                label,
                                tooltip=tip,
                                enabled=not project
                                or label in ("Open / Restore", "Inspect version"),
                            )
                            for label, tip, _ in entries
                        ]
                    )
                    self.context_menu.open_at(*im.get_io().mouse_pos)
            else:
                value = identifier if key == "id" else row.get(key, "")
                if key == "created_at":
                    value = str(value)[:19].replace("T", " ")
                im.text(str(value))
                im.set_item_tooltip(f"{FIELDS[index][0]}: {value}")
        im.pop_id()

    def details(self, box):
        selected = self.model.selected
        if selected is None:
            im.text_wrapped(
                "Select a project to restore its latest version, or expand it to select an exact version."
            )
            return
        self.action(
            "Inspect stored version",
            "Load artifacts, fitted parameter values, branches and parent relationships.",
            self.inspect,
        )
        if im.begin_tab_bar("project_details"):
            for title in ("Summary", "Artifacts", "Parameters", "Branches", "Version graph"):
                if im.begin_tab_item(title):
                    self.details_tab = title
                    if title == "Summary":
                        im.text_wrapped(json.dumps(selected, indent=2, default=str))
                    else:
                        data = {
                            "Artifacts": self.model.artifacts,
                            "Parameters": self.model.parameters,
                            "Branches": self.model.branches,
                            "Version graph": self.model.graph,
                        }[title]
                        im.text_wrapped(
                            json.dumps(data, indent=2, default=str)
                            if data
                            else "Inspect the stored version to load this information."
                        )
                    im.end_tab_item()
                im.set_item_tooltip(
                    "Show " + title.lower() + " for the selected stored project version."
                )
            im.end_tab_bar()

    def draw_modal(self, box):
        close = self.modal_window.begin(box)
        if self.modal == "save":
            im.begin_disabled(not self.allow_name_edit)
            _, self.name = im.input_text("Project name", self.name)
            im.set_item_tooltip(
                "Name a new project; existing project versions retain their project name."
            )
            im.end_disabled()
            _, self.visibility = im.combo("Visibility", self.visibility, ["Private", "Public"])
            im.set_item_tooltip(
                "Private is visible to its owner; public is readable to authenticated users."
            )
            _, self.notes = im.input_text_multiline("Version notes", self.notes, size=(-1.0, 180.0))
            im.set_item_tooltip("Record optional notes for this saved version.")
            self.action(
                "Save version",
                "Serialize the current session and save one new database version.",
                self.save,
            )
        elif self.modal == "delete":
            im.text_wrapped(
                f"Delete version {self.pending.get('version_number', '?')} of '{self.pending.get('project_name', '')}'?\nID: {self.pending['version_id']}\nThis soft-deletes the version and requires manage permission."
            )
            self.action(
                "Delete this version",
                "Confirm soft deletion of this exact selected version.",
                self.confirm_delete,
            )
        elif self.modal == "import":
            preview = self.pending["preview"]
            im.text_wrapped("Archive origin: " + json.dumps(preview.get("origin", {})))
            im.text_wrapped("Contents: " + json.dumps(preview.get("entity_counts", {})))
            collisions = {
                key: values for key, values in preview.get("collisions", {}).items() if values
            }
            im.text_wrapped(
                "Conflicting IDs will be remapped." if collisions else "No ID collisions detected."
            )
            if collisions:
                im.text_wrapped(json.dumps(collisions, indent=2))
            self.action(
                "Remap & Import" if collisions else "Import archive",
                "Import this checked archive, remapping conflicting IDs when required.",
                self.confirm_import,
            )
        im.same_line()
        if im.button("Cancel") or close:
            self.modal = ""
        im.set_item_tooltip("Close this confirmation without changing the database.")
        if self.model.status.startswith("Error:"):
            im.text_wrapped(self.model.status)
        self.modal_window.end()

    def render(self):
        self.row_rects.clear()
        self.jobs.poll()
        if self.autoload and not self.loaded:
            self.loaded = True
            self.error(self.refresh)
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        im.begin_disabled(
            self.jobs.future is not None or bool(self.modal) or self.dialog is not None
        )
        self.docks.draw(box)
        im.end_disabled()
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
                            lambda target: setattr(
                                self.model, "status", "Exported to " + str(target)
                            ),
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

    def export_settings(self):
        return {**self.model.export_preferences(), "expanded": sorted(self.expanded)}


def make_app():
    return ProjectBrowserApp()
