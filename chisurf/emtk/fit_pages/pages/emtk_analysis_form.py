r"""The fit Info page's Analysis tab, drawn by emtk.

The Qt page laid a ``QFormLayout`` over two line edits, an editable sample
combo, a UUID tool button and two small plain-text edits. This module keeps
every behaviour but draws the controls with emtk widgets inside one
:class:`emtk.qt_host.ControlHost`, like every other surface on the page:

* *Sample* is emtk's :class:`~emtk.widgets.combo.EditableComboBox` -- the
  database's samples in the list, a new id typed straight into the frame;
* *Analysis id* and *Analysis type* are one-line
  :class:`~emtk.widgets.basic.TextInput` fields (the id read-only in spirit:
  nothing routes keys into it);
* the two detail boxes are small read-write emtk ``TextEditor``\ s -- the
  same widget the report above the tab strip uses;
* the UUID regenerate button is an emtk :class:`~emtk.widgets.buttons.Button`.

Focus follows the click: a press routes into the field it landed on and keys
go there until another field is clicked. The Qt-facing call surface
(``sample_combo.setEditText``, ``sample_details_edit.setPlainText`` and
friends) is preserved on the form so ``_refresh`` keeps its vocabulary.
"""

from __future__ import annotations

import importlib.util
from typing import Any, Callable

