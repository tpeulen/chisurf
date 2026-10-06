"""The ProteinMC pages of a fit window: trajectory curves, structure, distance network.

Pages are Qt-free (:class:`~chisurf.gui.plots.plotbase.Plot`): the fit window's
emtk surface draws them, and their settings are AutoForm specs beside this
module (``proteinmc_*_settings.view.json``) drawn in the *Plot settings* dock.
Playback is driven by the frames that draw the page or its settings
(:meth:`_FramePlayback.tick`), not by a timer.
"""

import json
import time

import numpy as np

import chisurf as cs
import chisurf.core.settings
from chisurf.emtk.chimol_view import ChimolView
from chisurf.gui import chiplot as cp
from chisurf.gui.plots.plotbase import Plot

colors = cs.core.settings.gui["plot"]["colors"]
color_scheme = cs.core.settings.colors


_REPRESENTATIONS = ("cartoon", "ca_trace", "atoms")

#: Seconds between two playback steps.
PLAY_INTERVAL = 0.12


class ProteinMCPlot(Plot):
    """RMSD, dRMSD, energy and labeling chi2r of a ProteinMC trajectory, two by two."""

    name = "Trajectory-Plot"
    settings_view = "proteinmc_traces_settings.view.json"

    def __init__(self, fit, *args, **kwargs):
        super().__init__(fit=fit, *args, **kwargs)
        self.trajectory = fit.model
        self.source = fit.model

        p1, p2, p3, p4 = (cp.Panel() for _ in range(4))
        self.rmsd_plot = p1
        self.drmsd_plot = p2
        self.energy_plot = p3
        self.fret_plot = p4
        #: Panel -> shown, in grid order (the settings' toggles).
        self._shown = {id(p): True for p in (p1, p2, p3, p4)}
        self._grid_key = None
        self._grid_body = None
        from chisurf.gui.plots.emtk_page import PanelItem

        self.panel_items = [PanelItem(p, p.control()) for p in (p1, p2, p3, p4)]

        self.rmsd_plot.set_title("RMSD")
        self.drmsd_plot.set_title("dRMSD")
        self.energy_plot.set_title("Energy")
        self.fret_plot.set_title("FRET")

        lw = cs.core.settings.gui["plot"]["line_width"]
        self.rmsd_curve = self.rmsd_plot.line(
            [0.0], [0.0], pen=colors["irf"], width=lw, name="rmsd"
        )
        self.drmsd_curve = self.drmsd_plot.line(
            [0.0], [0.0], pen=colors["data"], width=lw, name="drmsd"
        )
        self.energy_curve = self.energy_plot.line(
            [0.0], [0.0], pen=colors["model"], width=lw, name="energy"
        )
        self.fret_curve = self.fret_plot.line(
            [0.0], [0.0], pen=colors["model"], width=lw, name="fret"
        )
        # A movable=False "current frame" cursor on each panel.
        self.frame_lines = []
        for plot_item in (self.rmsd_plot, self.drmsd_plot, self.energy_plot, self.fret_plot):
            line = plot_item.vline(0, movable=False, pen=cp.to_pen((255, 255, 0, 180), width=1))
            self.frame_lines.append(line)

        try:
            cs.logging.info(
                "ProteinMCPlot: initialized for fit '%s' with model '%s'",
                getattr(fit, "name", "unknown"),
                getattr(fit.model.__class__, "name", fit.model.__class__.__name__),
            )
        except Exception:
            pass

    # -- settings: which curves are shown ---------------------------------
    def _is_shown(self, panel) -> bool:
        return bool(self._shown.get(id(panel), True))

    def _set_shown(self, panel, shown: bool) -> None:
        self._shown[id(panel)] = bool(shown)
        self.request_redraw()

    show_rmsd = property(lambda self: self._is_shown(self.rmsd_plot),
                         lambda self, v: self._set_shown(self.rmsd_plot, v),
                         doc="Whether the RMSD panel is shown.")
    show_drmsd = property(lambda self: self._is_shown(self.drmsd_plot),
                          lambda self, v: self._set_shown(self.drmsd_plot, v),
                          doc="Whether the dRMSD panel is shown.")
    show_energy = property(lambda self: self._is_shown(self.energy_plot),
                           lambda self, v: self._set_shown(self.energy_plot, v),
                           doc="Whether the energy panel is shown.")
    show_fret = property(lambda self: self._is_shown(self.fret_plot),
                         lambda self, v: self._set_shown(self.fret_plot, v),
                         doc="Whether the labeling (FRET) panel is shown.")

    def autoscale(self) -> None:
        """Fit every panel's axes to its curve."""
        for panel in (self.rmsd_plot, self.drmsd_plot, self.energy_plot, self.fret_plot):
            try:
                panel.autoscale()
            except Exception:
                pass
        self.request_redraw()

    def get_settings_state(self) -> dict:
        """The shown curves, for the project file (the old controller's keys)."""
        return {
            "show_rmsd": self.show_rmsd,
            "show_drmsd": self.show_drmsd,
            "show_energy": self.show_energy,
            "show_fret": self.show_fret,
        }

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if not isinstance(state, dict):
            return
        for key in ("show_rmsd", "show_drmsd", "show_energy", "show_fret"):
            if key in state:
                setattr(self, key, bool(state[key]))

    # -- page --------------------------------------------------------------
    def _grid(self):
        """The shown series panels, two to a row; rebuilt when the shown set changes."""
        shown = [item for item in self.panel_items if self._is_shown(item.plot)]
        for item in self.panel_items:
            if item not in shown:
                item.box = None  # a hidden panel must not answer a right click
        key = tuple(id(item) for item in shown)
        if key != self._grid_key:
            self._grid_key = key
            self._grid_body = None
            if shown:
                from emtk.flags import Axis
                from emtk.widgets.pane_stack import PaneStack

                rows = [shown[k:k + 2] for k in range(0, len(shown), 2)]
                stacks = [r[0] if len(r) == 1 else PaneStack(r, axis=Axis.X) for r in rows]
                self._grid_body = stacks[0] if len(stacks) == 1 else PaneStack(stacks, axis=Axis.Y)
        return self._grid_body

    def emtk_draw(self, box) -> None:
        """The shown series panels filling the page, or a line saying none is shown."""
        from emtk import im

        grid = self._grid()
        if grid is None:
            im.text_disabled("No trajectory curve is shown; tick one in Plot settings.")
            return
        width, height = im.get_content_region_avail()
        im.host_control("##proteinmc-traces", grid, (width, height))

    def update_all(self, *args, **kwargs):

        try:
            rmsd = np.array(self.trajectory.rmsd)
            drmsd = np.array(self.trajectory.drmsd)
            energy = np.array(self.trajectory.energy)
            energy_fret = np.array(self.trajectory.chi2r)
        except Exception as e:
            cs.logging.warning(f"ProteinMCPlot.update_all: failed to read trajectory arrays: {e}")
            return

        x = list(range(len(rmsd))) if rmsd.size else []

        self.rmsd_curve.set_data(x, rmsd)
        self.drmsd_curve.set_data(x, drmsd)
        self.energy_curve.set_data(x, energy)
        self.fret_curve.set_data(x, energy_fret)
        frame_index = int(getattr(self.trajectory, "current_frame_index", 0))
        for line in self.frame_lines:
            line.set_value(frame_index)

        try:
            cs.logging.info(
                "ProteinMCPlot.update_all: updated trajectory curves with %d points", len(x)
            )
        except Exception:
            pass

    def update(self, *args, **kwargs):
        """Refresh ProteinMC trajectory curves."""
        super().update(*args, **kwargs)
        self.update_all(*args, **kwargs)


