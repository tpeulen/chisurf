"""Assess spectra quality and merge duplicate probes in a fluorophore staging DB.

The scraper stages fluorophore probes (fpbase / chroma / photochemcad / …) into a
SQLite database; the same fluorophore is frequently ingested from several sources,
producing near-identical probe rows that carry *complementary* spectra and optical
properties. This utility

1. **assesses** spectra quality — decoding each ``spectra`` BLOB and flagging empty,
   length-mismatched, non-monotonic, non-finite, all-zero or negative-intensity
   curves — and
2. **merges** duplicate probes: it reuses MMFDB's duplicate grouping
   (:func:`mmfdb.admin.backend.duplicate_grouping.group_duplicates`, the exact model
   the ChiSurf duplicates dialog and the MMFDB web-admin run) and applies the same
   union-merge as ``fluorophores.merge_probes`` — copy each duplicate's missing
   spectra / optical properties into the richest probe (``INSERT OR IGNORE`` on the
   ``UNIQUE`` constraints), keep the longest name, then soft-delete the duplicates, and
3. **highlights potential duplicates** with a self-contained Bayesian classifier
   (:func:`duplicate_probability`) — a naive-Bayes posterior over normalized-name
   similarity plus absorption/emission maxima — so borderline pairs the automatic
   merge does *not* touch can be surfaced for human review (``--candidates``). This
   step only reports; it never writes.

Runs read-only by default; pass ``--apply`` to write. ``--apply`` first makes a
timestamped ``.backup`` copy beside the database.

Examples
--------
Assess only (no writes)::

    python -m chisurf.plugins.spectra_downloader.download.dedupe_spectra path/to/spectra.db

Merge duplicates, including cross-category exact-name matches (backs up first)::

    python -m …dedupe_spectra path/to/spectra.db --apply --cross-category

Highlight potential (fuzzy) duplicates for review without merging::

    python -m …dedupe_spectra path/to/spectra.db --candidates --min-prob 0.5
"""

from __future__ import annotations

import argparse
import datetime
import math
import pathlib
import re
import sqlite3
from difflib import SequenceMatcher
from typing import Any

import numpy as np


# ── quality assessment ────────────────────────────────────────────────────────
def _decode(blob: Any) -> np.ndarray:
    """Decode a ``spectra`` BLOB (float64 buffer) into a 1-D array."""
    if isinstance(blob, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(blob), dtype=np.float64)
    return np.asarray(blob, dtype=np.float64)


def assess_spectra(conn: sqlite3.Connection) -> dict[str, Any]:
    """Decode every live spectrum and collect per-curve quality issues.

    Returns
    -------
    dict
        ``{"n": <count>, "issues": [(spectrum_id, probe_id, spectrum_type, reason), …]}``.
    """
    rows = conn.execute(
        "SELECT id, probe_id, spectrum_type, wavelengths, intensity_values "
        "FROM spectra WHERE deleted_at IS NULL"
    ).fetchall()
    issues: list[tuple[int, int, str, str]] = []
    for sid, pid, stype, w_blob, i_blob in rows:
        w = _decode(w_blob)
        y = _decode(i_blob)
        reasons: list[str] = []
        if w.size == 0 or y.size == 0:
            reasons.append("empty")
        if w.size != y.size:
            reasons.append(f"length mismatch ({w.size} vs {y.size})")
        if w.size and not np.all(np.isfinite(w)):
            reasons.append("non-finite wavelengths")
        if y.size and not np.all(np.isfinite(y)):
            reasons.append("non-finite intensities")
        if w.size > 1 and not np.all(np.diff(w) > 0):
            reasons.append("non-monotonic wavelengths")
        if 0 < w.size < 5:
            reasons.append(f"too few points ({w.size})")
        if y.size and np.nanmax(np.abs(y)) == 0:
            reasons.append("all-zero intensities")
        if y.size and np.nanmin(y) < 0:
            reasons.append("negative intensities")
        if reasons:
            issues.append((sid, pid, stype, "; ".join(reasons)))
    return {"n": len(rows), "issues": issues}


