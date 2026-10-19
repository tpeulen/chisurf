"""The style editor: emtk style sheets (``.css``), edited, saved and applied to the running window."""

from __future__ import annotations

import json
import pathlib
import shutil
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.widgets.text_editor import Language, TextEditor

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size


class StyleManagerModel:
    def __init__(self, styles_dir=None, package_dir=None):
        import chisurf
        from chisurf.core.settings import get_path

        self.styles_dir = pathlib.Path(styles_dir or get_path("settings") / "styles")
        self.package_dir = pathlib.Path(
            package_dir or pathlib.Path(chisurf.__file__).parent / "gui" / "styles"
        )
        self.styles_dir.mkdir(parents=True, exist_ok=True)
        self.editor = TextEditor()
        self._configure_default_editor()
        try:
            self.editor.set_language(Language.css())
        except Exception:
            self.editor.set_language(
                Language(
                    name="CSS",
                    comment_start="/*",
                    comment_end="*/",
                    has_double_quoted_strings=True,
                    has_single_quoted_strings=True,
                    punctuation=frozenset("{}:;,.#()"),
                )
            )

    def _configure_default_editor(self):
        self.editor.config.show_line_numbers = True
        self.editor.config.show_spaces = False
        self.editor.config.show_tabs = False
        self.editor.config.tab_size = 4
        self.editor.config.insert_spaces_on_tabs = True
        self.editor.config.highlight_current_line = True
        self.editor.config.font_role = "code"

        try:
            from chisurf.plugins.core.code_editor.gui.editor_preferences import (
                COLOR_SCHEMES,
                THEME_SCHEME,
                concrete_scheme,
                palette_for,
                rgba,
            )
            scheme_name = concrete_scheme(THEME_SCHEME)
            scheme = COLOR_SCHEMES.get(scheme_name, COLOR_SCHEMES["Dark"])
            self.editor.config.background_color = rgba(scheme["paper_color"])
            self.editor.config.margin_color = rgba(scheme["margins_background_color"])
            self.editor.config.selection_color = rgba(scheme["marker_background_color"])
            self.editor.config.current_line_color = rgba(scheme["caret_line_background_color"])
            self.editor.config.caret_color = rgba(scheme["default_color"])
            self.editor.config.line_number_color = rgba(scheme["default_color"])
            self.editor.palette = palette_for(scheme_name, scheme["default_color"])
        except Exception:
            pass
        self.current_file = None
        self.saved_text = ""
        self.status = ""
        self.apply_callback = None
        #: ``application_callback(css_text)`` restyles the running application; ``None`` uses
        #: :meth:`restyle_application` (the Qt application when one is already loaded in this process).
        self.application_callback = None
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
        css_files = list(self.styles_dir.glob("*.css"))
        self.files = sorted(css_files, key=lambda p: p.name)

    def copy_defaults(self):
        sources = list(self.package_dir.glob("*.css"))
        if not sources:
            try:
                from emtk import styles as emtk_styles

                for name in emtk_styles.available_stylesheets():
                    p = emtk_styles.get_stylesheet_path(name)
                    if p is not None and p.is_file():
                        sources.append(p)
            except Exception:
                pass
        for source in sources:
            destination = self.styles_dir / source.name
            if not destination.exists():
                try:
                    shutil.copyfile(source, destination)
                except (OSError, UnicodeError):
                    continue

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
        stem = pathlib.Path(name).stem
        if any(f.stem == stem for f in self.files):
            self.status = f"A style named {stem!r} already exists."
            return False
        if not name.endswith(".css"):
            name += ".css"
        destination = self.styles_dir / name
        try:
            with destination.open("x", encoding="utf-8") as stream:
                stream.write("/* EMTK Native Style Sheet */\n\n:root {\n    --window-bg: #242424;\n    --frame-bg: #2c2c2c;\n    --text: #f0f0f0;\n}\n\nwindow {\n    background-color: #242424;\n    color: #f0f0f0;\n}\n")
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

    def combined_css(self, theme_text):
        """The application's sheet as the startup builds it: the shared widget fragments, then the theme."""
        parts = []
        for folder in (self.package_dir / "widgets", self.styles_dir / "widgets"):
            if folder.is_dir():
                for path in sorted(folder.glob("*.css")):
                    try:
                        parts.append(path.read_text(encoding="utf-8"))
                    except (OSError, UnicodeError):
                        continue
        return "\n\n".join(part for part in (*parts, theme_text) if part)

    def restyle_application(self, text):
        """Apply *text* to EMTK and any application callback; returns ``True`` when restyled."""
        from emtk import theme

        theme_name = self.current_file.stem if self.current_file else "custom"
        try:
            theme.apply_stylesheet(text, name=theme_name)
        except Exception:
            pass

        if callable(self.application_callback):
            return bool(self.application_callback(text))

        return True

    def apply(self):
        if not self.save():
            return False
        try:
            from emtk import theme
            from emtk.stylesheet import parse_stylesheet

            theme_name = self.current_file.stem if self.current_file else "custom"
            full_text = self.combined_css(self.editor.text)
            try:
                theme.apply_stylesheet(full_text, name=theme_name)
            except Exception:
                pass

            try:
                _, _, style = parse_stylesheet(full_text)
                if self.apply_callback:
                    self.apply_callback(style)
                self.applied_style = style
            except Exception:
                pass

            restyled = self.restyle_application(full_text)

            from chisurf.core.settings.settings_utils import update_settings_section

            persisted = update_settings_section("gui", {"style_sheet": self.current_file.name, "theme": theme_name})
            self.status = (
                f"Applied {self.current_file.name} to EMTK."
                + (
                    " The running application was restyled."
                    if restyled
                    else " Takes effect in the main window at the next launch."
                )
            )
            if not persisted:
                self.status += " Preference could not be saved."
            return True
        except Exception as error:
            self.status = f"Error applying style: {error}"
            return False

    def reset(self, *, discard=False):
        if not discard:
            self.status = "Confirm reset: custom style files and unsaved changes will be removed."
            return False
        try:
            for path in self.styles_dir.glob("*.css"):
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