class _FramePlayback:
    """Frame navigation and playback over the ProteinMC model's shared frame.

    The frame is the model's (``current_frame_index``, ``set_current_frame``,
    ``frame_count``), shared by every ProteinMC page. Playback is a flag and a
    clock: each frame that draws the page or its settings calls :meth:`tick`,
    which steps once :data:`PLAY_INTERVAL` has passed and asks for the next
    frame while playing.
    """

    model = None
    playing = False
    _step = 1
    _last_tick = 0.0
    _local_frame = 0

    # -- the frame ---------------------------------------------------------
    def frame_count(self) -> int:
        """How many frames the trajectory has."""
        return int(getattr(self.model, "frame_count", 0) or 0) if self.model is not None else 0

    @property
    def frame(self) -> int:
        """The shared current frame."""
        model = self.model
        if model is not None and hasattr(model, "current_frame_index"):
            return int(getattr(model, "current_frame_index", 0) or 0)
        return int(self._local_frame)

    @frame.setter
    def frame(self, value: int) -> None:
        last = max(0, self.frame_count() - 1)
        value = max(0, min(int(value), last))
        model = self.model
        if model is not None and hasattr(model, "set_current_frame"):
            model.set_current_frame(value)
        else:
            self._local_frame = value
        self._frame_changed(value)
        self.request_redraw()

    def _frame_changed(self, value: int) -> None:
        """Follow a new frame (pages override)."""

    @property
    def step(self) -> int:
        """Frames per playback step."""
        return int(self._step)

    @step.setter
    def step(self, value: int) -> None:
        self._step = max(1, int(value))

    def bounds(self, name: str):
        """The frame spin runs over the trajectory (the form asks for it)."""
        if name == "frame":
            return (0, max(0, self.frame_count() - 1))
        return None

    def frame_total_text(self) -> str:
        """The ``/ N`` beside the frame field: the last frame index."""
        return f"/ {max(0, self.frame_count() - 1)}"

    # -- actions (the settings' buttons) ------------------------------------
    def goto_first(self) -> None:
        """Go to the first frame."""
        self.frame = 0

    def goto_prev(self) -> None:
        """Back by the step size."""
        self.frame = max(0, self.frame - self.step)

    def goto_next(self) -> None:
        """Forward by the step size, wrapping past the last frame."""
        total = self.frame_count()
        if total <= 1:
            self.frame = 0
            return
        self.frame = (self.frame + self.step) % total

    def goto_last(self) -> None:
        """Go to the last frame."""
        self.frame = max(0, self.frame_count() - 1)

    def play(self) -> None:
        """Start playback."""
        self.playing = True
        self._last_tick = time.monotonic()
        self.request_redraw()

    def pause(self) -> None:
        """Pause playback at the current frame."""
        self.playing = False

    def stop(self) -> None:
        """Stop playback and return to the first frame."""
        self.playing = False
        self.goto_first()

    def tick(self, now: float | None = None) -> None:
        """Step the playback if its interval has passed; keep frames coming while playing."""
        if not self.playing:
            return
        now = time.monotonic() if now is None else now
        if now - self._last_tick >= PLAY_INTERVAL:
            self._last_tick = now
            self.goto_next()
        self.request_redraw()

    def request_redraw(self) -> None:
        """Playback moves the page and the frame field in the settings dock."""
        Plot.request_redraw(self)
        self.request_settings_redraw()

    def draw_settings(self) -> None:
        self.tick()
        Plot.draw_settings(self)

    def _playback_state(self) -> dict:
        return {"frame": int(self.frame), "step": int(self.step), "playing": bool(self.playing)}

    def _restore_playback(self, state: dict) -> None:
        if "step" in state:
            try:
                self.step = int(state["step"])
            except (TypeError, ValueError):
                pass
        if "frame" in state:
            try:
                self.frame = int(state["frame"])
            except (TypeError, ValueError):
                pass
        if state.get("playing"):
            self.play()


