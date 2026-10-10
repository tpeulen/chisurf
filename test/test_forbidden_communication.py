"""Static guard tests that fail on forbidden direct communication patterns.

These tests scan GUI widget source files for patterns that indicate
direct in-process access to fit/model/parameter objects, which the ZMQ
migration project aims to eliminate.

The expected violation count is tracked so the test fails only when
new violations are introduced. The count should monotonically decrease
as migration progresses.

Usage:
    pytest test/test_forbidden_communication.py -v
    python test/test_forbidden_communication.py   # print current violations
"""

from __future__ import annotations

import pathlib
import re

import pytest

# ── Configuration ─────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).resolve().parent.parent

SCAN_DIRECTORIES = [
    "chisurf/gui",
    "chisurf/gui/widgets/fitting",
    "chisurf/gui/widgets/models",
    "chisurf/gui/plots",
    "chisurf/plugins",
]

# Per-file expected violation counts.
# Keys are relative paths from ROOT, values are the expected count for that file.
# The test fails if ANY file exceeds its expected count, preventing the
# "hide five old violations, add five new ones" problem of a global threshold.
# Run ``python -m pytest test/test_forbidden_communication.py --update-expected``
# to regenerate this dict from the current state.
EXPECTED_VIOLATIONS: dict[str, int] = {
    "chisurf/gui/autoform/auto_form.py": 1,
    "chisurf/gui/autoform/sections/builtin.py": 2,
    "chisurf/gui/autoform/sections/parameter_table.py": 5,
    "chisurf/gui/autoform/sections/rate_matrix_section.py": 2,
    "chisurf/gui/main.py": 9,
    "chisurf/gui/main_helper.py": 12,
    "chisurf/gui/widgets/experiments/ics.py": 1,
    "chisurf/gui/widgets/experiments/widgets.py": 5,
    "chisurf/gui/widgets/fitting/fit_controller.py": 8,
    "chisurf/gui/widgets/fitting/parameter_widgets.py": 7,
    "chisurf/plugins/burst/accurate_fret/parameters.py": 3,
    "chisurf/plugins/burst/mfd_prepare/cli/main.py": 1,
    "chisurf/plugins/core/batch_analysis/core/runner.py": 1,
    "chisurf/plugins/core/batch_analysis/gui/view_model.py": 1,
    # backend/services.py: server-side RPC handlers — direct param.link = is LEGITIMATE here
    "chisurf/plugins/core/globalview/backend/services.py": 3,
    "chisurf/plugins/core/lightpath_simulator/core/parameters.py": 2,
    "chisurf/plugins/fluorescence_decay/irf_estimator/backend/services.py": 1,
    "chisurf/plugins/fluorescence_decay/synthetic_decay/gui/view_model.py": 1,
    "chisurf/plugins/fluorescence_decay/tr_anisotropy/gui/view_model.py": 3,
    "chisurf/plugins/fret_line/gui/tool.py": 1,
}

# Files that are entirely exempt from scanning
ALLOWED_FILES: set[str] = {
    "test_forbidden_communication.py",
    "test_fitting_client.py",
    "fitting_client.py",  # contains deprecated get_fit_objects() bridge with getattr(cs, "fits", [])
}

# ── Forbidden patterns ────────────────────────────────────────────────

FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "direct chisurf.fits or cs.fits access",
        re.compile(r'(?<!["\'\w])chisurf\.fits(?!["\'\w])|(?<!["\'\w])cs\.fits(?!["\'\w])'),
    ),
    (
        "direct chisurf.cs or cs.current_fit access",
        re.compile(r'(?<!["\'\w])chisurf\.cs(?!["\'\w])|cs\.current_fit'),
    ),
    (
        "direct cs.run or chisurf.run command strings",
        re.compile(r'(?<!["\'\w])cs\.run\(|(?<!["\'\w])chisurf\.run\('),
    ),
    (
        "direct chisurf.imported_datasets or cs.imported_datasets",
        re.compile(r'(?<!["\'\w])chisurf\.imported_datasets|cs\.imported_datasets'),
    ),
    (
        "direct cs.current_setup access",
        re.compile(r'(?<!["\'\w])cs\.current_setup'),
    ),
    (
        "direct chisurf.cs.current_experiment access",
        re.compile(r"chisurf\.cs\.current_experiment"),
    ),
    (
        "getattr(cs, 'fits', ...) access",
        re.compile(r'getattr\(cs,\s*["\']fits["\']'),
    ),
    (
        "getattr(cs, 'imported_datasets', ...) access",
        re.compile(r'getattr\(cs,\s*["\']imported_datasets["\']'),
    ),
]

