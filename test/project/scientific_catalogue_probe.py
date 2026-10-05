"""Fresh interpreter verifier; archive contents never supply Python code."""

import importlib.abc
import json
import sys
from pathlib import Path

import numpy as np


def scientific_observables(fit):
    """Read the declared model observables, including tools without a curve."""
    model = fit.model
    if type(model).__name__ in {"FCSKineticsModel", "MaxEntFCSModel", "MaxEntRHModel"}:
        from test.project.test_fcs_snapshot_science_edits import fcs_scientific_observables

        return fcs_scientific_observables(model)
    if type(model).__name__ == "ParameterTransformModel":
        return {
            "native_outputs": {p.name: float(p.value) for p in model.parameters_all if p.is_output}
        }
    if type(model).__name__ == "ProteinMCModel":
        return {
            "distances": {name: float(p.value) for name, p in model._distance_parameters.items()},
            "coordinates": np.asarray(model.structure.xyz).tolist(),
            "energy": list(model.energy),
            "chi2r": list(model.chi2r),
        }
    return {"prediction": np.asarray(model.y).tolist()}


def original_sources(project):
    """List explicit measurement and resource source references to forbid rereads."""
    paths = set()
    datasets = project["datasets"] if isinstance(project, dict) else project.datasets
    fits = project["fits"] if isinstance(project, dict) else project.fits
    for record in datasets.values():
        if record.get("filename"):
            paths.add(str(Path(record["filename"]).resolve()))
        mfd = record.get("auxiliary", {}).get("mfd", {})
        for path in mfd.get("preparation", {}).get("sources", {}).get("paths", {}).values():
            paths.add(str(Path(path).resolve()))
    for record in fits:
        for member in record["members"]:
            state = member["model"]["adapter_state"]
            for path in state.get("structure_files", []):
                paths.add(str(Path(path).resolve()))
            structural = state.get("proteinmc", {})
            for field in ("structure_source", "labeling_file"):
                if structural.get(field):
                    paths.add(str(Path(structural[field]).resolve()))
    return paths


class _BlockMMFDB(importlib.abc.MetaPathFinder):
    """Require ordinary scientific files to work without optional MMFDB."""

    def find_spec(self, fullname, path=None, target=None):
        """Reject every optional MMFDB import in this fresh interpreter."""
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            raise AssertionError(f"optional MMFDB import: {fullname}")


def _differences(left, right, path):
    """Report exact snapshot disagreements without normalising scientific UIDs."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(left.keys() | right.keys()):
            yield from _differences(left.get(key), right.get(key), f"{path}.{key}")
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            yield f"{path}: lengths {len(left)} != {len(right)}"
        for index, (a, b) in enumerate(zip(left, right)):
            yield from _differences(a, b, f"{path}[{index}]")
    elif left != right:
        yield f"{path}: {left!r} != {right!r}"


def main():
    """Load, check and recapture the canonical science in a fresh registry."""
    if sys.argv[1] == "--case":
        from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _file_roundtrip

        _file_roundtrip(Path(sys.argv[3]), CATALOGUE[int(sys.argv[2])])
        return
    sys.meta_path.insert(0, _BlockMMFDB())
    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file

    source, expected_path = map(Path, sys.argv[1:3])
    expected = json.loads(expected_path.read_text())
    from chisurf.core.project.pto import read_project

    payload, _ = read_project(source)
    blocked_paths = set(expected.get("source_paths", []))
    blocked_paths.update(original_sources(payload))

    def forbid_source_reads(event, arguments):
        """Reject Python file access to the original declared scientific inputs."""
        if event == "open" and isinstance(arguments[0], (str, bytes)):
            filename = arguments[0]
            filename = filename.decode() if isinstance(filename, bytes) else filename
            if str(Path(filename).resolve()) in blocked_paths:
                raise AssertionError(f"original scientific source reread: {filename}")

    sys.addaudithook(forbid_source_reads)
    project = load_file(source)
    blocked_paths.update(original_sources(project))
    restored = restore_session(project)
    for fit, prediction in zip(restored.fits, expected["predictions"]):
        if prediction is not None:
            np.testing.assert_allclose(fit.model.y, prediction, rtol=1e-12, atol=1e-12)
    if "observables" in expected:
        assert [scientific_observables(fit) for fit in restored.fits] == expected["observables"]
    recaptured = capture_session(restored.datasets, restored.fits)
    import itertools

    assert recaptured.datasets == project.datasets, list(
        itertools.islice(_differences(project.datasets, recaptured.datasets, "datasets"), 10)
    )
    assert recaptured.fits == project.fits, list(
        itertools.islice(_differences(project.fits, recaptured.fits, "fits"), 10)
    )
    save_file(recaptured, source.with_name("fresh-" + source.name))


if __name__ == "__main__":
    main()