class StylePreview:
    """The live preview panel: the buffer's rules drawn as sample widgets.

    The buffer is parsed on change (cached by the editor's revision) and the
    samples are drawn through ``push_style_color`` -- the ImGui mechanism for
    "this region is coloured differently" -- so the preview shows the sheet
    being edited without touching the theme the rest of the process uses.
    That is the difference between the preview and Apply.
    """

    def __init__(self, model: StyleManagerModel):
        self.model = model
        self.style = None
        self._revision: tuple[Any, ...] | None = None
        self._text = None
        self._error = ""

    # -- the parsed sheet ------------------------------------------------ #
    def _sync(self) -> None:
        """Parse the buffer when it changed; a broken sheet previews the base."""
        editor = self.model.editor
        key = (editor.revision, editor.text)
        if key == self._revision:
            return
        self._revision = key
        from emtk.stylesheet import parse_stylesheet

        try:
            _, _, style = parse_stylesheet(editor.text)
            self.style = style
            self._error = ""
        except Exception as error:  # a half-typed sheet is not an error state
            self.style = None
            self._error = str(error)

    def _push(self) -> list:
        """Push the parsed colours; returns the tokens to pop afterwards."""
        from emtk.im_core import Col

        ctx = im.get_current_context()
        style = self.style
        if style is None:
            return []
        pushed = []
        for role in (
            Col.WINDOW_BG, Col.TEXT, Col.BORDER, Col.FRAME_BG,
            Col.BUTTON, Col.BUTTON_HOVERED, Col.BUTTON_ACTIVE,
            Col.HEADER, Col.HEADER_HOVERED, Col.HEADER_ACTIVE,
            Col.TAB, Col.TAB_SELECTED, Col.TITLE_BG, Col.TITLE_BG_ACTIVE,
            Col.POPUP_BG, Col.MENU_BAR_BG, Col.SCROLLBAR_BG, Col.SCROLLBAR_GRAB,
            Col.CHECK_MARK, Col.SLIDER_GRAB, Col.SLIDER_GRAB_ACTIVE,
            Col.TEXT_DISABLED,
        ):
            colour = style.colors.get(role)
            if colour is not None:
                ctx.push_style_color(role, colour)
                pushed.append(role)
        return pushed

    # -- drawing --------------------------------------------------------- #
    def draw(self) -> None:
        """Draw the preview surface and its samples, in the buffer's colours."""
        from emtk.im_core import Col

        self._sync()
        style = self.style
        avail = im.get_content_region_avail()
        width = max(200.0, min(360.0, avail[0] * 0.4))
        height = max(120.0, avail[1])
        ctx = im.get_current_context()
        pushed = self._push()
        try:
            im.begin_child("style_preview", (width, height), scrollable=False)
        except Exception:
            for role in reversed(pushed):
                ctx.pop_style_color()
            raise
        try:
            window_bg = (
                style.color(Col.WINDOW_BG) if style is not None else ctx.style.color(Col.WINDOW_BG)
            )
            box = im.get_cursor_screen_pos()
            box = (box[0], box[1], width, height)
            im.get_window_draw_list().add_rect_filled(
                (box[0], box[1]), (box[0] + width, box[1] + height), window_bg
            )
            im.text("Preview")
            if self._error:
                im.text_colored((255, 120, 120, 255), self._error[:120])
            elif style is None:
                im.text_wrapped("Nothing parsed yet.")
            else:
                self._draw_samples()
            im.end_child()
        finally:
            for role in reversed(pushed):
                ctx.pop_style_color()

    def _draw_samples(self) -> None:
        """A column of widgets that between them use most palette roles."""
        note = tr("Preview sample: shows how this control looks in the theme; it does nothing")
        if im.button("Button"):
            pass
        im.set_item_tooltip(note)
        im.same_line()
        if im.button("Hover me"):
            pass
        im.set_item_tooltip(note)
        changed, checked = im.checkbox("Check", True)
        im.set_item_tooltip(note)
        changed, value = im.slider_float("Slider##preview", 0.4, 0.0, 1.0)
        im.set_item_tooltip(note)
        changed, index = im.combo("Combo##preview", 0, ["First", "Second", "Third"])
        im.set_item_tooltip(note)
        changed, text = im.input_text("##preview_field", "Input field")
        im.set_item_tooltip(note)
        im.progress_bar(0.55)
        im.separator()
        im.text_wrapped("The quick brown fox jumps over the lazy dog.")
        im.text_disabled("Disabled text")