# An assignment, not a comparison: ``x.value == 1`` must not match.
PARAM_MUTATION = re.compile(
    r"\.link\s*=(?!=)\s*"
    r"|\.fixed\s*=(?!=)\s*"
    r"|\.bounds\s*=(?!=)\s*"
    r"|\.bounds_on\s*=(?!=)\s*"
    r"|(?<=[a-zA-Z_])(?:\.value)\s*=(?!=)\s*"
)

# Parameter/fit-method patterns are only a *communication* violation in a module
# that can reach a chisurf fit: one that names the process-global fit state, a
# fit group / parameter list, or the fitting client/API.  A plugin whose own
# parameter objects, dialog values or test fakes carry ``.value`` never touches a
# chisurf fit, so its assignments are not counted.  Derived from the module's
# code, not from a list of file names.
FIT_CONTEXT = re.compile(
    r"\b(?:chisurf|cs)\.(?:fits|current_fit|cs)\b"
    r"|getattr\(\s*cs\s*,\s*[\"']fits[\"']"
    r"|get_fitting_client|FittingClient|ChiSurfAPI|FittingParameter"
    r"|\bfit\.(?:run|update|fit_range)\b"
)

# ``{"cs": chisurf.cs}`` hands the session module to a user-script / console
# namespace; no widget reaches a fit through it.
_NAMESPACE_INJECTION = re.compile(r"[\"']cs[\"']\s*:\s*chisurf\.cs\b")

# ``self.value = ...`` / ``self.fixed = ...`` assign the object's own attribute;
# only a longer chain (``self.fit.x.value``) reaches another object.
_OWN_ATTRIBUTE = re.compile(r"^self\.\w+\s*(?:,\s*self\.\w+\s*)*=(?!=)")


def _has_fit_context(text: str) -> bool:
    """Return True if the module source can reach a chisurf fit object."""
    return bool(FIT_CONTEXT.search(text))

FIT_METHOD_CALLS = re.compile(
    r"(?<!self\.)fit\.run\s*\("
    r"|(?!\.scan|\.adaptive_scan)fit\.update\s*\("
    r"|fit\.fit_range\s*="
    r"|fit\.data\s*="
    r"|fit\.mask\s*="
)


def _is_test_module(rel: str) -> bool:
    """Return True for a test module (``test/``, ``tests/`` or ``test_*.py``).

    Tests assert on, and set up, the process-global session on purpose; they are
    the harness, not a GUI client talking to a fit.
    """
    parts = rel.split("/")
    return (
        any(part in ("test", "tests") for part in parts[:-1])
        or parts[-1].startswith("test_")
        or parts[-1] == "conftest.py"
        or parts[-1] == "fakes.py"
    )


def _is_allowed_file(filepath: pathlib.Path) -> bool:
    rel = filepath.relative_to(ROOT).as_posix()
    if _is_test_module(rel):
        return True
    for allowed in ALLOWED_FILES:
        if rel == allowed or rel.endswith(f"/{allowed}"):
            return True
    return False


