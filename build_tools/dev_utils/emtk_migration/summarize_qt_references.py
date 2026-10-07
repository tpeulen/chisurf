"""Merge isolated capture batches against the current manifest catalog."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "okf/plugins/emtk-references"


def main() -> None:
    """Merge capture evidence after parsing the read-only CLI help entry point."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    results = []
    blockers = []
    for manifest_path in sorted((ROOT / "chisurf/plugins").rglob("manifest.json")):
        relative = manifest_path.relative_to(ROOT / "chisurf/plugins")
        if any(
            part in {"test", "tests", "renders", "cookiecutter-chisurf-plugin"}
            for part in relative.parts
        ):
            continue
        manifest = json.loads(manifest_path.read_text())
        filename = "__".join(relative.parts[:-1]) + ".json"
        candidates = []
        for metadata_path in OUTPUT.rglob(filename):
            data = json.loads(metadata_path.read_text())
            if data.get("document_fixture"):
                continue  # Rich-document scenarios do not replace the startup baseline.
            rank = {"captured": 3, "failed": 2, "timeout": 2}.get(data.get("status"), 1)
            candidates.append((rank, metadata_path.stat().st_mtime, metadata_path, data))
        if candidates:
            _, _, metadata_path, data = max(candidates, key=lambda item: item[:2])
            if metadata_path != OUTPUT / filename:
                shutil.copy2(metadata_path, OUTPUT / filename)
                if data.get("status") == "captured":
                    shutil.copy2(
                        metadata_path.with_suffix(".png"), (OUTPUT / filename).with_suffix(".png")
                    )
                    for page in data.get("tab_pages", []):
                        shutil.copy2(metadata_path.parent / page["image"], OUTPUT / page["image"])
            status = data.get("status", "unknown")
            if status in {"failed", "timeout"}:
                error = data.get("error", "")
                diagnostic = next(
                    (
                        line
                        for line in reversed(error.splitlines())
                        if line.startswith(
                            (
                                "ModuleNotFoundError:",
                                "ImportError:",
                                "AttributeError:",
                                "RuntimeError:",
                                "FileNotFoundError:",
                                "TypeError:",
                                "KeyError:",
                            )
                        )
                    ),
                    "Bounded timeout" if status == "timeout" else "See capture metadata",
                )
                if status == "timeout":
                    category = "startup_timeout"
                elif "No genuine Qt implementation" in diagnostic:
                    category = "historical_factory_unresolved"
                elif "embeds EMTK" in diagnostic:
                    category = "historical_qt_shell_embeds_emtk"
                elif "blank offscreen framebuffer" in diagnostic:
                    category = "offscreen_rendering_blocker"
                elif "Legacy script did not create a Qt widget" in diagnostic:
                    category = "host_action_no_standalone_window"
                elif "No module named 'chisurf." in diagnostic:
                    category = "historical_source_gap"
                elif "ModuleNotFoundError:" in diagnostic or "ImportError:" in diagnostic:
                    category = "dependency_or_historical_api_gap"
                elif "FileNotFoundError:" in diagnostic:
                    category = "historical_asset_gap"
                else:
                    category = "factory_or_runtime_failure"
                blockers.append(
                    {
                        "plugin": manifest.get("id", manifest_path.parent.name),
                        "category": category,
                        "diagnostic": diagnostic,
                        "metadata": filename,
                    }
                )
        else:
            status = "not_attempted"
        results.append(
            {
                "plugin": manifest.get("id", manifest_path.parent.name),
                "manifest": str(manifest_path.relative_to(ROOT)),
                "status": status,
                "metadata": filename,
                "entrypoints": manifest.get("entrypoints", {}),
            }
        )
    (OUTPUT / "capture-index.json").write_text(json.dumps(results, indent=2))
    counts = dict(Counter(result["status"] for result in results))
    (OUTPUT / "capture-blockers.json").write_text(json.dumps(blockers, indent=2))
    (OUTPUT / "capture-summary.json").write_text(
        json.dumps(
            {
                "total": len(results),
                "counts": counts,
                "scope": "Initial Qt reference captures only; does not prove EMTK functionality or visual parity.",
            },
            indent=2,
        )
    )
    print(json.dumps({"total": len(results), "counts": counts}))


if __name__ == "__main__":
    main()
