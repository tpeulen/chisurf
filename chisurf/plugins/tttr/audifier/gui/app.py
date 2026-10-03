"""Native TTTR audio transport, channel mixer and lifetime/micro-time waterfall."""

import json
from copy import copy, deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
from emtk import Texture, im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_form

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import button_row, layout_spec
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from ..core import TTTRData, load_tttr_with_tttrlib
from ..native_playback import NativeSoundPlayer
from .view_model import AudifierViewModel


def _spin(sections):
    """The Qt spin boxes had arrows: number fields step by the spec's step."""
    for section in sections:
        if section.get("type") == "value" and section.get("kind") in ("int", "float") and not section.get("read_only"):
            section["style"] = "spin"
        _spin(section.get("sections", []))


def hex_of(rgb):
    return "#{:02x}{:02x}{:02x}".format(*(int(round(max(0.0, min(1.0, c)) * 255)) for c in rgb))


class _Rows(list):
    revision = 0


RANGE_SPEC = {"sections": [{"type": "panel", "title": "", "n_col": 2, "description": "The part of the stream that is rendered.", "sections": [
    {"type": "value", "attr": "range_start", "kind": "float", "style": "spin", "label": "Range start", "minimum": 0.0, "maximum": 1e6,
     "decimals": 3, "step": 1.0, "suffix": " s", "description": "Start relative to the first photon in the source."},
    {"type": "value", "attr": "range_end", "kind": "float", "style": "spin", "label": "Range end", "minimum": 0.0, "maximum": 1e6,
     "decimals": 3, "step": 1.0, "suffix": " s", "description": "Exclusive end; zero includes all remaining photons."}]}]}

DETECTOR_TABLE = {"sections": [{"type": "custom", "key": "data_table",
    "description": "The detectors of the waterfall. The Show box includes a detector; the colour is its hue in the waterfall (type #rrggbb).",
    "options": {"source": "detector_rows", "editable": True, "height": 150, "row_key": "row", "selected_call": "select_detector",
                "edited_call": "edit_detector", "columns": [
        {"key": "show", "title": "Show", "width": 54, "editable": True, "description": "Include this detector in the micro-time and lifetime waterfall."},
        {"key": "name", "title": "Detector", "description": "The detector's name from the setup."},
        {"key": "channels", "title": "Channels", "description": "The routing channels of the detector."},
        {"key": "color", "title": "Colour", "width": 90, "editable": True, "description": "Waterfall colour of the detector as #rrggbb (red, green, blue)."}]}}]}

CHANNEL_TABLE = {"sections": [{"type": "custom", "key": "data_table",
    "description": "One row per routing channel: whether it is played and exported, its chord, pitch, gain and micro-time gate.",
    "options": {"source": "channel_rows", "editable": True, "expand": True, "reserve": 70, "row_key": "row", "selected_call": "select_channel",
                "edited_call": "edit_channel", "columns": [
        {"key": "on", "title": "On", "width": 44, "editable": True, "description": "Include this routing channel in playback and WAV export."},
        {"key": "channel", "title": "Channel", "width": 70, "description": "The routing channel."},
        {"key": "chord", "title": "Chord", "description": "Chord quality of the channel's photon envelope (change it below)."},
        {"key": "pitch", "title": "Pitch", "width": 80, "editable": True, "description": "Transpose the chord by this many semitones (-24 to 24)."},
        {"key": "gain", "title": "Gain", "width": 70, "editable": True, "description": "Channel amplitude multiplier (0 to 10)."},
        {"key": "micro_min", "title": "Micro first", "width": 90, "editable": True, "description": "Inclusive lower photon micro-time gate (bin)."},
        {"key": "micro_max", "title": "Micro last", "width": 90, "editable": True, "description": "Exclusive upper photon micro-time gate (bin)."}]}}]}

CHANNEL_FORM = {"sections": [{"type": "choice", "attr": "chord", "label": "Chord of the selected channel", "options_source": "chord_options",
                              "description": "Chord quality assigned to the selected channel's photon envelope."}]}


