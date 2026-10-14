"""The license tracker classifies every declared dependency.

A new dependency without recognisable license metadata must fail here rather
than land silently — the whole point of the tracker is that the compatibility
answer stays current (BUGS: license tracker).
"""

from __future__ import annotations

from build_tools.license_tracker import CLASSES, collect


def test_every_runtime_dependency_is_classified():
    data = collect()
    runtime = [e for e in data["entries"] if e["group"] == "runtime"]
    assert runtime, "no runtime dependencies found"
    unknown = [e["name"] for e in runtime if e["class"] is None]
    assert not unknown, (
        f"unclassified licenses: {unknown} — add metadata or an override in "
        "build_tools/license_tracker.py, then regenerate docs/development/licenses.md"
    )


def test_the_binding_constraint_is_stated():
    """Weak copyleft (MPL, imp-bff and LabelLib) today. If this fails, the dependency graph's
    licensing changed — regenerate docs/development/licenses.md and read the diff before
    adjusting the assertion.
    """
    data = collect()
    assert data["binding_class"] in CLASSES
    assert data["binding_class"] == 2
    assert "imp-bff" in data["blockers"]
