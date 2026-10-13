"""The photon-simulator setup dialog, drawn by emtk from an AutoForm ``view.json``.

The dialog edits :class:`SimulationSetupModel`, the Qt-free
:class:`~chisurf.plugins.core.acq.tcspc_devices.simulation.settings_model.SimulationSettingsModel`
that the CLI serializes too, so both say the same thing about what a value means. What this
module adds is the emtk side of that model: the species grid (molecules, diffusion, per-colour
brightness, background), the two N x N kinetics rate grids and the per-species decay editor, all
declared as ``data_table`` sections in ``sim_setup_emtk.view.json`` / ``sim_decay_emtk.view.json``.

Apply (``OK``) hands :meth:`SimulationSettingsModel.to_parameters` -- the dictionary the simulator
engine consumes -- to the host, which validates it with the production engine before use.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from emtk import im, implot
from emtk.dialog_window import DialogWindow
from emtk.view_form import FormState, draw_form

from chisurf.core.support.i18n import tr
from chisurf.plugins.core.acq.tcspc_devices.simulation.settings_model import (
    SimulationSettingsModel,
)
from chisurf.plugins.emtk_layout import action_button

HERE = Path(__file__).resolve().parent
SETUP_VIEW = HERE / "sim_setup_emtk.view.json"
DECAY_VIEW = HERE / "sim_decay_emtk.view.json"

_DEFAULT_COMPONENT = [1.0, 3.2]
_COLOR_ABBR = {"green": "G", "red": "R", "yellow": "Y"}


def _number(value: Any, default: float = 0.0) -> float:
    """Return *value* as a finite float, or *default* for text that is not a number."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


class _RateTable:
    """One N x N species-interconversion grid, row -> column, as ``data_table`` hooks.

    ``source`` / ``columns_source`` / ``edited_call`` / ``editable_call`` are looked up on this
    object through a dotted name (``k_rad_table.rows``), so the two grids share one implementation.
    The matrix lives on the model as a flat row-major list (``rate[i * n + j]`` is the i -> j rate).
    """

    def __init__(self, model: SimulationSetupModel, attr: str) -> None:
        self.model, self.attr = model, attr
        self._cache: tuple[tuple, list] | None = None

    def _matrix(self) -> list[float]:
        """The stored matrix, re-shaped (not truncated) to the current species count."""
        n = self.model.species_count()
        flat = [float(v) for v in (getattr(self.model, self.attr) or [])]
        if len(flat) != n * n:
            old = math.isqrt(len(flat))
            grid = [0.0] * (n * n)
            if old * old == len(flat):
                for i in range(min(old, n)):
                    for j in range(min(old, n)):
                        grid[i * n + j] = flat[i * old + j]
            else:
                grid[: min(len(flat), n * n)] = flat[: n * n]
            flat = grid
        if getattr(self.model, self.attr) is not flat:
            setattr(self.model, self.attr, flat)
        return flat

    def rows(self) -> list[dict]:
        """One record per source state; rebuilt only when the matrix changes."""
        flat = self._matrix()
        n = self.model.species_count()
        key = (n, tuple(flat))
        if self._cache is None or self._cache[0] != key:
            records = [
                {"_i": i, "from": f"s{i}", **{f"to{j}": flat[i * n + j] for j in range(n)}}
                for i in range(n)
            ]
            self._cache = (key, records)
        return self._cache[1]

    def columns(self) -> list[dict]:
        """A row-label column, then one editable column per target state."""
        n = self.model.species_count()
        cols = [
            {
                "key": "from",
                "title": "from \\ to",
                "width": 90,
                "description": "Source species (row) of the transition.",
            }
        ]
        for j in range(n):
            cols.append(
                {
                    "key": f"to{j}",
                    "title": f"s{j}",
                    "editable": True,
                    "format": "%.4g",
                    "description": f"Rate (1/ms) of leaving the row's species for s{j}.",
                }
            )
        return cols

    def cell_editable(self, record: dict, key: str) -> bool:
        """The diagonal is not a rate: refuse it."""
        return key != f"to{record.get('_i', -1)}"

    def edited(self, record: dict, key: str, value: Any) -> None:
        """Write one rate into the matrix (clamped at zero)."""
        n = self.model.species_count()
        flat = self._matrix()
        i, j = int(record["_i"]), int(key[2:])
        if i == j or not (0 <= i < n and 0 <= j < n):
            return
        flat[i * n + j] = max(_number(value, flat[i * n + j]), 0.0)
        record[key] = flat[i * n + j]
        self._cache = ((n, tuple(flat)), self._cache[1] if self._cache else [])


