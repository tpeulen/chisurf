"""Compare exact existing OKF findings without hiding new or stale debt."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from build_tools.okf.okf_lint import Finding, scan


def records(root: Path, findings: list[Finding]) -> list[dict[str, Any]]:
    """Attach exact source context and accountable cleanup ownership to findings."""
    contents: dict[str, list[str]] = {}
    result = []
    for finding in findings:
        if finding.path not in contents:
            path = root / finding.path
            contents[finding.path] = (
                path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
            )
        lines = contents[finding.path]
        source = lines[finding.line - 1] if 0 < finding.line <= len(lines) else ""
        result.append(
            {
                "rule": finding.rule,
                "path": finding.path,
                "line": finding.line,
                "message": finding.msg,
                "source": source,
                "owner": "W0b",
                "acceptance": "Remove this finding and its baseline record; final baseline must be empty.",
            }
        )
    return result


def identity(record: dict[str, Any]) -> str:
    """Identify a finding independently of preceding line insertions."""
    return json.dumps(
        [record[key] for key in ("rule", "path", "message", "source")], ensure_ascii=False
    )


def compare(current: list[dict[str, Any]], expected: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Report new and stale exact findings, preserving duplicate multiplicity."""
    actual = Counter(map(identity, current))
    baseline = Counter(map(identity, expected))
    return {
        "new": list((actual - baseline).elements()),
        "stale": list((baseline - actual).elements()),
    }


def main(argv: list[str] | None = None) -> int:
    """Check an explicit baseline; never create or expand one automatically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("okf"))
    parser.add_argument("--baseline", type=Path, default=Path("test/okf_bundle_baseline.json"))
    args = parser.parse_args(argv)
    expected = json.loads(args.baseline.read_text(encoding="utf-8"))
    if expected.get("version") != 1 or any(
        record.get("owner") != "W0b" or not record.get("acceptance")
        for record in expected["findings"]
    ):
        raise ValueError("Every baseline finding must have W0b ownership and an acceptance check")
    current = records(args.root, scan(args.root))
    delta = compare(current, expected["findings"])
    print(json.dumps({"findings": len(current), **delta}, ensure_ascii=False, indent=2))
    return int(any(delta.values()))


if __name__ == "__main__":
    raise SystemExit(main())
