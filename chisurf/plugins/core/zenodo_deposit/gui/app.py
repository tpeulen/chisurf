"""Native emtk Zenodo deposit tool: review a record, then upload it as a draft.

The window is the view spec ``zenodo_deposit_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections`; the review state, the gate and the
worker are :class:`~.model.ZenodoDepositModel`. Only Help and Guide are drawn
here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_sections

from chisurf.plugins.core.metadata_editor.core import zenodo_schema
from chisurf.plugins.core.metadata_editor.gui.widget import MetadataEditorWidget

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .model import ZenodoDepositModel

HERE = Path(__file__).parent


class ZenodoDepositApp(ImApp):
    """Review a deposition record and upload it to Zenodo."""

    def __init__(self, model: ZenodoDepositModel | None = None) -> None:
        self.model = model or ZenodoDepositModel()
        spec = json.loads((HERE / "zenodo_deposit_emtk.view.json").read_text(encoding="utf-8"))
        self.window_size = window_size(spec, (1280, 900))
        self.sections = spec["sections"]
        self.metadata_editor = MetadataEditorWidget(on_apply=self.model.apply_metadata)
        self.form = FormState()
        self.form.custom["metadata_editor"] = self._draw_metadata_editor
        self.item_rects: dict[str, tuple] = {}
        self.help_window = EmTkHelpWindow(
            title="Zenodo deposit — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        #: The file dialog of step 2 (Add files / Add folder), open while the model asks.
        self.dialog: FileDialog | None = None
        self.dialog_window = DialogWindow("Add to the record", size=(720.0, 460.0),
                                          key="zenodo-deposit-add")
        #: Modal while a build, scan, upload or check runs: the record must not change under it.
        self.progress_window = DialogWindow("Working", size=(520.0, 170.0), close_button=False,
                                            key="zenodo-deposit-progress", escape_closes=False,
                                            fit_height=True)
        self.file_window = DialogWindow("File", size=(900.0, 620.0),
                                        key="file-view")
        self.file_editor = None          # TextEditor, rebuilt when the file changes
        self.file_editor_path = None
        self.tttr_window = DialogWindow("TTTR Inspector", size=(1100.0, 760.0),
                                        key="tttr-inspector")
        self.inspector = None            # NativeHeaderEditor of the open TTTR file
        self.inspector_path = None
        self.publish_window = DialogWindow("Publish", size=(560.0, 190.0),
                                           key="zenodo-deposit-publish", fit_height=True)
        self.docks = DockManager(Region("deposit"))
        # The tool's only panel: it cannot be closed, or the tool would stay empty.
        self.docks.add_window("deposit", "Zenodo deposit", self.draw_deposit, dock="deposit",
                              closable=False)
        super().__init__(self.render, continuous=True)

    def render(self) -> None:
        self.model.poll()
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        if not self.docks.window("deposit").visible:
            # a layout saved while the panel could still be closed
            self.docks.show("deposit")
        busy = self.model.job.running or bool(self.model.publish_stage)
        im.begin_disabled(self.dialog is not None or busy)
        self.docks.draw(box)
        im.end_disabled()
        self.help_window.draw(box)
        self.draw_file_window(box)
        self.draw_tttr_window(box)
        self.tour.draw(*vp.size)
        self.draw_dialog(box)
        self.draw_progress(box)
        self.draw_publish_question(box)

    def draw_publish_question(self, box: Any) -> None:
        """Publishing is irreversible: three questions, each must be answered yes; Cancel stops."""
        title, text, button = self.model.publish_question()
        if not title:
            self.publish_window.hide()
            return
        self.publish_window.title = title
        self.publish_window.show()
        pressed = self.publish_window.begin(box)
        from emtk.widgets.markdown import render_markdown

        render_markdown(text)
        im.spacing()
        yes = im.button(f"{button}##publish-yes")
        im.set_item_tooltip(
            tr("Answer yes. The third yes publishes the record, which cannot be undone.")
        )
        im.same_line()
        no = action_button("cancel", tooltip=tr("Stop here: nothing is published."), id="publish-no")
        self.publish_window.end()
        if yes:
            self.model.confirm_publish()
        elif no or pressed == "close":
            self.model.cancel_publish()

    def draw_file_window(self, box: Any) -> None:
        """The file a reviewer double-clicked in the file listing, in a modal:
        text files in a read-only code editor, Markdown rendered, binary raw
        data as a short info card."""
        m = self.model
        if m.file_view is None or m.file_view.get("kind") == "tttr":
            self.file_window.hide()
            return
        self.file_window.title = f"File: {m.file_view['title']}"
        self.file_window.show()
        pressed = self.file_window.begin(box)
        from emtk.widgets.markdown import render_markdown

        if m.file_view.get("markdown"):
            render_markdown(m.file_view["text"])
        else:
            from emtk.widgets.text_editor import TextEditor, shipped_languages

            path = m.file_view["path"]
            if self.file_editor is None or self.file_editor_path != path:
                langs = {k.lower(): v for k, v in shipped_languages().items()}
                language = langs.get(str(m.file_view.get("language") or "").lower())
                self.file_editor = TextEditor(m.file_view["text"], language=language,
                                              read_only=True)
                self.file_editor_path = path
            editor = self.file_editor
            cb = self.file_window.content_box
            ex, ey = (cb[0], cb[1]) if cb else (0.0, 0.0)
            avail_w, avail_h = im.get_content_region_avail()[:2]
            editor.draw(im.get_current_context().p, ex, ey, avail_w, max(avail_h, 60.0))
            io = im.get_current_context().io
            if io.mouse_wheel and im.is_item_hovered():
                editor.scroll(-3 if io.mouse_wheel > 0 else 3)
        self.file_window.end()
        if pressed == "close":
            m.close_file_view()

    def draw_tttr_window(self, box: Any) -> None:
        """A double-clicked TTTR file opens the TTTR inspector itself (the
        plugins/tttr/tttr_header_edit tool) in a modal: header tags and the
        photon table, loaded in the background so big files do not stall."""
        m = self.model
        fv = m.file_view
        if not fv or fv.get("kind") != "tttr":
            self.tttr_window.hide()
            if self.inspector is not None:      # released with the view
                self.inspector.close()
                self.inspector, self.inspector_path = None, None
            return
        path = fv["path"]
        if self.inspector_path != path:
            if self.inspector is not None:
                self.inspector.close()
            from chisurf.plugins.tttr.tttr_header_edit.gui.native import (
                NativeHeaderEditor,
            )

            self.inspector = NativeHeaderEditor()
            self.inspector_path = path
            self.inspector.load(path)          # background job
        self.tttr_window.title = f"TTTR Inspector — {fv['title']}"
        self.tttr_window.show()
        pressed = self.tttr_window.begin(box)
        inspector = self.inspector
        if inspector is not None:
            inspector.job.poll()
            x, y = im.get_cursor_screen_pos()
            width, height = im.get_content_region_avail()[:2]
            inspector.docks.draw((x, y, max(100.0, width), max(120.0, height)))
            if inspector.dialog is not None:   # its Open / Save-as-PTU chooser
                if im.begin("Header file chooser"):
                    result = inspector.dialog.draw()
                    if result is not None:
                        callback = inspector.dialog_callback
                        inspector.dialog = None
                        if result:
                            callback(result)
                im.end()
        self.tttr_window.end()
        if pressed == "close":
            if inspector is not None:
                inspector.close()
            self.inspector, self.inspector_path = None, None
            m.close_file_view()

    def draw_progress(self, box: Any) -> None:
        """While a job runs: what it is, its current step, the time so far; Cancel for a build."""
        m = self.model
        if not m.job.running:
            self.progress_window.hide()
            return
        self.progress_window.title = m.busy_what[:1].upper() + m.busy_what[1:]
        self.progress_window.show()
        pressed = self.progress_window.begin(box, ["Cancel"] if m.busy_cancellable else [])
        im.progress_bar(-im.get_time() * 0.6, (-1.0, 0.0))
        im.text_wrapped(m.busy_step or "working…")
        im.text_disabled(f"{m.busy_elapsed} elapsed -- the window is locked until it is done")
        self.progress_window.end()
        if pressed == "Cancel":
            m.cancel_job()

    def draw_dialog(self, box: Any) -> None:
        """The chooser of step 2: files (several) or one folder, added as the named item."""
        if self.model.pick and self.dialog is None:
            folder = self.model.pick == "folder"
            self.dialog = FileDialog(
                "Add a folder to the record" if folder else "Add files to the record",
                mode="folder" if folder else "open", multiselect=not folder,
                directory=self.model.pick_directory, action="Add")
            self.dialog_window.title = self.dialog.title
            self.dialog_window.show()
        if self.dialog is None:
            return
        pressed = self.dialog_window.begin(box)
        result = self.dialog.draw()
        self.dialog_window.end()
        if result:
            self.model.pick_directory = self.dialog.directory
            self.dialog = None
            self.model.add_paths(result)
        elif result is False or pressed == "close":
            self.dialog = None
            self.model.pick = ""

    def on_files_dropped(self, paths) -> bool:
        """Files dropped on the window are added as the item named in step 2."""
        if self.dialog is None and self.model.enabled("add_files"):
            self.model.add_paths([str(p) for p in paths])
        return True

    def _draw_metadata_editor(self, section, model, state, width: float) -> None:
        """The deposit metadata through the one shared editor (core plugin)."""
        if model.record is None or model.job.running:
            return  # nothing to edit while a job owns the record
        if not self.metadata_editor.visible:
            self.metadata_editor.open(zenodo_schema(), model.metadata_values())
        self.metadata_editor.draw()
        self.item_rects.update(self.metadata_editor.item_rects)

    def draw_deposit(self, box: Any) -> None:
        """Help / Guide, then the records, the items, the selected item and the upload."""
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        im.same_line()
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.separator()
        draw_sections(self.sections, self.model, self.form, titles=True)
        for name in ("records", "items"):
            if name in self.form.rects:
                self.item_rects[f"{name}_table"] = self.form.rects[name]

    def export_settings(self) -> dict:
        """The data root and the sandbox switch; reviews live in the records."""
        return self.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.model.restore_settings(settings)

    def close(self) -> None:
        """Stop a running step; an upload in flight is abandoned, never half-published."""
        self.model.close()


def create_app() -> ZenodoDepositApp:
    """Build the deposit app (the manifest's ``entrypoints.emtk``)."""
    return ZenodoDepositApp()


make_app = create_app
