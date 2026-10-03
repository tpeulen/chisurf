"""Qt-free style-file editor and QSS palette migration."""
from __future__ import annotations

import pathlib
import re
import shutil

from emtk import im
from emtk.app import ImApp
from emtk.file_dialog import FileDialog
from emtk.im_core import Style
from emtk.widgets.text_editor import Language, TextEditor


def color(value):
    value = value.strip()
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        if len(digits) == 6:
            return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    match = re.fullmatch(r"rgba?\(([^)]+)\)", value)
    if match:
        parts = [float(v.strip()) for v in match[1].split(",")]
        if len(parts) in (3, 4):
            alpha = parts[3] if len(parts) == 4 else 255
            if len(parts) == 4 and alpha <= 1:
                alpha *= 255
            return tuple(max(0, min(255, round(v))) for v in parts[:3] + [alpha])
    named = {"white": (255, 255, 255, 255), "black": (0, 0, 0, 255), "transparent": (0, 0, 0, 0)}
    if value in named:
        return named[value]
    raise ValueError(f"Unsupported color: {value}")


# Specific roles are handled by native controls, rather than Qt widget selectors.
_ROLES = {
    "*": (im.Col.WINDOW_BG, im.Col.TEXT), "QWidget": (im.Col.WINDOW_BG, im.Col.TEXT),
    "QWidget:disabled": (None, im.Col.TEXT_DISABLED),
    "QLineEdit": (im.Col.FRAME_BG, None), "QPlainTextEdit": (im.Col.FRAME_BG, None),
    "QComboBox": (im.Col.FRAME_BG, None), "QSpinBox": (im.Col.FRAME_BG, None),
    "QAbstractButton": (im.Col.BUTTON, None), "QPushButton": (im.Col.BUTTON, None),
    "QPushButton:hover": (im.Col.BUTTON_HOVERED, None), "QPushButton:pressed": (im.Col.BUTTON_ACTIVE, None),
    "QAbstractItemView": (im.Col.FRAME_BG, None), "QTreeView": (im.Col.FRAME_BG, None),
    "QHeaderView::section": (im.Col.HEADER, None),
    "QTabBar::tab": (im.Col.TAB, None), "QTabBar::tab:selected": (im.Col.TAB_SELECTED, None),
    "QTabBar::tab:hover": (im.Col.HEADER_HOVERED, None),
    "QMenu": (im.Col.POPUP_BG, None), "QToolTip": (im.Col.POPUP_BG, None),
    "QMenuBar::item": (im.Col.MENU_BAR_BG, None), "QMenu::item:selected": (im.Col.HEADER_ACTIVE, None),
    "QWidget:item:selected": (im.Col.HEADER_ACTIVE, None), "QWidget:item:hover": (im.Col.HEADER_HOVERED, None),
    "QDockWidget::title": (im.Col.TITLE_BG, None),
    "QScrollBar:vertical": (im.Col.SCROLLBAR_BG, None),
    "QScrollBar::handle:vertical": (im.Col.SCROLLBAR_GRAB, None),
    "QCheckBox::indicator:checked": (im.Col.CHECK_MARK, None),
}


def convert_qss(source: str) -> tuple[Style, list[str]]:
    """Translate supported palette rules; retain/report unsupported QSS verbatim."""
    style = Style()
    ignored = []
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
        for selector in selectors.split(","):
            selector = selector.strip()
            roles = _ROLES.get(selector)
            for declaration in body.split(";"):
                if ":" not in declaration:
                    continue
                prop, value = (v.strip() for v in declaration.split(":", 1))
                role = None
                if roles:
                    role = roles[0] if prop in ("background", "background-color") else roles[1] if prop == "color" else None
                    if prop == "selection-background-color":
                        role = im.Col.HEADER_ACTIVE
                    elif prop == "border-color":
                        role = im.Col.BORDER
                if role is not None:
                    try:
                        style.colors[role] = color(value)
                        continue
                    except ValueError:
                        pass
                ignored.append(f"{selector}: {prop}")
    return style, ignored