def _scan_file(filepath: pathlib.Path) -> list[tuple[str, int, str]]:
    if _is_allowed_file(filepath):
        return []

    try:
        with open(filepath, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return []
    return _scan_lines(lines)


def _scan_lines(lines: list[str]) -> list[tuple[str, int, str]]:
    """Return the violations in the source ``lines`` of one (non-test) module."""
    violations: list[tuple[str, int, str]] = []
    fit_context = _has_fit_context("".join(lines))
    in_docstring = False
    docstring_delim = None
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue
        if _NAMESPACE_INJECTION.search(stripped):
            continue

        # Track multi-line docstrings ("""...""" or '''...''')
        if not in_docstring:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                delim = stripped[:3]
                # Single-line docstring: opening and closing on same line
                if stripped.count(delim) >= 2 and stripped.endswith(delim) and len(stripped) > 3:
                    continue
                in_docstring = True
                docstring_delim = delim
                continue
        else:
            if stripped.endswith(docstring_delim):
                in_docstring = False
                docstring_delim = None
                continue

        if in_docstring:
            continue

        if stripped.startswith("#"):
            continue

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(stripped):
                violations.append((name, lineno, stripped))
                break  # Only report one violation per line

        if fit_context and PARAM_MUTATION.search(stripped) and not _OWN_ATTRIBUTE.match(stripped):
            violations.append(("direct parameter mutation", lineno, stripped))
            continue

        if fit_context and FIT_METHOD_CALLS.search(stripped):
            violations.append(("direct fit method call", lineno, stripped))
            continue

    return violations


def _collect_files() -> list[pathlib.Path]:
    # SCAN_DIRECTORIES nest (``chisurf/gui`` contains ``chisurf/gui/plots`` ...);
    # a file reachable from two roots must be scanned once or its count doubles.
    files: dict[pathlib.Path, None] = {}
    for rel_dir in SCAN_DIRECTORIES:
        scan_dir = ROOT / rel_dir
        if scan_dir.is_dir():
            for py_file in scan_dir.rglob("*.py"):
                files[py_file] = None
    return sorted(files)


def _collect_violations() -> list[tuple[str, str, int, str]]:
    """Scan all files and return sorted violation list."""
    files = _collect_files()
    violations: list[tuple[str, str, int, str]] = []
    for filepath in files:
        for name, lineno, line in _scan_file(filepath):
            rel = filepath.relative_to(ROOT).as_posix()
            violations.append((rel, name, lineno, line))
    violations.sort(key=lambda v: (v[0], v[2]))
    return violations


def _build_expected_doc() -> str:
    """Return documentation on how to update EXPECTED_VIOLATIONS."""
    return (
        "EXPECTED_VIOLATIONS is a per-file dictionary. To update it:\n"
        '  python -c "from test_forbidden_communication import _collect_violations;'
        " from collections import Counter; v = _collect_violations();"
        " by_file = sorted(Counter(rel for rel,_,_,_ in v).items());"
        ' print(dict(by_file))"\n'
        "Then copy the output into EXPECTED_VIOLATIONS in this file."
    )


def test_no_new_forbidden_communication():
    """Fail if any file has MORE violations than its expected count.

    Per-file tracking prevents the 'hide five old violations, add five new
    ones' problem of a global threshold. Each file must monotonically
    decrease toward zero.
    """
    violations = _collect_violations()
    from collections import Counter

    by_file: dict[str, int] = Counter(rel for rel, _, _, _ in violations)

    failures: list[str] = []
    for rel, actual in sorted(by_file.items()):
        expected = EXPECTED_VIOLATIONS.get(rel, 0)
        if actual > expected:
            failures.append(f"  {rel}: {actual} violations (expected ≤ {expected})")

    # Also flag files that disappeared from EXPECTED_VIOLATIONS but still
    # have violations (unlikely but possible after a rename)
    for rel, expected in EXPECTED_VIOLATIONS.items():
        actual = by_file.get(rel, 0)
        if actual > expected:
            failures.append(f"  {rel}: {actual} violations (expected ≤ {expected})")

    if failures:
        msg = (
            "\n" + "=" * 72 + "\n"
            "Files with MORE forbidden patterns than expected:\n"
            + "=" * 72
            + "\n"
            + "\n".join(failures)
            + "\n\n"
            + "=" * 72
            + "\n"
            "These patterns bypass the FittingClient adapter — migrate them.\n"
            + _build_expected_doc()
        )
        pytest.fail(msg)


def test_no_unknown_files_with_violations():
    """Fail if a file NOT in EXPECTED_VIOLATIONS has violations."""
    violations = _collect_violations()
    from collections import Counter

    by_file: dict[str, int] = Counter(rel for rel, _, _, _ in violations)
    unknown = {rel: c for rel, c in by_file.items() if rel not in EXPECTED_VIOLATIONS}
    if unknown:
        msg = (
            "\n" + "=" * 72 + "\n"
            "Files with violations but NO entry in EXPECTED_VIOLATIONS:\n"
            + "=" * 72
            + "\n"
            + "\n".join(f"  {rel}: {c}" for rel, c in sorted(unknown.items()))
            + "\n\nAdd them to EXPECTED_VIOLATIONS.\n"
            + _build_expected_doc()
        )
        pytest.fail(msg)


def test_violations_are_reported(capsys):
    """Print all current violations (informational — always passes)."""
    violations = _collect_violations()
    with capsys.disabled():
        if not violations:
            print("\nNo violations found — ZMQ migration is complete!")
            print("Remove test_violations_are_reported from this file.")
            return
        from collections import Counter

        by_file = Counter(rel for rel, _, _, _ in violations)
        print(f"\n{'=' * 72}")
        print(f"ZMQ Migration — {len(violations)} violations in {len(by_file)} files")
        print(f"{'=' * 72}")
        for rel, _, lineno, line in sorted(violations, key=lambda v: (v[0], v[2])):
            print(f"\n  {rel}:{lineno}")
            print(f"    {line.strip()}")
        print(f"\n{'=' * 72}")
        for rel, count in sorted(by_file.items()):
            exp = EXPECTED_VIOLATIONS.get(rel)
            status = "UNKNOWN" if exp is None else ("OK" if count <= exp else "EXCEEDS")
            exp = "N/A" if exp is None else exp
            print(f"  {count:3d} / {str(exp):>3s}  {status:8s}  {rel}")
        print(f"\n  {'=' * 30}")
        print(f"  {len(violations):3d}  {'TOTAL':>3s}")


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "code,expected_name",
    [
        ("chisurf.fits", "direct chisurf.fits or cs.fits access"),
        ("chisurf.cs.mdiarea", "direct chisurf.cs or cs.current_fit access"),
        ('cs.run("cmd")', "direct cs.run or chisurf.run command strings"),
        ("fp.link = other", "direct parameter mutation"),
        ("fp.fixed = True", "direct parameter mutation"),
        ("fp.value = 3.5", "direct parameter mutation"),
        ("fp.bounds = (0, 10)", "direct parameter mutation"),
        ("fit.run()", "direct fit method call"),
        ("fit.update()", "direct fit method call"),
        ("fit.fit_range = (0, 100)", "direct fit method call"),
    ],
)
def test_forbidden_pattern_is_detected(code, expected_name):
    """Verify that the static guard detects specific known-bad patterns."""
    found = any(pattern.search(code) for name, pattern in FORBIDDEN_PATTERNS)
    if not found:
        found = bool(PARAM_MUTATION.search(code) or FIT_METHOD_CALLS.search(code))
    assert found, f"No pattern matched '{code}' (expected '{expected_name}')"


