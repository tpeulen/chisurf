"""Ported from the script-style test_slugify.py: chisurf.core.base's slugify,
pinned as real tests (the old file carried a copy of the function and only
printed). The cases pin the actual contract: lowercase, NFKD accent folding,
the default keep-class ``[^-a-z0-9_]+`` (hyphens are kept)."""

from __future__ import annotations

from chisurf.core.base import slugify


def test_slugify_strips_accents_and_joins():
    # The original script's case, the only one it actually checked.
    assert slugify("ldldöö_ddd   dd**") == "ldldoo_ddd_dd"


def test_slugify_lowercases_but_keeps_hyphens():
    assert slugify("A -- B__c") == "a_--_b_c"
    assert slugify("2-state model") == "2-state_model"


def test_slugify_collapses_repeated_separators_and_trims():
    assert slugify("  spacing   out  ") == "spacing_out"