class ProteinMCStructurePlot(_FramePlayback, Plot):
    """Chimol structure plot for live ProteinMC trajectories."""

    name = "Structure"
    settings_view = "proteinmc_structure_settings.view.json"

    def __init__(self, fit, *args, **kwargs):
        """Create a Chimol-backed ProteinMC structure plot."""
        super().__init__(fit=fit, *args, **kwargs)
        self.model = fit.model
        self.object_id = None
        self._representation = "atoms"
        # chimol's offscreen renderer, drawn on the fit window's emtk surface
        # (emtk_draw). Started when first asked for; ``viewer`` is None where it
        # cannot run (no WebGPU adapter). ChiSurf coordinates are in Angstrom;
        # chimol's default scale of 10 assumes nanometres, so 1.0.
        self.chimol = ChimolView(
            viewer_options={"representation_mode": "atoms", "scale_factor": 1.0}
        )
        self.update_all()

    @property
    def viewer(self):
        """chimol's viewer, or ``None`` when chimol cannot run here."""
        return self.chimol.viewer

    def frame_count(self) -> int:
        """Frames of the model, else of the viewer's object."""
        total = super().frame_count()
        if total or self.model is not None and hasattr(self.model, "frame_count"):
            return total
        viewer = self.viewer
        if viewer is None:
            return 0
        try:
            return int(viewer.get_frame_count(self.object_id))
        except Exception:
            return 0

    def _frame_changed(self, value: int) -> None:
        viewer = self.viewer
        if viewer is None:
            return
        try:
            viewer.set_active_frame(int(value), object_id=self.object_id)
        except Exception:
            try:
                viewer.set_current_frame(int(value))
            except Exception:
                pass

    @property
    def representation(self) -> str:
        """How the structure is drawn: one of ``cartoon``, ``ca_trace``, ``atoms``."""
        return self._representation

    @representation.setter
    def representation(self, mode: str) -> None:
        if mode in _REPRESENTATIONS:
            self._representation = str(mode)
            self._apply_representation()
            self.request_redraw()

    def _apply_representation(self) -> None:
        viewer = self.viewer
        if viewer is None or self.object_id is None:
            return
        try:
            viewer.set_representation(self._representation, object_id=self.object_id)
        except Exception:
            try:
                viewer.set_representation(self._representation)
            except Exception:
                pass

    def get_settings_state(self) -> dict:
        """Frame, step, representation and playback (the old controller's keys)."""
        return dict(self._playback_state(), representation=self.representation)

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if not isinstance(state, dict):
            return
        representation = state.get("representation")
        if isinstance(representation, str) and representation:
            self.representation = representation
        self._restore_playback(state)

    def emtk_draw(self, box) -> None:
        """The molecular view, filling the page (inside the surface's emtk frame)."""
        from emtk import im

        self.tick()
        if not self.chimol.draw():
            im.text_wrapped(
                f"The molecular viewer could not start here ({self.chimol.error}). The "
                "trajectory and distance plots are on the other tabs."
            )

    def close(self):
        """Stop chimol with the page."""
        self.playing = False
        self.chimol.close()
        return super().close()

    def update_all(self, *args, **kwargs):
        """Refresh the structure display from the ProteinMC model widget."""
        if self.viewer is None:
            return
        # The sampler's structure once it exists, else the starting structure
        # (a restored, not-yet-sampled project). A new structure object -- a
        # reloaded starting file, a fresh run -- replaces the displayed one.
        structure = getattr(self.model, "proteinmc_structure", None)
        if structure is None:
            structure = getattr(self.model, "structure", None)
        frames = getattr(self.model, "trajectory_frames", None)
        if structure is None and not frames:
            return
        if self.object_id is not None and structure is not getattr(self, "_shown_structure", None):
            self.viewer.remove_object(self.object_id)
            self.object_id = None
        if self.object_id is None:
            self._shown_structure = structure
            if structure is not None:
                self.object_id = self.viewer.add_structure(structure, name="ProteinMC")
            else:
                self.object_id = self.viewer.add_coordinates(
                    np.asarray(frames[0], dtype=float), name="ProteinMC"
                )
            self.chimol.sync_panel()
        if frames:
            arr = np.asarray(frames, dtype=float)
            active_frame = min(
                max(0, int(getattr(self.model, "current_frame_index", len(arr) - 1))), len(arr) - 1
            )
            try:
                self.viewer.set_frames(
                    arr,
                    object_id=self.object_id,
                    active_frame=active_frame,
                )
            except TypeError:
                self.viewer.set_frames(arr, object_id=self.object_id)
                set_active_frame = getattr(self.viewer, "set_active_frame", None)
                if set_active_frame is not None:
                    set_active_frame(active_frame, object_id=self.object_id)
        self._apply_representation()

    def update(self, *args, **kwargs):
        """Refresh the Chimol structure plot."""
        super().update(*args, **kwargs)
        self.update_all(*args, **kwargs)




