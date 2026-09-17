"""Test fixtures for mmfdb-admin handler tests."""

from __future__ import annotations

import os
import tempfile
from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest
from mmfdb.models import (
    EntityDefinition,
    FretPairDefinition,
    ProbeDefinition,
    SampleDefinition,
)
from mmfdb.repository import MFDatabase
from mmfdb.samples.sample_manager import create_sample


@pytest.fixture
def db():
    """Create a temporary MFDatabase for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from mmfdb.security.session import configured_default_user_id

        database = MFDatabase(os.path.join(tmpdir, "test.db"))
        # Writes stamp ownership with the configured default user, so that row
        # has to exist. Asked rather than named: this fixture hard-coded
        # ``admin`` after the default moved to ``user`` (e5d06d58e), and every
        # owned write then failed its foreign key. It is created unprivileged,
        # which keeps the first-admin bootstrap scenarios intact.
        default_user = configured_default_user_id()
        if not any(user.get("user_id") == default_user for user in database.get_users()):
            database.add_user(default_user, "Configured test user", is_admin=0)
        try:
            yield database
        finally:
            database.close()


@contextmanager
def patch_db(db):
    """Context manager that patches the services module's
    resolve_database_path to return the test database path,
    and patches auth functions to skip authentication/ACL checks.

    Usage in tests::

        def test_my_handler(db):
            sample_id = ...
            with patch_db(db):
                result = my_handler(sample_id=sample_id, auth=None)
    """
    mock_principal = MagicMock()
    mock_principal.user_id = "user_default"
    mock_principal.is_admin = True

    with ExitStack() as stack:
        mock = stack.enter_context(patch("mmfdb.admin.backend.services.resolve_database_path"))
        mock.return_value = db.db_path
        # A server registered earlier in the process pins its database path,
        # and the handlers prefer the pin to resolve_database_path.
        stack.enter_context(
            patch("mmfdb.admin.backend.services._resolved_db_path", str(db.db_path))
        )
        for target in (
            "mmfdb.admin.backend.auth_services.resolve_database_path",
            "mmfdb.admin.backend.measurement_services.resolve_database_path",
            "mmfdb.admin.backend.ndxplorer_services.resolve_database_path",
            "mmfdb.admin.backend.fluorophore_services.resolve_database_path",
        ):
            patched = stack.enter_context(patch(target))
            patched.return_value = db.db_path
        stack.enter_context(
            patch(
                "mmfdb.admin.backend.services._require_auth",
                return_value=mock_principal,
            )
        )
        stack.enter_context(
            patch(
                "mmfdb.admin.backend.services._require_or_acl_access",
                return_value=mock_principal,
            )
        )
        yield mock


@pytest.fixture
def sample_with_entities(db):
    """Create a sample with entities, probes, and FRET pairs for testing."""
    probes = [
        ProbeDefinition(
            name="Cy3B",
            entity_index=0,
            seq_id=1,
            comp_id="DA",
            asym_id="A",
        ),
        ProbeDefinition(
            name="ATTO647N",
            entity_index=0,
            seq_id=1,
            comp_id="DA",
            asym_id="A",
        ),
    ]
    entities = [
        EntityDefinition(
            name="DNA hairpin HP3",
            entity_type="polymer",
            sequence="CGTACG",
        ),
    ]
    fret_pairs = [
        FretPairDefinition(
            probe_1_index=0,
            probe_2_index=1,
            forster_radius_nm=6.5,
            kappa_squared=0.6666667,
            refractive_index=1.4,
        ),
    ]
    definition = SampleDefinition(
        name="HP3-Cy3B-ATTO647N",
        description="DNA hairpin with Cy3B and ATTO647N",
        entities=entities,
        probes=probes,
        fret_pairs=fret_pairs,
        buffer_description="PBS pH 7.4",
        ph=7.4,
        temperature_k=298.0,
    )
    sample_id = create_sample(db, definition)
    return db, sample_id