@dataclass
class SimulationSetupModel(SimulationSettingsModel):
    """The simulator settings plus the table sources the emtk dialog binds.

    Attributes
    ----------
    selected_species : int
        Row last selected in the species grid; the *Decay...* button opens there.
    status : str
        Result of the last load / save.
    show_json : bool
        Whether the serialized parameters are shown under the form.
    """

    def __post_init__(self) -> None:
        """Create the non-field state (caches, hooks, the two rate grids)."""
        self.selected_species = 0
        self.status = ""
        self.show_json = False
        self._hooks: dict[str, Callable[..., None]] = {}
        self._species_cache: tuple[tuple, list] | None = None
        self.k_rad_table = _RateTable(self, "k_rad")
        self.k_nrad_table = _RateTable(self, "k_nrad")

    # ---- hooks the dialog installs ----------------------------------------------------
    def bind(self, **hooks: Callable[..., None]) -> None:
        """Install the dialog's ``open_decay`` / ``load`` / ``save`` callbacks."""
        self._hooks.update(hooks)

    def apply_parameters(self, params: dict[str, Any]) -> None:
        """Load a parameter dictionary, keeping the dialog's hooks."""
        own = (self._hooks, self.k_rad_table, self.k_nrad_table)
        super().apply_parameters(params)
        self._hooks, self.k_rad_table, self.k_nrad_table = own
        self.selected_species = min(self.selected_species, self.species_count() - 1)
        self.touched()

    def touched(self) -> None:
        """Forget cached table records after a value changed behind the tables' back."""
        self._species_cache = None
        for table in (self.k_rad_table, self.k_nrad_table):
            table._cache = None

    # ---- sizes ------------------------------------------------------------------------
    def species_count(self) -> int:
        """The number of species, at least one."""
        return max(1, int(self.n_species or 1))

    def sync_sizes(self) -> None:
        """Pad every per-species list to the species count (never wrap around)."""
        n = self.species_count()
        self.species_M = (list(self.species_M) + [50.0] * n)[: max(n, len(self.species_M))]
        self.species_D = (list(self.species_D) + [3.0] * n)[: max(n, len(self.species_D))]
        q = [float(v) for v in self.species_q]
        q += [0.0] * max(0, n * 6 - len(q))
        self.species_q = q
        lifetimes = list(self.decay_lifetimes or [])
        while len(lifetimes) < n:
            lifetimes.append([list(_DEFAULT_COMPONENT)])
        self.decay_lifetimes = lifetimes
        files = list(self.decay_pattern_files or [])
        files += [""] * max(0, n - len(files))
        self.decay_pattern_files = files
        for table in (self.k_rad_table, self.k_nrad_table):
            table._matrix()

    def species_changed(self, _value: Any = None) -> None:
        """React to the species spin: re-size everything that follows it."""
        self.selected_species = min(self.selected_species, self.species_count() - 1)
        self.sync_sizes()
        self.touched()

    def to_parameters(self) -> dict[str, Any]:
        """Serialize after re-sizing the per-species lists to the species count."""
        self.sync_sizes()
        return super().to_parameters()

    # ---- species grid -----------------------------------------------------------------
    def _q_columns(self) -> list[tuple[str, int, str]]:
        """``(colour, slot, header)`` of every brightness column of an enabled colour."""
        out = []
        for color in self.enabled_colors():
            base = self._CHANNEL_COLORS.index(color) * 2
            for k, mark in enumerate(("∥", "⊥")):
                out.append((color, base + k, f"{_COLOR_ABBR[color]} {mark}"))
        return out

    def species_columns(self) -> list[dict]:
        """Columns of the species grid: M, D, the enabled colours' q, and the decay cell."""
        cols: list[dict] = [
            {"key": "species", "title": "#", "width": 44, "description": "Species number."},
            {
                "key": "M",
                "title": "M",
                "editable": True,
                "format": "%.6g",
                "description": "Molecules (mean number in the box) for this species.",
            },
            {
                "key": "D",
                "title": "D",
                "editable": True,
                "format": "%.6g",
                "description": "Diffusion coefficient (µm²/ms) for this species.",
            },
        ]
        for color, slot, header in self._q_columns():
            pol = "parallel" if slot % 2 == 0 else "perpendicular"
            cols.append(
                {
                    "key": f"q{slot}",
                    "title": header,
                    "editable": True,
                    "format": "%.6g",
                    "description": f"{color.capitalize()} {pol} brightness q (the BG row: background rate).",
                }
            )
        cols.append(
            {
                "key": "decay",
                "title": "Decay",
                "display": "link",
                "width": 120,
                "description": "This species' lifetimes. Double-click to edit its lifetime spectrum, decay pattern and IRF.",
            }
        )
        return cols

    def _decay_label(self, i: int) -> str:
        """A one-line summary of species *i*'s decay for its grid cell."""
        path = (
            (self.decay_pattern_files or [""] * (i + 1))[i]
            if i < len(self.decay_pattern_files or [])
            else ""
        )
        if path:
            return Path(str(path)).name
        spectrum = self.decay_lifetimes[i] if i < len(self.decay_lifetimes) else []
        taus = []
        for entry in spectrum:
            tau = entry[1] if isinstance(entry, (list, tuple)) and len(entry) >= 2 else entry
            taus.append(f"{_number(tau):g}")
        return ("τ " + ", ".join(taus) + " ns") if taus else "…"

    def _bg_name(self, slot: int) -> str:
        """Model attribute holding the background rate of brightness slot *slot*."""
        color = self._CHANNEL_COLORS[slot // 2]
        return f"bg_{color}_{'p' if slot % 2 == 0 else 's'}"

    def _species_token(self) -> tuple:
        """Everything a species-grid record shows, to notice a change made elsewhere."""
        return (
            self.species_count(),
            tuple(self.enabled_colors()),
            tuple(self.species_M),
            tuple(self.species_D),
            tuple(self.species_q),
            tuple(getattr(self, self._bg_name(s)) for _c, s, _h in self._q_columns()),
            repr(self.decay_lifetimes),
            tuple(self.decay_pattern_files),
        )

    def species_rows(self) -> list[dict]:
        """One record per species, then the background row; rebuilt only on a change."""
        self.sync_sizes()
        token = self._species_token()
        if self._species_cache is not None and self._species_cache[0] == token:
            return self._species_cache[1]
        slots = [slot for _c, slot, _h in self._q_columns()]
        rows = []
        for i in range(self.species_count()):
            row = {
                "_i": i,
                "species": str(i + 1),
                "M": float(self.species_M[i]),
                "D": float(self.species_D[i]),
                "decay": self._decay_label(i),
            }
            row.update({f"q{s}": float(self.species_q[i * 6 + s]) for s in slots})
            rows.append(row)
        bg = {"_i": -1, "species": "BG", "M": None, "D": None, "decay": None}
        bg.update({f"q{s}": float(getattr(self, self._bg_name(s))) for s in slots})
        rows.append(bg)
        self._species_cache = (token, rows)
        return rows

    def species_cell_editable(self, record: dict, key: str) -> bool:
        """The background row has no molecules or diffusion to edit."""
        return record.get("_i", -1) >= 0 or key.startswith("q")

    def species_edited(self, record: dict, key: str, value: Any) -> None:
        """Write one edited cell of the species grid back into the model."""
        i = int(record["_i"])
        if key.startswith("q") and key[1:].isdigit():
            slot = int(key[1:])
            if i < 0:
                setattr(self, self._bg_name(slot), max(_number(value), 0.0))
            else:
                self.species_q[i * 6 + slot] = max(_number(value), 0.0)
        elif i >= 0 and key == "M":
            self.species_M[i] = max(_number(value), 0.0)
        elif i >= 0 and key == "D":
            self.species_D[i] = max(_number(value), 0.0)
        else:
            return
        # The record already shows the typed value; keep it, and keep the table bound.
        self._species_cache = (
            (self._species_token(), self._species_cache[1]) if (self._species_cache) else None
        )

    def species_selected(self, record: dict | None) -> None:
        """Remember the selected species for the *Decay...* button."""
        if record is not None and int(record.get("_i", -1)) >= 0:
            self.selected_species = int(record["_i"])

    def species_cell_activated(self, record: dict, key: str) -> None:
        """A double click on the Decay cell opens that species' decay editor."""
        if key == "decay" and int(record.get("_i", -1)) >= 0:
            self.selected_species = int(record["_i"])
            self.open_decay_dialog()

    # ---- buttons ----------------------------------------------------------------------
    def open_decay_dialog(self, species: int | None = None) -> None:
        """Open the decay editor at *species* (default: the selected row)."""
        hook = self._hooks.get("open_decay")
        if hook is not None:
            hook(self.selected_species if species is None else int(species))

    def load_json(self) -> None:
        """Ask the host for a JSON file and load it."""
        hook = self._hooks.get("load")
        if hook is not None:
            hook()

    def save_json(self) -> None:
        """Ask the host for a path and save the parameters there."""
        hook = self._hooks.get("save")
        if hook is not None:
            hook()

    def view_json(self) -> None:
        """Toggle the read-only parameter JSON under the form."""
        self.show_json = not self.show_json

    def load_json_file(self, path: str | Path) -> bool:
        """Load parameters from *path*; the status line says what went wrong."""
        try:
            params = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(params, dict):
                raise ValueError("a simulation settings file holds one JSON object")
            self.apply_parameters(params)
        except (OSError, ValueError) as exc:
            self.status = f"Could not load {Path(path).name}: {exc}"
            return False
        self.status = f"Loaded {Path(path).name}."
        return True

    def save_json_file(self, path: str | Path) -> bool:
        """Save the current parameters as JSON to *path*."""
        try:
            Path(path).write_text(json.dumps(self.to_parameters(), indent=2), encoding="utf-8")
        except OSError as exc:
            self.status = f"Could not save {Path(path).name}: {exc}"
            return False
        self.status = f"Saved {Path(path).name}."
        return True


class DecayEditModel:
    """Per-species decay editing state for the decay dialog (written back on OK).

    The edits are local copies: *Cancel* discards them, *OK* writes the
    lifetime spectra, pattern files and the shared Gaussian IRF width to the setup model.
    """

    def __init__(self, setup: SimulationSetupModel, start: int = 0) -> None:
        setup.sync_sizes()
        self.setup = setup
        n = setup.species_count()
        self.lifetimes = [self._pairs(setup.decay_lifetimes[i]) for i in range(n)]
        self.patterns = [str(setup.decay_pattern_files[i] or "") for i in range(n)]
        self.irf_fwhm_ns = float(setup.irf_fwhm_ns or 0.0)
        self.cur = max(0, min(int(start), n - 1))
        self.species = self.cur + 1
        self.pattern_path = self.patterns[self.cur]
        self.selected = -1
        self._rows: list[dict] | None = None

    @staticmethod
    def _pairs(spec: Any) -> list[list[float]]:
        """``[[amplitude, lifetime], ...]`` from pairs or bare lifetimes."""
        out = []
        for entry in spec or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                out.append([float(entry[0]), float(entry[1])])
            else:
                out.append([1.0, float(entry)])
        return out or [list(_DEFAULT_COMPONENT)]

    # ---- the per-species switch --------------------------------------------------------
    def _pull(self) -> None:
        """Keep the pattern field of the species being left."""
        self.patterns[self.cur] = str(self.pattern_path or "")

    def species_switched(self, _value: Any = None) -> None:
        """Move to the species the spin shows (clamped), keeping the one left."""
        self._pull()
        self.cur = max(0, min(int(self.species) - 1, len(self.lifetimes) - 1))
        self.species = self.cur + 1
        self.pattern_path = self.patterns[self.cur]
        self.selected, self._rows = -1, None

    # ---- spectrum table ---------------------------------------------------------------
    def spectrum_rows(self) -> list[dict]:
        """The current species' components as editable records."""
        if self._rows is None:
            self._rows = [
                {"_i": i, "amplitude": a, "lifetime": t}
                for i, (a, t) in enumerate(self.lifetimes[self.cur])
            ]
        return self._rows

    def spectrum_edited(self, record: dict, key: str, value: Any) -> None:
        """Write an edited amplitude or lifetime into the species' spectrum."""
        pair = self.lifetimes[self.cur][int(record["_i"])]
        pair[0 if key == "amplitude" else 1] = _number(value, pair[0 if key == "amplitude" else 1])

    def spectrum_selected(self, record: dict | None) -> None:
        """Remember the selected component for *Remove*."""
        self.selected = -1 if record is None else int(record["_i"])

    def add_component(self) -> None:
        """Append a component (amplitude 1, lifetime 1 ns)."""
        self.lifetimes[self.cur].append([1.0, 1.0])
        self._rows = None

    def remove_component(self) -> None:
        """Remove the selected component, or the last; one always remains."""
        spectrum = self.lifetimes[self.cur]
        if len(spectrum) > 1:
            spectrum.pop(self.selected if 0 <= self.selected < len(spectrum) else -1)
        self.selected, self._rows = -1, None

    def clear_pattern(self) -> None:
        """Forget the decay-pattern file."""
        self.pattern_path = ""

    # ---- preview ----------------------------------------------------------------------
    def preview(self) -> tuple[Any, Any]:
        """``(time_ns, counts)`` of the current species on the simulator's TAC axis."""
        import numpy as np

        from chisurf.core.fluorescence.decay import synthetic_decay
        from chisurf.plugins.core.acq.tcspc_devices.simulation.core.algorithms import (
            _gaussian_irf_pattern,
        )

        s = self.setup
        n_bins = int(max(8, min(int(s.n_tac_channels), 4096)))
        dt = float(s.tac_dt)
        path = Path(str(self.pattern_path)) if self.pattern_path else None
        if path is not None and path.is_file():
            try:
                arr = np.load(path) if path.suffix.lower() == ".npy" else np.loadtxt(path)
                y = np.asarray(arr, dtype=float).ravel()[:n_bins]
                return np.arange(y.size) * dt, y
            except (OSError, ValueError):
                pass
        taus = [t for a, t in self.lifetimes[self.cur] if t > 0.0]
        amps = [a for a, t in self.lifetimes[self.cur] if t > 0.0]
        if not taus:
            return np.arange(n_bins) * dt, np.zeros(n_bins)
        irf = None
        if self.irf_fwhm_ns > 0:
            irf = _gaussian_irf_pattern(n_bins, dt, self.irf_fwhm_ns, 2.0 * self.irf_fwhm_ns)
        y = synthetic_decay(
            n_bins, taus, amplitudes=amps, bin_width=dt, irf=irf, allow_rise_terms=True
        )
        return np.arange(n_bins) * dt, np.asarray(y, dtype=float)

    def commit(self) -> None:
        """OK: write every species' decay and the shared IRF width to the setup model."""
        self._pull()
        self.setup.decay_lifetimes = [[list(p) for p in spec] for spec in self.lifetimes]
        self.setup.decay_pattern_files = list(self.patterns)
        self.setup.irf_fwhm_ns = float(self.irf_fwhm_ns)
        self.setup.touched()


class SimulationSetupDialog:
    """Modal-style emtk dialog around :class:`SimulationSetupModel`.

    Parameters
    ----------
    params : dict, optional
        The ``simulation_params`` dictionary to start from.
    on_apply : callable
        ``on_apply(params)`` after *OK*: the full dictionary the simulator consumes.
    request_file : callable, optional
        ``request_file(kind)`` with ``"load"`` or ``"save"``: the host opens its file chooser
        and answers with :meth:`file_chosen`. Without one, load / save do nothing.

    Attributes
    ----------
    rects : dict
        Named control rectangles of the last frame (form controls, ``sim_ok``, ``sim_cancel``,
        the tables by source name), for tests and the guided tour.
    """

    TITLE = "Simulation Setup"

    def __init__(
        self,
        params: dict[str, Any] | None,
        on_apply: Callable[[dict[str, Any]], None],
        request_file: Callable[[str], None] | None = None,
    ) -> None:
        self.model = SimulationSetupModel.from_parameters(params)
        self.model.bind(open_decay=self.open_decay, load=self._load, save=self._save)
        self.on_apply = on_apply
        self.request_file = request_file
        self.spec = json.loads(SETUP_VIEW.read_text(encoding="utf-8"))
        self.decay_spec = json.loads(DECAY_VIEW.read_text(encoding="utf-8"))
        self.form = FormState()
        self.form.custom["sim_json_view"] = self._draw_json
        self.decay_form = FormState()
        self.decay_form.custom["sim_decay_preview"] = self._draw_preview
        self.rects: dict[str, tuple] = {}
        self.window = DialogWindow(tr(self.TITLE), size=(820, 760), key="acq_sim_setup")
        self.decay_window = DialogWindow(tr("Decay settings"), size=(600, 640), key="acq_sim_decay")
        self.decay: DecayEditModel | None = None
        self._json_text = ""

    # ---- lifecycle --------------------------------------------------------------------
    @property
    def open(self) -> bool:
        """Whether the dialog is showing."""
        return self.window.open

    def show(self) -> None:
        """Show the dialog."""
        self.window.show()

    def apply(self) -> dict[str, Any]:
        """*OK*: hand the parameters to the host and close."""
        params = self.model.to_parameters()
        if self.on_apply(params) is False:
            self.model.status = (
                "The simulator engine rejected these settings (see the status line)."
            )
            return params
        self.model.status = ""
        self.window.hide()
        self.decay_window.hide()
        return params

    def cancel(self) -> None:
        """*Cancel*: close without applying."""
        self.window.hide()
        self.decay_window.hide()

    # ---- decay editor -----------------------------------------------------------------
    def open_decay(self, species: int = 0) -> None:
        """Open the decay editor on *species*."""
        self.model.sync_sizes()
        self.decay = DecayEditModel(self.model, species)
        self.decay_window.show()

    def decay_ok(self) -> None:
        """Write the decay edits back and close the decay editor."""
        if self.decay is not None:
            self.decay.commit()
        self.decay_window.hide()

    def decay_cancel(self) -> None:
        """Close the decay editor, discarding its edits."""
        self.decay_window.hide()

    # ---- file hooks -------------------------------------------------------------------
    def _load(self) -> None:
        if self.request_file is not None:
            self.request_file("load")

    def _save(self) -> None:
        if self.request_file is not None:
            self.request_file("save")

    def file_chosen(self, kind: str, path: str | Path) -> None:
        """The host's file chooser answered for a ``load`` or ``save`` request."""
        if kind == "load":
            self.model.load_json_file(path)
        else:
            self.model.save_json_file(path)

    # ---- drawing ----------------------------------------------------------------------
    def _draw_json(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """The serialized parameters, read-only, while *View JSON* is on."""
        if not model.show_json:
            return
        self._json_text = json.dumps(model.to_parameters(), indent=2)
        im.input_text_multiline("##sim_json_view", self._json_text, (0.0, 220.0))
        state.rects["sim_json_view"] = im.get_item_rect()

    def _draw_preview(self, section: dict, model: Any, state: FormState, width: float) -> None:
        """Live decay of the species being edited."""
        x, y = model.preview()
        top = im.get_cursor_screen_pos()
        if implot.begin_plot(tr("Decay preview") + "##sim_decay_preview", (width, 200.0)):
            implot.setup_axes(tr("Micro-time (ns)"), tr("Counts"))
            positive = y[y > 0]
            if positive.size:
                implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                implot.setup_axis_limits(
                    implot.AXIS_Y1, float(positive.min()), float(positive.max()) * 1.2
                )
            import numpy as np

            implot.plot_line(tr("Decay"), x, np.where(y > 0, y, np.nan))
            implot.end_plot()
        state.rects["sim_decay_preview"] = (top[0], top[1], width, 200.0)

    def _buttons(self, ok: str, cancel: str, ok_tip: str, cancel_tip: str) -> tuple[bool, bool]:
        """The OK / Cancel row; returns which was pressed."""
        pressed_ok = im.button(tr("OK") + f"##{ok}")
        im.set_item_tooltip(tr(ok_tip))
        self.rects[ok] = im.get_item_rect()
        im.same_line()
        pressed_cancel = action_button("cancel", id=cancel, tooltip=tr(cancel_tip))
        self.rects[cancel] = im.get_item_rect()
        return pressed_ok, pressed_cancel

    def draw(self, box: tuple) -> None:
        """Draw the dialog (and the decay editor above it) over *box*."""
        if self.window.open:
            close = self.window.begin(box)
            avail = im.get_content_region_avail()
            foot = 40.0 if not self.model.status else 62.0
            im.begin_child("##sim_setup_body", (0.0, max(avail[1] - foot, 80.0)))
            draw_form(self.spec, self.model, self.form, titles=True)
            im.end_child()
            if self.model.status:
                im.text_wrapped(tr(self.model.status))
            ok, cancel = self._buttons(
                "sim_ok",
                "sim_cancel",
                "Validate these settings with the simulator engine and use them for the next run.",
                "Close without changing the simulation settings.",
            )
            self.rects.update(self.form.rects)
            self.window.end()
            if ok:
                self.apply()
            elif cancel or close == "close":
                self.cancel()
        if self.decay_window.open and self.decay is not None:
            close = self.decay_window.begin(box)
            avail = im.get_content_region_avail()
            im.begin_child("##sim_decay_body", (0.0, max(avail[1] - 40.0, 80.0)))
            draw_form(self.decay_spec, self.decay, self.decay_form, titles=True)
            im.end_child()
            ok, cancel = self._buttons(
                "decay_ok",
                "decay_cancel",
                "Write the edited decays of all species back to the simulation setup.",
                "Close the decay editor and discard its edits.",
            )
            self.rects.update(self.decay_form.rects)
            self.decay_window.end()
            if ok:
                self.decay_ok()
            elif cancel or close == "close":
                self.decay_cancel()
