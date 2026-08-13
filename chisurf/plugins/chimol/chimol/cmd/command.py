from __future__ import annotations

from .animation import AnimationMixin
from .base import BaseCmd
from .editing import EditingMixin
from .exporting import ExportMixin
from .inspect import InspectMixin
from .lifecycle import LifecycleMixin
from .loader import LoaderCommands
from .measurements import MeasurementMixin
from .presets import PresetMixin
from .rendering import RenderingMixin
from .selection import SelectionMixin
from .session import SessionMixin
from .symmetry import SymmetryMixin
from .volumes import VolumeMixin
from .settings import SettingsMixin
from .interactions import InteractionMixin

MixinType = type[BaseCmd]


class Cmd(LoaderCommands, SelectionMixin, SettingsMixin, RenderingMixin, PresetMixin, AnimationMixin, MeasurementMixin, InteractionMixin, EditingMixin, InspectMixin, LifecycleMixin, ExportMixin, SessionMixin, SymmetryMixin, VolumeMixin, BaseCmd):
    """Thin aggregator that wires together all command mixins."""

    def as_(self, rep: str) -> None:
        """Expose the ``as`` command under a valid Python name (``as`` is a keyword)."""
        self.show_as(rep)

