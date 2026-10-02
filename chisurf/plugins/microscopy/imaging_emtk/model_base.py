"""What every imaging model needs to be driven by an emtk window (no Qt)."""

from __future__ import annotations

from typing import Any, Callable


class EmtkModelMixin:
    """State and helpers an emtk app reads from its model.

    Attributes
    ----------
    SETTINGS : tuple of str
        Attributes saved by ``export_settings`` (the analysis parameters; never the data).
    runner : callable or None
        ``runner(method) -> bool`` runs the named method on a worker (the app installs it); without one the
        method runs at once, so the model is usable headless.
    dialog : str
        A file dialog the model asks the window to open (``""`` for none).
    busy : bool
        A worker is running: the form is greyed and the actions are disabled.
    status_line : str
        The message shown under the window's Help / Guide row (what the Qt status bar showed).
    folder : str
        Folder of the last file chosen, where the next dialog opens.
    """

    SETTINGS: tuple[str, ...] = ()
    runner: Callable[[str], bool] | None = None
    dialog: str = ""
    busy: bool = False
    status_line: str = ""
    folder: str = ""

    # -- jobs ----------------------------------------------------------- #
    def run_job(self, method: str) -> bool:
        """Run ``self.<method>()`` on the app's worker, or at once when there is none."""
        if self.busy:
            return False
        if self.runner is not None:
            return bool(self.runner(method))
        getattr(self, method)()
        return True

    def _progress(self, fraction: float, text: str) -> None:
        """A progress callback for the core functions: the status line counts the run."""
        self.status_line = f"{text} ({int(float(fraction) * 100)} %)"
        self.notify("progress")

    def request_dialog(self, kind: str) -> None:
        """Ask the window to open the file dialog *kind* (ignored while a worker runs)."""
        if not self.busy:
            self.dialog = kind

    def remember_folder(self, path: str) -> None:
        import pathlib

        parent = pathlib.Path(str(path)).parent
        if str(parent) not in ("", "."):
            self.folder = str(parent)

    # -- settings ------------------------------------------------------- #
    def export_settings(self) -> dict[str, Any]:
        """The analysis parameters and the last folder."""
        state = {name: getattr(self, name) for name in self.SETTINGS}
        state["folder"] = self.folder
        return state

    def restore_settings(self, state: dict[str, Any]) -> None:
        """Adopt saved parameters; a value of the wrong type or outside a choice is ignored."""
        if not isinstance(state, dict):
            return
        for name in self.SETTINGS:
            if name not in state:
                continue
            current = getattr(self, name)
            value = state[name]
            try:
                if isinstance(current, bool):
                    if not isinstance(value, bool):
                        continue
                elif isinstance(current, int):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                        continue
                    value = int(value)
                elif isinstance(current, float):
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
                        continue
                    value = float(value)
                elif isinstance(current, str):
                    if not isinstance(value, str):
                        continue
                    options = getattr(self, f"{name}_choices", None)
                    if options is not None and value not in options():
                        continue
            except (TypeError, ValueError):
                continue
            setattr(self, name, value)
        if isinstance(state.get("folder"), str):
            self.folder = state["folder"]
