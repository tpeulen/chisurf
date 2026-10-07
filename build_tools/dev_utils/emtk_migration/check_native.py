"""Isolated native-factory checks; these are runtime evidence, not parity proof.

Run with the environment that supplies the plugin's scientific dependencies:
pixi run -e test python build_tools/dev_utils/emtk_migration/check_native.py --report /tmp/native-checks.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", help="Check one factory in the current subprocess")
    parser.add_argument("--report", type=Path, default=Path("/tmp/chisurf-native-checks.json"))
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.factory:
        from chisurf.emtk.validation import check_factory

        try:
            screenshot = str(args.screenshots) if args.screenshots else None
            result = check_factory(args.factory, screenshot)
        except Exception as error:
            result = {
                "factory": args.factory,
                "status": "fail",
                "error": str(error),
                "error_type": type(error).__name__,
            }
        print(json.dumps(result))
        return 0 if result["status"] == "pass" else 1
    results = []
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    font_cache = Path(os.environ.get("MPLCONFIGDIR") or
                      Path(tempfile.gettempdir()) / "chisurf-emtk-native-font-cache")
    font_cache.mkdir(parents=True, exist_ok=True)
    for manifest in sorted((ROOT / "chisurf" / "plugins").rglob("manifest.json")):
        data = json.loads(manifest.read_text())
        if not isinstance(data, dict) or not data.get("id") or not data.get("version"):
            continue
        if "cookiecutter" in str(manifest):
            continue
        spec = data.get("entrypoints", {}).get("emtk")
        record = {"id": data["id"], "manifest": str(manifest.relative_to(ROOT))}
        if not spec:
            record.update(
                status="pending"
                if data.get("entrypoints", {}).get("gui")
                or data.get("entrypoints", {}).get("script")
                else "non_gui",
                reason="No declared native factory",
            )
            results.append(record)
            continue
        with tempfile.TemporaryDirectory(prefix="chisurf-native-check-") as temp:
            env = dict(os.environ, CHISURF_SETTINGS_DIR=temp, MPLCONFIGDIR=str(font_cache),
                       MMFDB_SETTINGS_DIR=temp, MMFDB_OBJECT_STORE_ROOT=str(Path(temp) / "objects"),
                       NDXPLORER_SETTINGS_DIR=str(Path(temp) / "ndxplorer"))
            env["PYTHONPATH"] = os.pathsep.join(
                (str(ROOT), str(ROOT.parent / "emtk"), env.get("PYTHONPATH", ""))
            )
            command = [sys.executable, str(Path(__file__).resolve()), "--factory", spec]
            if args.screenshots:
                command += ["--screenshots", str(args.screenshots.resolve() / f"{data['id']}.png")]
            try:
                process = subprocess.run(
                    command, capture_output=True, text=True, env=env, cwd=ROOT, timeout=args.timeout
                )
                record["exit_code"] = process.returncode
                if process.stderr:
                    record["diagnostics"] = process.stderr[-4000:]
                if not process.stdout.strip():
                    raise ValueError(f"Native process exited without a result ({process.returncode})")
                parsed = json.loads(process.stdout.strip().splitlines()[-1])
                record.update(parsed)
            except (subprocess.TimeoutExpired, ValueError, IndexError) as error:
                record.update(status="fail", error=str(error))
        results.append(record)
        print(f"{record['id']}: {record['status']}", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"checks": results}, indent=2) + "\n")
    counts = {
        status: sum(row["status"] == status for row in results)
        for status in ("pass", "fail", "pending", "non_gui")
    }
    print(json.dumps(counts))
    return int(bool(counts["fail"]))


if __name__ == "__main__":
    raise SystemExit(main())