ALLOWED_SAMPLES = [
    "get_fitting_client().list_fits()",
    "has_fitting_client()",
    "fc = get_fitting_client()",
    "fc.run_fit(fit_uid=uid)",
    "fc.set_parameter_value('tau1', 3.5, fit_uid='abc')",
    "# TODO: migrate this later",
    "# fp.fixed = True  # legacy",
    "self._reg.value = float(v)",
    # fp.do_value which is not a mutation
    "fp.do_value = True",
]


@pytest.mark.parametrize("code", ALLOWED_SAMPLES)
def test_allowed_pattern_not_falsely_detected(code):
    """Verify that allowed patterns (comments, FittingClient usage) pass."""
    if code.strip().startswith("#"):
        return
    for name, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(code):
            pytest.fail(f"Allowed code '{code}' was falsely detected")
    if FIT_METHOD_CALLS.search(code):
        pytest.fail(f"Allowed code '{code}' was falsely detected by fit method call pattern")
    if PARAM_MUTATION.search(code):
        # Allow self._* patterns that are not parameter mutations
        if code.strip().startswith("self._") and ".value =" in code:
            return  # model widget internal variables
        pytest.fail(f"Allowed code '{code}' was falsely detected by parameter mutation pattern")


def _scan_text(code: str) -> list[tuple[str, int, str]]:
    return _scan_lines(code.splitlines(keepends=True))


