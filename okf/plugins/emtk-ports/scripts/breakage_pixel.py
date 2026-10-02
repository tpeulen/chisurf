"""Deliberate breakage of an imaging pixel plugin, twice: apply a mutation, run the plugin's tests, record how many fail, restore the file (byte-identical), then the next.
Usage: breakage_pixel.py <plugin_id> -> prints a JSON list of "mutation -> N failed" strings."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path("/Users/tpeulen/dev/chisurf")
M = "chisurf/plugins/microscopy/"
PY = "/Users/tpeulen/mambaforge/envs/arm64/bin/python"
MUT = {
    "img_pixel_micro_time": [
        (M + "img_pixel_micro_time/gui/model.py", 'self._columns[f"mean_micro_time ({window})"] = maps["mean_micro_time"]', 'self._columns[f"mean_micro_time ({window})"] = maps["intensity"]', "the written column holds the intensity"),
        (M + "imaging_emtk/pixel_model.py", 'self.status_line = "Nothing changed since the last run; the maps are up to date."', 'self.status_line = "Done"', "the up-to-date message replaced"),
    ],
    "img_pixel_phasor": [
        (M + "img_pixel_phasor/gui/view_model.py", "return freq * 1e6 * resolution if resolution > 0 else freq", "return freq", "the MHz conversion removed (the original defect)"),
        (M + "img_pixel_phasor/gui/model.py", 'self.detectors[window]["irf"] = [value] if value else []', 'self.detectors[window]["irf"] = []', "the IRF reference never stored"),
    ],
    "img_pixel_nb": [
        (M + "img_pixel_nb/gui/model.py", "            return not self.busy and bool(self._by_window)", "            return not self.busy", "Calibrate analog enabled without a result"),
        (M + "imaging_emtk/pixel_model.py", "        self.pipeline_hdf5 = path\n        if callable", "        if callable", "the written HDF5 not remembered"),
    ],
    "img_pixel_mle": [
        (M + "img_pixel_mle/gui/model.py", "self.irf_files = [str(paths[0])]", "self.irf_files = [str(p) for p in paths]", "the IRF no longer one file"),
        (M + "img_pixel_mle/gui/model.py", "        self.cancel_event.set()\n        self.status_text = \"Cancelling...\"", "        self.status_text = \"Cancelling...\"", "Cancel does nothing"),
    ],
    "img_coloc": [
        (M + "img_coloc/gui/model.py", "        self.gate_enabled = bool(len(self.gates))\n        self.notify(\"gate\")", "        self.notify(\"gate\")", "a gate no longer switches gating on"),
        (M + "img_coloc/gui/model.py", 'self.status_line = "" if ok else self.results_text', 'self.status_line = "Computing"', "the status after a run replaced"),
    ],
}
pid = sys.argv[1]
out = []
for rel, old, new, what in MUT[pid]:
    path = ROOT / rel
    original = path.read_bytes()
    text = original.decode()
    assert old in text, f"{rel}: pattern not found"
    path.write_bytes(text.replace(old, new, 1).encode())
    try:
        r = subprocess.run([PY, "-m", "pytest", f"{M}{pid}/test", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True,
                           env={**__import__("os").environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONPATH": f"{ROOT}:/Users/tpeulen/dev/emtk"})
        tail = [l for l in r.stdout.splitlines() if (" passed" in l or " failed" in l) and " in " in l]
        out.append(f"{what} -> {tail[-1].strip() if tail else r.stdout[-200:]}")
    finally:
        path.write_bytes(original)
    assert path.read_bytes() == original
print(json.dumps(out))