# ── duplicate probes (delegates grouping to MMFDB) ────────────────────────────
def _load_probes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load live probes with abs/em maxima and spectra types (find_duplicates shape)."""
    conn.row_factory = sqlite3.Row
    probes = [
        dict(r)
        for r in conn.execute(
            "SELECT probe_id, chromophore_name, category, source, verification_status "
            "FROM probes WHERE deleted_at IS NULL"
        ).fetchall()
    ]
    props: dict[int, dict[str, Any]] = {}
    for r in conn.execute(
        "SELECT probe_id, property_name, property_value FROM optical_properties WHERE deleted_at IS NULL"
    ):
        props.setdefault(r["probe_id"], {})[r["property_name"]] = r["property_value"]
    spec: dict[int, list[str]] = {}
    for r in conn.execute("SELECT probe_id, spectrum_type FROM spectra WHERE deleted_at IS NULL"):
        spec.setdefault(r["probe_id"], []).append(r["spectrum_type"])
    for p in probes:
        pid = p["probe_id"]
        op = props.get(pid, {})
        p["optical_properties"] = op
        p["abs_max"] = op.get("abs_max")
        p["em_max"] = op.get("em_max")
        p["spectra_types"] = spec.get(pid, [])
        p["_richness"] = len(op) + len(spec.get(pid, []))
    return probes


def _merge_group(conn: sqlite3.Connection, primary_id: int, duplicate_ids: list[int]) -> None:
    """Union-merge duplicates into the primary (mirrors fluorophores.merge_probes)."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT chromophore_name, category, source FROM probes WHERE probe_id = ?", (primary_id,)
    ).fetchone()
    longest, best_cat, best_src = row["chromophore_name"], row["category"], row["source"]
    ids = [primary_id, *duplicate_ids]
    ph = ",".join("?" for _ in ids)
    for r in conn.execute(
        f"SELECT chromophore_name, category, source FROM probes WHERE probe_id IN ({ph}) AND deleted_at IS NULL",
        ids,
    ):
        if r["chromophore_name"] and len(r["chromophore_name"]) > len(longest or ""):
            longest = r["chromophore_name"]
        best_cat = best_cat or r["category"]
        best_src = best_src or r["source"]
    conn.execute(
        "UPDATE probes SET chromophore_name = ?, category = ?, source = ? WHERE probe_id = ?",
        (longest, best_cat, best_src, primary_id),
    )
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for dup in duplicate_ids:
        conn.execute(
            "INSERT OR IGNORE INTO optical_properties "
            "(probe_id, property_name, property_value, unit, details, created_at, updated_at) "
            "SELECT ?, property_name, property_value, unit, details, created_at, updated_at "
            "FROM optical_properties WHERE probe_id = ? AND deleted_at IS NULL",
            (primary_id, dup),
        )
        conn.execute(
            "INSERT OR IGNORE INTO spectra "
            "(probe_id, spectrum_type, wavelengths, intensity_values, wavelength_unit, intensity_unit, details, created_at, updated_at) "
            "SELECT ?, spectrum_type, wavelengths, intensity_values, wavelength_unit, intensity_unit, details, created_at, updated_at "
            "FROM spectra WHERE probe_id = ? AND deleted_at IS NULL",
            (primary_id, dup),
        )
        for table, col in (
            ("probes", "probe_id"),
            ("optical_properties", "probe_id"),
            ("spectra", "probe_id"),
        ):
            conn.execute(
                f"UPDATE {table} SET deleted_at = ? WHERE {col} = ? AND deleted_at IS NULL",
                (now, dup),
            )


#: Categories / spectrum types that mark an optical filter rather than a fluorophore.
_FILTER_SPECTRUM = "transmission"