def test_new_violation_is_caught():
    """A fit poke added to a module that can reach a chisurf fit must be counted."""
    code = "import chisurf as cs\n\ndef f(p):\n    p.fixed = True\n    cs.fits[0].update()\n"
    names = [n for n, _l, _s in _scan_text("from chisurf.fits import x\n" + code)]
    assert "direct parameter mutation" in names
    assert _scan_text("def g(client):\n    for f in cs.fits:\n        pass\n")


def test_own_parameters_are_not_counted():
    """A module with no path to a chisurf fit may mutate its own parameter objects."""
    code = (
        "class Panel:\n"
        "    def set(self, p, v):\n"
        "        p.value = v\n"
        "        p.fixed = True\n"
        "        self.dialog.value = v\n"
    )
    assert _scan_text(code) == []


def test_comparison_is_not_a_mutation():
    """``x.value == 1`` reads; only assignment is a mutation."""
    code = "from chisurf.core.api import ChiSurfAPI\nassert x.value == 1\nok = p.fixed == True\n"
    assert _scan_text(code) == []


def test_fit_context_makes_mutation_count():
    """The same assignment counts once the module goes through a fit."""
    code = "from chisurf.core.api import ChiSurfAPI\np.value = 2\n"
    assert [n for n, _l, _s in _scan_text(code)] == ["direct parameter mutation"]


def test_nested_scan_roots_scan_each_file_once():
    """Overlapping SCAN_DIRECTORIES must not double a file's count."""
    files = _collect_files()
    assert len(files) == len(set(files))


def test_violations_print(capsys):
    """Print current violation summary (always passes)."""
    violations = _collect_violations()
    count = len(violations)
    print(f"\n{'=' * 72}")
    print(f"ZMQ Migration Progress: {count} violations remaining")
    print(f"{'=' * 72}")
    if count == 0:
        print("🎉 Migration complete! Update EXPECTED_VIOLATIONS = 0.")
    else:
        print("Violations by directory:")
        by_dir: dict[str, int] = {}
        for rel, _name, _lineno, _line in violations:
            parts = rel.split("/")
            key = "/".join(parts[:4]) if len(parts) > 4 else rel
            by_dir[key] = by_dir.get(key, 0) + 1
        for d, c in sorted(by_dir.items(), key=lambda x: -x[1]):
            print(f"  {c:4d}  {d}")
        print(f"\n  {'=' * 30}")
        print(f"  {count:4d}  TOTAL")
    print(f"\nTarget: ≤ {EXPECTED_VIOLATIONS} (fails if exceeded)")
    print(f"{'=' * 72}")


if __name__ == "__main__":
    violations = _collect_violations()
    count = len(violations)
    print(f"\n{'=' * 72}")
    print(f"ZMQ Migration — {count} violations found (threshold: {EXPECTED_VIOLATIONS})")
    print(f"{'=' * 72}")
    for rel, name, lineno, line in sorted(violations, key=lambda v: (v[0], v[2])):
        print(f"\n  {rel}:{lineno}")
        print(f"    Pattern: {name}")
        print(f"    Line:    {line.strip()}")
    print(f"\n{'=' * 72}")
    print(f"Total: {count} violations in {len(set(v[0] for v in violations))} files")
    print(f"Scanned directories: {', '.join(SCAN_DIRECTORIES)}")
