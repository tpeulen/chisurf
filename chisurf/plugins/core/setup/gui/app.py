"""Pure EMTK unified settings with lazy native destinations."""

from __future__ import annotations

import json

from pathlib import Path

from emtk import im
from emtk.app import ImApp

from chisurf.plugins.emtk_layout import action_button, action_caption, button_width, window_size
from emtk.dialog_window import DialogWindow
from emtk.i18n import tr
from emtk.file_dialog import FileDialog
from emtk.keys import KEY_ENTER, KEY_RETURN

from chisurf.emtk.background_build import BackgroundBuild, draw_opening
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.plugin_icons import entry_icon
from chisurf.emtk.typed_field import parse_number, typed_number_field

from .model import (
    DEFAULT_PANEL,
    FILE_EDITOR,
    PANELS,
    SettingsDocument,
    resolve_factory,
    step_target,
    visible_panels,
)

HERE = Path(__file__).parent
#: UI languages the native catalogues ship (``chisurf.emtk.i18n.SUPPORTED_LOCALES``) with their endonyms.
LANGUAGES = [
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Fran\u00e7ais"),
    ("es", "Espa\u00f1ol"),
    ("pt", "Portugu\u00eas"),
    ("ru", "\u0420\u0443\u0441\u0441\u043a\u0438\u0439"),
]
SIDEBAR_WIDTH = 200.0
HEADER_HEIGHT = 34.0
STATUS_HEIGHT = 34.0
READY = "Ready"