def find_and_merge_cross_category(conn: sqlite3.Connection, *, apply: bool) -> dict[str, Any]:
    """Merge probes that share an *exact* normalized name across categories.

    MMFDB's grouping compares probes only within a category, so the same
    fluorophore ingested under different category labels (e.g. an fpbase
    ``protein`` and a chroma ``organic_dye`` EGFP, carrying complementary
    absorption / excitation spectra) is never linked. This pass catches those by
    exact :func:`normalize_name` equality, but **skips any probe that looks like an
    optical filter** (a ``transmission`` spectrum or a ``filter`` category) so
    filter sets named after a dye are never fused into the dye.
    """
    from mmfdb.admin.backend.duplicate_grouping import normalize_name

    probes = _load_probes(conn)
    filter_ids = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT probe_id FROM spectra WHERE deleted_at IS NULL AND spectrum_type = ?",
            (_FILTER_SPECTRUM,),
        )
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for p in probes:
        if p["probe_id"] in filter_ids or "filter" in (p.get("category") or "").lower():
            continue
        groups.setdefault(normalize_name(p["chromophore_name"]), []).append(p)

    plans: list[dict[str, Any]] = []
    for norm, members in groups.items():
        if len(members) < 2:
            continue
        primary = max(members, key=lambda p: (p["_richness"], -p["probe_id"]))
        dups = [m["probe_id"] for m in members if m["probe_id"] != primary["probe_id"]]
        plans.append(
            {
                "name": primary["chromophore_name"],
                "primary_id": primary["probe_id"],
                "primary_source": primary["source"],
                "duplicate_ids": dups,
                "duplicate_sources": [
                    next(m["source"] for m in members if m["probe_id"] == d) for d in dups
                ],
            }
        )

    if apply:
        for plan in plans:
            _merge_group(conn, plan["primary_id"], plan["duplicate_ids"])
        conn.commit()
    return {
        "groups": plans,
        "n_groups": len(plans),
        "n_removed": sum(len(p["duplicate_ids"]) for p in plans),
    }


def find_and_merge(conn: sqlite3.Connection, *, apply: bool) -> dict[str, Any]:
    """Group duplicate probes and (optionally) merge each group into its richest member."""
    from mmfdb.admin.backend.duplicate_grouping import group_duplicates

    probes = _load_probes(conn)
    by_id = {p["probe_id"]: p for p in probes}
    groups = group_duplicates(probes)

    plans: list[dict[str, Any]] = []
    for g in groups:
        members = [by_id[p["probe_id"]] for p in g["probes"]]
        # richest member wins (most spectra + optical properties); tie-break by lower id.
        primary = max(members, key=lambda p: (p["_richness"], -p["probe_id"]))
        dups = [m["probe_id"] for m in members if m["probe_id"] != primary["probe_id"]]
        plans.append(
            {
                "name": g["norm_name"],
                "primary_id": primary["probe_id"],
                "primary_source": primary["source"],
                "duplicate_ids": dups,
                "duplicate_sources": [by_id[d]["source"] for d in dups],
            }
        )

    if apply:
        for plan in plans:
            _merge_group(conn, plan["primary_id"], plan["duplicate_ids"])
        conn.commit()
    return {
        "groups": plans,
        "n_groups": len(plans),
        "n_removed": sum(len(p["duplicate_ids"]) for p in plans),
    }


# ── Bayesian duplicate classifier (highlights candidates for human review) ────
#: Posterior above which a pair is auto-merge-worthy; the review band is [LOW, HIGH).
_REVIEW_PROB_LOW = 0.5
_REVIEW_PROB_HIGH = 0.98
#: abs-max gap (nm) beyond which the sorted scan stops comparing a pair.
_ABS_MAX_WINDOW_NM = 20.0
#: Sources whose *same-source* pairs are strongly down-weighted (curated, deduped upstream).
_SELF_DEDUPED_SOURCES = frozenset({"fpbase", "pubmed", "atto"})


def normalize_name(name: str) -> str:
    """Comparison key for a probe name (drop filler, canonicalise AF/cyanine, strip)."""
    text = (name or "").lower()
    for filler in ("fluor", "dye", "fluorescent"):
        text = text.replace(filler, "")
    if text.startswith("af-") or text.startswith("af "):
        text = text.replace("af", "alexa", 1)
    elif text.startswith("af") and len(text) > 2 and text[2].isdigit():
        text = "alexa" + text[2:]
    text = text.replace("cyanine", "cy")
    return re.sub(r"[^a-z0-9]", "", text)


