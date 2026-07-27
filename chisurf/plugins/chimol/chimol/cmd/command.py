from __future__ import annotations

from .animation import AnimationMixin
from .base import BaseCmd
from .editing import EditingMixin
from .exporting import ExportMixin
from .lifecycle import LifecycleMixin
from .loader import LoaderCommands
from .measurements import MeasurementMixin
from .rendering import RenderingMixin
from .selection import SelectionMixin
from .session import SessionMixin
from .symmetry import SymmetryMixin
from .volumes import VolumeMixin
from .settings import SettingsMixin

MixinType = type[BaseCmd]


class Cmd(LoaderCommands, SelectionMixin, SettingsMixin, RenderingMixin, AnimationMixin, MeasurementMixin, EditingMixin, LifecycleMixin, ExportMixin, SessionMixin, SymmetryMixin, VolumeMixin, BaseCmd):
    """Thin aggregator that wires together all command mixins."""

    def as_(self, rep: str) -> None:
        """Expose the ``as`` command under a valid Python name (``as`` is a keyword)."""
        self.show_as(rep)

