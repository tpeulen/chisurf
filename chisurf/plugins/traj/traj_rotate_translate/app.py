"""emtk app for the Rotate/Translate-Trajectory tool: x' = R x + t on every frame.

Drawn from ``rotate_translate.view.json`` by the shared trajectory-tool app; the
spec's ``traj_rotate_translate_io`` section is the trajectory and topology rows,
the 3x3 rotation matrix, the translation and the save button, as the Qt section
draws them, followed by the stride.
"""

from __future__ import annotations

import pathlib

import numpy as np
from emtk import im

from chisurf.plugins.emtk_layout import NUMBER_WIDTH, icon_label
from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, topology_field, trajectory_field

from .view_model import RotateTranslateViewModel

HERE = pathlib.Path(__file__).parent
WARNING = (1.0, 0.75, 0.3, 1.0)
CELL_WIDTH = NUMBER_WIDTH     # one matrix / translation cell lines up with the stride field below it

MATRIX_TIP = ("The 3x3 rotation matrix. The coordinates of every frame are multiplied by this matrix; "
              "the user must ensure it is a valid rotation matrix.")
TRANSLATION_TIP = "Added to every coordinate after the rotation, in Ångström."

SAVE = SaveAction(
    key="save",
    label=icon_label("💾", "Save rotated/translated…"),
    tooltip="Rotate + translate every frame and write a new DCD trajectory.",
    dialog_title="Save trajectory",
    filters=[("DCD trajectory", ["*.dcd"])],
    run=lambda model, path: model.save_rotated_translated(path),
    suggest=lambda model: pathlib.Path(model.trajectory_filename).stem + "_moved.dcd",
)


def rotation_problem(matrix) -> str:
    """Why *matrix* is not a proper rotation, or ``""`` when it is (RᵀR = 1, det = +1)."""
    r = np.asarray(matrix, dtype=float)
    if not np.allclose(r.T @ r, np.eye(3), atol=1e-3):
        return "Not a rotation: RᵀR ≠ 1, so the molecule is sheared or scaled."
    if np.linalg.det(r) < 0:
        return "Not a rotation: det R = −1, so the molecule is mirrored."
    return ""


class RotateTranslateApp(TrajToolApp):
    """The Rotate/Translate-Trajectory window."""

    def __init__(self, model: RotateTranslateViewModel | None = None) -> None:
        self._typed: dict[str, str] = {}                  # what a cell shows while it is being typed
        super().__init__(model or RotateTranslateViewModel(), HERE, "rotate_translate.view.json",
                         "traj_rotate_translate_io", "Rotate / translate trajectory",
                         [trajectory_field(), topology_field()], SAVE)

    def _cell(self, name: str, value: float, width: float, tooltip: str) -> float | None:
        """One typed number cell; the new value on Enter or when the click goes elsewhere, else ``None``.

        The Qt editors are line edits: a number is typed, not dragged (emtk's ``input_float`` is a drag
        field). A text that is no number leaves the value.
        """
        shown = self._typed.get(name, f"{value:.6g}")
        im.set_next_item_width(width)
        entered, text = im.input_text(f"##{name}", shown, "",
                                      im.InputTextFlags.ENTER_RETURNS_TRUE | im.InputTextFlags.AUTO_SELECT_ALL)
        im.set_item_tooltip(tooltip)
        if text != shown:
            self._typed[name] = text
        clicked_away = im.get_io().mouse_clicked[0] and not im.is_item_hovered()
        if name in self._typed and (entered or clicked_away):
            typed = self._typed.pop(name)
            try:
                number = float(typed)
            except ValueError:
                return None
            if np.isfinite(number) and number != value:
                return number
        return None

    def extra_captions(self) -> list[str]:
        return ["Rotation matrix", "Translation [Ang.]"]

    def draw_extra_io(self, width: float) -> None:
        """The matrix and the translation as label/field rows: the caption in the label column, the cells beside it."""
        spacing = im.get_style().item_spacing[0]
        label_w = self.label_column()
        cell = min(CELL_WIDTH, (width - label_w - 2 * spacing) / 3.0)
        matrix = np.array(self.model.rotation_matrix, dtype=np.float32)
        top = None
        for i in range(3):
            im.text("Rotation matrix" if i == 0 else "")
            im.same_line(label_w)
            if top is None:
                top = im.get_cursor_screen_pos()
            for j in range(3):
                if j:
                    im.same_line()
                value = self._cell(f"r{i}{j}", float(matrix[i, j]), cell, MATRIX_TIP)
                if value is not None:
                    matrix[i, j] = value
                    self.model.rotation_matrix = matrix
                    self.tour.notify_used("rotation_matrix")
        self.remember("rotation_matrix", (top[0], top[1], 3 * cell + 2 * spacing,
                                          im.get_cursor_screen_pos()[1] - top[1]))
        im.text("Translation [Ang.]")
        im.same_line(label_w)
        top = im.get_cursor_screen_pos()
        vector = np.array(self.model.translation_vector, dtype=np.float32)
        for k in range(3):
            if k:
                im.same_line()
            value = self._cell(f"t{k}", float(vector[k]), cell, TRANSLATION_TIP)
            if value is not None:
                vector[k] = value
                self.model.translation_vector = vector
                self.tour.notify_used("translation")
        self.remember("translation", (top[0], top[1], 3 * cell + 2 * spacing, im.get_frame_height()))
        problem = rotation_problem(self.model.rotation_matrix)
        if problem:
            im.text_colored(WARNING, problem)

    def export_settings(self) -> dict:
        settings = super().export_settings()
        settings["rotation_matrix"] = np.asarray(self.model.rotation_matrix, dtype=float).tolist()
        settings["translation_vector"] = np.asarray(self.model.translation_vector, dtype=float).tolist()
        return settings

    def restore_settings(self, settings: dict) -> None:
        super().restore_settings(settings)
        if np.shape(settings.get("rotation_matrix")) == (3, 3):
            self.model.rotation_matrix = np.asarray(settings["rotation_matrix"], dtype=np.float32)
        if np.shape(settings.get("translation_vector")) == (3,):
            self.model.translation_vector = np.asarray(settings["translation_vector"], dtype=np.float32)


def make_app(**kwargs) -> RotateTranslateApp:
    """Construct the standalone Rotate/Translate-Trajectory app."""
    from chisurf.emtk.i18n import install

    install()
    return RotateTranslateApp()


__all__ = ["RotateTranslateApp", "make_app", "rotation_problem"]
