"""Group JUnit failures by release workstream without importing the application.

Usage: ``python build_tools/dev_utils/triage_failures.py --junit junit.xml
[--write report.md]``. File paths identify the owner; manifest metadata adds
plugin context, including plugin ids in parametrized e2e tests.
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_FAMILIES = {
    "tttr": "W6a", "fcs": "W6a", "burst": "W6b", "microscopy": "W6c",
    "modelling": "W6d", "traj": "W6d", "structure": "W6d",
    "calculator": "W6e", "fret_line": "W6e", "fluorescence_decay": "W6e",
    "core": "W6f", "misc": "W6f",
}


@dataclass(frozen=True)
class FailedTest:
    """One failing testcase, including both call and teardown outcomes."""

    node_id: str
    file: str
    workstream: str
    plugin_id: str
    outcomes: tuple[str, ...]


def _path(value: str, root: Path) -> str:
    """Normalize JUnit paths, retaining paths from other checkout roots."""
    value = value.replace("\\", "/")
    prefix = root.resolve().as_posix() + "/"
    return value.removeprefix(prefix).removeprefix("./")


def _prefix(path: str, prefix: str) -> bool:
    """Match a directory or filename prefix at a path-component boundary."""
    return bool(re.search(r"(?:^|/)" + re.escape(prefix), path))


def workstream_for(path: str) -> str:
    """Route specific infrastructure paths before general plugin families."""
    if _prefix(path, "test/e2e/") or re.search(r"(?:^|/)test/test_ui_schemas\.py$", path):
        return "W7"
    if re.search(r"(?:^|/)mmfdb(?:/|$)", path):
        return "W13"
    if re.search(r"(?:^|/)okf(?:/|$)", path):
        return "W0"
    if (re.search(r"(?:^|/)(?:test_)?sampling(?:[/_.]|$)", path)
            or _prefix(path, "test/core/test_fit")
            or _prefix(path, "test/gui/test_global_fit")
            or _prefix(path, "test/gui/test_fit_group")):
        return "W3"
    if (re.search(r"(?:^|/)(?:test_)?pto(?:[/_.]|$)", path)
            or _prefix(path, "chisurf/core/fio/") or _prefix(path, "core/fio/")
            or _prefix(path, "test/fio/")):
        return "W4"
    match = re.search(r"(?:^|/)chisurf/plugins/([^/]+)(?:/|$)", path)
    return PLUGIN_FAMILIES.get(match.group(1), "unassigned") if match else "unassigned"


def _identity(case: ET.Element, root: Path) -> tuple[str, str]:
    """Reconstruct pytest node ids without losing class names or parameters."""
    name = case.get("name", "")
    file = _path(case.get("file", ""), root)
    classname = case.get("classname", "")
    if ".py::" in name:
        return name, file or _path(name.split("::", 1)[0], root)
    parts = classname.split(".") if classname else []
    index = len(parts)
    while index and parts[index - 1][:1].isupper():
        index -= 1
    if file:
        module = file.removesuffix(".py").replace("/", ".")
        suffix = classname.removeprefix(module + ".") if classname != module else ""
        # Absolute JUnit file paths can have a relative classname.
        if suffix == classname:
            suffix = ".".join(parts[index:])
    else:
        file = "/".join(parts[:index]) + ".py" if index else ""
        suffix = ".".join(parts[index:])
    node_id = "::".join(part for part in (file, suffix.replace(".", "::"), name) if part)
    return node_id, file


def _manifests(root: Path) -> dict[str, str]:
    """Read plugin ids from manifests, with no GUI imports or initialization."""
    result = {}
    for path in sorted((root / "chisurf" / "plugins").rglob("manifest.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("id"), str):
            result[path.parent.relative_to(root).as_posix() + "/"] = data["id"]
    return result


def parse_failures(junit: Path, root: Path = ROOT) -> list[FailedTest]:
    """Read failure and error cases from a testsuite or nested testsuites XML."""
    manifests = _manifests(root)
    ids = set(manifests.values())
    result = []
    for case in ET.parse(junit).getroot().iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        outcomes = tuple(child.tag.rsplit("}", 1)[-1] for child in case
                         if child.tag.rsplit("}", 1)[-1] in {"failure", "error"})
        if not outcomes:
            continue
        node_id, file = _identity(case, root)
        plugin_id = next((value for prefix, value in sorted(
            manifests.items(), key=lambda item: len(item[0]), reverse=True)
            if _prefix(file, prefix)), "")
        parameter = re.search(r"\[([^\]]+)\]$", case.get("name", ""))
        if not plugin_id and parameter and parameter.group(1) in ids:
            plugin_id = parameter.group(1)
        result.append(FailedTest(node_id, file, workstream_for(file), plugin_id, outcomes))
    return result


def _code(value: str) -> str:
    """Escape table separators and preserve literal backticks in node ids."""
    longest = max((len(run) for run in re.findall(r"`+", value)), default=0)
    ticks = "`" * (longest + 1)
    return ticks + " " + value.replace("|", "\\|").replace("\n", " ") + " " + ticks


def markdown_report(failures: list[FailedTest]) -> str:
    """Render counts of failing testcases and their complete node identities."""
    grouped = defaultdict(list)
    for failure in failures:
        grouped[failure.workstream].append(failure)
    lines = ["| Workstream | Count | Manifest ids | Node ids |",
             "| --- | ---: | --- | --- |"]
    for owner, cases in sorted(grouped.items()):
        plugins = ", ".join(_code(value) for value in sorted({case.plugin_id for case in cases
                                                            if case.plugin_id})) or "—"
        nodes = "<br>".join(_code(case.node_id) for case in cases)
        lines.append(f"| {owner} | {len(cases)} | {plugins} | {nodes} |")
    if any(case.workstream == "W3" and ("global_fit" in case.node_id or "fit_group" in case.node_id)
           for case in failures):
        lines += ["", "Global-fit failures: check `FitGroup.model` versus `_model` before triage."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Print the triage report and optionally write the same Markdown to disk."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", required=True, type=Path, help="JUnit XML report to read")
    parser.add_argument("--write", type=Path, help="Also write the report to this Markdown path")
    args = parser.parse_args(argv)
    try:
        report = markdown_report(parse_failures(args.junit))
        if args.write:
            args.write.parent.mkdir(parents=True, exist_ok=True)
            args.write.write_text(report, encoding="utf-8")
    except (OSError, ET.ParseError, ValueError) as error:
        parser.error(str(error))
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