class ConfigurationApp(ImApp):
    """Working validated file route while a dedicated settings panel is pending."""

    def __init__(self, panel, settings_dir):
        self.panel = panel
        self.document = SettingsDocument(Path(settings_dir) / panel.filename, merge_defaults=True)
        self.error = ""
        self.status = ""
        self.dialog = None
        self.dialog_window = None
        self.action = ""
        self.source_mode = False
        self.setting_filter = ""
        self._drafts = {}
        #: In-progress text of the typed number fields, by setting name (committed on Enter / click-away).
        self._number_buffers = {}
        self._number_paths = {}
        self._invalid_fields = {}
        self._draft_source = self.document.text
        self.item_rects = {}
        self.help = EmTkHelpWindow(title="ChiSurf Settings - Help", resource=HERE / "settings_help.md", owner=self)
        super().__init__(self.render, continuous=False)

    def language(self):
        """The ``gui.language`` code stored in the document (``en`` when unset or unreadable)."""
        try:
            data = self.document.parse()
        except Exception:  # noqa: BLE001
            return "en"
        gui = data.get("gui") if isinstance(data, dict) else None
        code = str(gui.get("language", "") if isinstance(gui, dict) else "").strip()
        return code if code in dict(LANGUAGES) else "en"

    def set_language(self, code):
        """Store the UI language in the document and switch the native catalogue at once (Save persists it)."""
        data = self.document.parse()
        if not isinstance(data, dict):
            raise ValueError("The settings file does not hold a mapping.")
        data.setdefault("gui", {})["language"] = code
        self._store(data)
        try:
            from chisurf.emtk.i18n import set_locale

            set_locale(code)
        except Exception:  # noqa: BLE001 - the stored choice is what matters
            pass
        self.status = "Language set to " + dict(LANGUAGES)[code] + "; Save keeps it."

    def draw_language(self):
        """The Qt editor's language selector: display name shown, locale code stored."""
        codes = [c for c, _ in LANGUAGES]
        im.text_unformatted("Language:")
        im.same_line()
        im.set_next_item_width(180)
        changed, index = im.combo("##Language", codes.index(self.language()), [n for _, n in LANGUAGES])
        im.set_item_tooltip(
            tr("UI language. Applies to newly opened tools immediately; restart to fully retranslate open windows.")
        )
        self.item_rects["language"] = im.get_item_rect()
        if changed:
            try:
                self.set_language(codes[index])
                self.error = ""
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)

    def choose(self, action):
        self.action = action
        self.dialog = FileDialog(
            "Open configuration" if action == "open" else "Save configuration as",
            mode="open" if action == "open" else "save",
            directory=str(self.document.path.parent),
            filename=self.document.path.name,
        )
        self.dialog_window = DialogWindow(self.dialog.title, size=(700, 540), key="settings_file")
        self.dialog_window.show()

    def save(self, path=None):
        try:
            self.commit_typed_numbers()
            if self._invalid_fields and not self.source_mode:
                raise ValueError(
                    "Repair invalid setting fields before saving: "
                    + ", ".join(self._invalid_fields)
                )
            value = self.document.save(path)
            from chisurf.core import settings

            if self.document.path.resolve() == Path(
                settings.chisurf_settings_file
            ).resolve() and isinstance(value, dict):
                settings.cs_settings.clear()
                settings.cs_settings.update(value)
                settings.gui.update(value.get("gui", {}))
            self.status = "Saved " + str(self.document.path)
            self.error = ""
            return True
        except Exception as exc:
            self.error = str(exc)
            return False

    def render(self):
        vp = im.get_main_viewport()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin(self.panel.label + " configuration", flags=im.WindowFlags.NO_RESIZE):
            self.draw_language()
            im.text_wrapped(
                str(self.document.path) + (" - modified" if self.document.dirty else "")
            )
            for label, tip, action in [
                (
                    "Open file",
                    "Open another YAML or JSON configuration document.",
                    lambda: self.choose("open"),
                ),
                (
                    "Reload",
                    "Reload this document from disk; discard unsaved edits.",
                    self.document.reload,
                ),
                ("Validate", "Parse YAML/JSON without writing the file.", self.validate),
                ("Help", "Explain the settings editor and its file handling.", self.help.show),
                (
                    "Save",
                    "Validate and atomically save the configuration; refresh active ChiSurf settings.",
                    self.save,
                ),
                (
                    "Save as",
                    "Validate and write a copy under another filename.",
                    lambda: self.choose("save"),
                ),
            ]:
                if im.button(label):
                    try:
                        action()
                    except Exception as exc:
                        self.error = str(exc)
                im.set_item_tooltip(tip)
                im.same_line()
            im.new_line()
            _, self.source_mode = im.checkbox(tr("Edit source"), self.source_mode)
            im.set_item_tooltip(
                tr("Switch between typed setting fields and the complete YAML/JSON source.")
            )
            # The status line stays below the body; two lines leave room for a wrapped error.
            status_h = 2.0 * im.get_text_line_height_with_spacing()
            if self.source_mode:
                avail_h = im.get_content_region_avail()[1]
                _, self.document.text = im.input_text_multiline(
                    "##Configuration", self.document.text, size=(-1, max(150.0, avail_h - status_h))
                )
                im.set_item_tooltip(
                    tr("YAML or JSON source. Comments and exact string/list types are preserved when saving. Invalid content cannot replace the existing file.")
                )
            else:
                self.draw_search()
                # A window does not scroll in emtk, a child does: the fields scroll with the wheel and a scrollbar.
                avail_w, avail_h = im.get_content_region_avail()
                im.begin_child("##settings_body", (float(avail_w), max(60.0, float(avail_h) - status_h)))
                self.structured_fields()
                self.item_rects["settings_body"] = im.end_child()
            im.text_wrapped(self.error or self.status)
        im.end()
        self.help.draw((0, 0, *vp.size))
        if self.dialog:
            window = self.dialog_window
            pressed = window.begin((0, 0, *vp.size))
            result = self.dialog.draw()
            if result:
                try:
                    if self.action == "open":
                        self.document = SettingsDocument(result[0], merge_defaults=True)
                    else:
                        self.save(result[0])
                except Exception as exc:
                    self.error = str(exc)
                self.dialog = None
                self.dialog_window = None
            elif result is False or pressed == "close":
                self.dialog = None
                self.dialog_window = None
            window.end()

    def draw_search(self):
        im.align_text_to_frame_padding()
        im.text_unformatted("Find a setting")
        im.same_line()
        im.set_next_item_width(-1)
        _, self.setting_filter = im.input_text("##Setting search", self.setting_filter)
        im.set_item_tooltip(
            tr("Search full setting names; matching entries retain their parent section names.")
        )
        self.item_rects["setting_search"] = im.get_item_rect()

    def _store(self, data):
        """Write *data* back into the document text in its own format (JSON or YAML)."""
        import json

        import yaml

        self.document.text = (
            json.dumps(data, indent=2) + "\n"
            if self.document.path.suffix == ".json"
            else yaml.safe_dump(data, sort_keys=False)
        )
        self._draft_source = self.document.text

    def commit_typed_numbers(self):
        """Apply number fields typed but not yet committed (Save is pressed before the field sees the click-away)."""
        if not self._number_buffers or self.source_mode:
            return
        data = self.document.parse()
        for label, text in list(self._number_buffers.items()):
            path = self._number_paths.get(label)
            if not path:
                continue
            parent = data
            for key in path[:-1]:
                parent = parent[key]
            try:
                parent[path[-1]] = parse_number(text, integer=isinstance(parent[path[-1]], int))
            except ValueError:
                self._invalid_fields[label] = f"{text!r} is not a number"
                continue
            self._invalid_fields.pop(label, None)
            del self._number_buffers[label]
        self._store(data)

    def structured_fields(self):
        import yaml

        try:
            data = self.document.parse()
        except Exception as exc:
            im.text_wrapped(
                "Cannot build typed fields: "
                + str(exc)
                + ". Enable Edit source to repair this document."
            )
            return
        if self._draft_source != self.document.text:
            self._drafts.clear()
            self._number_buffers.clear()
            self._invalid_fields.clear()
            self._draft_source = self.document.text
        edited = False
        # One row per setting: its key in a label column, the field beside it (a label above every field halved how
        # many settings fit). The column is as wide as the longest key that is shown, at most 40% of the room.
        indent = 12.0

        def keys(value, depth=0):
            if isinstance(value, dict):
                for key, item in value.items():
                    if isinstance(item, dict):
                        yield from keys(item, depth + 1)
                    else:
                        yield depth, str(key)

        room = im.get_content_region_avail()[0]
        widest = max((im.calc_text_size(k)[0] + indent * d for d, k in keys(data)), default=80.0)
        column = min(widest + 16.0, max(120.0, room * 0.4))

        def draw_values(value, prefix=()):
            nonlocal edited
            if isinstance(value, dict):
                for key, item in value.items():
                    path = prefix + (key,)
                    label = ".".join(map(str, path))
                    if isinstance(item, dict):
                        if self.setting_filter or im.collapsing_header(label, open_=True):
                            draw_values(item, path)
                        continue
                    if self.setting_filter.casefold() not in label.casefold():
                        continue
                    im.push_id(label)
                    depth = len(prefix)
                    if depth:
                        im.indent(indent * depth)
                    im.align_text_to_frame_padding()
                    im.text_unformatted(str(key))
                    if depth:
                        im.unindent(indent * depth)
                    im.set_item_tooltip(label)
                    im.same_line(column)
                    im.set_next_item_width(-1)
                    if isinstance(item, bool):
                        changed, new = im.checkbox("##Value", item)
                    elif isinstance(item, (int, float)):
                        self._number_paths[label] = path
                        new, problem = typed_number_field(
                            label, item, self._number_buffers, integer=isinstance(item, int)
                        )
                        changed = new is not None
                        if problem:
                            self.error = label + ": " + problem
                    else:
                        text = (
                            yaml.safe_dump(item, default_flow_style=True).strip()
                            if not isinstance(item, str)
                            else item
                        )
                        changed, new = im.input_text("##Value", self._drafts.get(label, text))
                        if changed:
                            self._drafts[label] = new
                        if changed and not isinstance(item, str):
                            try:
                                new = yaml.safe_load(new)
                                if item is not None and not isinstance(new, type(item)):
                                    raise ValueError(
                                        "Keep the existing " + type(item).__name__ + " value type."
                                    )
                            except Exception as exc:
                                self.error = label + ": " + str(exc)
                                self._invalid_fields[label] = str(exc)
                                changed = False
                    self.item_rects["field:" + label] = im.get_item_rect()
                    im.set_item_tooltip(
                        label
                        + " ("
                        + type(item).__name__
                        + "). Edit the stored configuration value; Save validates and persists it."
                    )
                    if changed:
                        self._invalid_fields.pop(label, None)
                        value[key] = new
                        edited = True
                    im.pop_id()
            else:
                im.text_wrapped(
                    tr("This document has a list at its root; use Edit source to edit list records.")
                )

        draw_values(data)
        if edited:
            self._store(data)
            self.error = (
                ""
                if not self._invalid_fields
                else "Invalid fields: " + ", ".join(self._invalid_fields)
            )

    def validate(self):
        self.document.parse()
        self.status = "Valid " + self.document.path.suffix + " configuration."
        self.error = ""

    def export_settings(self):
        return {"path": str(self.document.path)}

    def restore_settings(self, data):
        if data.get("path"):
            self.document = SettingsDocument(data["path"], merge_defaults=True)