class ProteinMCDistanceNetworkPlot(_FramePlayback, Plot):
    """Circular FPS distance-network plot for the selected ProteinMC frame."""

    name = "Distance Network"
    settings_view = "proteinmc_network_settings.view.json"

    def __init__(self, fit, *args, **kwargs):
        """Create a circular distance-agreement plot."""
        super().__init__(fit=fit, *args, **kwargs)
        from chisurf.gui.plots.emtk_page import PanelItem

        self.model = fit.model
        self._network_cache_key = None
        self._network_edges = []
        self._network_edge_items = []
        self._network_node_positions = {}
        self._network_static_items = []
        self.plot_widget = cp.Panel()
        self.plot_widget.set_aspect_locked(True)
        self.plot_widget.set_background((20, 20, 20))
        self.plot_widget.set_axis_visible(left=False, bottom=False)
        self.panel_items = [PanelItem(self.plot_widget, self.plot_widget.control())]
        self.update_all()

    def _frame_changed(self, value: int) -> None:
        self.update_all()

    def get_settings_state(self) -> dict:
        """Frame, step and playback (the old controller's keys)."""
        return self._playback_state()

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if isinstance(state, dict):
            self._restore_playback(state)

    def emtk_draw(self, box) -> None:
        """The network panel, filling the page; playback steps here too."""
        from emtk import im

        self.tick()
        width, height = im.get_content_region_avail()
        im.host_control("##proteinmc-network", self.panel_items[0], (width, height))

    def update_all(self, *args, **kwargs):
        """Redraw network agreement for the shared current frame."""
        # Before any sampling (e.g. a freshly restored project) the network is
        # drawn on the starting structure.
        structure = getattr(self.model, "proteinmc_structure", None)
        if structure is None:
            structure = getattr(self.model, "structure", None)
        frames = getattr(self.model, "trajectory_frames", []) or []
        if not frames and structure is not None:
            xyz = getattr(structure, "xyz", None)
            if xyz is not None:
                frames = [xyz]
        # A model attribute, not a line edit: the ProteinMC editor is generated
        # from a view spec now, so the widget this used to reach into is gone.
        labeling_file = str(getattr(self.model, "labeling_file", "") or "").strip()
        if not labeling_file:
            try:
                for pot in getattr(self.model, "potential_settings", lambda: [])():
                    if pot.get("name") == "dye":
                        labeling_file = pot.get("settings", {}).get("labeling_file", "")
                        if labeling_file:
                            break
            except Exception:
                pass
        if structure is None or not frames or not labeling_file:
            self.plot_widget.clear()
            self._network_cache_key = None
            self._draw_message("No FPS network data")
            return
        cache_key = (id(structure), str(labeling_file))
        if cache_key != self._network_cache_key:
            self._build_network_cache(structure, labeling_file, cache_key)
        if not self._network_edges or not self._network_edge_items:
            return
        frame_idx = max(0, min(int(getattr(self.model, "current_frame_index", 0)), len(frames) - 1))
        xyz = np.asarray(frames[frame_idx], dtype=float)
        for edge, item in zip(self._network_edges, self._network_edge_items):
            try:
                model_distance = float(np.linalg.norm(xyz[edge["i1"]] - xyz[edge["i2"]]))
            except Exception:
                continue
            target = float(edge["target"])
            error = max(
                float(edge["error_neg"] if model_distance < target else edge["error_pos"]), 1e-12
            )
            wres = (model_distance - target) / error
            item.set_pen(cp.to_pen(_agreement_color(wres), width=1.0 + min(abs(wres), 3.0) * 0.8))

    def _build_network_cache(self, structure, labeling_file: str, cache_key) -> None:
        """Build static network graphics once for responsive playback."""
        self.plot_widget.clear()
        self._network_cache_key = cache_key
        self._network_edges = []
        self._network_edge_items = []
        self._network_node_positions = {}
        self._network_static_items = []
        try:
            payload = self._labeling_payload(labeling_file)
            nodes, edges = _network_from_labeling(structure, payload)
        except Exception as exc:
            self._draw_message(f"Cannot load network: {exc}")
            return
        if not nodes or not edges:
            self._draw_message("No distances in FPS file")
            return
        self._network_node_positions = _circle_positions(nodes)
        for edge in edges:
            p1 = self._network_node_positions.get(edge["p1"])
            p2 = self._network_node_positions.get(edge["p2"])
            if p1 is None or p2 is None:
                continue
            item = self.plot_widget.line(
                [p1[0], p2[0]], [p1[1], p2[1]], pen=(80, 80, 80, 120), width=1.0
            )
            self._network_edges.append(edge)
            self._network_edge_items.append(item)
        scatter = self.plot_widget.scatter(
            [self._network_node_positions[name][0] for name in nodes],
            [self._network_node_positions[name][1] for name in nodes],
            size=8,
            brush=(230, 230, 230),
            pen=(30, 30, 30),
        )
        self._network_static_items.append(scatter)
        for name in nodes:
            pos = self._network_node_positions[name]
            label = self.plot_widget.text(
                str(name),
                (float(pos[0] * 1.12), float(pos[1] * 1.12)),
                color=(230, 230, 230),
                anchor=(0.5, 0.5),
            )
            self._network_static_items.append(label)
        self.plot_widget.set_xlim(-1.25, 1.25, padding=0.02)
        self.plot_widget.set_ylim(-1.25, 1.25, padding=0.02)

    def _labeling_payload(self, labeling_file: str) -> dict:
        """The model's labelling definition; the file only when it has none.

        A restored project carries the payload, so drawing must not depend on
        the original labelling file still being on disk.
        """
        payload = getattr(self.model, "_labeling_payload", None)
        if callable(payload):
            loaded = payload()
            if loaded:
                return loaded
        return _load_labeling_payload(labeling_file)

    def _draw_message(self, message: str) -> None:
        self.plot_widget.text(
            str(message),
            (0.0, 0.0),
            color=(230, 230, 230),
            anchor=(0.5, 0.5),
        )
        self.plot_widget.set_xlim(-1, 1, padding=0.02)
        self.plot_widget.set_ylim(-1, 1, padding=0.02)

    def update(self, *args, **kwargs):
        """Refresh the circular network plot."""
        super().update(*args, **kwargs)
        self.update_all(*args, **kwargs)




