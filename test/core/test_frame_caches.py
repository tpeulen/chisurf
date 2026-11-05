"""What a window asks for every frame is not rebuilt every frame.

Measured on the Burst Analysis hub (DNA13bp_3, ~22 000 bursts): the Data step's frame spent
~60 ms copying the whole dye database once per word of every file name (``get_dye``), and every
Burst MLE frame merged the registries again (``catalog.registry``, a deep copy per extended
entry)."""

from __future__ import annotations

import copy

from chisurf.core.fluorescence import dyes
from chisurf.core.registry import catalog


def test_get_dye_copies_the_entry_not_the_table(monkeypatch):
    dyes.reference_dyes()  # loaded once
    name = sorted(dyes._CACHE)[0]
    copied = []
    real = copy.deepcopy

    def counting(value, *args, **kwargs):
        copied.append(value)
        return real(value, *args, **kwargs)

    monkeypatch.setattr(dyes.copy, "deepcopy", counting)
    entry = dyes.get_dye(name)
    assert entry is not None and entry["name"] == name
    assert all(value is not dyes._CACHE for value in copied)
    entry["name"] = "changed"  # detached: the cache keeps its own
    assert dyes.get_dye(name)["name"] == name
    assert dyes.get_dye("no such dye at all") is None


def test_registry_is_merged_once_and_again_after_a_registration(monkeypatch):
    calls = []
    real = catalog._merged
    monkeypatch.setattr(catalog, "_merged", lambda: calls.append(1) or real())
    monkeypatch.setattr(catalog, "_MERGED", None)
    first = catalog.registry()
    catalog.registry("fit")
    assert len(calls) == 1
    first.setdefault("fit", {})["mine"] = {}  # a caller's table is a copy
    assert "mine" not in catalog.registry("fit")
    monkeypatch.setitem(catalog._LOCAL, "frame_cache_test", {})
    catalog.register("frame_cache_test", "probe", {"label": "probe"})
    assert "probe" in catalog.registry("frame_cache_test")
    assert len(calls) == 2
