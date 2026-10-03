"""A fake ChiSurf session for the batch-analysis tests: datasets, one template fit, a fit client and a dispatcher.

The numbers are deterministic: running the fit on the k-th item gives ``tau = 1 + 0.5 k`` and ``chi2r = 1 + 0.05 k``,
so the results of a batch differ item by item and a test can tell the items apart.
"""

from __future__ import annotations

import os


class FakeParam:
    """A fitting parameter."""

    def __init__(self, name, value, fixed=False):
        self.name = name
        self.value = value
        self.fixed = fixed


class FakeFit:
    """A fit with a model of three parameters, a reduced chi-square and ``save``."""

    def __init__(self, name="Template fit", dataset=None):
        self.name = name
        self.model = type("M", (), {})()
        self.model.parameters_all = [FakeParam("tau", 4.0), FakeParam("amplitude", 0.5), FakeParam("offset", 0.0, True)]
        self.chi2r = 1.0
        self.dataset = dataset
        self.saved: list[tuple] = []

    def save(self, base, fmt, save_curves=False):
        with open(f"{base}.{fmt}", "w") as handle:
            handle.write("x,y\n0,1\n")
        self.saved.append((base, fmt))


class FakeDataset:
    """A loaded dataset."""

    def __init__(self, name):
        self.name = name
        self.experiment = None


class FakeClient:
    """The fitting client: lists the fits, sets parameter values and flags like the real one."""

    def __init__(self, fits):
        self.fits = fits
        self.calls: list[tuple] = []

    def get_fit_objects(self):
        return self.fits

    def set_parameter_value(self, parameter_name, value, fit_index):
        self.calls.append(("value", parameter_name, value))
        for p in self.fits[fit_index].model.parameters_all:
            if p.name == parameter_name:
                p.value = value
        return {"ok": True}

    def set_parameter_fixed(self, parameter_name, fixed, fit_index):
        self.calls.append(("fixed", parameter_name, fixed))
        for p in self.fits[fit_index].model.parameters_all:
            if p.name == parameter_name:
                p.fixed = fixed
        return {"ok": True}


class FakeSession:
    """Datasets, fits, the client and the action dispatcher of one ChiSurf session."""

    def __init__(self, datasets=("Sample A", "Sample B", "Sample C"), fits=("Template fit",)):
        self.datasets = [FakeDataset(n) for n in datasets]
        self.fits = [FakeFit(n) for n in fits]
        self.client = FakeClient(self.fits)
        self.log: list[tuple] = []
        self.runs = 0

    def dispatch(self, name, payload):
        self.log.append((name, dict(payload)))
        fit = self.fits[payload.get("fit_index", 0)] if "fit_index" in payload else self.fits[0]
        if name == "dataset.add":
            self.datasets.append(FakeDataset(os.path.basename(payload["filename"])))
        elif name == "fit.set_dataset":
            index = payload["dataset_index"]
            fit.dataset = self.datasets[index]
        elif name == "fit.run":
            k = self.runs
            self.runs += 1
            for p in fit.model.parameters_all:
                if p.name == "tau":
                    p.value = 1.0 + 0.5 * k
            fit.chi2r = 1.0 + 0.05 * k