def _maxima_likelihoods(v1: object, v2: object) -> tuple[float, float]:
    """(P(Δ|dup), P(Δ|not)) for a pair of absorption/emission maxima (nm)."""
    if v1 and v2:
        try:
            diff = abs(float(v1) - float(v2))
        except (TypeError, ValueError):
            return 1.0, 1.0
        # ~5 nm scale for "same dye"; a random pair is ~uniform over ~300 nm.
        return math.exp(-0.5 * (diff / 5.0) ** 2), 1.0 / 300.0
    return 1.0, 1.0  # a missing measurement is uninformative


def duplicate_probability(p1: dict[str, Any], p2: dict[str, Any]) -> float:
    """Posterior P(same entity | evidence) from a small naive-Bayes model.

    Evidence: normalized-name similarity (exact / fuzzy via :class:`SequenceMatcher`)
    plus absorption and emission maxima. Same-source pairs from already-deduped
    curated sources are down-weighted (they should not contain internal duplicates).
    """
    prior_dup = 0.001
    prior_not = 1.0 - prior_dup

    n1, n2 = normalize_name(p1["chromophore_name"]), normalize_name(p2["chromophore_name"])
    if n1 == n2:
        like_name_dup, like_name_not = 0.99, 0.0001
    else:
        sim = SequenceMatcher(None, n1, n2).ratio()
        if sim < 0.6:
            like_name_dup, like_name_not = 1e-6, 0.99
        else:
            like_name_dup = math.exp(-10.0 * (1.0 - sim) ** 2)
            like_name_not = 0.01 if sim > 0.8 else 0.1

    like_abs_dup, like_abs_not = _maxima_likelihoods(p1.get("abs_max"), p2.get("abs_max"))
    like_em_dup, like_em_not = _maxima_likelihoods(p1.get("em_max"), p2.get("em_max"))

    num = prior_dup * like_name_dup * like_abs_dup * like_em_dup
    den = num + prior_not * like_name_not * like_abs_not * like_em_not
    prob = num / den if den > 0 else 0.0

    s1, s2 = p1.get("source"), p2.get("source")
    if s1 and s1 == s2 and s1 in _SELF_DEDUPED_SOURCES:
        prob *= 0.01
    return prob


def _abs_max(probe: dict[str, Any]) -> float:
    """Absorption maximum as a float, or a large sentinel when absent."""
    try:
        return float(probe.get("abs_max"))
    except (TypeError, ValueError):
        return math.inf


def find_duplicate_candidates(
    conn: sqlite3.Connection, *, min_prob: float = _REVIEW_PROB_LOW
) -> list[dict[str, Any]]:
    """Score every plausible probe pair and return likely duplicates for review.

    Uses an abs-max sorted window so the scan is ~O(n·w) rather than O(n²); pairs
    with an identical normalized name are always compared (they may lack maxima).
    Returns ``[{"prob", "a", "b", "name_a", "name_b", "source_a", "source_b",
    "exact_name", "band"}, …]`` sorted by descending probability, where ``band`` is
    ``"review"`` for the human-check zone and ``"strong"`` above it.
    """
    probes = _load_probes(conn)
    probes.sort(key=_abs_max)
    by_name: dict[str, list[dict[str, Any]]] = {}
    for p in probes:
        by_name.setdefault(normalize_name(p["chromophore_name"]), []).append(p)

    seen: set[tuple[int, int]] = set()
    out: list[dict[str, Any]] = []

    def _emit(a: dict[str, Any], b: dict[str, Any]) -> None:
        key = (min(a["probe_id"], b["probe_id"]), max(a["probe_id"], b["probe_id"]))
        if key in seen:
            return
        seen.add(key)
        prob = duplicate_probability(a, b)
        if prob < min_prob:
            return
        out.append(
            {
                "prob": prob,
                "a": a["probe_id"],
                "b": b["probe_id"],
                "name_a": a["chromophore_name"],
                "name_b": b["chromophore_name"],
                "source_a": a["source"],
                "source_b": b["source"],
                "exact_name": normalize_name(a["chromophore_name"])
                == normalize_name(b["chromophore_name"]),
                "band": "strong" if prob >= _REVIEW_PROB_HIGH else "review",
            }
        )

    # abs-max windowed scan for fuzzy near-matches.
    n = len(probes)
    for i in range(n):
        ai = _abs_max(probes[i])
        for j in range(i + 1, n):
            aj = _abs_max(probes[j])
            if math.isfinite(ai) and math.isfinite(aj) and aj - ai > _ABS_MAX_WINDOW_NM:
                break
            _emit(probes[i], probes[j])
    # always compare exact normalized-name collisions (maxima may be missing).
    for members in by_name.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                _emit(members[i], members[j])

    out.sort(key=lambda d: d["prob"], reverse=True)
    return out