class AudifierApp(TourTarget, ImApp):
    def __init__(self, player=None, loader=None):
        self.model = AudifierViewModel()
        self.player = player or NativeSoundPlayer()
        self.loader = loader
        self.source_data = None
        self.range_start = self.range_end = 0.0
        self.editor = ChannelDefinitionWidget(on_changed=self.update_channels)
        self.job = BackgroundJob()
        self.message = "Load a TTTR stream to render audio and its waterfall."
        self.dialog = None
        self.dialog_callback = None
        self.dialog_window = DialogWindow("Audifier file chooser", size=(640.0, 420.0), key="audifier-file")
        self.item_rects = {}
        self.selected_detector = -1
        self.selected_channel = -1
        self.texture = None
        self.waveform = None
        self.audio_signature = None
        self.pending_play = False
        self.help = EmTkHelpWindow(
            title="Audifier help", resource=Path(__file__).with_name("help.md")
        )
        self.guide = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"), get_target_rect=lambda k: self.item_rects.get(k),
                                    owner=self, wait_for_controls=True,
                                    on_step_change=lambda _i, step: step.get("window") and self.docks.focus(step["window"]))
        self.docks = DockManager(
            Split(
                "h", 0.37, Region("config"), Split("v", 0.62, Region("waterfall"), Region("mixer"))
            )
        )
        self.docks.add_window("setup", "Detector setup", self.draw_setup, dock="config")
        self.docks.add_window(
            "audio", "Audio parameters", lambda box: self.draw_parameters("Audio"), dock="config"
        )
        self.docks.add_window(
            "waterfall_parameters",
            "Waterfall parameters",
            lambda box: self.draw_parameters("Waterfall params"),
            dock="config",
        )
        self.docks.add_window(
            "waterfall", "Waterfall and audio transport", self.draw_waterfall, dock="waterfall"
        )
        self.docks.add_window("mixer", "Detector colours", self.draw_mixer, dock="mixer")
        self.docks.add_window(
            "notes",
            "Channel notes",
            lambda box: self.draw_mixer(box, detectors=False),
            dock="mixer",
        )
        panels = json.loads(Path(__file__).with_name("audifier.view.json").read_text())["sections"][0]["sections"]
        self.parameter_specs = panels
        self.specs = {}
        for panel in panels:
            if panel.get("title") in ("Audio", "Waterfall params"):
                spec = {"sections": json.loads(json.dumps(panel["sections"]))}
                _spin(spec["sections"])
                self.specs[panel["title"]] = layout_spec(spec)
        self.forms = {name: FormState(on_used=self.guide.notify_used) for name in (*self.specs, "range", "channel")}
        self.table_forms = {name: FormState(on_used=self.guide.notify_used) for name in ("detectors", "channels")}
        self.view = self
        self.waterfall_view = None
        super().__init__(gui=self.render, continuous=False)

    def snapshot(self):
        model = copy(self.model)
        model.__dict__ = {
            key: (value if key == "data" else deepcopy(value))
            for key, value in self.model.__dict__.items()
            if key != "_observers"
        }
        model._observers = []
        return model

    def error(self, exc):
        self.message = str(exc)

    def load(self, path):
        if self.job.running or self.editor._future is not None:
            return False
        self.player.stop()
        settings = deepcopy(self.editor.model.get_settings())
        snapshot = self.snapshot()

        def work():
            data = (
                self.loader(str(path))
                if self.loader
                else load_tttr_with_tttrlib(str(path), setup=settings)
            )
            if not len(data.macro_ticks):
                raise ValueError("The TTTR stream has no events.")
            model = snapshot
            model.data = data
            model.input_file = str(path)
            if not settings.get("detectors"):
                settings["detectors"] = {
                    f"Routing {int(ch)}": {"chs": [int(ch)]} for ch in np.unique(data.routing)
                }
            previous_configs = model.channel_configs
            previous_enabled = model.channel_enabled
            previous_detectors = {det["name"]: det for det in model.detectors}
            model.set_detectors_from_settings(settings)
            for ch in model.channels:
                if ch in previous_configs:
                    model.channel_configs[ch] = previous_configs[ch]
                    model.channel_enabled[ch] = previous_enabled.get(ch, True)
            for det in model.detectors:
                if det["name"] in previous_detectors:
                    previous = previous_detectors[det["name"]]
                    det["enabled"] = previous["enabled"]
                    det["color"] = previous["color"]
            return model

        def publish(model):
            self.model = model
            if not self.editor.model.data.get("detectors"):
                self.editor.model.data["detectors"] = deepcopy(settings["detectors"])
            self.source_data = model.data
            self.range_start = self.range_end = 0.0
            self.texture = self.waveform = None
            self.audio_signature = None
            self.message = f"Loaded {len(model.data.macro_ticks):,} events: {Path(path).name}"

        return self.job.start(work, publish, self.error)

    def update_channels(self, settings=None):
        if self.job.running:
            return
        previous_configs = self.model.channel_configs
        previous_enabled = self.model.channel_enabled
        self.model.set_detectors_from_settings(settings or self.editor.model.get_settings())
        for ch in self.model.channels:
            if ch in previous_configs:
                self.model.channel_configs[ch] = previous_configs[ch]
                self.model.channel_enabled[ch] = previous_enabled.get(ch, True)
        self.waveform = None
        self.audio_signature = None
        self.texture = None

    def apply_range(self, model, start=None, end=None):
        if self.source_data is None:
            return
        data = self.source_data
        start = self.range_start if start is None else start
        end = self.range_end if end is None else end
        if start == 0 and end == 0:
            model.data = data
            return
        relative = (data.macro_ticks - data.macro_ticks.min()) * data.macro_time_unit_s
        mask = relative >= start
        if end > 0:
            if end <= start:
                raise ValueError(
                    "Range end must exceed its start (or be zero for all remaining events)."
                )
            mask &= relative < end
        if not np.any(mask):
            raise ValueError("The selected macro-time range contains no photons.")
        model.data = TTTRData(
            data.routing[mask],
            data.macro_ticks[mask],
            data.micro_bins[mask],
            data.macro_time_unit_s,
            data.micro_time_unit_s,
        )

    def compute_waterfall(self):
        if self.job.running or self.editor._future is not None:
            return False
        model = self.snapshot()
        range_values = (self.range_start, self.range_end)
        self.pending_play = False

        def work():
            self.apply_range(model, *range_values)
            return model.compute_waterfall()

        def publish(payload):
            self.model._waterfall_payload = payload
            self.texture = None
            if payload:
                displayed = payload["rgb_data"]
                if model.waterfall_mode == "lifetime" and not model.lt_log_tau:
                    tau = payload["micro_centers"]
                    linear = np.linspace(tau[0], tau[-1], len(tau))
                    displayed = np.stack(
                        [
                            np.stack(
                                [
                                    np.interp(linear, tau, displayed[:, column, color])
                                    for color in range(3)
                                ],
                                axis=1,
                            )
                            for column in range(displayed.shape[1])
                        ],
                        axis=1,
                    )
                rgb = np.clip(displayed[::-1] * 255, 0, 255).astype(np.uint8)
                rgba = np.concatenate([rgb, np.full((*rgb.shape[:2], 1), 255, np.uint8)], axis=2)
                self.texture = Texture(rgb.shape[1], rgb.shape[0], rgba.tobytes(), filter="nearest")
                self.message = payload["info"]
            else:
                self.message = "No detectors enabled for the waterfall."

        return self.job.start(work, publish, self.error)

    def fingerprint(self):
        return json.dumps(self.export_settings(), sort_keys=True)

    def play(self):
        if self.player.state == "paused" and self.audio_signature == self.fingerprint():
            self.player.play()
            return True
        return self.render_audio(play=True)

    def render_audio(self, play=False, output=None):
        if self.job.running or self.editor._future is not None:
            return False
        model = self.snapshot()
        range_values = (self.range_start, self.range_end)
        reason = model.can_render()
        if reason:
            raise ValueError(reason)
        signature = self.fingerprint()
        self.player.stop()
        self.pending_play = play

        def work():
            self.apply_range(model, *range_values)
            if output:
                return model.save_wav(str(output))
            return model.build_audio()[0]

        def publish(waveform):
            self.waveform = waveform
            self.audio_signature = signature
            if play:
                try:
                    self.player.load_audio(waveform, model.sample_rate)
                    self.player.play()
                except Exception as exc:
                    self.error(exc)
                    return
            self.message = f"{'Saved WAV' if output else 'Rendered audio'}: {len(waveform) / model.sample_rate:.3f} s at {model.sample_rate} Hz"

        return self.job.start(work, publish, self.error)

    # ── input ─────────────────────────────────────────────────────────────

    def choose(self, save=False):
        if self.job.running:
            return
        if save and self.model.can_render():
            self.message = self.model.can_render()
            return
        self.dialog = FileDialog(
            "Save audio as WAV" if save else "Load TTTR",
            mode="save" if save else "open",
            filters="WAV (*.wav)"
            if save
            else "TTTR (*.ptu *.pto *.ht3 *.spc *.h5 *.hdf5);;All files (*)",
            filename="audified.wav" if save else "",
        )
        self.dialog_window.title = self.dialog.title
        self.dialog_window.show()
        self.dialog_callback = lambda paths: (
            self.render_audio(output=paths[0]) if save else self.load(paths[0])
        )
        self.request_frame()

    def stop_playback(self):
        self.player.stop()
        if self.pending_play and self.job.running:
            self.job.stop()
            self.message = "Playback stopped; pending audio will not start."
        self.pending_play = False

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

    def on_files_dropped(self, paths):
        """The host's drop verb: the first file is the stream to load."""
        if self.dialog is None and paths:
            self.on_paths_dropped([str(p) for p in paths])
        self.request_frame()
        return True

    # ── table sources and callbacks ───────────────────────────────────────

    def detector_rows(self):
        rows = _Rows([{"row": i, "show": bool(d["enabled"]), "name": d["name"],
                       "channels": ", ".join(str(c) for c in d["channels"]), "color": hex_of(d["color"])}
                      for i, d in enumerate(self.model.detectors)])
        rows.revision = hash(tuple((r["show"], r["name"], r["color"]) for r in rows))
        return rows

    def select_detector(self, record):
        self.selected_detector = record["row"] if isinstance(record, dict) else -1

    def edit_detector(self, record, key, value):
        i = record["row"]
        if key == "show":
            self.model.set_detector(i, enabled=value in (True, "True", "true", 1))
        elif key == "color":
            text = str(value).strip().lstrip("#")
            try:
                if len(text) != 6:
                    raise ValueError
                rgb = tuple(int(text[j:j + 2], 16) / 255 for j in (0, 2, 4))
            except ValueError:
                self.message = f"Not a colour: {value} (use #rrggbb)."
                return
            self.model.set_detector(i, color=rgb)

    def channel_rows(self):
        rows = _Rows()
        for ch in self.model.channels:
            cfg = self.model.channel_configs[ch]
            rows.append({"row": ch, "on": bool(self.model.channel_enabled.get(ch, True)), "channel": ch, "chord": cfg.chord_type,
                         "pitch": cfg.pitch_semitones, "gain": cfg.gain, "micro_min": cfg.micro_min, "micro_max": cfg.micro_max})
        rows.revision = hash(tuple((r["row"], r["on"], r["chord"], r["pitch"], r["gain"], r["micro_min"], r["micro_max"]) for r in rows))
        return rows

    def select_channel(self, record):
        self.selected_channel = record["row"] if isinstance(record, dict) else -1

    def edit_channel(self, record, key, value):
        ch = record["row"]
        if key == "on":
            self.model.set_channel(ch, enabled=value in (True, "True", "true", 1))
            return
        limits = {"pitch": ("pitch_semitones", -24.0, 24.0, float), "gain": ("gain", 0.0, 10.0, float),
                  "micro_min": ("micro_min", 0, 2**31 - 1, int), "micro_max": ("micro_max", 1, 2**31 - 1, int)}
        attr, lo, hi, kind = limits[key]
        try:
            number = kind(float(str(value).strip()))
        except ValueError:
            self.message = f"Not a number: {value}"
            return
        self.model.channel_configs[ch] = replace(self.model.channel_configs[ch], **{attr: max(lo, min(hi, number))})

    # the selected channel's chord, for the form under the channel table
    @property
    def chord(self):
        cfg = self.model.channel_configs.get(self.selected_channel)
        return cfg.chord_type if cfg else ""

    @chord.setter
    def chord(self, value):
        if self.selected_channel in self.model.channel_configs:
            self.model.set_channel(self.selected_channel, chord_type=value)

    def chord_options(self):
        return list(self.model.CHORD_TYPES)

    def enabled(self, name):
        return not self.job.running and self.dialog is None

    # ── drawing ───────────────────────────────────────────────────────────

    def draw_setup(self, box):
        im.begin_disabled(self.job.running)
        self.editor.draw()
        if im.button("Update channels"):
            self.update_channels()
        im.set_item_tooltip("Rebuild detector colours and audio channels from the current setup.")
        self.remember("update_channels")
        im.end_disabled()

    def draw_parameters(self, title):
        form = self.forms[title]
        form.rects.clear()
        im.begin_disabled(self.job.running)
        draw_form(self.specs[title], self.model, form)
        im.end_disabled()
        self.item_rects.update(form.rects)

    def draw_mixer(self, box, detectors=True):
        if detectors:
            if not self.model.detectors:
                im.text_wrapped("Load a stream or define detectors to choose the detector colours.")
                return
            form = self.table_forms["detectors"]
            form.rects.clear()
            draw_form(DETECTOR_TABLE, self, form)
            self.item_rects.update(form.rects)
            return
        if not self.model.channels:
            im.text_wrapped("Load a stream or define detectors to configure channel notes.")
            return
        form = self.table_forms["channels"]
        form.rects.clear()
        draw_form(CHANNEL_TABLE, self, form)
        self.item_rects.update(form.rects)
        if self.selected_channel in self.model.channel_configs:
            f = self.forms["channel"]
            f.rects.clear()
            draw_form(CHANNEL_FORM, self, f)
            self.item_rects.update(f.rects)
        else:
            im.text_disabled("Select a channel row to change its chord.")

    def draw_waterfall(self, box):
        if self.model.input_file:
            im.text_disabled(Path(self.model.input_file).name)
            im.set_item_tooltip(self.model.input_file)
            self.remember("file_name")
        playing = self.player.state in {"playing", "paused"}
        pressed = button_row([
            {"label": "Load TTTR", "key": "load", "tip": "Load a photon stream. Drag and drop is also supported."},
            {"label": "Update", "key": "update", "tip": "Compute the selected detector waterfall in the background."},
            {"label": "Play / Resume", "key": "play", "tip": "Render current settings, or resume the paused audio without restarting."},
            {"label": "Pause", "key": "pause", "enabled": self.player.state == "playing", "tip": "Pause the native audio process at its current position."},
            {"label": "Stop", "key": "stop", "enabled": playing or self.pending_play, "tip": "Stop audio and return the playback indicator to its beginning."},
            {"label": "Revert", "key": "revert", "enabled": playing, "tip": "Restart from the beginning if playing, otherwise reset the position."},
            {"label": "Save WAV", "key": "save_wav", "tip": "Render selected channels and range to a 16-bit mono WAV file."},
            {"label": "Guide", "key": "guide", "tip": "Step-by-step audification workflow."},
            {"label": "Help", "key": "help", "tip": "Audio, lifetime and timing workflow reference."},
        ], remember=self.remember)
        actions = {"load": self.choose, "update": self.compute_waterfall, "play": self.play, "pause": self.player.pause,
                   "stop": self.stop_playback, "revert": self.player.revert, "save_wav": lambda: self.choose(save=True),
                   "guide": self.guide.start, "help": self.help.show}
        if pressed:
            try:
                actions[pressed]()
                self.guide.notify_used(pressed)
            except Exception as exc:
                self.message = str(exc)
        im.text_wrapped(self.message)
        self.remember("message")
        if self.job.running:
            im.text("Computing in background...")
        im.text(f"{self.player.state}: {self.player.position:.2f} / {self.player.duration:.2f} s")
        self.remember("player_state")
        form = self.forms["range"]
        form.rects.clear()
        im.begin_disabled(self.job.running)
        draw_form(RANGE_SPEC, self, form)
        im.end_disabled()
        self.item_rects.update(form.rects)
        self._draw_plot()

    def _draw_plot(self):
        payload = self.model.waterfall_payload()
        if self.texture is None or not payload:
            im.text_wrapped("Update computes a waterfall using the enabled detectors. Audio channel selection is independent of detector visibility.")
            self.remember("empty_waterfall")
            return
        times = payload["macro_t_s"]
        axis = np.asarray(payload["micro_centers"], dtype=float)
        lifetime = self.model.waterfall_mode == "lifetime"
        y = axis * 1e9 if lifetime else axis
        ylabel = "Lifetime (ns)" if lifetime else "Micro-time (bin)"
        if lifetime and self.model.lt_log_tau:
            y, ylabel = np.log10(y), "log10 lifetime (ns)"
        t_end = float(times[-1] + times[0]) if len(times) else 1.0
        avail = im.get_content_region_avail()
        if implot.begin_plot("##waterfall", (-1, max(90.0, avail[1] - 4.0)), implot.FLAGS_NO_LEGEND):
            implot.setup_axes("Macro-time (s)", ylabel)
            implot.plot_image("waterfall", self.texture, (0.0, float(y[0])), (t_end, float(y[-1])))
            if self.player.duration > 0 and self.player.state in {"playing", "paused"}:
                implot.plot_inf_lines("position", [t_end * self.player.position / self.player.duration])
            implot.end_plot()
            im.set_item_tooltip("Horizontal axis: elapsed macro-time; vertical axis: micro-time bins or lifetime. "
                                "Brightness encodes amplitude and hue identifies detectors. Wheel zooms, drag pans.")
            self.remember("waterfall_plot")

    def render(self):
        self.job.poll()
        self.editor.poll()
        try:
            self.player.poll()
        except Exception as exc:
            self.error(exc)
        vp = im.get_main_viewport()
        frame = (0, 0, *vp.size)
        im.begin_disabled(self.dialog is not None)
        self.docks.draw(frame)
        im.end_disabled()
        self.editor.draw_dialogs(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.guide.active:
            self.guide.draw(*vp.size)
        if self.dialog:
            pressed = self.dialog_window.begin(frame)
            result = self.dialog.draw()
            self.dialog_window.end()
            if result:
                callback, self.dialog = self.dialog_callback, None
                try:
                    callback(result)
                except Exception as exc:
                    self.error(exc)
            elif result is False or pressed == "close":
                self.dialog = None

    def animating(self):
        return super().animating() or self.job.running or self.player.state == "playing" or self.editor._future is not None

    def next_frame_in(self):
        return 0.05 if (self.job.running or self.player.state == "playing" or self.editor._future is not None) else super().next_frame_in()

    def export_settings(self):
        setup = self.editor.model.get_settings()
        setup.pop("_microtime_per_channel_decay", None)
        setup.pop("_raw_microtime_per_channel_decay", None)
        keys = [
            key
            for key, value in self.model.__dict__.items()
            if isinstance(value, (int, float, str, bool)) and key not in {"input_file"}
        ]
        return {
            "parameters": {key: getattr(self.model, key) for key in keys},
            "range_start": self.range_start,
            "range_end": self.range_end,
            "detectors": deepcopy(self.model.detectors),
            "configs": {str(ch): vars(cfg) for ch, cfg in self.model.channel_configs.items()},
            "enabled": {str(ch): value for ch, value in self.model.channel_enabled.items()},
            "setup": setup,
        }

    def restore_settings(self, settings):
        from chisurf.core.setup_channel_definition import ChannelDefinition

        from ..core import ChannelConfig

        for key, value in settings.get("parameters", {}).items():
            if hasattr(self.model, key) and isinstance(
                getattr(self.model, key), (int, float, str, bool)
            ):
                setattr(self.model, key, value)
        self.range_start = float(settings.get("range_start", 0))
        self.range_end = float(settings.get("range_end", 0))
        self.editor.model = ChannelDefinition(settings.get("setup", {}))
        self.editor.model.on_changed = self.update_channels
        self.model.detectors = deepcopy(settings.get("detectors", []))
        self.model.channel_configs = {
            int(ch): ChannelConfig(**cfg) for ch, cfg in settings.get("configs", {}).items()
        }
        self.model.channels = sorted(self.model.channel_configs)
        self.model.channel_enabled = {
            int(ch): bool(value) for ch, value in settings.get("enabled", {}).items()
        }

    def close(self):
        self.job.close()
        self.player.close()
        self.editor.close()


def create_app(player=None, loader=None):
    return AudifierApp(player=player, loader=loader)