class UnavailablePanel(ImApp):
    """What a destination shows when its app cannot be built: the reason and a Retry button.

    Never a stand-in editor: a destination either is its dedicated panel or says why it is not.
    """

    def __init__(self, panel, error, retry):
        self.panel = panel
        self.error = error
        self.retry = retry
        self.item_rects = {}
        super().__init__(self.render, continuous=False)

    def render(self):
        vp = im.get_main_viewport()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin(self.panel.label + " unavailable", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            im.heading(self.panel.label, level=2)
            im.text_wrapped(tr("This settings panel could not be opened."))
            im.text_wrapped(self.error)
            if im.button(tr("Retry") + "##unavailable_retry"):
                self.retry()
            im.set_item_tooltip(tr("Try to build this panel again."))
            self.item_rects["retry"] = im.get_item_rect()
        im.end()


class UnifiedSettingsApp(ImApp):
    """The Settings hub: a searchable list of destinations hosting each one's dedicated native panel."""

    def __init__(self, settings_dir=None, panels=None):
        spec = json.loads((HERE / "app.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1200, 800))
        if settings_dir is None:
            from chisurf.core.settings.path_utils import get_path

            settings_dir = get_path("settings")
        self.settings_dir = Path(settings_dir)
        self.panels = list(PANELS if panels is None else panels)
        self.selected = DEFAULT_PANEL if any(p.key == DEFAULT_PANEL for p in self.panels) else self.panels[0].key
        self.children = {}
        self.routes = {}
        self.errors = {}
        self.pending_state = {}
        #: The destination shown when the window opens is made on a worker thread (its app imports a database and
        #: a dictionary); :meth:`_build` wires it in from here.
        self._builder = BackgroundBuild(wake=self.request_frame)
        self._prebuilt = {}
        self.error = ""
        self.status = READY
        self.filter = ""
        self.item_rects = {}
        self.child_box = (SIDEBAR_WIDTH, HEADER_HEIGHT, 700.0, 500.0)
        self._painter = None
        self._child_focus = False
        self._press_in_child = False
        self.fast_forward = False
        self._ff_queue = []
        self._ff_total = 0
        self.help = EmTkHelpWindow(title="Settings - Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key),
        )
        super().__init__(self.render, continuous=False)

    # -- destinations -------------------------------------------------------------------------------------------- #
    @property
    def child(self):
        return self.children.get(self.selected)

    @property
    def native_layouts(self):
        layouts = {}
        for key, child in self.children.items():
            if hasattr(child, "docks"):
                layouts[key] = child.docks
            for name, manager in getattr(child, "native_layouts", {}).items():
                layouts[key + "/" + name] = manager
        return layouts

    def panel_of(self, key):
        panel = next((p for p in self.panels if p.key == key), None)
        if panel is None:
            raise ValueError("Unknown settings panel: " + key)
        return panel

    def _build(self, panel):
        if self._builder.building(panel.key):
            self._prebuilt.update(self._builder.collect(wait=True) or {})
        if panel.key in self._prebuilt:
            made, exc = self._prebuilt.pop(panel.key)
            if exc is not None:
                raise exc
            child, route = made
        else:
            child, route = self._make(panel)
        state = self.pending_state.pop(panel.key, None)
        if state and callable(getattr(child, "restore_settings", None)):
            try:
                child.restore_settings(state)
            except Exception:  # noqa: BLE001 - a stale saved state must not block the panel
                pass
        return child, route

    def _make(self, panel):
        """Construct a destination's app: ``(child, route)``. May run on the build thread (no hub state)."""
        if panel.key == FILE_EDITOR:
            child = ConfigurationApp(panel, self.settings_dir)
            route = "configuration"
        else:
            factory = resolve_factory(panel)
            if factory is None:
                raise RuntimeError("no native app is declared for " + panel.label)
            import inspect

            takes_dir = "settings_dir" in inspect.signature(factory).parameters
            child = factory(settings_dir=self.settings_dir) if takes_dir else factory()
            route = "native"
        return child, route

    def select(self, key):
        """Show a destination, building its app on first use (its state is kept while others are shown)."""
        panel = self.panel_of(key)
        self.selected = key
        self.error = ""
        self.status = READY
        if key not in self.children:
            try:
                self.children[key], self.routes[key] = self._build(panel)
                self.errors.pop(key, None)
            except Exception as exc:  # noqa: BLE001
                self.errors[key] = str(exc) or type(exc).__name__
                self.error = "Cannot load " + panel.label + ": " + self.errors[key]
                self.status = self.error
                self.children[key] = UnavailablePanel(panel, self.errors[key], lambda k=key: self.retry(k))
                self.routes[key] = "unavailable"
        return self.child

    def retry(self, key):
        """Drop an unavailable stand-in and build the destination again."""
        stale = self.children.pop(key, None)
        if isinstance(stale, UnavailablePanel):
            self.select(key)

    def choose(self, key):
        """A destination picked by hand (a click): ends a fast-forward."""
        self._stop_fast_forward("Fast-forward stopped")
        self.select(key)

    # -- the Back / Next / fast-forward stepper ------------------------------------------------------------------ #
    def can_step(self, delta):
        return step_target(self.panels, self.selected, delta) is not None

    def next_step(self):
        target = step_target(self.panels, self.selected, 1)
        if target is None:
            return False
        self.select(target)
        return True

    def previous_step(self):
        self._stop_fast_forward("Fast-forward stopped")
        target = step_target(self.panels, self.selected, -1)
        if target is None:
            return False
        self.select(target)
        return True

    def toggle_fast_forward(self):
        """Walk every remaining destination in order, one per frame; a second press stops after the current one."""
        if self.fast_forward:
            self._stop_fast_forward("Fast-forward stopped - finishing this step")
            return
        keys = [p.key for p in self.panels]
        self._ff_queue = keys[keys.index(self.selected):]
        if not self._ff_queue:
            return
        self._ff_total = len(self._ff_queue)
        self.fast_forward = True
        self._ff_step()

    def _ff_step(self):
        if not self.fast_forward:
            return
        if not self._ff_queue:
            self._stop_fast_forward("Fast-forward finished - the pipeline is done")
            return
        key = self._ff_queue.pop(0)
        done = self._ff_total - len(self._ff_queue)
        self.select(key)
        self.status = f"Fast-forward {done}/{self._ff_total}: {self.panel_of(key).label}"
        self.request_frame()

    def _stop_fast_forward(self, message=""):
        if not self.fast_forward:
            return
        self.fast_forward = False
        self._ff_queue = []
        if message:
            self.status = message

    # -- drawing ------------------------------------------------------------------------------------------------- #
    def draw(self, painter, x, y, w, h):
        self._painter = painter
        if self.child is None:
            self._prebuilt.update(self._builder.collect() or {})
            if self.selected in self._prebuilt:
                self.select(self.selected)
            elif not self._builder.busy:
                panel = self.panel_of(self.selected)
                self._builder.start({panel.key: lambda: self._make(panel)}, name="chisurf-settings-" + panel.key)
        super().draw(painter, x, y, w, h)
        self._painter = None

    def render(self):
        vp = im.get_main_viewport()
        width, height = vp.size
        # 200 px like the Qt list; narrower windows give the hosted panel the room (the longest label needs
        # ~140 px), plus the rows' icon slot
        left = SIDEBAR_WIDTH if width >= 1100 else (180.0 if width >= 900 else 152.0)
        left += im.selectable_icon_width()
        body = max(1.0, height - STATUS_HEIGHT)
        flags = im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE | im.WindowFlags.NO_MOVE
        self.item_rects["destinations"] = (0.0, 0.0, left, body)

        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((left, body), im.Cond.ALWAYS)
        if im.begin("Settings destinations", flags=flags):
            im.set_next_item_width(-1)
            changed, self.filter = im.input_text_with_hint("##Find settings", self.filter, "Search...")
            im.set_item_tooltip(tr("Filter the destinations by name."))
            self.item_rects["search"] = im.get_item_rect()
            if changed and self.filter:
                self.tour.notify_used("search")
            shown = visible_panels(self.panels, self.filter)
            avail_w, avail_h = im.get_content_region_avail()
            # A window does not scroll in emtk, a child does: the list scrolls with the wheel when it does not fit.
            im.begin_child("##destination_list", (float(avail_w), max(float(avail_h), 30.0)))
            for panel in shown:
                if im.selectable(
                    panel.label,
                    self.selected == panel.key,
                    size=(0, 26),
                    icon=entry_icon(panel, panel.plugin, panel.entry),
                ):
                    self.choose(panel.key)
                    self.tour.notify_used("destinations")
                im.set_item_tooltip(panel.description or panel.label)
                self.item_rects["dest_" + panel.key] = im.get_item_rect()
            if not shown:
                im.text_disabled(tr("No matching settings."))
            im.end_child()
        im.end()

        im.set_next_window_pos((left, 0), im.Cond.ALWAYS)
        im.set_next_window_size((max(1.0, width - left), HEADER_HEIGHT), im.Cond.ALWAYS)
        if im.begin("Settings header", flags=flags):
            avail = im.get_content_region_avail()[0]
            cx = im.get_cursor_pos()[0]
            reserved = button_width(action_caption("guide")) + im.get_style().item_spacing[0] + 28.0
            im.set_cursor_pos_x(cx + max(0.0, avail - reserved))
            if action_button("guide", id="settings_guide"):
                self.tour.start()
            self.item_rects["guide"] = im.get_item_rect()
            im.same_line()
            if im.button(tr("?") + "##settings_help", size=(28, 0)):
                self.help.show()
            im.set_item_tooltip(tr("Read how the Settings hub, its destinations and its stepper work."))
            self.item_rects["help"] = im.get_item_rect()
        im.end()

        im.set_next_window_pos((0, body), im.Cond.ALWAYS)
        im.set_next_window_size((width, STATUS_HEIGHT), im.Cond.ALWAYS)
        if im.begin("Settings status", flags=flags):
            avail = im.get_content_region_avail()[0]
            cx = im.get_cursor_pos()[0]
            im.text_disabled(self.status)
            self.item_rects["status"] = im.get_item_rect()
            im.same_line()
            im.set_cursor_pos_x(cx + max(0.0, avail - 196.0))
            im.begin_disabled(not self.can_step(-1))
            if im.button(tr("< Back") + "##settings_back", size=(70, 0)):
                self.previous_step()
            im.end_disabled()
            im.set_item_tooltip(tr("Go to the previous destination."))
            self.item_rects["back"] = im.get_item_rect()
            im.same_line()
            if im.button(("||" if self.fast_forward else ">>") + "##settings_ff", size=(40, 0)):
                self.toggle_fast_forward()
            im.set_item_tooltip(
                "Stop the fast-forward after the current destination."
                if self.fast_forward
                else "Fast-forward: visit every remaining destination in order. Press again to stop."
            )
            self.item_rects["ff"] = im.get_item_rect()
            im.same_line()
            im.begin_disabled(not self.can_step(1))
            if im.button(tr("Next >") + "##settings_next", size=(70, 0)):
                if self.next_step():
                    self.tour.notify_used("next")
            im.end_disabled()
            im.set_item_tooltip(tr("Go to the next destination."))
            self.item_rects["next"] = im.get_item_rect()
        im.end()

        self.child_box = (
            left,
            HEADER_HEIGHT,
            max(1.0, width - left),
            max(1.0, body - HEADER_HEIGHT),
        )
        self.item_rects["panel"] = self.child_box
        if self.child is not None and self._painter is not None:
            self.draw_child(self._painter, self.child, *self.child_box, local_coordinates=True)
        elif self._builder.busy:
            draw_opening(tr(self.panel_of(self.selected).label), self.child_box, "Settings opening")
        if self.child is not None and getattr(self.child, "close_requested", False):
            # A hosted panel's own Close button: the window stays, the panel says so instead of doing nothing.
            self.child.close_requested = False
            self.status = "Close the Settings window to leave this panel."
        if self.fast_forward:
            self._ff_step()
        self.help.draw((0, 0, width, height))
        self.tour.draw(width, height)

    # -- input: hosted children get region-relative events ------------------------------------------------------- #
    def _inside(self, x, y):
        bx, by, bw, bh = self.child_box
        return bx <= x < bx + bw and by <= y < by + bh

    def _local(self, x, y):
        return x - self.child_box[0], y - self.child_box[1]

    def _overlay(self):
        return self.help.open or self.tour.active

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        self._press_in_child = self._inside(x, y) and not self._overlay()
        self._child_focus = self._press_in_child
        super().pointer_press(x, y, button, modifiers, clicks)
        if self.child is not None and self._press_in_child:
            self.child.pointer_press(*self._local(x, y), button, modifiers, clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self.child is not None and self._press_in_child:
            self.child.pointer_release(*self._local(x, y), button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self.child is not None and not self._overlay():
            self.child.pointer_move(*self._local(x, y), buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0):
        if self.child is not None and self._inside(x, y) and not self._overlay():
            super().pointer_move(x, y, 0, modifiers)
            self.child.wheel(*self._local(x, y), steps, modifiers)
        else:
            super().wheel(x, y, steps, modifiers)

    def scroll(self, rows):
        # The classic host contract: no position, so the last pointer position decides who scrolls.
        if self.child is not None and self._inside(*self.io.mouse_pos) and not self._overlay():
            return self.child.scroll(rows)
        return super().scroll(rows)

    def key(self, key, text="", modifiers=0):
        if self.child is not None and self._child_focus and not self._overlay():
            return self.child.key(key, text, modifiers)
        captured = super().key(key, text, modifiers)
        if captured and key in (KEY_RETURN, KEY_ENTER) and self.filter and not self._overlay():
            shown = visible_panels(self.panels, self.filter)
            if shown:
                self.choose(shown[0].key)
                self.tour.notify_used("destinations")
        return captured

    def key_release(self, key, text="", modifiers=0):
        release = getattr(self.child, "key_release", None)
        if self._child_focus and callable(release):
            return release(key, text, modifiers)
        return False

    def focus_lost(self):
        """The window lost focus mid-press: every hosted app must drop a held key or button."""
        for child in self.children.values():
            lost = getattr(child, "focus_lost", None)
            if callable(lost):
                lost()
        self._child_focus = False
        self._press_in_child = False

    def files_dropped(self, paths):
        for name in ("files_dropped", "on_files_dropped"):
            handler = getattr(self.child, name, None)
            if callable(handler):
                return bool(handler(paths))
        return False

    on_files_dropped = files_dropped

    def animating(self):
        child = self.child
        return (super().animating() or self.fast_forward or self._builder.busy
                or (child is not None and child.animating()))

    def next_frame_in(self):
        values = [super().next_frame_in(), getattr(self.child, "next_frame_in", lambda: None)()]
        return min((v for v in values if v is not None), default=None)

    # -- persistence --------------------------------------------------------------------------------------------- #
    def export_settings(self):
        children = dict(self.pending_state)
        for key, child in self.children.items():
            if callable(getattr(child, "export_settings", None)):
                children[key] = child.export_settings()
        return {"selected": self.selected, "children": children}

    def restore_settings(self, state):
        keys = {p.key for p in self.panels}
        self.pending_state = {k: v for k, v in state.get("children", {}).items() if k in keys}
        selected = state.get("selected", DEFAULT_PANEL)
        self.select(selected if selected in keys else DEFAULT_PANEL)

    def close(self):
        self._prebuilt.update(self._builder.collect(wait=True) or {})
        for made, _exc in self._prebuilt.values():  # made for the first frame, never shown
            if made is not None and callable(getattr(made[0], "close", None)):
                made[0].close()
        self._prebuilt.clear()
        for child in self.children.values():
            if callable(getattr(child, "close", None)):
                child.close()
        self.children.clear()


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return UnifiedSettingsApp(settings_dir=kwargs.get("settings_dir"), panels=kwargs.get("panels"))
