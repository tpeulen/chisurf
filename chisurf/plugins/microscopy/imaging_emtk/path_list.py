"""A list of files with Add, Database, Remove and Clear: the CLSM files and the IRF file of the pixel-wise MLE tool.

Drawn as a ``custom`` section whose ``options`` name the model attribute (``target``), the dialog that adds files (``add``) and the button that
opens the database picker (``database``). The model owns the list (``sel_files`` / ``sel_irf_files``), the app only draws it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from emtk import im


class PathListView:
    """One file list: a selectable column of names and its buttons."""

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.selected: dict[str, int] = {}

    def draw(self, section: dict, model: Any) -> None:
        options = section.get("options") or {}
        target = str(options.get("target", section.get("target", "")))
        title = str(section.get("title", target))
        im.text_unformatted(title)
        im.set_item_tooltip(str(section.get("description", "")))
        start = im.get_item_rect()
        paths = list(getattr(model, target))
        index = min(self.selected.get(target, 0), max(len(paths) - 1, 0))
        if not paths:
            im.text_disabled(str(options.get("empty", "No file. Add or drop one.")))
        for i, path in enumerate(paths):
            if im.selectable(f"{Path(path).name}##{target}{i}", index == i):
                self.selected[target] = index = i
            im.set_item_tooltip(path)
            self.owner.item_rects[f"{target}.{i}"] = im.get_item_rect()
        self.owner.item_rects[title] = self.owner.form.rects[target] = start
        busy = bool(model.busy)
        room = im.get_content_region_avail()[0]
        used = 0.0
        for key, label, tip, needs_files, act in (
            (
                "add",
                "Add files" if not options.get("single") else "Choose file",
                str(options.get("add_tip", "Choose photon files to add.")),
                False,
                lambda: model.request_dialog(str(options.get("add", "add_files"))),
            ),
            (
                "database",
                "Database",
                "Pick a registered photon dataset from the database.",
                False,
                lambda: model.request_dialog(str(options.get("database", "database"))),
            ),
            (
                "remove",
                "Remove",
                "Remove the selected file from the list (the file itself is not deleted).",
                True,
                lambda: self._remove(model, target, index),
            ),
            (
                "clear",
                "Clear",
                "Empty the list without deleting any file.",
                True,
                lambda: self._clear(model, target),
            ),
        ):
            width = im.calc_text_size(label)[0] + 16.0
            if used and used + 6.0 + width <= room:
                im.same_line()
                used += 6.0 + width
            else:
                used = width
            im.begin_disabled(busy or (needs_files and not paths))
            if im.button(f"{label}##{target}.{key}"):
                act()
            im.set_item_tooltip(tip)
            self.owner.item_rects[f"{target}.{key}"] = im.get_item_rect()
            im.end_disabled()

    def _remove(self, model: Any, target: str, index: int) -> None:
        paths = list(getattr(model, target))
        if 0 <= index < len(paths):
            setattr(model, target, [p for i, p in enumerate(paths) if i != index])
            self.selected[target] = max(0, index - 1)
            model.notify("settings")

    def _clear(self, model: Any, target: str) -> None:
        setattr(model, target, [])
        self.selected[target] = 0
        model.notify("settings")
