"""Finding probes that are probably the same component (Qt-free).

The curation of the fluorophore / optical-component table groups entries that a
name-similarity and spectral-maximum likelihood ratio calls duplicates. Shared by
the Qt ``DuplicateFinderThread`` and the native admin's Find duplicates.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable
from difflib import SequenceMatcher
from typing import Any


def _norm(name: str) -> str:
    n = (name or "").lower()
    for filler in ["fluor", "dye", "fluorescent"]:
        n = n.replace(filler, "")
    if n.startswith("af-") or n.startswith("af "):
        n = n.replace("af", "alexa", 1)
    elif n.startswith("af") and len(n) > 2 and n[2].isdigit():
        n = "alexa" + n[2:]
    n = n.replace("cyanine", "cy")
    return re.sub(r"[^a-z0-9]", "", n)


def _calc_prob(p1: dict, p2: dict) -> float:
    # Prior probability
    P_dup = 0.001
    P_not_dup = 1 - P_dup

    # 1. Name Match
    n1 = _norm(p1["chromophore_name"])
    n2 = _norm(p2["chromophore_name"])

    if n1 == n2:
        L_name_dup = 0.99
        L_name_not = 0.0001
    else:
        sim = SequenceMatcher(None, n1, n2).ratio()

        if sim < 0.6:
            L_name_dup = 1e-6
            L_name_not = 0.99
        else:
            L_name_dup = math.exp(-10 * (1 - sim) ** 2)
            L_name_not = 0.01 if sim > 0.8 else 0.1

    # 2. Abs Max Match
    a1, a2 = p1.get("abs_max"), p2.get("abs_max")
    if a1 and a2:
        try:
            diff = abs(float(a1) - float(a2))
            L_abs_dup = math.exp(-0.5 * (diff / 5.0) ** 2)
            L_abs_not = 1.0 / 300.0  # Approx chance of random match in 300nm range
        except ValueError:
            L_abs_dup = L_abs_not = 1.0
    else:
        # If missing, it tells us nothing
        L_abs_dup = L_abs_not = 1.0

    # 3. Em Max Match
    e1, e2 = p1.get("em_max"), p2.get("em_max")
    if e1 and e2:
        try:
            diff = abs(float(e1) - float(e2))
            L_em_dup = math.exp(-0.5 * (diff / 5.0) ** 2)
            L_em_not = 1.0 / 300.0
        except ValueError:
            L_em_dup = L_em_not = 1.0
    else:
        L_em_dup = L_em_not = 1.0

    num = P_dup * L_name_dup * L_abs_dup * L_em_dup
    den = num + P_not_dup * L_name_not * L_abs_not * L_em_not
    prob = num / den if den > 0 else 0

    # Strongly penalize duplicates from the same curated source
    s1, s2 = p1.get("source"), p2.get("source")
    if s1 and s2 and s1 == s2 and s1 in ("fpbase", "pubmed"):
        prob *= 0.01  # Highly unlikely that fpbase has exact duplicates of its own entries

    return prob


def find_duplicate_groups(
    probes: list[dict[str, Any]],
    progress: Callable[[int], None] | None = None,
    interrupted: Callable[[], bool] | None = None,
) -> list[dict[str, Any]] | None:
    """Group *probes* that are probably duplicates.

    Parameters
    ----------
    probes : list of dict
        ``fluorophores.find_duplicates`` rows (``probe_id``, ``chromophore_name``,
        ``category``, ``abs_max``, ``em_max``, ``source``).
    progress : callable, optional
        ``progress(percent)``.
    interrupted : callable, optional
        Polled between categories and rows; ``True`` stops the search.

    Returns
    -------
    list of dict or None
        ``[{"norm_name", "probes"}]`` sorted by name, each group with at least two
        probes (shortest name first); ``None`` when interrupted.
    """
    progress = progress or (lambda _value: None)
    interrupted = interrupted or (lambda: False)
    by_category = defaultdict(list)
    for p in probes:
        by_category[p.get("category", "other")].append(p)

    edges = []
    total_categories = len(by_category)

    def _get_abs(p):
        try:
            return float(p.get("abs_max"))
        except (TypeError, ValueError):
            return 999999.0

    for cat_idx, cat_probes in enumerate(by_category.values()):
        if interrupted():
            return None
        progress(int(cat_idx / max(1, total_categories) * 90))
        cat_probes.sort(key=_get_abs)
        n = len(cat_probes)
        for i in range(n):
            if interrupted():
                return None
            p1 = cat_probes[i]
            a1 = _get_abs(p1)
            for j in range(i + 1, n):
                p2 = cat_probes[j]
                a2 = _get_abs(p2)
                # Exact name matches are always checked
                if _norm(p1["chromophore_name"]) == _norm(p2["chromophore_name"]):
                    edges.append((p1["probe_id"], p2["probe_id"]))
                    continue
                # If abs_max diff > 15nm, break inner loop (since sorted)
                if a1 != 999999.0 and a2 != 999999.0 and a2 - a1 > 15.0:
                    break
                if _calc_prob(p1, p2) > 0.8:
                    edges.append((p1["probe_id"], p2["probe_id"]))

    progress(95)
    parent = {p["probe_id"]: p["probe_id"] for p in probes}

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    for i, j in edges:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[root_i] = root_j

    groups_by_root = defaultdict(list)
    probe_map = {p["probe_id"]: p for p in probes}
    for pid in parent:
        groups_by_root[find(pid)].append(probe_map[pid])

    duplicate_groups = []
    for group_probes in groups_by_root.values():
        if len(group_probes) > 1:
            group_probes.sort(key=lambda p: len(p["chromophore_name"]))
            duplicate_groups.append(
                {"norm_name": group_probes[0]["chromophore_name"], "probes": group_probes}
            )
    duplicate_groups.sort(key=lambda g: g["norm_name"].lower())
    progress(100)
    return duplicate_groups