class StyleManagerModel:
    def __init__(self, styles_dir=None, package_dir=None):
        import chisurf
        from chisurf.core.settings import get_path
        self.styles_dir = pathlib.Path(styles_dir or get_path("settings") / "styles")
        self.package_dir = pathlib.Path(package_dir or pathlib.Path(chisurf.__file__).parent / "gui" / "styles")
        self.styles_dir.mkdir(parents=True, exist_ok=True)
        self.editor = TextEditor()
        self.editor.set_language(Language(name="QSS", comment_start="/*", comment_end="*/", has_double_quoted_strings=True,
            has_single_quoted_strings=True, punctuation=frozenset("{}:;,.#()")))
        self.current_file = None
        self.saved_text = ""
        self.status = ""
        self.apply_callback = None
        self.applied_style = None
        self.ignored_rules = []
        self.copy_defaults()
        self.refresh()
        if self.files:
            self.load(self.files[0], discard=True)

    @property
    def modified(self):
        return self.editor.text != self.saved_text

    def refresh(self):
        self.files = sorted(self.styles_dir.glob("*.qss"))

    def copy_defaults(self):
        for source in self.package_dir.glob("*.qss"):
            destination = self.styles_dir / source.name
            if not destination.exists():
                shutil.copyfile(source, destination)

    def load(self, path, *, discard=False):
        if self.modified and not discard:
            self.status = "Save or discard unsaved changes before opening another style."
            return False
        try:
            path = pathlib.Path(path)
            text = path.read_text(encoding="utf-8")
            self.editor.set_text(text)
            self.saved_text = text
            # Store the path as given: refresh() globs unresolved names, and a
            # resolved current_file (macOS /private symlinks) then never
            # matches the file list, leaving the combo on the wrong entry.
            self.current_file = path
            self.status = f"Loaded {path.name}"
            return True
        except (OSError, UnicodeError) as error:
            self.status = f"Error loading style: {error}"
            return False

    def new(self, name, *, discard=False):
        if self.modified and not discard:
            self.status = "Save or discard unsaved changes before creating a style."
            return False
        if not name or pathlib.Path(name).name != name or name in (".", ".."):
            self.status = "Choose a file name without directory components."
            return False
        if not name.endswith(".qss"):
            name += ".qss"
        destination = self.styles_dir / name
        try:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write("/* QSS Style Sheet */\n\n")
            self.refresh()
            return self.load(destination, discard=True)
        except OSError as error:
            self.status = f"Error creating style: {error}"
            return False

    def save(self, path=None, *, overwrite=False):
        destination = pathlib.Path(path).resolve() if path else self.current_file
        if destination is None:
            self.status = "Choose a save destination."
            return False
        if destination.exists() and destination != self.current_file and not overwrite:
            self.status = "Confirm replacement of the existing style."
            return False
        try:
            text = self.editor.text
            destination.write_text(text, encoding="utf-8")
            self.current_file = destination
            self.saved_text = text
            self.refresh()
            self.status = f"Saved {destination.name}"
            return True
        except (OSError, UnicodeError) as error:
            self.status = f"Error saving style: {error}"
            return False

    def apply(self):
        if not self.save():
            return False
        try:
            style, ignored = convert_qss(self.editor.text)
            if self.apply_callback:
                self.apply_callback(style)
            self.applied_style = style
            self.ignored_rules = ignored
            from chisurf.core.settings.settings_utils import update_settings_section
            persisted = update_settings_section("gui", {"style_sheet": self.current_file.name})
            self.status = f"Applied {self.current_file.name}; {len(ignored)} Qt-only declarations retained."
            if not persisted:
                self.status += " Preference could not be saved."
            return True
        except Exception as error:
            self.status = f"Error applying style: {error}"
            return False

    def reset(self, *, discard=False):
        if not discard:
            self.status = "Confirm reset: custom QSS files and unsaved changes will be removed."
            return False
        try:
            for path in self.styles_dir.glob("*.qss"):
                if path.is_file() or path.is_symlink():
                    path.unlink()
            self.copy_defaults()
            self.refresh()
            if self.files:
                self.load(self.files[0], discard=True)
            else:
                self.current_file = None
                self.editor.set_text("")
                self.saved_text = ""
            self.status = "Style files reset to defaults."
            return True
        except OSError as error:
            self.status = f"Error resetting styles: {error}"
            return False


