"""Native TTTR audio transport, channel mixer and lifetime/micro-time waterfall."""

import json
from copy import copy, deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
from emtk import Texture, im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from ..core import TTTRData, load_tttr_with_tttrlib
from ..native_playback import NativeSoundPlayer
from .view_model import AudifierViewModel


class AudifierApp(ImApp):
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
        self.texture = None
        self.waveform = None
        self.audio_signature = None
        self.pending_play = False
        self.help = EmTkHelpWindow(
            title="Audifier help", resource=Path(__file__).with_name("help.md")
        )
        self.guide = EmTkGuidedTour(steps=Path(__file__).with_name("guide.json"))
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
        self.parameter_specs = json.loads(
            Path(__file__).with_name("audifier.view.json").read_text()
        )["sections"][0]["sections"]
        super().__init__(gui=self.render, continuous=True)

    def snapshot(self):
        model = copy(self.model)
        model.__dict__ = {
            key: (value if key == "data" else deepcopy(value))
            for key, value in self.model.__dict__.items()
            if key != "_observers"
        }
        model._observers = []
        return model

    def button(self, label, tip, callback):
        if im.button(label):
            try:
                callback()
            except Exception as exc:
                self.message = str(exc)
        im.set_item_tooltip(tip)

    def numeric(self, label, value, tip, integer=False):
        im.text(label + ":")
        im.set_next_item_width(-1)
        changed, value = (
            im.input_int("##" + label, int(value), step=0)
            if integer
            else im.input_float("##" + label, float(value), step=0)
        )
        im.set_item_tooltip(tip)
        return changed, value

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
                rgb = np.clip(displayed * 255, 0, 255).astype(np.uint8)
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
        self.dialog_callback = lambda paths: (
            self.render_audio(output=paths[0]) if save else self.load(paths[0])
        )

    def stop_playback(self):
        self.player.stop()
        if self.pending_play and self.job.running:
            self.job.stop()
            self.message = "Playback stopped; pending audio will not start."
        self.pending_play = False

    def draw_setup(self, box):
        im.begin_disabled(self.job.running)
        self.editor.draw()
        self.button(
            "Update channels",
            "Rebuild detector colours and audio channels from the current setup.",
            self.update_channels,
        )
        im.end_disabled()

    def draw_parameters(self, title):
        im.begin_disabled(self.job.running)
        section = next(spec for spec in self.parameter_specs if spec.get("title") == title)

        def draw(specs):
            for spec in specs:
                if "sections" in spec:
                    im.separator()
                    im.text(spec.get("title", ""))
                    draw(spec["sections"])
                elif "items" in spec:
                    draw(spec["items"])
                else:
                    attr = spec["attr"]
                    value = getattr(self.model, attr)
                    label = spec.get("label", attr) + spec.get("suffix", "")
                    tip = (
                        spec.get("description")
                        or f"{label} controls the {title.lower()} calculation."
                    )
                    if isinstance(value, bool):
                        changed, value = im.checkbox(label, value)
                        im.set_item_tooltip(tip)
                    elif spec.get("options"):
                        im.text(label + ":")
                        im.set_next_item_width(-1)
                        changed, index = im.combo(
                            "##" + attr, spec["options"].index(value), spec["options"]
                        )
                        value = spec["options"][index]
                        im.set_item_tooltip(tip)
                    else:
                        changed, value = self.numeric(label, value, tip, spec.get("kind") == "int")
                        value = max(
                            spec.get("minimum", value), min(spec.get("maximum", value), value)
                        )
                    if changed:
                        setattr(self.model, attr, value)

        draw(section["sections"])
        im.end_disabled()

    def draw_mixer(self, box, detectors=True):
        im.begin_disabled(self.job.running)
        if not self.model.channels:
            im.text_wrapped("Load a stream or define detectors to configure channel notes.")
        for i, det in enumerate(self.model.detectors if detectors else []):
            changed, enabled = im.checkbox(det["name"], det["enabled"])
            im.set_item_tooltip("Include this detector in the micro-time and lifetime waterfall.")
            if changed:
                self.model.set_detector(i, enabled=enabled)
            changed, color = im.color_edit3(
                "##Colour" + str(i), tuple(value * 255 for value in det["color"])
            )
            im.set_item_tooltip("Waterfall detector colour (red, green and blue components).")
            if changed:
                self.model.set_detector(i, color=tuple(value / 255 for value in color))
        for ch in [] if detectors else self.model.channels:
            im.separator()
            cfg = self.model.channel_configs[ch]
            changed, enabled = im.checkbox(f"Channel {ch}", self.model.channel_enabled[ch])
            im.set_item_tooltip("Include this routing channel in playback and WAV export.")
            if changed:
                self.model.set_channel(ch, enabled=enabled)
            im.text("Chord:")
            im.set_next_item_width(-1)
            changed, index = im.combo(
                f"##chord{ch}", self.model.CHORD_TYPES.index(cfg.chord_type), self.model.CHORD_TYPES
            )
            im.set_item_tooltip("Chord quality assigned to the channel's photon envelope.")
            if changed:
                self.model.set_channel(ch, chord_type=self.model.CHORD_TYPES[index])
            for attr, label, tip, minimum, maximum in (
                (
                    "pitch_semitones",
                    "Pitch semitones",
                    "Transpose the chord by this many semitones.",
                    -24,
                    24,
                ),
                ("gain", "Gain", "Channel amplitude multiplier.", 0, 10),
                (
                    "micro_min",
                    "Micro-time first bin",
                    "Inclusive lower photon micro-time gate.",
                    0,
                    2**31 - 1,
                ),
                (
                    "micro_max",
                    "Micro-time last bin",
                    "Exclusive upper photon micro-time gate.",
                    1,
                    2**31 - 1,
                ),
            ):
                changed, value = self.numeric(
                    f"{label} channel {ch}",
                    getattr(self.model.channel_configs[ch], attr),
                    tip,
                    attr.startswith("micro"),
                )
                if changed:
                    self.model.channel_configs[ch] = replace(
                        self.model.channel_configs[ch], **{attr: max(minimum, min(maximum, value))}
                    )

        im.end_disabled()

    def draw_waterfall(self, box):
        if self.model.input_file:
            im.text_disabled(Path(self.model.input_file).name)
            im.set_item_tooltip(self.model.input_file)
        self.button(
            "Load TTTR", "Load a photon stream. Drag and drop is also supported.", self.choose
        )
        im.same_line()
        self.button(
            "Update",
            "Compute the selected detector waterfall in the background.",
            self.compute_waterfall,
        )
        im.same_line()
        self.button(
            "Play / Resume",
            "Render current settings, or resume the paused audio without restarting.",
            self.play,
        )
        im.same_line()
        self.button(
            "Pause", "Pause the native audio process at its current position.", self.player.pause
        )
        self.button(
            "Stop",
            "Stop audio and return the playback indicator to its beginning.",
            self.stop_playback,
        )
        im.same_line()
        self.button(
            "Revert",
            "Restart from the beginning if playing, otherwise reset the position.",
            self.player.revert,
        )
        im.same_line()
        self.button(
            "Save WAV",
            "Render selected channels and range to a 16-bit mono WAV file.",
            lambda: self.choose(save=True),
        )
        im.same_line()
        self.button("Help", "Audio, lifetime and timing workflow reference.", self.help.show)
        im.same_line()
        self.button("Guide", "Step-by-step audification workflow.", self.guide.start)
        im.text_wrapped(self.message)
        if self.job.running:
            im.text("Computing in background...")
        im.text(f"{self.player.state}: {self.player.position:.2f} / {self.player.duration:.2f} s")
        for attr, label, tip in (
            ("range_start", "Range start s", "Start relative to the first photon in the source."),
            ("range_end", "Range end s", "Exclusive end; zero includes all remaining photons."),
        ):
            changed, value = self.numeric(label, getattr(self, attr), tip)
            if changed:
                setattr(self, attr, max(0, value))
        payload = self.model.waterfall_payload()
        if self.texture is not None and payload:
            width = max(30, im.get_content_region_avail()[0])
            height = max(70, im.get_content_region_avail()[1] - 40)
            im.image(self.texture, (width, height))
            im.set_item_tooltip(
                "Horizontal axis: elapsed macro-time; vertical axis: micro-time bins or lifetime, increasing downward. Brightness encodes amplitude and hue identifies detectors."
            )
            rect = im.get_item_rect()
            if self.player.duration > 0 and rect and self.player.state in {"playing", "paused"}:
                x = rect[0] + rect[2] * self.player.position / self.player.duration
                im.get_window_draw_list().add_line(
                    (x, rect[1]), (x, rect[1] + rect[3]), (255, 255, 255, 255), 2
                )
            times = payload["macro_t_s"]
            axis = payload["micro_centers"]
            lifetime = self.model.waterfall_mode == "lifetime"
            scale = 1e9 if lifetime else 1
            im.text(
                f"Time 0–{float(times[-1] + times[0]):.3f} s; {'lifetime ns' if lifetime else 'micro-time bin'} {float(axis[0]) * scale:.3g}–{float(axis[-1]) * scale:.3g}"
            )
        else:
            im.text_wrapped(
                "Update computes a waterfall using the enabled detectors. Audio channel selection is independent of detector visibility."
            )

    def render(self):
        self.job.poll()
        self.editor.poll()
        try:
            self.player.poll()
        except Exception as exc:
            self.error(exc)
        self.docks.draw((0, 0, *im.get_main_viewport().size))
        frame = (0, 0, *im.get_main_viewport().size)
        self.editor.draw_dialogs(frame)
        if self.help.open:
            self.help.draw(frame)
        if self.guide.active:
            self.guide.draw(*im.get_main_viewport().size)
        if self.dialog:
            im.begin("Audifier file chooser")
            result = self.dialog.draw()
            if result is not None:
                callback = self.dialog_callback
                self.dialog = None
                if result:
                    try:
                        callback(result)
                    except Exception as exc:
                        self.error(exc)
            im.end()

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

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
