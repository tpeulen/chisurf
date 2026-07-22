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
                "quit": self._cmd_quit,
                "exit": self._cmd_quit,
            }
        )
        return cmds

    # Python convenience API (thin wrappers around internal commands)
    def help(self) -> str:
        return self._cmd_help([])

    def as_(self, rep: str) -> None:
        # 'as' is a Python keyword, so this thin alias exposes the show_as command.
        self.show_as(rep)

    def quit(self) -> None:
        self._cmd_quit([])

    def exit(self) -> None:
        self._cmd_quit([])

