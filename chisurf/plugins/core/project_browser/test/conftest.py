"""Shared fixtures for the project browser's tests.

``db`` is a scratch project database served by a real authenticated MMFDB
server; pytest resolves a fixture's own dependencies by name from the
requesting test's scope, so they are exposed here with it.
"""

from .test_emtk_project_browser_parity import db  # noqa: F401
from .test_project_browser_services import (  # noqa: F401
    authenticated_browser,
    sample_project_payload,
    standalone_server,
)
