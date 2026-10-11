"""Native simulator actions and plots bound to the original scientific reader."""

from __future__ import annotations

import json

import numpy as np
from emtk import im, implot

from chisurf.core.data import DataCurve
from chisurf.core.experiments.tcspc.simulator import resolve_irf
from chisurf.core.support.i18n import tr
from chisurf.emtk.reader_settings import ReaderSettingsApp


class SimulatorSettingsModel:
    """Delegate declared fields to a reader while keeping GUI state in the frontend."""

    def __init__(self, reader, context):
        self.reader = reader
        self.context = context
        self.preview = None
        self.irf_candidate = ""
        self.status = ""

    def __getattr__(self, name):
        """Read scientific fields directly from their original owner."""
        return getattr(self.reader, name)

    def __setattr__(self, name, value):
        """Commit ordinary settings to the owner and invalidate outdated previews."""
        if name in {"reader", "context", "preview", "irf_candidate", "status"} or name.startswith(
            "_"
        ):
            object.__setattr__(self, name, value)
        elif isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
        else:
            try:
                setattr(self.reader, name, value)
                if name == "polarization":
                    self.reader.is_vv_vh = str(value) != "vm"
                self.preview = None
                self.status = ""
            except ValueError as exc:
                self.status = str(exc)

    @property
    def seed_text(self):
        """Represent a nullable seed without silently converting blank input to zero."""
        return "" if self.reader.seed is None else str(self.reader.seed)

    @seed_text.setter
    def seed_text(self, value):
        """Accept a nonnegative integer seed or the unseeded empty value."""
        try:
            seed = int(value) if str(value).strip() else None
            if seed is not None and seed < 0:
                raise ValueError(tr("The random seed must be nonnegative."))
            self.reader.seed = seed
            self.preview = None
            self.status = ""
        except ValueError as exc:
            self.status = str(exc)

    @property
    def irf_label(self):
        """Describe the actual measured response or Gaussian fallback."""
        irf = self.reader.instrument_response_function
        return tr("IRF: Gaussian") if irf is None else tr("IRF: ") + str(irf.name)

    def irf_options(self):
        """Return stable parent/member identities rather than positional substitutes."""
        api = getattr(self.context, "api", None)
        rows = api.list_datasets() if api is not None else []
        result = []
        for row in rows:
            parent = str(row.get("uid", ""))
            if not parent:
                continue
            if "members" in row:
                for member in row["members"]:
                    uid = str(member.get("uid", ""))
                    if uid and member.get("length") is not None:
                        result.append(
                            (
                                json.dumps([parent, uid]),
                                f"{row.get('name', parent)} / {member.get('name', uid)} [{uid[:8]}]",
                            )
                        )
            elif str(row.get("type", "")).endswith("Curve"):
                result.append((json.dumps([parent, None]), str(row.get("name", parent))))
        return result

    def enabled(self, action):
        """Disable actions whose actual required inputs are unavailable."""
        if action == "select_irf":
            return bool(self.irf_candidate and self.irf_options())
        if action == "unload_irf":
            return self.reader.instrument_response_function is not None
        if action == "add_preview":
            return callable(getattr(self.context, "load_dataset", None))
        return True

    def irf_choices(self):
        """Keep an explicit unselected state until the user chooses a real curve."""
        return [("", tr("Choose a session curve…")), *self.irf_options()]

    def select_irf(self):
        """Fetch exactly the chosen live session curve through the owning API."""
        options = dict(self.irf_options())
        if self.irf_candidate not in options:
            self.status = tr("Select an available session curve.")
            return
        parent, member = json.loads(self.irf_candidate)
        parameters = {"dataset_uid": parent}
        if member is not None:
            parameters["member_uid"] = member
        result = self.context.api.get_dataset_curve_data(**parameters)
        x, y = (
            np.asarray(result.get("x", []), dtype=float),
            np.asarray(result.get("y", []), dtype=float),
        )
        if (
            not result.get("ok")
            or x.ndim != 1
            or x.size < 2
            or x.shape != y.shape
            or not np.all(np.isfinite(x + y))
            or not np.any(y > 0)
        ):
            self.status = str(result.get("error") or tr("The selected curve is not a usable IRF."))
            return
        self.reader.instrument_response_function = DataCurve(
            x=x, y=y, name=options[self.irf_candidate]
        )
        self.preview = None
        self.status = ""

    def unload_irf(self):
        """Remove the measured IRF and leave the Gaussian parameters unchanged."""
        self.reader.instrument_response_function = None
        self.preview = None
        self.status = ""

    def load_lifetime_spectrum_file(self, filename):
        """Report parse failures and retain the previously valid reader spectrum."""
        try:
            self.reader.load_lifetime_spectrum_file(filename)
            self.preview = None
            self.status = ""
        except (OSError, ValueError) as exc:
            self.status = str(exc)

    def simulate_preview(self):
        """Cache the actual reader result, preserving its noise, seed and group metadata."""
        self.preview = self.reader.read()
        self.status = tr("Simulation ready.")

    def add_preview(self):
        """Submit the displayed group without repeating the scientific computation."""
        if self.preview is None:
            self.simulate_preview()
        result = self.context.load_dataset(experiment_reader=self.reader, dataset=self.preview)
        self.status = tr("Simulation added.") if result.get("ok") else str(result.get("error", ""))

    def register_settings_sections(self, form):
        """Register only the plot canvases; controls remain declared AutoForm sections."""
        form.custom["simulator_decay"] = self.draw_decay
        form.custom["simulator_anisotropy"] = self.draw_anisotropy

    def draw_decay(self, section, model, state, width):
        """Draw cached VM or VV/VH arrays and a display-only scaled IRF overlay."""
        if self.preview is None:
            im.text_wrapped(tr("Press Simulate to preview the decay."))
            return
        if implot.begin_plot(
            tr("Simulated TCSPC decay") + "##simulator-decay", (width, section.get("height", 420))
        ):
            implot.setup_axes(tr("Time [ns]"), tr("Counts"))
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            maximum = max(float(np.max(curve.y)) for curve in self.preview)
            implot.setup_axis_limits(implot.AXIS_Y1, 0.1, max(1.0, maximum * 1.1))
            for curve in self.preview:
                implot.plot_line(curve.name, curve.x, np.where(curve.y > 0, curve.y, np.nan))
            first = self.preview[0]
            irf = resolve_irf(
                first.x,
                self.reader.instrument_response_function,
                mean=self.reader.irf_mean,
                sigma=self.reader.irf_sigma,
            )
            irf = irf * (maximum / float(np.max(irf))) if np.any(irf > 0) else irf
            implot.plot_line(tr("IRF"), first.x, np.where(irf > 0, irf, np.nan))
            implot.end_plot()

    def draw_anisotropy(self, section, model, state, width):
        """Draw the reader's ideal anisotropy on its own linear axis in both modes."""
        x, y = self.reader.simulate_aniso()
        if implot.begin_plot(
            tr("Anisotropy r(t)") + "##simulator-anisotropy", (width, section.get("height", 190))
        ):
            implot.setup_axes(tr("Time [ns]"), tr("r(t)"))
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            implot.plot_line(tr("r(t)"), x, y)
            implot.end_plot()


class SimulatorSettingsApp(ReaderSettingsApp):
    """Host the simulator frontend using the standard declaration-backed reader form."""

    def __init__(self, reader, *, context):
        self.reader = reader
        super().__init__(SimulatorSettingsModel(reader, context))

    def _used(self, name):
        """Commit the nested file field through its owner before changing tabs."""
        if not self.closed and name in {
            "simulator.decay",
            "simulator.anisotropy",
            "simulator.preview",
        }:
            for source in self.sources.values():
                if source.options.get("read_only"):
                    continue
                pending = source.state.buffers.get("path")
                if pending is None or pending == source.path:
                    continue
                source.path = pending
                # Invalid input remains editable; the existing setter reports
                # its error and retains the previously valid source.
                if source.path == pending:
                    source.state.buffers.pop("path", None)
        super()._used(name)
