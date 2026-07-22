from __future__ import annotations

from collections.abc import Callable

from .animation import AnimationMixin
from .base import BaseCmd
from .editing import EditingMixin
from .exporting import ExportMixin
from .lifecycle import LifecycleMixin
from .loader import LoaderCommands
from .measurements import MeasurementMixin
from .rendering import RenderingMixin
from .rmf import RmfMixin
from .selection import SelectionMixin

MixinType = type[BaseCmd]


class Cmd(LoaderCommands, SelectionMixin, RenderingMixin, AnimationMixin, RmfMixin, MeasurementMixin, EditingMixin, LifecycleMixin, ExportMixin, BaseCmd):
    """Thin aggregator that wires together all command mixins."""

    def _builtin_commands(self) -> dict[str, Callable[[list[str]], object]]:
        cmds: dict[str, Callable[[list[str]], object]] = {}
        for mixin in (
            LoaderCommands,
            SelectionMixin,
            RenderingMixin,
            MeasurementMixin,
            EditingMixin,
            AnimationMixin,
            RmfMixin,
            LifecycleMixin,
            ExportMixin,
        ):
            helper = getattr(mixin, "_mixin_commands", None)
            if callable(helper):
                cmds.update(helper(self))
        cmds.update(
            {
                "help": self._cmd_help,
                "objects": self._cmd_objects,
                "get_names": self._cmd_get_names,
                "quit": self._cmd_quit,
                "exit": self._cmd_quit,
            }
        )
        return cmds

    # Python convenience API (thin wrappers around internal commands)
    def help(self) -> str:
        return self._cmd_help([])

    def load(self, *paths: str) -> None:
        self._cmd_load(list(paths))

    def open(self, *paths: str) -> None:
        self._cmd_load(list(paths))

    def fetch(self, *pdb_ids: str) -> None:
        self._cmd_fetch(list(pdb_ids))

    def fetch_emdb(self, *emdb_ids: str) -> None:
        self._cmd_fetch_emdb(list(emdb_ids))

    def fetch_ihm(self, *entry_ids: str) -> None:
        self._cmd_fetch_ihm(list(entry_ids))

    def as_(self, rep: str) -> None:
        # 'as' is a Python keyword, so this thin alias exposes the show_as command.
        self.show_as(rep)

    def distance(self, *tokens: str) -> None:
        self._cmd_distance(list(tokens))

    def angle(self, *tokens: str) -> None:
        self._cmd_angle(list(tokens))

    def dihedral(self, *tokens: str) -> None:
        self._cmd_dihedral(list(tokens))

    def rms(self, *args: str) -> None:
        self._cmd_rms(list(args))

    def rms_cur(self, *args: str) -> None:
        self._cmd_rms(list(args))

    def align(self, *args: str) -> None:
        self._cmd_align(list(args))

    def super(self, *args: str) -> None:
        self._cmd_super(list(args))

    def split_chains(self, prefix: str | None = None) -> None:
        args: list[str] = []
        if prefix:
            args.append(str(prefix))
        self._cmd_split_chains(args)

    def mset(self, *args: str) -> None:
        self._cmd_mset(list(args))

    def mplay(self, *args: str) -> None:
        self._cmd_mplay(list(args))

    def mpause(self, *args: str) -> None:
        self._cmd_mpause(list(args))

    def mstop(self, *args: str) -> None:
        self._cmd_mstop(list(args))

    def mclear(self, *args: str) -> None:
        self._cmd_mclear(list(args))

    def frame(self, index: int) -> None:
        self._cmd_frame([str(index)])

    def select(self, *tokens: str) -> None:
        self._cmd_select(list(tokens))

    def set(self, name: str, value: str) -> None:
        self._cmd_set([name, value])

    def objects(self) -> None:
        self._cmd_objects([])

    def get_names(self) -> None:
        self._cmd_get_names([])

    def enable(self, *tokens: str) -> None:
        self._cmd_enable(list(tokens))

    def disable(self, *tokens: str) -> None:
        self._cmd_disable(list(tokens))

    def deselect(self) -> None:
        self._cmd_deselect([])

    def clear(self) -> None:
        self._cmd_clear([])

    def iterate(self, *args: str) -> None:
        self._cmd_iterate(list(args))

    def alter(self, *args: str) -> None:
        self._cmd_alter(list(args))

    def remove(self, *args: str) -> None:
        self._cmd_remove(list(args))

    def quit(self) -> None:
        self._cmd_quit([])

    def exit(self) -> None:
        self._cmd_quit([])

    def delete(self, *tokens: str) -> None:
        """Delete objects by id or name (PyMOL-style delete)."""
        self._cmd_delete(list(tokens))

    def reinitialize(self, *tokens: str) -> None:
        self._cmd_reinitialize(list(tokens))

    def copy(self, target: str, source: str) -> None:
        self._cmd_copy([target, source])

    def png(self, filename: str, *args: str) -> None:
        self._cmd_png([filename, *args])

    def ray(self, *args: str) -> None:
        self._cmd_ray(list(args))