def _load_labeling_payload(filename: str) -> dict:
    """Load an FPS JSON labeling file."""
    with open(filename) as fp:
        return json.load(fp)


def _network_from_labeling(structure, payload: dict) -> tuple[list[str], list[dict]]:
    """Return sorted network nodes and resolved edges from FPS JSON."""
    positions = payload.get("Positions", {}) or {}
    distances = payload.get("Distances", {}) or {}
    used = []
    edges = []
    for distance in distances.values():
        p1_name = str(distance.get("position1_name", ""))
        p2_name = str(distance.get("position2_name", ""))
        if not p1_name or not p2_name or p1_name not in positions or p2_name not in positions:
            continue
        try:
            i1 = _resolve_position_index(structure, positions[p1_name])
            i2 = _resolve_position_index(structure, positions[p2_name])
        except Exception:
            continue
        used.extend([p1_name, p2_name])
        edges.append(
            {
                "p1": p1_name,
                "p2": p2_name,
                "i1": i1,
                "i2": i2,
                "target": float(distance.get("distance", 0.0)),
                "error_neg": float(distance.get("error_neg", 1.0)),
                "error_pos": float(distance.get("error_pos", 1.0)),
            }
        )
    nodes = sorted(set(used), key=_node_sort_key)
    return nodes, edges


