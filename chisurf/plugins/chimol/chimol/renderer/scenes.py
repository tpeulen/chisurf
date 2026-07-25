"""Named scenes — PyMOL's ``scene``.

A scene is a bookmark for *everything you can see*: the camera, which objects are
enabled, how each is drawn, and what colour it is. That is more than ``get_view``
saves, and the difference is the point — a figure is rarely one camera angle, it
is a camera angle plus a particular set of things shown in particular colours.

PyMOL's ``scene`` takes flags for which of those to store and recall
(``view``, ``color``, ``active``, ``rep``, ``frame``), so a scene can carry only a
viewpoint, or only a colour scheme, and recalling it leaves the rest alone. Those
flags are reproduced here because they are what makes scenes composable: store one
scene for the orientation of a figure and another for its colouring, and recall
them independently.

What a scene deliberately does **not** capture is the structure itself. Recalling a
scene after deleting an object restores what it can and reports the rest, rather
than resurrecting atoms — a bookmark is not a snapshot of the session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["SCENE_ASPECTS", "Scene", "SceneStore"]

#: The aspects a scene can carry, matching PyMOL's per-aspect flags.
SCENE_ASPECTS: tuple[str, ...] = ("view", "active", "rep", "color")

#: State fields that describe *how* an object is drawn.
_REPRESENTATION_FIELDS: tuple[str, ...] = (
    "show_cartoon",
    "show_trace",
    "show_atoms",
    "show_sticks",
    "show_lines",
    "show_dots",
    "show_nonbonded",
    "show_labels",
    "show_atom_gaussians",
    "representation_mode",
    "cartoon_mask",
    "ball_mask",
    "sticks_mask",
    "sidechains_visible",
)

#: State fields that describe what colour it is.
_COLOR_FIELDS: tuple[str, ...] = (
    "color_mode",
    "colors_per_ca",
    "colors_per_residue_override",
    "colors_per_atom_override",
)


@dataclass
class Scene:
    """One stored scene.

    Attributes
    ----------
    name : str
        Scene key.
    view : list of float or None
        The 18-float camera tuple, when the scene carries a view.
    objects : dict
        Per object name: the captured aspects. Keyed by *name* rather than by id
        so that a scene survives objects being deleted and reloaded, which is the
        common case between sessions.
    message : str
        Optional text PyMOL displays with the scene.
    """

    name: str
    view: list[float] | None = None
    objects: dict[str, dict] = field(default_factory=dict)
    message: str = ""


def _copy(value):
    """Deep-enough copy: arrays are copied, everything else is immutable here."""
    if isinstance(value, np.ndarray):
        return value.copy()
    if isinstance(value, (list, dict, set)):
        return type(value)(value)
    return value


class SceneStore:
    """The scenes of one session, and the capture/recall against a viewer."""

    def __init__(self) -> None:
        self._scenes: dict[str, Scene] = {}
        #: Insertion order, which is the order ``scene next`` walks.
        self._order: list[str] = []

    # ------------------------------------------------------------------ query
    def names(self) -> list[str]:
        """Return the scene keys, in the order they were stored."""
        return list(self._order)

    def get(self, name: str) -> Scene | None:
        """Return the scene stored under ``name``, or ``None``."""
        return self._scenes.get(str(name))

    def __contains__(self, name: object) -> bool:
        """Whether a scene is stored under this key."""
        return str(name) in self._scenes

    def __len__(self) -> int:
        """Count the stored scenes."""
        return len(self._scenes)

    # ----------------------------------------------------------------- store
    def store(
        self,
        viewer,
        name: str,
        *,
        aspects: tuple[str, ...] = SCENE_ASPECTS,
        message: str = "",
    ) -> Scene:
        """Capture the current state under ``name``.

        Parameters
        ----------
        viewer : MolView
            Viewer to read.
        name : str
            Scene key. Storing over an existing key replaces it, keeping its
            position in the order, as PyMOL does.
        aspects : tuple of str
            Which of ``view``, ``active``, ``rep``, ``color`` to capture.
        message : str, optional
            Text to carry with the scene.

        Returns
        -------
        Scene
            The stored scene.
        """
        key = str(name)
        scene = Scene(name=key, message=str(message or ""))

        if "view" in aspects:
            try:
                scene.view = list(viewer.get_view_state())
            except Exception:
                scene.view = None

        for entry in getattr(viewer, "_objects", {}).values():
            captured: dict = {}
            if "active" in aspects:
                captured["visible"] = bool(getattr(entry, "visible", True))
            state = getattr(entry, "state", None)
            if state is not None:
                if "rep" in aspects:
                    captured["rep"] = {
                        f: _copy(getattr(state, f, None))
                        for f in _REPRESENTATION_FIELDS
                    }
                if "color" in aspects:
                    captured["color"] = {
                        f: _copy(getattr(state, f, None)) for f in _COLOR_FIELDS
                    }
            if captured:
                scene.objects[str(entry.name)] = captured

        if key not in self._scenes:
            self._order.append(key)
        self._scenes[key] = scene
        return scene

    # ---------------------------------------------------------------- recall
    def recall(
        self,
        viewer,
        name: str,
        *,
        aspects: tuple[str, ...] = SCENE_ASPECTS,
    ) -> tuple[int, list[str]]:
        """Restore a stored scene.

        Parameters
        ----------
        viewer : MolView
            Viewer to write.
        name : str
            Scene key.
        aspects : tuple of str
            Which aspects to restore. Aspects the scene never captured are
            skipped, so recalling ``color`` from a view-only scene does nothing
            rather than blanking the colours.

        Returns
        -------
        tuple
            ``(n_objects_restored, missing)`` where ``missing`` names objects the
            scene knew about that are no longer loaded. Reported rather than
            ignored: a scene recalled against a changed session is a common
            surprise, and silence makes it look like the scene was wrong.

        Raises
        ------
        KeyError
            If no scene is stored under ``name``.
        """
        scene = self._scenes[str(name)]

        # `view=0` has to mean the camera does not move, and in chimol that takes
        # work: the camera's offset is stored relative to the scene centre, which
        # shifts when what is drawn changes. Without holding the view across the
        # rebuild, "leave the view alone" still moves the picture.
        keep_view = None
        if "view" not in aspects:
            try:
                keep_view = list(viewer.get_view_state())
            except Exception:
                keep_view = None

        by_name = {
            str(entry.name): entry
            for entry in getattr(viewer, "_objects", {}).values()
        }
        restored, missing = 0, []
        for object_name, captured in scene.objects.items():
            entry = by_name.get(object_name)
            if entry is None:
                missing.append(object_name)
                continue
            if "active" in aspects and "visible" in captured:
                entry.visible = bool(captured["visible"])
            state = getattr(entry, "state", None)
            if state is not None:
                for aspect, fields in (("rep", "rep"), ("color", "color")):
                    if aspect not in aspects or fields not in captured:
                        continue
                    for attribute, value in captured[fields].items():
                        setattr(state, attribute, _copy(value))
            restored += 1

        try:
            viewer._update_view()
        except Exception:
            pass

        # The view goes back **last**, after the representations. The camera's
        # offset is stored relative to the scene centre, and changing what is
        # drawn moves that centre -- so a view restored first is undone by the
        # rebuild that follows it.
        wanted = scene.view if "view" in aspects else keep_view
        if wanted is not None:
            try:
                viewer.set_view_state(wanted)
            except Exception:
                pass
        return restored, missing

    # ---------------------------------------------------------------- manage
    def delete(self, name: str) -> bool:
        """Forget a scene. ``*`` forgets all of them, as in PyMOL."""
        key = str(name)
        if key == "*":
            self._scenes.clear()
            self._order.clear()
            return True
        if key not in self._scenes:
            return False
        del self._scenes[key]
        self._order.remove(key)
        return True

    def rename(self, name: str, new_name: str) -> bool:
        """Rename a scene, keeping its position in the order."""
        key, new_key = str(name), str(new_name)
        if key not in self._scenes or not new_key:
            return False
        scene = self._scenes.pop(key)
        scene.name = new_key
        self._scenes[new_key] = scene
        self._order[self._order.index(key)] = new_key
        return True

    def step(self, current: str | None, direction: int) -> str | None:
        """Return the next or previous scene key, wrapping around.

        Parameters
        ----------
        current : str or None
            Where to step from; ``None`` starts before the first scene.
        direction : int
            ``+1`` for next, ``-1`` for previous.

        Returns
        -------
        str or None
            The key to recall, or ``None`` when no scenes are stored.
        """
        if not self._order:
            return None
        if current is None or current not in self._order:
            return self._order[0 if direction >= 0 else -1]
        index = (self._order.index(current) + direction) % len(self._order)
        return self._order[index]