if importlib.util.find_spec("emtk") is not None:  # pragma: no cover - env guard
    from emtk import style
    from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER
    from emtk.widgets.basic import TextInput
    from emtk.widgets.buttons import SmallButton
    from emtk.widgets.combo import EditableComboBox
    from emtk.widgets.text_editor import TextEditor

    class _DetailEditor:
        """A small read-write emtk text editor standing in for a QPlainTextEdit."""

        def __init__(self, on_change: Callable[[], None]) -> None:
            self.editor = TextEditor()
            self._on_change = on_change
            self._revision = 0

        @property
        def text(self) -> str:
            return self.editor.text

        def set_text(self, text: str) -> None:
            self.editor.set_text(text)

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            self.editor.draw(p, x, y, w, h)

        def press(self, *args) -> bool:
            before = (self.editor.text, self.editor.revision)
            self.editor.press(*args)
            return self._changed_since(before)

        def key(self, key: int, text: str, modifiers: int) -> bool:
            before = (self.editor.text, self.editor.revision)
            self.editor.key(key, text, modifiers)
            return self._changed_since(before)

        def _changed_since(self, before: tuple) -> bool:
            after = (self.editor.text, self.editor.revision)
            if after != before:
                self._on_change()
                return True
            return False

    class EmtkAnalysisForm:
        """One emtk control: the whole Analysis form, drawn into a box."""

        #: Fraction of the row's width the caption takes; the control the rest.
        LABEL_SHARE = 0.24

        def __init__(
            self,
            on_generate_uuid: Callable[[], None],
            on_changed: Callable[[], None],
        ) -> None:
            self._on_generate_uuid = on_generate_uuid
            self._on_changed = on_changed
            self.analysis_id = TextInput("Analysis id", "")
            self.method = TextInput("Analysis type", "", placeholder="auto-detected or type here")
            self.method.field.on_change = lambda _text: on_changed()
            self.sample = EditableComboBox("Sample", [], on_change=lambda _t: on_changed())
            self.uuid_button = SmallButton("↻")
            self._uuid_press = on_generate_uuid
            self.sample_details = _DetailEditor(on_change=on_changed)
            self.condition_details = _DetailEditor(on_change=on_changed)
            self.uuid_text = ""
            self._focus: Any = self.method.field
            self._rows: list[tuple[str, float, float, float, float, Any]] = []
            self._uuid_box: tuple[float, float, float, float] | None = None
            self._sample_details_box: tuple[float, float, float, float] | None = None
            self._condition_box: tuple[float, float, float, float] | None = None

        # -- values (the vocabulary _refresh speaks) ----------------------- #
        def set_analysis_id(self, text: str) -> None:
            self.analysis_id.set_text(text)

        def set_method(self, text: str) -> None:
            self.method.set_text(text)

        def set_samples(self, options: list[str]) -> None:
            current = self.sample.text
            self.sample.set_options(options)
            if current:
                self.sample.set_text(current)

        def set_sample(self, text: str) -> None:
            self.sample.set_text(text)

        def set_uuid(self, text: str) -> None:
            self.uuid_text = text

        def method_value(self) -> str:
            return self.method.text

        def sample_value(self) -> str:
            return self.sample.text

        # -- drawing ------------------------------------------------------- #
        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            line = p.line_height()
            pad = 4.0
            row_h = line * 1.7
            inner_w = w - 2.0 * pad
            label_w = inner_w * self.LABEL_SHARE
            self._rows = []

            def row(at_y: float, height: float, caption: str, control) -> float:
                p.text(
                    x + pad,
                    at_y,
                    max(label_w - 8.0, 1.0),
                    height,
                    ALIGN_VCENTER | ALIGN_LEFT,
                    caption,
                    style.DIM,
                )
                cx = x + pad + label_w
                control.label = ""
                control.draw(p, cx, at_y, max(x + w - pad - cx, 1.0), height)
                self._rows.append((caption, cx, at_y, x + w - pad - cx, height, control))
                return at_y + height + pad * 0.5

            y_cursor = y + pad * 0.5
            y_cursor = row(y_cursor, row_h, "Analysis id", self.analysis_id)
            y_cursor = row(y_cursor, row_h, "Analysis type", self.method)
            # Sample row: combo + the UUID regenerate button beside it.
            p.text(
                x + pad,
                y_cursor,
                max(label_w - 8.0, 1.0),
                row_h,
                ALIGN_VCENTER | ALIGN_LEFT,
                "Sample",
                style.DIM,
            )
            button_w = line * 1.4
            combo_w = max(x + w - pad - (x + pad + label_w) - button_w - pad, 1.0)
            self.sample.label = ""
            self.sample.draw(p, x + pad + label_w, y_cursor, combo_w, row_h)
            self._rows.append(("Sample", x + pad + label_w, y_cursor, combo_w, row_h, self.sample))
            self._uuid_box = (x + pad + label_w + combo_w + pad, y_cursor, button_w, row_h)
            self.uuid_button.draw(p, *self._uuid_box)
            y_cursor += row_h + pad * 0.5
            # The UUID line: small text under the sample row.
            p.text(
                x + pad + label_w,
                y_cursor,
                max(inner_w - label_w, 1.0),
                line * 0.9,
                ALIGN_VCENTER | ALIGN_LEFT,
                self.uuid_text,
                style.DIM,
            )
            y_cursor += line * 0.9 + pad * 0.25
            rest = max(y + h - y_cursor - pad, line * 3.0)
            self._sample_details_box = (x + pad, y_cursor, inner_w, rest * 0.5 - pad * 0.25)
            self._condition_box = (
                x + pad,
                y_cursor + rest * 0.5 + pad * 0.25,
                inner_w,
                rest * 0.5 - pad * 0.25,
            )
            self.sample_details.draw(p, *self._sample_details_box)
            self.condition_details.draw(p, *self._condition_box)

        # -- input --------------------------------------------------------- #
        def press(
            self,
            x: float,
            y: float,
            box_x: float,
            box_y: float,
            box_w: float,
            box_h: float,
            modifiers: int,
            clicks: int,
        ) -> bool:
            if self._uuid_box is not None:
                ux, uy, uw, uh = self._uuid_box
                if ux <= x <= ux + uw and uy <= y <= uy + uh:
                    self.uuid_button.press(x, y, ux, uy, uw, uh)
                    self._uuid_press()
                    return True
            for _caption, cx, cy, cw, ch, control in self._rows:
                if cx <= x <= cx + cw and cy <= y <= cy + ch:
                    self._focus = getattr(control, "field", None) or control
                    press = getattr(control, "press", None)
                    if callable(press):
                        press(x, y, cx, cy, cw, ch)
                    return True
            for name, box in (
                ("sample_details", self._sample_details_box),
                ("condition_details", self._condition_box),
            ):
                if box is None:
                    continue
                bx, by, bw, bh = box
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    editor = getattr(self, name)
                    self._focus = editor.editor.cursors
                    editor.press(x, y, bx, by, bw, bh, modifiers, clicks)
                    return True
            return True

        def key(self, key: int, text: str, modifiers: int) -> bool:
            """Route a key into whichever field the last click focused."""
            focus = self._focus
            if focus is self.sample.field:
                return self.sample.key(key, text, modifiers)
            if focus is self.method.field:
                return self._feed(self.method, key, text, modifiers)
            if focus is self.sample_details.editor.cursors:
                return self.sample_details.key(key, text, modifiers)
            if focus is self.condition_details.editor.cursors:
                return self.condition_details.key(key, text, modifiers)
            key_hook = getattr(focus, "key", None)
            if callable(key_hook):
                return bool(key_hook(key, text, modifiers))
            return True

        @staticmethod
        def _feed(target: Any, key: int, text: str, modifiers: int) -> bool:
            hook = getattr(target, "key", None)
            if callable(hook):
                return bool(hook(key, text, modifiers))
            field = getattr(target, "field", None)
            if field is not None:
                return bool(field.key(key, text, modifiers))
            return True

        def focus_lost(self) -> None:
            return None

else:  # pragma: no cover - emtk missing
    EmtkAnalysisForm = None  # type: ignore[assignment]
    _DetailEditor = None  # type: ignore[assignment]
