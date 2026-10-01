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

from chisurf.plugins.traj.emtk_tool import SaveAction, TrajToolApp, topology_field, trajectory_field

from .view_model import RotateTranslateViewModel

HERE = pathlib.Path(__file__).parent
WARNING = (1.0, 0.75, 0.3, 1.0)

MATRIX_TIP = ("The 3x3 rotation matrix. The coordinates of every frame are multiplied by this matrix; "
              "the user must ensure it is a valid rotation matrix.")
TRANSLATION_TIP = "Added to every coordinate after the rotation, in Ångström."

SAVE = SaveAction(
    key="save",
    label="💾 Save rotated/translated…",
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
        super().__init__(model or RotateTranslateViewModel(), HERE, "rotate_translate.view.json",
                         "traj_rotate_translate_io", "Rotate / translate trajectory",
                         [trajectory_field(), topology_field()], SAVE)

    def draw_extra_io(self, width: float) -> None:
        spacing = im.get_style().item_spacing[0]
        cell = (width - 2 * spacing) / 3.0
        im.text("Rotation matrix")
        top = im.get_cursor_screen_pos()
        matrix = np.array(self.model.rotation_matrix, dtype=np.float32)
        for i in range(3):
            for j in range(3):
                if j:
                    im.same_line()
                im.set_next_item_width(cell)
                changed, value = im.input_float(f"##r{i}{j}", float(matrix[i, j]), fmt="%.6g")
                im.set_item_tooltip(MATRIX_TIP)
                if changed:
                    matrix[i, j] = value
                    self.model.rotation_matrix = matrix
                    self.tour.notify_used("rotation_matrix")
        self.remember("rotation_matrix", (top[0], top[1], width, im.get_cursor_screen_pos()[1] - top[1]))
        im.text("Translation [Ang.]")
        top = im.get_cursor_screen_pos()
        vector = np.array(self.model.translation_vector, dtype=np.float32)
        for k in range(3):
            if k:
                im.same_line()
            im.set_next_item_width(cell)
            changed, value = im.input_float(f"##t{k}", float(vector[k]), fmt="%.6g")
            im.set_item_tooltip(TRANSLATION_TIP)
            if changed:
                vector[k] = value
                self.model.translation_vector = vector
                self.tour.notify_used("translation")
        self.remember("translation", (top[0], top[1], width, im.get_cursor_screen_pos()[1] - top[1]))
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