class StyleManagerApp(ImApp):
    def __init__(self, model=None):
        spec = json.loads(
            (pathlib.Path(__file__).with_name("app.view.json")).read_text(encoding="utf-8")
        )
        self.window_size = window_size(spec, (1200, 800))
        self.model = model or StyleManagerModel()
        self.preview = StylePreview(self.model)
        self.file_dialog = None
        self.dialog_operation = ""
        self.pending = None
        self.new_name = ""
        self.new_visible = False
        #: control name -> last drawn frame, for the guided tour's spotlight
        self.item_rects: dict[str, tuple] = {}
        gui_dir = pathlib.Path(__file__).parent
        self.tour = EmTkGuidedTour(
            gui_dir / "guide.json",
            get_target_rect=self.item_rects.get,
            owner=self,
            wait_for_controls=True,
        )
        self.help_window = EmTkHelpWindow(
            title="Style manager - Help",
            resource=gui_dir / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        super().__init__(gui=self._render, continuous=False)
        self.model.apply_callback = self._apply_style

    def _apply_style(self, style):
        self.style = style
        self.model.editor.config.background_color = style.color(im.Col.FRAME_BG)
        self.request_frame()

    def request_file(self, operation):
        self.dialog_operation = operation
        self.file_dialog = FileDialog(
            "Open style" if operation == "open" else "Save style as",
            mode="open" if operation == "open" else "save",
            directory=str(self.model.styles_dir),
            filters="Style sheets (*.css)",
            filename=self.model.current_file.name
            if operation != "open" and self.model.current_file
            else "custom.css",
        )

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
            im.begin_child(
                "style_content",
                (
                    viewport.pos[0] + 8,
                    viewport.pos[1] + 8,
                    max(100, viewport.size[0] - 16),
                    max(100, viewport.size[1] - 16),
                ),
                scrollable=False,
            )
            self._draw_main()
            im.end_child()
        im.end()
        self._draw_dialogs()
        vp = im.get_main_viewport()
        self.help_window.draw((0.0, 0.0, vp.size[0], vp.size[1]))
        self.tour.draw(*vp.size)

    def _remember(self, name):
        """Store the last drawn item's frame under *name* for the tour."""
        self.item_rects[name] = tuple(im.get_item_rect())

    def _draw_main(self):
        m = self.model
        wide_toolbar = im.get_content_region_avail()[0] >= 500
        choices = [path.name for path in m.files]
        selected = m.files.index(m.current_file) if m.current_file in m.files else -1
        im.set_next_item_width(max(160, min(320, im.get_content_region_avail()[0] - 120)))
        changed, index = im.combo("Style File", selected, choices)
        im.set_item_tooltip(tr("Browse the editable style sheets copied to your user settings directory"))
        self._remember("style_file")
        if changed:
            self.request_load(m.files[index])
            self.tour.notify_used("style_file")
        if im.button(tr("New")):
            if m.modified:
                self.pending = ("new", None)
            else:
                self.new_visible = True
        im.set_item_tooltip(tr("Create a new style sheet without replacing an existing one"))
        im.same_line()
        if action_button(
            "open",
            tooltip=tr(
                "Choose a style sheet from another directory; unsaved changes require confirmation"
            ),
        ):
            self.request_file("open")
        im.same_line()
        if action_button("save", tooltip=tr("Save the current buffer without applying it")):
            if m.current_file:
                m.save()
            else:
                self.request_file("save")
        im.same_line()
        if im.button(tr("Save As")):
            self.request_file("save")
        im.set_item_tooltip(
            tr("Choose another destination; existing files require replacement confirmation")
        )
        if wide_toolbar:
            im.same_line()
        if im.button(tr("Apply")):
            if m.apply():
                self.tour.notify_used("apply")
        im.set_item_tooltip(
            tr(
                "Save and apply supported palette rules to this native window; Qt-only rules remain in the file"
            )
        )
        self._remember("apply")
        im.same_line()
        if im.button(tr("Reset styles")):
            self.pending = ("reset", None)
        im.set_item_tooltip(tr("Confirm deletion of user custom style files and restore packaged defaults"))
        self._remember("reset_styles")
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self._remember("guide")
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self._remember("help")
        im.text_wrapped(str(m.current_file or "No style selected") + (" *" if m.modified else ""))
        im.text_wrapped(m.status)
        avail = im.get_content_region_avail()
        preview_w = max(200.0, min(340.0, avail[0] * 0.38)) if avail[0] >= 560 else 0.0
        editor_w = avail[0] - preview_w - (8.0 if preview_w else 0.0)
        im.text_editor(
            "##style_source", m.editor, (max(120.0, editor_w), max(100, avail[1] - 8))
        )
        self._remember("style_source")
        im.set_item_tooltip(
            tr(
                "Edit style sheet with syntax highlighting, selection, clipboard and undo/redo; "
                "hex colours show a swatch and braces fold"
            )
        )
        if preview_w:
            im.same_line()
            self.preview.draw()

    def _draw_dialogs(self):
        if self.pending:
            im.set_next_window_size((480, 180), im.Cond.FIRST_USE_EVER)
            if im.begin("Confirm style change"):
                operation, path = self.pending
                im.text_wrapped(
                    "Remove all user custom style files and restore defaults?"
                    if operation == "reset"
                    else "Discard unsaved changes?"
                )
                if im.button("Reset files" if operation == "reset" else "Discard changes"):
                    if operation == "reset":
                        self.model.reset(discard=True)
                    elif operation == "load":
                        self.model.load(path, discard=True)
                    else:
                        self.new_visible = True
                        self.model.editor.set_text(self.model.saved_text)
                    self.pending = None
                im.set_item_tooltip(
                    tr("Confirm the requested operation; discarded content cannot be restored")
                )
                im.same_line()
                if im.button(tr("Cancel change")):
                    self.pending = None
                im.set_item_tooltip(tr("Keep the current buffer and files"))
            im.end()
        if self.new_visible:
            im.set_next_window_size((480, 190), im.Cond.FIRST_USE_EVER)
            if im.begin("New style"):
                _, self.new_name = im.input_text("File name", self.new_name)
                im.set_item_tooltip(
                    tr(
                        "Enter a file name; .css is added automatically and directory components are rejected"
                    )
                )
                if im.button(tr("Create style")) and self.model.new(self.new_name):
                    self.new_visible = False
                im.set_item_tooltip(
                    tr("Create the file in your styles directory; existing names are preserved")
                )
                im.same_line()
                if im.button(tr("Cancel new")):
                    self.new_visible = False
                im.set_item_tooltip(tr("Leave the current style unchanged"))
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
        self.tour.stop()
        self.file_dialog = None
        self.pending = None


def make_style_manager_app():
    return StyleManagerApp()
