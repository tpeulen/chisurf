"""Shared fixtures for the ChiSurf agent tests."""

from __future__ import annotations

import pathlib

import pytest

import chisurf as cs
from chisurf.core.agent import AgentContext

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
TCSPC_DIR = DATA_DIR / "tcspc" / "EasyTau300"


@pytest.fixture()
def clean_session():
    """Empty ``chisurf.imported_datasets`` and ``chisurf.fits`` around a test."""
    datasets = list(getattr(cs, "imported_datasets", []))
    fits = list(getattr(cs, "fits", []))
    cs.imported_datasets[:] = []
    cs.fits[:] = []
    try:
        yield
    finally:
        cs.imported_datasets[:] = datasets
        cs.fits[:] = fits


@pytest.fixture()
def context(clean_session, tmp_path):
    """Return an :class:`AgentContext` rooted at the test-data directory."""
    return AgentContext(
        working_directory=str(DATA_DIR),
        allow_code_execution=True,
        extras={"tmp_path": str(tmp_path)},
    )