def _resolve_position_index(structure, position: dict) -> int:
    """Resolve one FPS position to a structure atom index."""
    atoms = structure.atoms
    if "chain_identifier" in position and "residue_seq_number" in position:
        chain = str(position["chain_identifier"])
        residue = int(position["residue_seq_number"])
        atom_name = str(position.get("atom_name", "CA"))
        mask = np.ones(len(atoms), dtype=bool)
        if "chain" in atoms.dtype.names:
            mask &= np.array([_as_text(v) == chain for v in atoms["chain"]])
        if "res_id" in atoms.dtype.names:
            mask &= atoms["res_id"] == residue
        if "atom_name" in atoms.dtype.names:
            atom_mask = np.array([_as_text(v) == atom_name for v in atoms["atom_name"]])
            ca_mask = np.array([_as_text(v) == "CA" for v in atoms["atom_name"]])
            selected = np.where(mask & atom_mask)[0]
            if selected.size == 0:
                selected = np.where(mask & ca_mask)[0]
        else:
            selected = np.where(mask)[0]
        if selected.size:
            return int(selected[0])
    if "attachment_atom_index" in position:
        index = int(position["attachment_atom_index"])
        if 0 <= index < len(atoms):
            return index
    raise ValueError(f"Cannot resolve labeling position: {position!r}")


def _circle_positions(nodes: list[str]) -> dict[str, np.ndarray]:
    """Return unit-circle coordinates for network nodes."""
    n = max(len(nodes), 1)
    return {
        name: np.array([np.cos(2.0 * np.pi * i / n), np.sin(2.0 * np.pi * i / n)], dtype=float)
        for i, name in enumerate(nodes)
    }


def _agreement_color(wres: float) -> tuple[int, int, int, int]:
    """Map signed weighted residual to blue-agree through magenta-disagree."""
    t = float(np.clip((abs(float(wres)) - 1.0) / 2.0, 0.0, 1.0))
    blue = np.array([45, 130, 255, 180], dtype=float)
    magenta = np.array([255, 0, 255, 230], dtype=float)
    color = blue * (1.0 - t) + magenta * t
    return tuple(int(v) for v in color)


def _node_sort_key(name: str) -> tuple[int, str]:
    digits = "".join(ch for ch in str(name) if ch.isdigit())
    return (int(digits) if digits else 10**9, str(name))


def _as_text(value) -> str:
    """Convert numpy string scalar values to plain text."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip()
    return str(value).strip()
