"""Qt-free AutoForm view-model for the synthetic decay generator."""

from __future__ import annotations

import pathlib
from typing import Any

from ..core.algorithms import compute_aniso_decay, compute_decay, compute_rt

_VIEW = pathlib.Path(__file__).with_name("synthetic_decay.view.json")


class SyntheticDecayViewModel:
    """Backing model for the AutoForm view (``synthetic_decay.view.json``).

    Holds an editable lifetime spectrum (amplitude/lifetime rows) plus histogram,
    IRF and shot-noise options, and generates the decay through the shared core
    generator. The plot reads :meth:`decay_series`.

    Anisotropy support: a detection-mode choice (magic-angle VM vs a polarized
    VV/VH pair), the VV/VH detection corrections (g-factor, l1, l2), a rotation
    spectrum table (b, rho rows) whose r(t) is plotted in both modes, VV/VH file
    output that carries the corrections in its footer, and a *Fit group* action
    that adds the generated curves as a dataset and creates the fit group the
    same way a VV/VH data load does.
    """

    def __init__(self) -> None:
        self.n_bins = 256
        self.bin_width = 0.032
        self.start_bin = 0
        self.irf_path = ""
        self.shot_noise = False
        self.photon_count = 1_000_000.0
        self.seed = 1
        self.spectrum_rows: list[dict[str, float]] = [
            {"amp": 1.0, "tau": 1.2},
            {"amp": 1.0, "tau": 4.0},
        ]
        self.selected_row = -1
        # -- anisotropy ------------------------------------------------------
        # Detection mode: magic angle ("vm") or a polarized VV/VH pair. The
        # g/l1/l2 detection corrections and the rotation spectrum only shape
        # the generated channels in VV/VH mode, but r(t) is a property of the
        # sample and is plotted in both.
        self.polarization = "vm"
        self.g_factor = 1.0
        self.l1 = 0.0
        self.l2 = 0.0
        self.rotation_rows: list[dict[str, float]] = [
            {"b": 0.2, "rho": 1.0},
        ]
        self.selected_rotation_row = -1
        self.status = "Edit the lifetime spectrum and press Generate."
        self._x: list[float] = []
        self._y: list[float] = []
        self._vv: list[float] = []
        self._vh: list[float] = []
        self._r: list[float] = []
        self._form: Any = None

    # ── view / table binding ─────────────────────────────────────────
    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW)

    def spectrum_source(self) -> list[dict[str, float]]:
        return [dict(row) for row in self.spectrum_rows]

    def update_spectrum(self, row_index: int, column_key: str, value: Any) -> None:
        try:
            self.spectrum_rows[int(row_index)][column_key] = float(value)
        except (ValueError, IndexError, TypeError):
            pass

    def add_row(self) -> None:
        self.spectrum_rows.append({"amp": 1.0, "tau": 2.0})
        self._refresh_fields()

    def remove_row(self) -> None:
        idx = int(self.selected_row)
        if 0 <= idx < len(self.spectrum_rows) and len(self.spectrum_rows) > 1:
            self.spectrum_rows.pop(idx)
            self._refresh_fields()

    # -- rotation spectrum (anisotropy) table -----------------------------
    def rotation_source(self) -> list[dict[str, float]]:
        return [dict(row) for row in self.rotation_rows]

    def update_rotation(self, row_index: int, column_key: str, value: Any) -> None:
        try:
            self.rotation_rows[int(row_index)][column_key] = float(value)
        except (ValueError, IndexError, TypeError):
            pass

    def add_rotation_row(self) -> None:
        self.rotation_rows.append({"b": 0.1, "rho": 2.0})
        self._refresh_fields()

    def remove_rotation_row(self) -> None:
        idx = int(self.selected_rotation_row)
        if 0 <= idx < len(self.rotation_rows):
            self.rotation_rows.pop(idx)
            self._refresh_fields()

    def set_polarization(self, value: Any) -> None:
        """Commit hook for the VM / VV-VH choice; keeps the value canonical."""
        text = str(value).lower().strip()
        if text in ("vm", "vv/vh", "vvvh"):
            self.polarization = "vm" if text == "vm" else "vv/vh"
        self._refresh_fields()

    def is_vv_vh(self) -> bool:
        """True when the detection mode is a polarized VV/VH pair."""
        return str(getattr(self, "polarization", "vm")).lower() != "vm"

    def load_spectrum(self) -> None:
        """Load a lifetime spectrum from a CSV/text file into the table.

        Accepts either a flat 1-D interleaved list ``a1, tau1, a2, tau2, …`` or a
        two-column ``(amplitude, lifetime)`` table (same convention as the TCSPC
        simulator experiment setup), validated via
        :func:`chisurf.core.fluorescence.decay.validate_lifetime_spectrum`.
        """
        import numpy as np
        from qtpy import QtWidgets

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            None, "Load lifetime spectrum", "",
            "Data files (*.csv *.txt *.dat);;All files (*)",
        )
        if not path:
            return
        try:
            arr = np.asarray(np.loadtxt(path, dtype=float, ndmin=1), dtype=float)
        except Exception as exc:
            self.status = f"Load failed: {exc}"
            self._refresh_fields()
            return
        if arr.ndim == 1:
            values = arr
        elif arr.ndim == 2 and arr.shape[1] >= 2:
            a, tau = arr[:, 0].ravel(), arr[:, 1].ravel()
            n = min(a.size, tau.size)
            values = np.empty(2 * n, dtype=float)
            values[0::2], values[1::2] = a[:n], tau[:n]
        else:
            self.status = "Load failed: expected an interleaved list or a 2-column table."
            self._refresh_fields()
            return
        try:
            from chisurf.core.fluorescence.decay import validate_lifetime_spectrum

            values = validate_lifetime_spectrum(values)
        except Exception as exc:
            self.status = f"Invalid lifetime spectrum: {exc}"
            self._refresh_fields()
            return
        self.spectrum_rows = [
            {"amp": float(values[i]), "tau": float(values[i + 1])}
            for i in range(0, len(values), 2)
        ]
        self.selected_row = -1
        self.status = f"Loaded {len(self.spectrum_rows)} components from {pathlib.Path(path).name}."
        self._refresh_fields()

    # ── compute ──────────────────────────────────────────────────────
    def generate(self) -> None:
        try:
            amps = [float(r.get("amp", 1.0)) for r in self.spectrum_rows]
            taus = [float(r.get("tau", 1.0)) for r in self.spectrum_rows]
            noisy = bool(self.shot_noise)
            common = dict(
                n_bins=int(self.n_bins),
                bin_width=float(self.bin_width),
                start_bin=int(self.start_bin),
                irf=(self.irf_path or None),
                normalize=not noisy,
                photon_count=(float(self.photon_count) if noisy else None),
                seed=(int(self.seed) if noisy else None),
            )
            self._vv, self._vh = [], []
            if self.is_vv_vh():
                # Polarized measurement: the VV/VH pair carries the anisotropy;
                # both channels share one Poisson budget when noise is on.
                result = compute_aniso_decay(
                    lifetimes=taus,
                    amplitudes=amps,
                    rotation_rows=self.rotation_rows,
                    g_factor=float(self.g_factor),
                    l1=float(self.l1),
                    l2=float(self.l2),
                    **common,
                )
                self._x = result["x"]
                self._vv, self._vh = result["vv"], result["vh"]
                self._r = result["r"]
                self._y = []
                self.status = (
                    f"Generated VV/VH pair, {len(self._vv)} bins "
                    f"({len(self.spectrum_rows)} lifetimes, "
                    f"{len(self.rotation_rows)} rotations, "
                    f"g={self.g_factor:g}, l1={self.l1:g}, l2={self.l2:g})."
                )
            else:
                # Magic angle: the decay carries no anisotropy, but the sample's
                # r(t) is still defined and shown next to it.
                result = compute_decay(lifetimes=taus, amplitudes=amps, **common)
                self._x = result["x"]
                self._y = result["y"]
                self._r = compute_rt(
                    n_bins=int(self.n_bins),
                    bin_width=float(self.bin_width),
                    rotation_rows=self.rotation_rows,
                )["r"]
                self.status = f"Generated {len(self._y)} bins ({len(self.spectrum_rows)} components)."
        except Exception as exc:
            self._x, self._y = [], []
            self._vv, self._vh, self._r = [], [], []
            self.status = f"Error: {exc}"
        self._refresh_plots()

    def status_text(self) -> str:
        return str(self.status)

    def decay_series(self) -> list[dict]:
        """Lines for the decay plot.

        VM mode shows the magic-angle decay; VV/VH mode shows the two
        polarized channels on the same log-count axis.
        """
        if self.is_vv_vh():
            series = []
            if self._vv:
                series.append({"x": self._x, "y": self._vv, "name": "VV", "color": "#f472b6"})
            if self._vh:
                series.append({"x": self._x, "y": self._vh, "name": "VH", "color": "#a78bfa"})
            return series
        if not self._y:
            return []
        return [{"x": self._x, "y": self._y, "name": "decay", "color": "#22d3ee"}]

    def aniso_series(self) -> list[dict]:
        """The anisotropy decay r(t) line, plotted in both detection modes."""
        if not self._r or not self._x:
            return []
        return [{"x": self._x, "y": self._r, "name": "r(t)", "color": "#fbbf24"}]

    def save(self) -> None:
        if self.is_vv_vh():
            self._save_vv_vh()
        else:
            self._save_vm()

    def _save_vm(self) -> None:
        if not self._y:
            self.status = "Nothing to save — press Generate first."
            self._refresh_fields()
            return
        from qtpy import QtWidgets

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save decay", "synthetic_decay.csv",
            "CSV (*.csv);;Text (*.txt);;NumPy (*.npy);;JSON (*.json)",
        )
        if not path:
            return
        import json

        import numpy as np

        low = path.lower()
        if low.endswith(".npy"):
            np.save(path, np.asarray(self._y, dtype=float))
        elif low.endswith(".json"):
            with open(path, "w") as fh:
                json.dump({"x": self._x, "y": self._y}, fh, indent=2)
        else:
            np.savetxt(
                path, np.column_stack([self._x, self._y]), header="time_ns\tcounts"
            )
        self.status = f"Saved {len(self._y)} bins to {pathlib.Path(path).name}."
        self._refresh_fields()

    def _save_vv_vh(self) -> None:
        """Write the pair as a VV/VH file.

        The shared writer puts the channel list and the anisotropy calibration
        (g-factor, l1, l2) into the footer, so reading the file back with the
        VV/VH reader restores the same corrections the data were generated
        with — the features travel with the data.
        """
        if not self._vv or not self._vh:
            self.status = "Nothing to save — press Generate first."
            self._refresh_fields()
            return
        from qtpy import QtWidgets

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save VV/VH decays", "synthetic_aniso.dat",
            "VV/VH data (*.dat *.txt);;All files (*)",
        )
        if not path:
            return
        import numpy as np

        from chisurf.core.fio.vv_vh import write_vv_vh

        write_vv_vh(
            path,
            vv=np.asarray(self._vv, dtype=float),
            vh=np.asarray(self._vh, dtype=float),
            g_factor=float(self.g_factor),
            metadata=self.aniso_metadata(),
            fmt="%.12g",
        )
        self.status = f"Saved VV/VH pair ({len(self._vv)} bins) to {pathlib.Path(path).name}."
        self._refresh_fields()

    def aniso_metadata(self) -> dict:
        """Anisotropy metadata that travels with the generated data.

        Written into the VV/VH file footer and attached to datasets created
        via *Fit group* — the same keys the TCSPC reader uses to carry the
        corrections into a fit (``g_factor``, ``l1``, ``l2``).
        """
        return {
            "polarization": "vv/vh" if self.is_vv_vh() else "vm",
            "g_factor": float(self.g_factor),
            "l1": float(self.l1),
            "l2": float(self.l2),
            "dt_ns": float(self.bin_width),
            "n_bins": int(self.n_bins),
            "lifetimes": ", ".join(f"{float(r.get('tau', 0.0)):g}" for r in self.spectrum_rows),
            "amplitudes": ", ".join(f"{float(r.get('amp', 0.0)):g}" for r in self.spectrum_rows),
            "rotation": ", ".join(
                f"{float(r.get('b', 0.0)):g}/{float(r.get('rho', 0.0)):g}"
                for r in self.rotation_rows
            ),
            "source": "synthetic_decay",
        }

    # ── fit group (like a VV/VH data load) ───────────────────────────
    def build_dataset_group(self):
        """Pack the generated curves into a dataset group, ready to fit.

        VV/VH mode yields a two-curve group (VV, VH) — the same structure the
        VV/VH file reader produces — so creating a fit over it yields one fit
        group whose members get the ``vv``/``vh`` polarizations by position.
        VM mode yields a single curve. The anisotropy calibration
        (``g_factor``, ``l1``, ``l2``) is attached as meta-data on the group
        and on each curve, which is how :func:`chisurf.macros.core_fit.add_fit`
        carries it into the model parameters. The bin width rides on the
        x-axis (``dx``), which is where the convolve group reads it from.
        """
        import numpy as np

        from chisurf.core.data import DataCurve, ExperimentDataCurveGroup

        if self.is_vv_vh():
            if not self._vv or not self._vh:
                return None
            channels = [
                ("VV", np.asarray(self._vv, dtype=float)),
                ("VH", np.asarray(self._vh, dtype=float)),
            ]
        else:
            if not self._y:
                return None
            channels = [("decay", np.asarray(self._y, dtype=float))]

        x = np.asarray(self._x, dtype=float)
        meta = self.aniso_metadata()
        curves = []
        for suffix, y in channels:
            curve = DataCurve(
                x=x.copy(),
                y=y.copy(),
                load_filename_on_init=False,
                name=f"synthetic {suffix}",
            )
            curve.meta_data = dict(meta)
            curves.append(curve)

        group = ExperimentDataCurveGroup(curves)
        group.meta_data = dict(meta)
        group.name = f"synthetic {'vv/vh' if self.is_vv_vh() else 'vm'}"

        # A reader-shaped object on the data, as after a real load: the
        # convolve parameter group reads the bin width (dx) together with
        # ``data_reader.rep_rate``, and ``add_fit`` prefers the reader's
        # g/l1/l2 for the calibration. This makes the synthetic dataset
        # indistinguishable from a read one as far as the fit stack cares.
        try:
            from chisurf.core.experiments.tcspc.reader import TCSPCReader

            reader = TCSPCReader(
                dt=float(self.bin_width),
                is_vv_vh=self.is_vv_vh(),
                g_factor=float(self.g_factor),
                l1=float(self.l1),
                l2=float(self.l2),
            )
            reader.polarization = "vv/vh" if self.is_vv_vh() else "vm"
            reader.experiment = None
            group.data_reader = reader
            for curve in curves:
                curve.data_reader = reader
        except Exception:
            pass
        return group

    def send_to_fit(self) -> None:
        """Add the generated data as a dataset and create its fit group.

        Mirrors a VV/VH data load followed by *Add fit*: the dataset enters
        ``cs.imported_datasets`` as one group, then the ``fit.add`` action
        builds a :class:`~chisurf.core.fitting.fit.FitGroup` over it with the
        lifetime view (the polarised one for a VV/VH pair). The description's
        group position assigns the polarizations (VV, VH by member, magic
        angle alone) and the meta-data supplies g/l1/l2, so the fit starts
        from the corrections the data were simulated with.
        """
        group = self.build_dataset_group()
        if group is None:
            self.status = "Nothing to send — press Generate first."
            self._refresh_fields()
            return
        try:
            import chisurf as cs

            from chisurf.core.models.description import for_family
            from chisurf.macros import core_data

            # Binding the family makes the view resolvable by its name.
            model_name = for_family("tcspc_polarized" if self.is_vv_vh() else "tcspc_lifetime").name
            core_data.add_dataset(experiment_reader=None, dataset=group, _from_controller=True)
            dataset_index = len(cs.imported_datasets) - 1
            cs.core.actions.dispatch(
                name="fit.add",
                payload={"dataset_indices": [dataset_index], "model_name": model_name},
            )
            self.status = (
                f"Added dataset #{dataset_index} and fit group "
                f"({len(group)} curve(s), model {model_name})."
            )
        except Exception as exc:
            self.status = f"Fit group failed: {exc}"
        self._refresh_fields()

    # ── refresh helpers ──────────────────────────────────────────────
    def _refresh_fields(self) -> None:
        form = self._form
        if form is not None:
            try:
                form.sync_fields()
            except Exception:
                pass

    def _refresh_plots(self) -> None:
        form = self._form
        if form is not None:
            try:
                form.refresh_plots()
            except Exception:
                pass
            self._refresh_fields()