class StyleManagerApp(ImApp):
    def __init__(self, model=None):
        self.model = model or StyleManagerModel()
        self.file_dialog = None
        self.dialog_operation = ""
        self.pending = None
        self.new_name = ""
        self.new_visible = False
        super().__init__(gui=self._render, continuous=False)
        self.model.apply_callback = self._apply_style

    def _apply_style(self, style):
        self.style = style
        self.model.editor.config.background_color = style.color(im.Col.FRAME_BG)
        self.request_frame()

    def request_file(self, operation):
        self.dialog_operation = operation
        self.file_dialog = FileDialog("Open style" if operation == "open" else "Save style as", mode="open" if operation == "open" else "save",
            directory=str(self.model.styles_dir), filters="Style sheets (*.qss)", filename=self.model.current_file.name if operation != "open" and self.model.current_file else "custom.qss")

    def accept_dialog(self, result):
        if result is False:
            self.file_dialog = None
        elif result:
            path = pathlib.Path(result[0]).resolve()
            if self.dialog_operation == "open":
                self.request_load(path)
                self.file_dialog = None
            else:
                if self.model.save(path, overwrite=bool(self.file_dialog.overwrite_confirmed)):
                    self.file_dialog = None

    def request_load(self, path):
        if self.model.modified:
            self.pending = ("load", path)
        else:
            self.model.load(path)

    def _render(self):
        viewport = im.get_main_viewport()
        im.set_next_window_pos(viewport.pos)
        im.set_next_window_size(viewport.size)
        if im.begin("Style Manager##native_style_root"):
            im.begin_child("style_content", (viewport.pos[0] + 8, viewport.pos[1] + 8,
                max(100, viewport.size[0] - 16), max(100, viewport.size[1] - 16)), scrollable=False)
            im.push_font({"family": "monospace", "size": 10})
            self._draw_main()
            im.pop_font()
            im.end_child()
        im.end()
        self._draw_dialogs()

    def _draw_main(self):
        m = self.model
        wide_toolbar = im.get_content_region_avail()[0] >= 500
        choices = [path.name for path in m.files]
        selected = m.files.index(m.current_file) if m.current_file in m.files else -1
        im.set_next_item_width(max(160, min(320, im.get_content_region_avail()[0] - 120)))
        changed, index = im.combo("Style File", selected, choices)
        im.set_item_tooltip("Browse editable QSS files copied to your user settings directory")
        if changed:
            self.request_load(m.files[index])
        if im.button("New"):
            if m.modified:
                self.pending = ("new", None)
            else:
                self.new_visible = True
        im.set_item_tooltip("Create a new QSS file without replacing an existing style")
        im.same_line()
        if im.button("Open"):
            self.request_file("open")
        im.set_item_tooltip("Choose a style sheet from another directory; unsaved changes require confirmation")
        im.same_line()
        if im.button("Save"):
            if m.current_file:
                m.save()
            else:
                self.request_file("save")
        im.set_item_tooltip("Save the current buffer without applying it")
        im.same_line()
        if im.button("Save As"):
            self.request_file("save")
        im.set_item_tooltip("Choose another destination; existing files require replacement confirmation")
        if wide_toolbar:
            im.same_line()
        if im.button("Apply"):
            m.apply()
        im.set_item_tooltip("Save and apply supported palette rules to this native window; Qt-only rules remain in the file")
        im.same_line()
        if im.button("Reset styles"):
            self.pending = ("reset", None)
        im.set_item_tooltip("Confirm deletion of user QSS files and restore packaged defaults")
        im.text_wrapped(str(m.current_file or "No style selected") + (" *" if m.modified else ""))
        if m.ignored_rules:
            if im.collapsing_header(f"Qt-only declarations ({len(m.ignored_rules)})"):
                im.text_wrapped(", ".join(dict.fromkeys(m.ignored_rules)))
            im.set_item_tooltip("Native widgets use palette roles; Qt selectors, images, dimensions and gradients cannot be applied verbatim")
        im.text_wrapped(m.status)
        im.text_editor("##style_source", m.editor, (0, max(100, im.get_content_region_avail()[1] - 8)))
        im.set_item_tooltip("Edit QSS source with syntax highlighting, selection, clipboard and undo/redo")

    def _draw_dialogs(self):
        if self.pending:
            im.set_next_window_size((480, 180), im.Cond.FIRST_USE_EVER)
            if im.begin("Confirm style change"):
                operation, path = self.pending
                im.text_wrapped("Remove all user QSS files and restore defaults?" if operation == "reset" else "Discard unsaved changes?")
                if im.button("Reset files" if operation == "reset" else "Discard changes"):
                    if operation == "reset":
                        self.model.reset(discard=True)
                    elif operation == "load":
                        self.model.load(path, discard=True)
                    else:
                        self.new_visible = True
                        self.model.editor.set_text(self.model.saved_text)
                    self.pending = None
                im.set_item_tooltip("Confirm the requested operation; discarded content cannot be restored")
                im.same_line()
                if im.button("Cancel change"):
                    self.pending = None
                im.set_item_tooltip("Keep the current buffer and files")
            im.end()
        if self.new_visible:
            im.set_next_window_size((480, 190), im.Cond.FIRST_USE_EVER)
            if im.begin("New style"):
                _, self.new_name = im.input_text("File name", self.new_name)
                im.set_item_tooltip("Enter a file name; .qss is added automatically and directory components are rejected")
                if im.button("Create style") and self.model.new(self.new_name):
                    self.new_visible = False
                im.set_item_tooltip("Create the file in your styles directory; existing names are preserved")
                im.same_line()
                if im.button("Cancel new"):
                    self.new_visible = False
                im.set_item_tooltip("Leave the current style unchanged")
                im.text_wrapped(self.model.status)
            im.end()
        if self.file_dialog:
            im.set_next_window_size((640, 520), im.Cond.FIRST_USE_EVER)
            if im.begin("Choose style file"):
                self.accept_dialog(self.file_dialog.draw())
                im.text_wrapped(self.model.status)
            im.end()

    def export_settings(self):
        return {"current_file": str(self.model.current_file) if self.model.current_file else ""}

    def restore_settings(self, settings):
        path = settings.get("current_file")
        if path and pathlib.Path(path).is_file():
            self.model.load(path, discard=True)

    def close(self):
        self.model.apply_callback = None
        self.file_dialog = None
        self.pending = None


def make_style_manager_app():
    return StyleManagerApp()