# ── CLI ───────────────────────────────────────────────────────────────────────
def _backup(db_path: pathlib.Path) -> pathlib.Path:
    """Make a timestamped ``.backup`` copy of the SQLite DB (WAL-safe)."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = db_path.with_name(f"{db_path.name}.{stamp}.bak")
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    return dest


def main(argv: list[str] | None = None) -> int:
    """Assess spectra quality and report/merge duplicate probes."""
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("db", type=pathlib.Path, help="Path to the fluorophore staging spectra.db")
    ap.add_argument(
        "--apply", action="store_true", help="Write the merge (backs up first). Default: dry-run."
    )
    ap.add_argument(
        "--cross-category",
        action="store_true",
        help="Also merge exact-name matches across categories (skips optical filters).",
    )
    ap.add_argument(
        "--candidates",
        action="store_true",
        help="Highlight potential duplicates via the Bayesian classifier (report only, never merges).",
    )
    ap.add_argument(
        "--min-prob",
        type=float,
        default=_REVIEW_PROB_LOW,
        help=f"Minimum posterior probability for a highlighted candidate (default {_REVIEW_PROB_LOW}).",
    )
    ap.add_argument("--max-issues", type=int, default=30, help="Max quality issues to print.")
    args = ap.parse_args(argv)

    if args.apply:
        backup = _backup(args.db)
        print(f"backup: {backup}")

    conn = sqlite3.connect(str(args.db))
    quality = assess_spectra(conn)
    print("\n=== spectra quality ===")
    print(f"live spectra: {quality['n']}   flagged: {len(quality['issues'])}")
    for sid, pid, stype, reason in quality["issues"][: args.max_issues]:
        print(f"  spectrum {sid} (probe {pid}, {stype}): {reason}")
    if len(quality["issues"]) > args.max_issues:
        print(f"  … {len(quality['issues']) - args.max_issues} more")

    verb = "merged" if args.apply else "would merge"
    result = find_and_merge(conn, apply=args.apply)
    print(f"\n=== duplicate probes — within-category ({verb}) ===")
    print(f"groups: {result['n_groups']}   probes removed: {result['n_removed']}")
    for g in result["groups"]:
        print(
            f"  {g['name']}: keep {g['primary_id']} ({g['primary_source']}) "
            f"<- {list(zip(g['duplicate_ids'], g['duplicate_sources']))}"
        )

    if args.cross_category:
        xresult = find_and_merge_cross_category(conn, apply=args.apply)
        print(f"\n=== duplicate probes — cross-category exact name ({verb}) ===")
        print(f"groups: {xresult['n_groups']}   probes removed: {xresult['n_removed']}")
        for g in xresult["groups"]:
            print(
                f"  {g['name']}: keep {g['primary_id']} ({g['primary_source']}) "
                f"<- {list(zip(g['duplicate_ids'], g['duplicate_sources']))}"
            )
    if args.candidates:
        candidates = find_duplicate_candidates(conn, min_prob=args.min_prob)
        review = [c for c in candidates if c["band"] == "review" and not c["exact_name"]]
        print(f"\n=== potential duplicates — Bayesian classifier (P ≥ {args.min_prob:g}) ===")
        print(f"candidates: {len(candidates)}   review-band (fuzzy, needs a human): {len(review)}")
        for c in candidates:
            flag = "★" if c["band"] == "strong" else "?"
            exact = " [exact-name]" if c["exact_name"] else ""
            print(
                f"  {flag} P={c['prob']:.3f}  {c['a']} ({c['source_a']}) ~ {c['b']} ({c['source_b']})"
                f"  '{c['name_a']}' ~ '{c['name_b']}'{exact}"
            )

    conn.close()
    if not args.apply:
        print("\n(dry-run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
