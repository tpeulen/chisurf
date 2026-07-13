"""General transformer contract (PRD-16).

One abstraction every data-transformer plugin (Burst Selection, Microtime Shifter,
background correction, correlation, …) obeys: declared typed input/output ports, a
`.dic`-declared parameter schema (PRD-11 ``mmfdb_operation_parameter_def``), a pure
``transform``, and uniform MMFDB registration as an operation node. Mirrors chinet's
typed node/ports on the data side.
"""

from chisurf.core.transform.transformer import (
    PortSpec,
    TransformInputs,
    TransformResult,
    Transformer,
    TransformerConformanceError,
    check_transformer_conformance,
    get_transformer,
    get_transformer_for_operation,
    list_transformers,
    register_transformer,
)
from chisurf.core.transform.mmfdb import require_authenticated_session, session_from_auth

__all__ = [
    "PortSpec",
    "TransformInputs",
    "TransformResult",
    "Transformer",
    "TransformerConformanceError",
    "check_transformer_conformance",
    "get_transformer",
    "get_transformer_for_operation",
    "list_transformers",
    "register_transformer",
    "require_authenticated_session",
    "session_from_auth",
]
