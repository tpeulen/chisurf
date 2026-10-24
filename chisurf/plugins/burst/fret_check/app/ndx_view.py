"""ndX as the burst-table viewer, hosted inside the smFRET window.

ndXplorer's emtk app (``ndxplorer.app.frame.NdxApp``) is a whole application
with its own docks, menus, gates and plots. Here it is a *child app*: drawn
into the "ndX" window's box with :meth:`emtk.app.ImApp.draw_child`, its
pointer, wheel and key events forwarded while the pointer is over that box,
and fed the burst table in memory as a ``DataSource`` -- no file in between,
the same rows the CSV export writes.

ndX lives in ChiSurf (``chisurf/modules/ndxplorer``). Without it installed
(or bundled into the page) the window says so; nothing else depends on it.
"""
from __future__ import annotations

__all__ = ["NdxView"]


class NdxView:
    def __init__(self, request_frame=None) -> None:
        self.app = None
        self.error = ""
        self._version = None
        self._request_frame = request_frame
        self.box = (0.0, 0.0, 0.0, 0.0)
        self.focus = False

    @staticmethod
    def available() -> bool:
        try:
            import ndxplorer.app.frame  # noqa: F401,PLC0415
        except Exception:  # noqa: BLE001 - absence is a state, not an error
            return False
        return True

    def ensure(self) -> bool:
        if self.app is not None:
            return True
        if self.error:
            return False
        try:
            from ndxplorer.app.frame import NdxApp  # noqa: PLC0415

            self.app = NdxApp(layout_store=None, session_autosave=False)
            if self._request_frame is not None and hasattr(self.app, "set_frame_request_callback"):
                self.app.set_frame_request_callback(self._request_frame)
        except Exception as exc:  # noqa: BLE001 - shown in the window
            self.error = f"ndX is not available here: {exc}"
            return False
        return True

    def show(self, columns: dict, version) -> None:
        """Give ndX the burst table (only when it changed)."""
        if version == self._version or not self.ensure():
            return
        import numpy as np  # noqa: PLC0415
        from ndxplorer.core.data_source import DataSource  # noqa: PLC0415

        source = DataSource.from_columns({k: np.asarray(v, dtype=np.float64) for k, v in columns.items()})
        self.app.model.path = "smFRET bursts"
        self.app.model.set_source(source)
        if hasattr(self.app, "data_changed"):
            self.app.data_changed()
        self._version = version

    # -- hosting ------------------------------------------------------------ #
    def draw(self, host, painter, box) -> None:
        self.box = tuple(float(v) for v in box)
        if self.app is not None and painter is not None:
            host.draw_child(painter, self.app, *self.box, local_coordinates=True)

    def inside(self, x, y) -> bool:
        bx, by, bw, bh = self.box
        return self.app is not None and bx <= x < bx + bw and by <= y < by + bh

    def _local(self, x, y):
        return x - self.box[0], y - self.box[1]

    def pointer_press(self, x, y, button, modifiers=0, clicks=1) -> bool:
        self.focus = self.inside(x, y)
        if self.focus:
            self.app.pointer_press(*self._local(x, y), button, modifiers, clicks)
        return self.focus

    def pointer_release(self, x, y, button, modifiers=0) -> None:
        if self.focus and self.app is not None:
            self.app.pointer_release(*self._local(x, y), button, modifiers)

    def pointer_move(self, x, y, buttons=0, modifiers=0) -> None:
        if self.app is not None and (self.focus or self.inside(x, y)):
            self.app.pointer_move(*self._local(x, y), buttons, modifiers)

    def wheel(self, x, y, steps, modifiers=0) -> bool:
        if self.inside(x, y):
            self.app.wheel(*self._local(x, y), steps, modifiers)
            return True
        return False

    def key(self, key, text="", modifiers=0) -> bool:
        if self.focus and self.app is not None:
            return bool(self.app.key(key, text, modifiers))
        return False

    def animating(self) -> bool:
        return bool(self.app is not None and getattr(self.app, "animating", lambda: False)())
