from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class PortSpec:
    """Specification of a node port used for layout and logic."""
    name: str
    is_output: bool
    # Optional type information and constraints. ``port_type`` is a short
    # abbreviation such as "sF"/"sI"/"vF"/"vI" (scalar/vector int/float).
    # ``fixed`` marks the port as fixed (non-variable), and ``min_value`` /
    # ``max_value`` allow bounded ranges for numeric ports. All fields are
    # optional so existing graphs that only specify names continue to work.
    #
    # Empty means **untyped**, and the port then draws no type label. The
    # default used to be the literal ``"spectral"`` -- a name from one graph's
    # domain -- so every port of every graph that stated no type was drawn with
    # the word "spectral" beside it. Compatibility is unchanged: an untyped port
    # matches only another untyped one, exactly as two "spectral" ports did.
    port_type: str = ""
    fixed: bool = False
    min_value: float | None = None
    max_value: float | None = None


@dataclass
class NodeModel:
    """Model for a node: title, port specs and optional widget factory.

    The document layer reads from this model; the emtk control draws it.
    The ``content_factory`` hook is what a host sets when a node body needs
    to host live controls rather than drawn text.
    """

    title: str
    inputs: List[PortSpec]
    outputs: List[PortSpec]
    node_type: str = "generic"
    config: Dict[str, Any] = field(default_factory=dict)
    content_factory: Optional[Callable] = None
    id: str = field(default_factory=lambda: str(__import__("uuid").uuid4()))
