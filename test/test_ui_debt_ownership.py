"""Keep every accepted UI omission assigned to a finite family and real guard."""

import ast
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "okf/validation/release-readiness-w6g/ui-debt-owners.json"


def test_every_remaining_ui_allowance_has_one_exact_owner():
    """Neither missing assignments nor obsolete ownership can silently survive."""
    ledger = json.loads(LEDGER.read_text())
    assert ledger["version"] == 1
    for contract, name in (
        ("tooltip", "tooltip_allowlist.txt"),
        ("translation", "i18n_allowlist.txt"),
    ):
        allowed = {
            line.strip()
            for line in (ROOT / "test" / name).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }
        assigned = Counter(
            item["key"] for item in ledger["findings"] if item["contract"] == contract
        )
        assert set(assigned) == allowed, {
            "unassigned": sorted(allowed - assigned.keys()),
            "stale": sorted(assigned.keys() - allowed),
        }
        assert all(count == 1 for count in assigned.values()), "Duplicate UI ownership"


def test_family_ownership_and_acceptance_checks_are_actionable():
    """Assignments resolve to scoped families and callable production test nodes."""
    ledger = json.loads(LEDGER.read_text())
    for item in ledger["findings"]:
        family = ledger["families"][item["family"]]
        assert item["owner"] == family["owner"]
        assert item["owner"] in {"W6a", "W6b", "W6c", "W6d", "W6e", "W6f", "W6g"}
        assert item["path"].startswith(item["family"] + "/")
        assert item["key"].startswith(item["path"] + "#")
        assert item["location"] and item["detail"]
        assert ledger["closure"][item["contract"]]
        assert family["scope"] == item["family"] + "/**"
    for node in ledger["checks"].values():
        file, function = node.split("::")
        parsed = ast.parse((ROOT / file).read_text())
        assert any(isinstance(n, ast.FunctionDef) and n.name == function for n in parsed.body), node


def test_shared_owner_does_not_absorb_plugin_family_repairs():
    """The W6g handoff coordinates family work without inheriting its debt."""
    ledger = json.loads(LEDGER.read_text())
    for item in ledger["findings"]:
        if item["owner"] == "W6g":
            assert item["family"] == "chisurf/emtk"
        if item["family"].startswith("chisurf/plugins/core"):
            assert item["owner"] == "W6f"
