"""
Deprecated schema module.

This module is maintained for backward compatibility only.
All schema definitions, migrations, and constants now live in
``mmfdb.schema.schema`` (version 17+).

New code should import from ``mmfdb.schema.schema`` directly.
"""

from __future__ import annotations

import warnings
from mmfdb.schema.schema import (
    SCHEMA_VERSION,
    CREATE_TABLES_SQL,
    CREATE_INDICES_SQL,
    migrate_schema,
    get_schema_version,
    set_schema_version,
    _ensure_column,
)

warnings.warn(
    "chisurf.core.fio.mmcif.db.schema is deprecated. "
    "Use mmfdb.schema.schema instead.",
    DeprecationWarning,
    stacklevel=2,
)
