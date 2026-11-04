"""emtk control panel for the cmc-light ALEX source.

    python -m cmc_light            # emtk window; ``run`` puts it in emtk.qt_host, so qtpy + a Qt binding host it
    python -m cmc_light --sim      # start connected to the simulator

The GUI thread only draws. Every instrument call goes through ``DeviceWorker``,
a background thread that owns the connection, coalesces rapid changes (a
dragged power slider sends the latest value, not every intermediate one) and
polls the run status.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time
import traceback

from emtk import im

from cmc_light import preview_edit, seqcore, steps_text
from cmc_light.client import LaserSource
from cmc_light.units import POWER_UNITS, fmt_power

SIMULATOR = "Simulator"
GUI_VERSION = "2.0"
MENU_H = 22.0


SENSOR_COLUMN_W = 600.0  # default width of the light sensor column
RESERVED_H = {"sensor": 440.0}  # default heights that leave room for contents arriving later
AUTO = "auto"  # start-up target: the first instrument found on USB, else the simulator
SYNC_LANE = dict(name="sync", color="#e6e6e6")  # the sync output (D5) as a step column


def hex_rgb(s, alpha=255):
    s = s.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)


def text_field(label, value, hint=""):
    """input_text that treats Return as 'confirm': returns (changed, text, entered).

    emtk inserts the Return character into the text; it is stripped here.
    """
    changed, text = im.input_text(label, value, hint)
    entered = "\r" in text or "\n" in text
    if entered:
        text = text.replace("\r", "").replace("\n", "")
    return changed, text, entered


TEXT_COL = (225, 228, 235, 255)
DIM_COL = (150, 155, 165, 255)


DIM_TEXT = (128, 128, 128, 255)  # emtk's dark style TEXT_DISABLED
WRAP_MIN_W = 240.0  # wrapped text needs at least this width, whatever width it fills now


class flex:
    """Contents that stretch with the window: only ``slack`` px of their width (and
    ``slack_y`` px of their height) is stretch, and does not count towards the window's
    minimum size."""

    def __init__(self, slack, slack_y=0.0):
        self.slack = max(0.0, float(slack))
        self.slack_y = max(0.0, float(slack_y))

    def __enter__(self):
        from emtk.im_widgets import get_current_context

        self.lay = get_current_context().layout
        self.before = self.lay._max_x
        self.before_y = self.lay._max_y
        return self

    def __exit__(self, *exc):
        if self.slack > 0:
            self.lay._max_x = max(self.before, self.lay._max_x - self.slack)
        if self.slack_y > 0:  # rows after this still go below the full height: the window's
            # measurement subtracts the vertical stretch at the end (windows._measure)
            self.lay.flex_y = getattr(self.lay, "flex_y", 0.0) + self.slack_y
        return False


def wrapped(text, colour=None):
    """Dim (or coloured) text broken to the window width, so long hints are never cut off."""
    avail = im.get_content_region_avail()[0]
    im.push_style_color(im.Col.TEXT, colour if colour is not None else DIM_TEXT)
    with flex(avail - WRAP_MIN_W):
        im.text_wrapped(text)
    im.pop_style_color()


def label(text, col=None, dim=False, colour=None, last=False):
    """Text vertically centred on a widget row, then continue on the same line.

    emtk's align_text_to_frame_padding is a no-op, so text beside a frame (input,
    slider, button) sat 3 px too high. *col* (window-relative x) starts the next
    widget in a fixed column, so fields line up under each other.
    """
    x, y = im.get_cursor_screen_pos()
    tw, th = im.calc_text_size(text)[:2]
    fh = im.get_frame_height()
    im.get_window_draw_list().add_text((x, y + max(0.0, (fh - th) / 2.0)),
                                       colour or (DIM_COL if dim else TEXT_COL), text)
    im.dummy(tw, fh)
    if last:
        return
    if col is None:
        im.same_line()
    else:
        im.same_line(col)


def nice_int(v):
    """Round to two significant digits above 100 (slider values stay readable)."""
    v = int(round(v))
    if v < 100:
        return max(1, v)
    digits = len(str(v)) - 2
    return int(round(v, -digits))


def fmt_us(us):
    if us >= 1000000:
        return "%g s" % (us / 1e6)
    if us >= 1000:
        return "%g ms" % (us / 1e3)
    return "%d us" % us


def log_slider(key, value, lo, hi, width, text, allow_zero=False):
    """Logarithmic integer slider; *text* is shown inside the slider.

    With *allow_zero*, the leftmost notch (below *lo*) means 0.
    """
    import math

    lo_e, hi_e = math.log10(lo), math.log10(hi)
    zero_e = lo_e - 0.3
    if allow_zero and value <= 0:
        pos = zero_e
    else:
        # only the drawn position is clamped: an untouched slider never rewrites the value
        pos = math.log10(max(lo, min(hi, max(1, int(value)))))
    im.set_next_item_width(width)
    # emtk formats the display with fmt % value: embed the text, swallow the value
    changed, e = im.slider_float("##" + key, pos, zero_e if allow_zero else lo_e, hi_e,
                                 text.replace("%", "%%") + "%.0s")
    if not changed:
        return False, value
    if allow_zero and e < lo_e - 0.15:
        new = 0
    else:
        new = max(lo, min(hi, nice_int(10 ** max(e, lo_e))))
    return new != value, new


def labelled_slider(label_text, key, value, lo, hi, width=240, allow_zero=False, fmt=None, col=None):
    label(label_text, col)
    text = "off" if allow_zero and value <= 0 else (fmt or fmt_us)(value)
    return log_slider(key, value, lo, hi, width, text, allow_zero)


NUMBER_CHARS = set("0123456789.-+eE")


class NumField:
    """Typed number entry (emtk's input_int cannot be typed into; input_text can).

    The text is only replaced when the value was changed elsewhere, never while
    typing. ``live=True`` commits every valid keystroke (settings that follow
    immediately); ``live=False`` commits on Return (values that rescale others).
    """

    def __init__(self):
        self.buf = {}  # key -> [text, last committed value]

    def __call__(self, key, label_text, value, lo, hi, width=110.0, kind=int, fmt="%g", live=True,
                 col=None):
        label(label_text, col)
        entry = self.buf.get(key)
        if entry is None or entry[1] != value:
            entry = self.buf[key] = [fmt % value, value]
        im.set_next_item_width(width)
        changed, text, entered = text_field("##" + key, entry[0])
        text = "".join(c for c in text if c in NUMBER_CHARS)  # numbers only
        entry[0] = text
        try:
            bad = not lo <= kind(float(text)) <= hi
        except ValueError:
            bad = True
        if bad and text != fmt % value:
            im.same_line()
            label("%s .. %s" % (fmt % lo, fmt % hi), colour=(255, 110, 110, 255), last=True)
        if not ((changed and live) or entered):
            return False, value
        try:
            v = kind(float(text))
        except ValueError:
            return False, value
        if not lo <= v <= hi or v == value:
            return False, value
        entry[1] = v
        return True, v

    def invalid(self, key, lo, hi, kind=int):
        entry = self.buf.get(key)
        if entry is None:
            return False
        try:
            v = kind(float(entry[0]))
        except ValueError:
            return True
        return not lo <= v <= hi


def list_ports():
    try:
        from serial.tools import list_ports as lp
    except ImportError:
        return []
    ports = []
    for p in lp.comports():
        dev = p.device
        if "Bluetooth" in dev or "debug-console" in dev:
            continue
        if getattr(p, "vid", None) is None:
            continue  # not a USB serial adapter (Bluetooth audio, modems, ...)
        if dev.startswith("/dev/tty.") and dev.replace("/dev/tty.", "/dev/cu.") != dev:
            continue  # macOS lists every port twice; cu.* is the right one
        ports.append(dev)
    return ports


def probe(port, timeout=0.6):
    """Ask one serial port for *IDN? without resetting the board."""
    try:
        import serial
    except ImportError:
        return None
    try:
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, 115200, timeout
        s.dtr = s.rts = False
        s.exclusive = True  # fails if another program has the port open: never steal its replies
        s.open()
        try:
            time.sleep(0.15)  # the CH340 needs a moment after opening before it answers
            s.reset_input_buffer()
            s.write(b"*IDN?\n")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                line = s.readline().decode(errors="replace").strip()
                if line.startswith("CMC,"):
                    return line
        finally:
            s.close()
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
class DeviceWorker:
    """Owns the instrument; runs calls off the GUI thread."""

    POLL_S = 0.5        # the whole status: ~10 round trips over USB
    FAST_POLL_S = 0.1   # what changes while a sequence plays: 2 round trips
    RECONNECT_S = 3.0  # how often to look for a board that was unplugged

    def __init__(self, debug=False):
        self.debug = debug
        self.src: LaserSource | None = None
        self.jobs: "queue.Queue" = queue.Queue()
        self.latest: dict = {}  # key -> callable, coalesced
        self.lock = threading.Lock()
        self.status = {}
        self.error = ""
        self.busy = ""
        self.found: dict = {}  # port -> idn
        self.pause_poll = False  # the computer player owns the link: no status queries
        self.monitor_present = None  # None: not asked yet
        self.connected_to = ""    # what connect() was last called with
        self.reconnect_to = None  # a port that vanished, to look for again
        self.on_reconnected = None
        self._next_try = 0.0
        self._last_live = 0.0
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    # -- API used by the GUI ------------------------------------------------ #
    def submit(self, fn, label=""):
        self.jobs.put((fn, label))

    def set_latest(self, key, fn):
        with self.lock:
            self.latest[key] = fn

    def close(self):
        """Stop the worker and switch the lasers off - in that order, and for certain.

        The switch-off used to be queued as a job after the stop flag was set, so the
        worker often exited without ever running it and the lasers stayed on (with the
        sequence still playing on the MCU). It is done here instead, once the worker
        thread has finished and cannot race with it.
        """
        self._stop = True
        if self.thread is not None:
            self.thread.join(timeout=3)
        try:
            self._disconnect()
        except Exception as e:  # a dead link must not stop the program from closing
            print("[cmc-light] switching off at exit: %s" % e, flush=True)

    # -- worker ------------------------------------------------------------ #
    def _lost_connection(self):
        """The board is gone (cable pulled, driver reset): drop it and look for it again."""
        port = self.connected_to
        try:
            if self.src is not None:
                self.src.t.close()
        except Exception:
            pass
        self.src = None
        self.status = {}
        self.monitor_present = None
        if self.reconnect_to is None and port and port != SIMULATOR:
            self.reconnect_to = port
            print("[cmc-light] lost %s; looking for it again" % port, flush=True)

    def _try_reconnect(self):
        if self.reconnect_to is None or time.monotonic() < self._next_try:
            return
        self._next_try = time.monotonic() + self.RECONNECT_S
        target = self.reconnect_to
        if not target.startswith("tcp://") and probe(target) is None:
            return  # not back yet
        try:
            self.connect(target, self.on_reconnected or (lambda src: None))
            self.reconnect_to = None
            self.error = ""
        except Exception as e:
            print("[cmc-light] reconnect %s: %s" % (target, e), flush=True)

    def _run(self):
        last_poll = last_fast = 0.0
        while not self._stop:
            if self.src is None and self.reconnect_to is not None:
                self._try_reconnect()
            try:
                fn, label = self.jobs.get(timeout=0.05)
                self._call(fn, label)
            except queue.Empty:
                pass
            # live updates are paced to the link: USB slower than the MCU, WiFi slowest
            interval = self.src.live_interval_s if self.src is not None else 0.0
            if time.monotonic() - self._last_live >= interval:
                with self.lock:
                    pending, self.latest = self.latest, {}
                if pending:
                    self._last_live = time.monotonic()
                for fn in pending.values():
                    self._call(fn, "")
            if self.src is not None and not self.pause_poll:
                now = time.monotonic()
                if now - last_poll > self.POLL_S:
                    last_poll = last_fast = now
                    self._call(self._poll, "")
                elif now - last_fast > self.FAST_POLL_S:
                    last_fast = now
                    self._call(self._fast_poll, "")

    def _call(self, fn, label):
        self.busy = label
        try:
            fn()
            if label:
                self.error = ""
        except Exception as e:  # show it, keep running
            self.error = "%s: %s" % (label or "device", e)
            if "Invalid argument" in str(e) or "Device not configured" in str(e):
                self.error += ("  -- the macOS CH340 USB driver is stuck: run "
                               "scripts/usb_reset_ch340.py or re-plug the cable")
            print("[cmc-light] ERROR in %s: %s" % (label or "device job", e), flush=True)
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            if isinstance(e, OSError) or "Device not configured" in str(e):
                self._lost_connection()
        finally:
            self.busy = ""

    def _fast_poll(self):
        """Only what moves while a sequence plays, so it can be asked ten times a second.

        The full poll's timestamp (t0) is left alone: it says how old the emission and
        duty readings are, and those are not refreshed here.
        """
        src = self.src
        if src is None:
            return
        running, cycles = src.running(), src.cycles_done()
        self.status = dict(self.status, running=running, cycles=cycles, t=time.monotonic())

    def _poll(self):
        src = self.src
        if src is None:
            return
        n = src.n_channels
        t0 = time.monotonic()
        self.status = dict(
            t0=t0,
            running=src.running(),
            cycles=src.cycles_done(),
            timing=src.timing(),
            source=src.source(),
            emission=[src.emission(k) for k in range(1, n + 1)],
            duty=[src.duty(k) for k in range(1, n + 1)],
            monitor=self._monitor_lux(src),
            t=time.monotonic(),
        )

    def _monitor_lux(self, src):
        """The internal power diode, if the instrument has one (checked once)."""
        if self.monitor_present is None:
            try:
                self.monitor_present = src.monitor_present()
            except Exception:
                self.monitor_present = False
        if not self.monitor_present:
            return None
        try:
            return src.monitor_lux()
        except Exception:
            return None

    def _disconnect(self):
        if self.src is not None:
            try:
                self.src.all_off()
            finally:
                self.src.close()
                self.src = None
                self.status = {}

    def scan(self):
        found = {}
        in_use = getattr(getattr(self.src, "t", None), "serial", None)
        in_use = getattr(in_use, "port", None) or getattr(getattr(getattr(self.src, "t", None), "inner", None), "serial", None)
        in_use = in_use if isinstance(in_use, str) else getattr(in_use, "port", None)
        for port in list_ports():
            if port == in_use and self.src is not None:
                found[port] = self.src.identity  # connected: do not open it a second time
                continue
            idn = probe(port)
            if idn:
                found[port] = idn
        self.found = found

    def connect(self, target, on_connected):
        self._disconnect()
        self.connected_to = target
        if target == SIMULATOR:
            src = LaserSource.simulated(debug=self.debug)
        elif target.startswith("tcp://"):
            host, _, port = target[len("tcp://"):].partition(":")
            src = LaserSource.open_tcp(host, int(port or 5025), debug=self.debug)
        else:
            src = LaserSource.open(target, debug=self.debug)
        self.src = src
        print("[cmc-light] connected to %s: %s" % (target, src.identity), flush=True)
        on_connected(src)


# --------------------------------------------------------------------------- #
class LaserGui:
    """All GUI state; ``draw()`` is one immediate-mode frame."""

    def __init__(self, worker: DeviceWorker | None = None, autoconnect: str | None = None,
                 scan_ports: bool | None = None):
        self.worker = worker or DeviceWorker()
        self.targets = [SIMULATOR]
        self.target = 0
        self.tcp_host = "cmc-light.local"
        self.tcp_port = 5025
        self.dropdown_request = None
        self.identity = ""
        self.channels = [
            dict(name="blue", color="#3a6bff"),
            dict(name="green", color="#2fd05a"),
            dict(name="red", color="#ff3b30"),
        ]
        n = len(self.channels)
        self.enabled = [False] * n
        self.power = [100.0] * n  # percent
        self.pwm_period = 1000
        self.min_pulse = 20
        self.power_mode = "cycles"  # sequences: "cycles" = whole windows lit (no gaps), "pwm" = PWM inside
        self.mode = 0  # 0 computer-driven (CW), 1 programmed sequence (SEQ)
        # preset parameters: the presets only write the Sequence table (the one sequence)
        self.on_us = 1000
        self.gap_us = 100
        self.window_us = [1000] * n  # per-laser on-window for the no-gap preset
        # custom steps: [duration, [on per laser..., sync]] - the last column is the sync output
        self.custom = [[1000, [True, False, False, False]], [1000, [False, True, False, False]],
                       [1000, [False, False, True, False]]]
        self.custom_text = ""
        from cmc_light.spreadsheet import StepSheet

        self.sheet = StepSheet(self.custom_rows, lambda rows: setattr(self, "custom", rows),
                               self.lanes, hex_rgb, seqcore.MAX_STEPS)
        self.resume = None  # what the OFF button switched off, for ON
        self.monitor_per_laser = {}  # laser index -> lux measured with the others off
        self.monitor_note = {}
        self.monitor_busy = ""
        self.diode_cal = {}      # str(laser index) -> {"w_per_au":…, "points":[[au, W],…]}
        self.dcal = None         # the calibration wizard while it is open
        self.show_diode_cal = False
        self._mcu_started_at = None  # when this GUI last started an MCU sequence (None: stopped)
        self.show_table = True
        self.table_top = None
        self.text_error = ""
        self.run_s = 0.0  # 0 = endless
        self.num = NumField()
        self.settings_path = None
        self.pwm_warning = ""
        self.steps_path = None
        self._mode_pending = 0
        self.stopped = False     # OFF was pressed: nothing is sent until ON
        self._sync_sig = None    # what the table last looked like
        self._sync_sent = None   # what the instrument was last given
        self._sync_at = None     # when the table stopped changing
        self._enable_pushed_at = 0.0
        self._mode_done_at = 0.0
        # dialogs (drawn by emtk over the panel)
        self.file_dialog = None
        self.show_about = False
        self.show_help = False
        self.help = None
        self.tutorial = None
        self.message = ""
        self.scanned = False
        self.on_scanned = None  # callback(found ports) after the start-up scan
        if autoconnect == AUTO:
            self._autoconnect()  # the first instrument found, or the simulator
        elif autoconnect:
            self._connect(autoconnect)
        if scan_ports is None:  # the simulator (and every test) never touches real ports
            scan_ports = autoconnect not in (SIMULATOR, AUTO)
        if scan_ports:
            self.rescan()  # list the USB devices, also when started with --port

    # -- helpers ------------------------------------------------------------ #
    @property
    def src(self):
        return self.worker.src

    def rescan(self):
        def job():
            self.worker.scan()
            lights = [p for p, idn in self.worker.found.items() if idn.startswith("CMC,LIGHT")]
            ports = sorted(lights) + [p for p in list_ports() if p not in self.worker.found]
            current = self.targets[self.target] if self.target < len(self.targets) else None
            self.targets = [SIMULATOR] + ports
            if current in self.targets:
                self.target = self.targets.index(current)
            self.scanned = True
        self.worker.submit(job, "scan")

    def target_label(self, t):
        idn = self.worker.found.get(t)
        if idn:
            parts = idn.split(",")
            return "%s  [%s %s]" % (t, parts[1], parts[2] if len(parts) > 2 else "")
        return t

    def _autoconnect(self):
        """Scan the serial ports; connect the first cmc-light found, else the simulator."""
        def job():
            self.worker.scan()
            found = sorted(p for p, idn in self.worker.found.items() if idn.startswith("CMC,LIGHT"))
            if not found:  # a port can be busy for a moment (a previous session closing): retry once
                time.sleep(1.0)
                self.worker.scan()
                found = sorted(p for p, idn in self.worker.found.items() if idn.startswith("CMC,LIGHT"))
            others = [p for p in list_ports() if p not in found and not self.worker.found.get(p, "").startswith("CMC,SENSE")]
            self.targets = [SIMULATOR] + found + others
            self.scanned = True
            target = found[0] if found else SIMULATOR
            if not found:
                print("[cmc-light] no cmc-light instrument on USB: using the simulator", flush=True)
                self.message = "no instrument found on USB: simulator (Scan + Connect when plugged in)"
            self.worker.on_reconnected = self._on_connected(target)
            self.worker.connect(target, self._on_connected(target))
            if self.on_scanned is not None:  # e.g. the light sensor picks its port from the same scan
                self.on_scanned(dict(self.worker.found))
        self.worker.submit(job, "scan + connect")

    def _connect(self, target):
        self.worker.on_reconnected = self._on_connected(target)  # same set-up after a re-plug
        self.worker.submit(lambda: self.worker.connect(target, self._on_connected(target)), "connect")

    def _on_connected(self, target):
        def connected(src):
            if target not in self.targets and not target.startswith("tcp://") and target != SIMULATOR:
                self.targets.append(target)
            if target in self.targets:
                self.target = self.targets.index(target)
            self.identity = src.identity
            self.channels = src.channels
            n = src.n_channels
            self.enabled = [src.emission(k) for k in range(1, n + 1)]
            self.power = [100.0 * src.power(k) for k in range(1, n + 1)]
            self.pwm_period = src.pwm_period()
            self.min_pulse = src.min_pulse()
            src.set_power_mode("CYCLes" if self.power_mode == "cycles" else "PWM")
            self.mode = 1 if src.source() == "SEQ" else 0
            self.resync()  # this instrument has not been given the table yet
        return connected

    def lanes(self):
        """Columns of a step: the lasers, then the sync output (mask bit n)."""
        return list(self.channels) + [SYNC_LANE]

    def lane_names(self):
        return [c["name"] for c in self.lanes()]

    def custom_rows(self):
        """The custom steps, every row padded to one flag per lane."""
        m = len(self.channels) + 1
        for row in self.custom:
            if len(row[1]) < m:
                row[1].extend([False] * (m - len(row[1])))
            elif len(row[1]) > m:
                del row[1][m:]
        return self.custom

    def rows_from_steps(self, steps):
        m = len(self.channels) + 1
        return [[d, [bool(mask >> k & 1) for k in range(m)]] for d, mask in steps]

    def steps(self):
        """The sequence: the Sequence table's rows as (duration, mask); bit n is the sync output."""
        n = len(self.channels)
        out = []
        for dur, on in self.custom:
            mask = sum(1 << k for k in range(n + 1) if k < len(on) and on[k])
            out.append((max(1, int(dur)), mask))
        return out

    MCU_MIN_STEP_US = 20
    MAX_STEP_US = 60_000_000

    def duration_limits(self):
        """(lo, hi) for step durations: the MCU plays every sequence."""
        return self.MCU_MIN_STEP_US, self.MAX_STEP_US

    def preset_steps(self, kind):
        n = len(self.channels)
        if kind == "alex":
            return seqcore.alex_steps(n, max(1, int(self.on_us)), max(0, int(self.gap_us)))
        return [(max(1, int(self.window_us[k])), 1 << k) for k in range(n)]

    def apply_preset(self, kind):
        """Write a preset into the Sequence table (replacing its rows).

        Called on every change of a preset's values, so the table follows live. Sync
        flags already ticked in the table stay on their rows when the row count is kept.
        """
        n = len(self.channels)
        old = self.custom_rows()
        rows = self.rows_from_steps(self.preset_steps(kind))
        if len(old) == len(rows):
            for row, prev in zip(rows, old):
                row[1][n] = bool(prev[1][n])
        self.custom = rows
        if self.sheet.sel is not None and self.sheet.sel[0] >= len(rows):
            self.sheet.sel = None
        self.num.buf = {k: v for k, v in self.num.buf.items() if not k.startswith("period")}
        if kind == "gapless" and self.power_mode != "cycles":
            self.set_power_mode("cycles")  # gapless means no dark time inside windows
        self.message = "%s preset written to the Sequence table (%d steps)" % (
            "ALEX" if kind == "alex" else "gapless", len(self.custom))

    def cycles(self):
        """Cycles for the requested run time (0 = endless)."""
        if self.run_s <= 0:
            return 0
        period = seqcore.period_us(self.steps())
        return max(1, int(round(self.run_s * 1e6 / period)))

    # -- settings files ----------------------------------------------------- #
    SETTINGS_VERSION = 1

    def settings(self):
        """Everything worth restoring, as JSON-able data (laser 'on' is not stored)."""
        return dict(
            cmc_light_settings=self.SETTINGS_VERSION,
            channels=[c["name"] for c in self.channels],
            power_percent=list(self.power),
            pwm_period_us=int(self.pwm_period),
            min_pulse_us=int(self.min_pulse),
            power_mode=self.power_mode,
            mode="SEQ" if self.mode else "CW",
            alex=dict(on_us=int(self.on_us), gap_us=int(self.gap_us)),
            no_gaps_window_us=[int(v) for v in self.window_us],
            custom_steps=[dict(duration_us=int(d), lasers=[k + 1 for k, on in enumerate(m[:len(self.channels)]) if on],
                               sync=bool(len(m) > len(self.channels) and m[len(self.channels)]))
                          for d, m in self.custom],
            run_time_s=float(self.run_s),
            diode_cal={k: dict(v) for k, v in self.diode_cal.items()},
            tcp_host=self.tcp_host,
            tcp_port=int(self.tcp_port),
        )

    def save_settings(self, path):
        import json

        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.settings(), f, indent=2)
        self.settings_path = path

    def load_settings(self, path):
        """Apply a settings file. Lasers are switched off, never on."""
        import json

        with open(path) as f:
            d = json.load(f)
        if "cmc_light_settings" not in d:
            raise ValueError("%s is not a cmc-light settings file" % os.path.basename(path))
        n = len(self.channels)

        def per_channel(values, default):
            values = list(values or [])
            return [values[k] if k < len(values) else default for k in range(n)]

        self.power = [min(100.0, max(0.0, float(v))) for v in per_channel(d.get("power_percent"), 100.0)]
        self.pwm_period = int(d.get("pwm_period_us", self.pwm_period))
        self.min_pulse = int(d.get("min_pulse_us", self.min_pulse))
        if d.get("power_mode") in seqcore.POWER_MODES:
            self.power_mode = d["power_mode"]
        self.mode = 1 if d.get("mode") == "SEQ" else 0
        alex = d.get("alex", {})
        self.on_us = int(alex.get("on_us", self.on_us))
        self.gap_us = int(alex.get("gap_us", self.gap_us))
        self.window_us = [int(v) for v in per_channel(d.get("no_gaps_window_us"), 1000)]
        steps = d.get("custom_steps")
        if steps:
            self.custom = [[int(s["duration_us"]), [(k + 1) in s.get("lasers", []) for k in range(n)]
                            + [bool(s.get("sync", False))]] for s in steps][: seqcore.MAX_STEPS]
        elif d.get("preset") in ("alex", "no_gaps"):  # files from before the table was the sequence
            self.apply_preset("alex" if d["preset"] == "alex" else "gapless")
        self.run_s = float(d.get("run_time_s", 0.0))
        self.diode_cal = {str(k): dict(w_per_au=float(v.get("w_per_au", 0.0)),
                                       points=[[float(a), float(b)] for a, b in v.get("points", [])])
                          for k, v in (d.get("diode_cal") or {}).items()}
        for k, mw in (d.get("monitor_mw_per_lux") or {}).items():  # settings from before the wizard
            self.diode_cal.setdefault(str(k), dict(w_per_au=float(mw) * 1e-3, points=[]))
        self.tcp_host = d.get("tcp_host", self.tcp_host)
        self.tcp_port = int(d.get("tcp_port", self.tcp_port))
        self.num.buf = {}
        self.settings_path = path
        # push to the instrument: everything off, then the loaded powers/PWM/mode
        self.all_off(remember=False)
        for k in range(n):
            self.push_power(k)
        self.push_pwm()
        self.push_mode()

    # -- device actions (all through the worker) ---------------------------- #
    def _adopt_device_emission(self):
        st = self.worker.status
        emission = st.get("emission")
        if not emission or len(emission) != len(self.enabled):
            return
        with self.worker.lock:
            pending = any(isinstance(key, tuple) and key[0] == "en" for key in self.worker.latest)
        if pending or not self.worker.jobs.empty() or st.get("t0", 0) <= self._enable_pushed_at:
            return
        self.enabled = list(emission)

    def _enable_sent(self):
        self._enable_pushed_at = time.monotonic()  # only polls started after this count

    def push_enable(self, k):
        self._enable_pushed_at = time.monotonic()
        if self.enabled[k]:
            self.resume = None   # switched on by hand: OFF/ON starts over
            self.stopped = False  # and the table plays again

        def job():
            # read the box when the job runs, so an all-off in between cannot be undone
            if self.src:
                self.src.set_emission(k + 1, self.enabled[k])
            self._enable_sent()
        self.worker.set_latest(("en", k), job)

    def check_playable(self, pwm_period=None, min_pulse=None, powers=None):
        """Compile locally what the instrument would compile; '' if it can be played."""
        n = len(self.channels)
        per = int(self.pwm_period if pwm_period is None else pwm_period)
        mn = int(self.min_pulse if min_pulse is None else min_pulse)
        pw = [p / 100.0 for p in (self.power if powers is None else powers)]
        steps = self.steps()  # the table is what plays, whatever the instrument is doing
        gpios = list(range(4, 4 + n))  # any distinct pins: timing does not depend on them
        try:
            seqcore.compile_program(steps, gpios, list(self.enabled), pw, per, mn,
                                    power_mode=self.power_mode)
        except ValueError as e:
            return str(e)
        return ""

    def push_power(self, k):
        p = self.power[k] / 100.0
        self.worker.set_latest(("pw", k), lambda: self.src and self.src.set_power(k + 1, p))

    def push_pwm(self):
        per, mn = int(self.pwm_period), int(self.min_pulse)
        pmode = "CYCLes" if self.power_mode == "cycles" else "PWM"

        def job():
            if self.src:
                self.src.set_pwm_period(per)
                self.src.set_min_pulse(mn)
                self.src.set_power_mode(pmode)
        self.worker.set_latest("pwm", job)

    def set_power_mode(self, key):
        old, self.power_mode = self.power_mode, key
        problem = self.check_playable()
        if problem:
            self.power_mode = old
            self.pwm_warning = "not applied: " + problem
            return
        self.pwm_warning = ""
        self.push_pwm()

    def push_mode(self):
        self._mode_pending += 1
        src_mode = "SEQ" if self.mode else "CW"

        def job():
            try:
                if self.src:
                    self.src.set_source(src_mode)
            finally:
                self._mode_pending -= 1
                self._mode_done_at = time.monotonic()
        self.worker.submit(job, "mode")

    SETTLE_S = 0.15  # a change has to stand this long before it is sent (drags, typing)

    def mcu_signature(self):
        """Everything the instrument needs to play the table. When this changes, upload."""
        return (tuple(self.steps()), self.cycles(), self.power_mode,
                int(self.pwm_period), int(self.min_pulse))

    def sync_sequence(self, force=False):
        """Keep the MCU playing what the table says, without anyone pressing anything.

        Called once per frame: the sequence is uploaded and started again whenever the
        table (or anything it compiles with) has changed and then stood still for a
        moment, so a slider drag or a typed duration is sent once, not per frame.
        """
        if self.src is None or self.stopped:
            return
        sig = self.mcu_signature()
        if sig != self._sync_sig:
            self._sync_sig, self._sync_at = sig, time.monotonic()
            return
        if self._sync_at is None or time.monotonic() - self._sync_at < self.SETTLE_S:
            return
        if sig == self._sync_sent and not force:
            self._sync_at = None
            return
        if self.check_playable():  # refuse to upload something the MCU would reject
            self._sync_at = None
            return
        self._sync_at, self._sync_sent = None, sig
        self.start_sequence(send_enables=False)

    def resync(self):
        """Send the table again at the next opportunity (after a reconnect, an ON)."""
        self._sync_sent = None
        self._sync_at = time.monotonic() - self.SETTLE_S

    def start_sequence(self, send_enables=True):
        """Give the table to the MCU and play it.

        *send_enables* is for the deliberate starts (ON): the automatic upload leaves
        the emission states alone, so it cannot undo an 'on' set from somewhere else.
        """
        steps, cycles = self.steps(), self.cycles()
        self._mcu_started_at = time.monotonic()
        self.mode = 1  # SEQuence:STARt puts the instrument in sequence mode
        pmode = "CYCLes" if self.power_mode == "cycles" else "PWM"
        enabled = list(self.enabled)
        if not any(enabled):
            self.message = "no laser is ticked 'on' in Laser power: the sequence would emit nothing"
        if send_enables:
            with self.worker.lock:  # the start job sends the enables; drop queued single ones
                self.worker.latest = {key: fn for key, fn in self.worker.latest.items()
                                      if not (isinstance(key, tuple) and key[0] == "en")}
            self._enable_pushed_at = time.monotonic()

        def job():
            src = self.src
            if not src:
                return
            if send_enables:  # what the panel shows is what plays
                src.set_emissions({k + 1: on for k, on in enumerate(enabled)})
                self._enable_sent()
            src.set_power_mode(pmode)
            src.load_steps(steps)
            src.set_cycles(cycles)
            src.set_sync_width(0)  # the sync output comes from the table's sync column only
            src.start()
        self.worker.submit(job, "start")

    def show_on_button(self):
        """ON replaces OFF while what OFF switched off can be restored (nothing is on now)."""
        if self.resume is None:
            return False
        if any(self.enabled) or self.worker.status.get("running"):
            return False
        return True

    def turn_on(self):
        """Restore what OFF switched off: the same lasers, and the sequence if one was playing."""
        resume, self.resume = self.resume, None
        if not resume:
            return
        self.stopped = False
        self.resync()
        self.enabled = list(resume["enabled"])
        for k in range(len(self.channels)):
            self.push_power(k)
        for k in range(len(self.channels)):
            self.push_enable(k)
        self.message = "restored: %s on%s" % (
            ", ".join(c["name"] for c, on in zip(self.channels, self.enabled) if on) or "no laser",
            "" if not resume["playing"] else ", sequence restarted")

    def mcu_playing(self):
        """The MCU plays a sequence: as polled, or just started here (the poll may still be old)."""
        st = self.worker.status
        started = self._mcu_started_at
        if started is not None and st.get("t0", 0) > started + 0.3 and not st.get("running"):
            self._mcu_started_at = started = None  # finished on its own (run time)
        return self.mode == 1 and (bool(st.get("running")) or started is not None)

    def all_off(self, remember=True):
        self.stopped = True  # OFF: nothing goes to the lasers until ON
        playing = "mcu" if self.mcu_playing() else None
        self._mcu_started_at = None
        if remember and (any(self.enabled) or playing):
            self.resume = dict(enabled=list(self.enabled), playing=playing)
        self.enabled = [False] * len(self.channels)
        self._enable_pushed_at = time.monotonic()
        with self.worker.lock:  # drop queued "on" commands so they cannot run after the stop
            self.worker.latest = {key: fn for key, fn in self.worker.latest.items()
                                  if not (isinstance(key, tuple) and key[0] == "en")}

        def job():
            if self.src:
                self.src.all_off()
            self._enable_sent()
        self.worker.submit(job, "all off")

    # -- frame ------------------------------------------------------------- #
    # -- window contents (each drawn inside its own window body) ---------------- #
    def draw_toolbar(self, w, h):
        self.sync_sequence()  # the table is kept on the MCU without anyone pressing upload
        if self.show_on_button():
            im.push_style_color(im.Col.BUTTON, (30, 130, 50, 255))
            im.push_style_color(im.Col.BUTTON_HOVERED, (50, 170, 70, 255))
            if im.button("ON##power", (90, 24)):
                self.turn_on()
        else:
            im.push_style_color(im.Col.BUTTON, (180, 30, 30, 255))
            im.push_style_color(im.Col.BUTTON_HOVERED, (220, 50, 50, 255))
            if im.button("OFF##power", (90, 24)):
                self.all_off()
        im.pop_style_color(2)
        im.same_line()
        if self.src is not None:
            label("connected (%s)" % self.src.link, colour=(120, 220, 120, 255))
        else:
            label("not connected", colour=(200, 160, 80, 255))
        im.same_line()
        self._mode_status()
        if self.worker.busy:
            im.same_line()
            label("(%s...)" % self.worker.busy, dim=True, last=not (self.worker.error or self.message))
        if self.worker.error:
            im.same_line()
            label(self.worker.error[:160], colour=(255, 110, 110, 255), last=True)
        elif self.message:
            im.same_line()
            label(self.message[:160], dim=True, last=True)

    def draw_connection(self, w, h):
        self._connection()

    def draw_lasers(self, w, h):
        self._lasers()

    def draw_sequence(self, w, h):
        self._sequence()

    def draw_preview(self, w, h):
        self._preview(w)

    def draw_file_dialog(self, w, h):
        if self.file_dialog is None:
            return
        result = self.file_dialog.draw(w, h)
        if result is None:
            return
        dialog, self.file_dialog = self.file_dialog, None
        mode = dialog.mode
        if not result:
            return
        try:
            if dialog.purpose == "steps":
                if mode == "save":
                    self.save_steps_csv(result)
                    self.message = "saved sequence %s" % result
                else:
                    self.load_steps_csv(result)
                    self.message = "loaded sequence %s (%d steps)" % (result, len(self.custom))
            elif mode == "save":
                self.save_settings(result)
                self.message = "saved %s" % result
            else:
                self.load_settings(result)
                self.message = "loaded %s (all lasers off)" % result
        except (OSError, ValueError, KeyError, TypeError) as e:
            self.message = "could not %s %s: %s" % (mode, dialog.what, e)
            print("[cmc-light] ERROR %s" % self.message, flush=True)

    def draw_about(self, w, h):
        from cmc_light import gui_dialogs as dlg

        if not dlg.draw_about(w, h, self.identity, GUI_VERSION):
            self.show_about = False

    def draw_tutorial(self, w, h):
        if self.tutorial is not None and not self.tutorial.draw(w, h):
            self.tutorial = None

    def draw_help(self, w, h):
        from cmc_light import gui_dialogs as dlg

        if self.help is None:
            self.help = dlg.HelpViewer()
        if not self.help.draw(w, h):
            self.show_help = False

    # -- menu commands --------------------------------------------------------- #
    def open_save_dialog(self):
        from cmc_light.gui_dialogs import FileDialog

        folder = os.path.dirname(self.settings_path) if self.settings_path else None
        name = os.path.basename(self.settings_path) if self.settings_path else "settings.json"
        self.file_dialog = FileDialog(mode="save", directory=folder, filename=name)

    def open_load_dialog(self):
        from cmc_light.gui_dialogs import FileDialog

        folder = os.path.dirname(self.settings_path) if self.settings_path else None
        # not-input: the laser panel's own settings file (its state), not measurement data
        self.file_dialog = FileDialog(mode="load", directory=folder)

    def open_steps_dialog(self, mode):
        from cmc_light.gui_dialogs import FileDialog

        folder = os.path.dirname(self.steps_path) if self.steps_path else None
        name = os.path.basename(self.steps_path) if self.steps_path else "sequence.csv"
        # not-input: the panel's own excitation sequence (CSV), tool state, not measurement data
        self.file_dialog = FileDialog(mode=mode, directory=folder, filename=name, ext=".csv",
                                      what="sequence (CSV)", purpose="steps")

    def save_steps_csv(self, path):
        text = steps_text.format_csv(self.steps(), self.lane_names())
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", newline="") as f:
            f.write(text)
        self.steps_path = path

    def load_steps_csv(self, path):
        with open(path, newline="") as f:
            steps = steps_text.parse_csv(f.read(), self.lane_names())
        if len(steps) > seqcore.MAX_STEPS:
            raise ValueError("%d steps, the instrument holds at most %d" % (len(steps), seqcore.MAX_STEPS))
        self.custom = self.rows_from_steps(steps)
        self.num.buf = {k: v for k, v in self.num.buf.items() if not k.startswith(("dur", "period"))}
        self.steps_path = path

    def start_tutorial(self):
        from cmc_light.gui_dialogs import Tutorial

        self.tutorial = Tutorial()

    def dropdown(self, key, current_label, width, labels, current, on_select):
        """A button that opens a emtk Popup list (drawn by the App above all windows)."""
        text = current_label
        while len(text) > 4 and im.calc_text_size(text + "...  v")[0] > width - 12:
            text = text[:-1]
        if text != current_label:
            text = text.rstrip() + "..."
        if im.button("%s  v##%s" % (text, key), (width, 0)):
            self.dropdown_request = (key, im.get_item_rect(), list(labels), current, on_select)

    def _connection(self):
        labels = [self.target_label(t) for t in self.targets] + ["TCP / WiFi"]
        self.target = min(self.target, len(labels) - 1)
        is_tcp = self.target == len(self.targets)
        is_sim = self.targets[self.target] == SIMULATOR if not is_tcp else False
        connected = self.src is not None
        avail = im.get_content_region_avail()[0]
        settings_w = 250.0 if is_tcp else 170.0
        drop_w = max(150.0, avail - settings_w - 100.0)

        def select(i):
            self.target = i

        row = flex(drop_w - 150.0)  # the dropdown stretches; the rest of the row does not
        row.__enter__()
        im.begin_disabled(connected)
        self.dropdown("device", labels[self.target], drop_w - 50, labels, self.target, select)
        im.same_line()
        if im.button("Scan", (44, 0)):
            self.rescan()
        im.same_line()
        if is_tcp:
            label("host")
            im.set_next_item_width(130)
            _, self.tcp_host, _ = text_field("##host", self.tcp_host)
            im.same_line()
            _, self.tcp_port = self.num("port", "port", self.tcp_port, 1, 65535, 56)
        elif is_sim:
            label("no hardware needed", dim=True)
        else:
            label("115200 baud", dim=True)
        im.end_disabled()
        im.same_line()
        if not connected:
            if im.button("Connect", (80, 0)):
                if is_tcp:
                    target = "tcp://%s:%d" % (self.tcp_host, self.tcp_port)
                else:
                    target = self.targets[self.target]
                self._connect(target)
        else:
            if im.button("Disconnect", (80, 0)):
                self.worker.submit(self.worker._disconnect, "disconnect")
        row.__exit__(None, None, None)
        if connected:
            im.text(self.identity)
        elif self.worker.busy == "scan":
            im.text_disabled("scanning serial ports for *IDN? ...")
        else:
            im.text_disabled("not connected")

    def _lasers(self):
        self._adopt_device_emission()
        duty = self.worker.status.get("duty") or [None] * len(self.channels)
        for k, ch in enumerate(self.channels):
            im.push_id(k)
            im.color_button("##c", hex_rgb(ch["color"]), 0, (18, 18))
            im.same_line()
            wl = ch.get("wavelength") or 0
            label(("%d %s" % (k + 1, ch["name"])) + (" %d nm" % wl if wl else ""), col=90)
            changed, self.enabled[k] = im.checkbox("on", self.enabled[k])
            if changed:
                self.push_enable(k)
            im.same_line()
            im.set_next_item_width(180)
            changed, self.power[k] = im.slider_float("##p", self.power[k], 0.0, 100.0, "%.1f %%")
            if changed:
                self.push_power(k)
            im.same_line()
            d = duty[k] if k < len(duty) else None
            label("achieved " + ("-" if d is None else "%.1f %%" % (100 * d)), dim=True, last=True)
            im.pop_id()
        label("PWM period", col=90)
        per = self.pwm_period
        c1, per = log_slider("pwm", per, 20, 1000000, 260,
                             "%s  (%.3g kHz)" % (fmt_us(per), 1000.0 / per))
        label("min pulse", col=90)
        mn = self.min_pulse
        c2, mn = log_slider("minp", mn, 1, 10000, 150, fmt_us(mn))
        if c1 or c2:
            problem = self.check_playable(pwm_period=per, min_pulse=mn)
            if problem:
                self.pwm_warning = "not applied: " + problem
            else:
                self.pwm_warning = ""
                self.pwm_period, self.min_pulse = per, mn
                self.push_pwm()
        label("low power", col=90)
        for idx, (key, choice) in enumerate((("cycles", "whole windows (no gaps)"),
                                              ("pwm", "PWM inside windows"))):
            if idx:
                im.same_line()
            if im.radio_button(choice + "##pmode%d" % idx, self.power_mode == key) \
                    and self.power_mode != key:
                self.set_power_mode(key)
        if self.pwm_warning:
            wrapped(self.pwm_warning, (255, 150, 90, 255))
        if self.power_mode == "cycles":
            wrapped("Sequences: a laser below 100 % lights its whole windows in that fraction "
                             "of the periods (averaged over 10-100 periods). CW always uses PWM.")
        else:
            wrapped("Power < 100 % is pulse-width modulation of the TTL line within each "
                             "on-window; 'achieved' is the duty after timing quantisation.")
        self._monitor()

    def _monitor(self):
        """The instrument's own light sensor: the total power of whatever is emitting.

        The sensor's "lux" is the human-eye weighting of white light; for a laser it is a
        relative reading (green reads far higher than blue at the same optical power).
        A reference measurement per laser turns it into mW.
        """
        lux = self.worker.status.get("monitor")
        if lux is None and not self.monitor_per_laser:
            return
        im.separator()
        label("power diode", col=90)
        lit = [k for k, on in enumerate(self.enabled) if on]
        total = None
        if lux is not None and len(lit) == 1:  # one laser: its own calibration applies
            total = self.diode_power(lit[0], lux)
        label(("%s  (%.2f a.u.)" % (fmt_power(total), lux)) if total is not None else
              ("%.2f a.u. total" % lux if lux is not None else "no reading"),
              dim=lux is None, colour=(150, 220, 150, 255) if total is not None else None)
        im.same_line()
        im.begin_disabled(bool(self.worker.busy) or self.src is None)
        if im.small_button("per laser"):
            self.measure_per_laser()
        im.same_line()
        if im.small_button("test diode"):
            self.strobe_test()
        im.end_disabled()
        im.same_line()
        if im.small_button("calibrate..."):
            self.diode_cal_open()
        if self.monitor_busy:
            im.same_line()
            label(self.monitor_busy, colour=(255, 190, 90, 255), last=True)
        else:
            label("", last=True)
        if self.monitor_per_laser:
            for k, ch in enumerate(self.channels):
                value = self.monitor_per_laser.get(k)
                if value is None:
                    continue
                watts = self.diode_power(k, value)
                im.color_button("##md%d" % k, hex_rgb(ch["color"]), 0, (12, 12))
                im.same_line()
                label("%-6s %8.2f a.u.%s%s" % (
                    ch["name"], value, "   = %s" % fmt_power(watts) if watts is not None else "",
                    "   %s" % self.monitor_note.get(k, "")), last=True)
        wrapped("Arbitrary units: the sensor weights light like the eye does, so a reading compares "
                "a laser with itself, not one colour with another. **calibrate...** turns a.u. into "
                "watts for one laser, from readings of a power meter.")

    # -- power diode calibration ------------------------------------------------ #
    # The diode reads arbitrary units weighted like the human eye, so one laser's
    # reading says nothing about another's. The wizard turns a.u. into watts for one
    # laser at a time: it drives that laser (alone) to a few powers and asks for the
    # power meter's reading at each, then fits watts per a.u. through zero.

    DCAL_LEVELS = (100.0, 75.0, 50.0, 25.0)

    def diode_cal_open(self):
        self.show_diode_cal = True
        if self.dcal is None:
            self.dcal = dict(laser=0, levels=list(self.DCAL_LEVELS), step=None, au=None,
                             dark=0.0, points=[], entry=1.0, unit=2, status="", busy=False,
                             before=None)

    def diode_cal_close(self):
        if self.dcal is not None and self.dcal.get("before") is not None:
            self.diode_cal_cancel()
        self.show_diode_cal = False

    def _dcal_restore(self, src, w):
        """Put the instrument back the way the wizard found it."""
        before = w.get("before")
        if not before or src is None:
            return
        src.set_exclusive(before["exclusive"])
        for k, p in enumerate(before["power"]):
            src.set_power(k + 1, p)
        src.set_emissions({k + 1: on for k, on in enumerate(before["on"])})
        self.enabled = list(before["on"])
        self.power = [100.0 * p for p in before["power"]]
        self._enable_pushed_at = time.monotonic()
        w["before"] = None
        self.resync()  # the table goes back to the MCU

    def diode_cal_start(self):
        """Measure the dark level, then the first power level."""
        w = self.dcal
        w.update(points=[], step=0, au=None, status="", busy=True)
        k = w["laser"]
        levels = list(w["levels"])

        def job():
            src = self.src
            if src is None:
                return
            n = src.n_channels
            try:
                w["before"] = dict(on=[src.emission(i + 1) for i in range(n)],
                                   power=[src.power(i + 1) for i in range(n)],
                                   exclusive=src.exclusive())
                src.abort()
                src.set_source("CW")
                src.set_exclusive(True)  # only the laser being calibrated may emit
                src.all_off()
                time.sleep(0.6)
                w["dark"] = self._dcal_read(src)
                self._dcal_apply(src, k, levels[0])
            finally:
                w["busy"] = False
        self.worker.submit(job, "diode calibration")

    def _dcal_read(self, src, n=5):
        """A settled diode reading: the sensor integrates over ~120 ms."""
        values = []
        for _ in range(n):
            time.sleep(0.16)
            values.append(src.monitor_lux())
        return sorted(values)[len(values) // 2]

    def _dcal_apply(self, src, k, level):
        """Drive laser k alone at *level* percent and read the diode."""
        w = self.dcal
        src.set_power(k + 1, level / 100.0)
        src.set_emission(k + 1, True)
        time.sleep(0.6)
        w["au"] = self._dcal_read(src) - w["dark"]

    def _dcal_goto(self, step):
        """Set the next power level and measure it (or finish when there are none left)."""
        w = self.dcal
        if step >= len(w["levels"]):
            self.diode_cal_finish()
            return
        w.update(step=step, au=None, busy=True)
        k, level = w["laser"], w["levels"][step]

        def job():
            src = self.src
            try:
                if src is not None:
                    self._dcal_apply(src, k, level)
            finally:
                w["busy"] = False
        self.worker.submit(job, "diode calibration")

    def diode_cal_record(self):
        """Keep the power meter reading the user typed for this level."""
        w = self.dcal
        if w["au"] is None:
            return
        watts = float(w["entry"]) * POWER_UNITS[w["unit"]][1]
        if watts <= 0:
            w["status"] = "type the power meter's reading first"
            return
        w["points"] = [p for p in w["points"] if p[0] != w["au"]] + [[w["au"], watts]]
        self._dcal_goto(w["step"] + 1)

    def diode_cal_finish(self):
        """Fit watts per a.u. through zero and keep it for this laser."""
        w = self.dcal
        k = w["laser"]
        pts = [(au, watt) for au, watt in w["points"] if au > 0 and watt > 0]
        if not pts:
            w["status"] = "no readings were recorded"
        else:
            num = sum(au * watt for au, watt in pts)
            den = sum(au * au for au, _ in pts)
            factor = num / den if den > 0 else 0.0
            worst = max(abs(watt - factor * au) / watt for au, watt in pts)
            self.diode_cal[str(k)] = dict(w_per_au=factor, points=[[au, watt] for au, watt in pts])
            name = self.channels[k]["name"]
            w["status"] = "%s: %s per a.u. from %d reading%s, worst miss %.0f %%" % (
                name, fmt_power(factor), len(pts), "" if len(pts) == 1 else "s", 100 * worst)
            self.message = "power diode calibrated for %s: %s per a.u." % (name, fmt_power(factor))
        w.update(step=None, au=None, busy=True)

        def job():
            try:
                self._dcal_restore(self.src, w)
            finally:
                w["busy"] = False
        self.worker.submit(job, "diode calibration")

    def diode_cal_cancel(self):
        w = self.dcal
        w.update(step=None, au=None, busy=True, status="cancelled")

        def job():
            try:
                self._dcal_restore(self.src, w)
            finally:
                w["busy"] = False
        self.worker.submit(job, "diode calibration")

    def diode_power(self, k, au):
        """*au* of laser k in watts, or None when that laser is not calibrated."""
        cal = self.diode_cal.get(str(k))
        if not cal or au is None:
            return None
        return cal["w_per_au"] * au

    def draw_diode_cal(self, width, height):
        w = self.dcal
        if w is None:
            self.diode_cal_open()
            w = self.dcal
        running = w["step"] is not None
        wrapped("Put the power meter where the laser goes, and read it there. The wizard drives "
                "one laser at a time (the others stay off) and asks for the meter's reading at a "
                "few powers; a.u. become watts for that laser only.")
        im.separator()
        label("laser", col=80)
        for k, ch in enumerate(self.channels):
            im.same_line()
            im.begin_disabled(running)
            if im.radio_button("%s##dcl%d" % (ch["name"], k), w["laser"] == k) and w["laser"] != k:
                w.update(laser=k, points=[], status="")
            im.end_disabled()
        im.same_line()
        cal = self.diode_cal.get(str(w["laser"]))
        label("calibrated: %s per a.u." % fmt_power(cal["w_per_au"]) if cal else "not calibrated",
              dim=not cal, last=True)

        if not running:
            im.begin_disabled(self.src is None or bool(w["busy"]))
            if im.button("start##dcal"):
                self.diode_cal_start()
            im.end_disabled()
            im.same_line()
            if cal and im.button("forget this laser##dcal"):
                self.diode_cal.pop(str(w["laser"]), None)
            im.same_line()
            label("%d power levels: %s %%" % (
                len(w["levels"]), ", ".join("%g" % v for v in w["levels"])), dim=True, last=True)
        else:
            name = self.channels[w["laser"]]["name"]
            im.text("step %d of %d: %s at %g %% power" % (
                w["step"] + 1, len(w["levels"]), name, w["levels"][w["step"]]))
            if w["busy"] or w["au"] is None:
                label("measuring the diode...", colour=(255, 190, 90, 255), last=True)
            else:
                label("diode reads", col=80)
                label("%.2f a.u. (dark %.2f)" % (w["au"], w["dark"]), last=True)
                label("meter says", col=80)
                _, w["entry"] = self.num("dcalv", "", float(w["entry"]), 1e-12, 1e6, 90, float)
                im.same_line()
                for i, (unit, _scale) in enumerate(POWER_UNITS):
                    if i:
                        im.same_line()
                    if im.radio_button("%s##dcu%d" % (unit, i), w["unit"] == i):
                        w["unit"] = i
                im.same_line()
                if im.button("record##dcal"):
                    self.diode_cal_record()
                im.same_line()
                if im.button("skip##dcal"):
                    self._dcal_goto(w["step"] + 1)
            im.same_line()
            if im.button("cancel##dcal"):
                self.diode_cal_cancel()
        if w["points"]:
            im.separator()
            for au, watt in w["points"]:
                label("%8.2f a.u.  =  %s" % (au, fmt_power(watt)), dim=True, last=True)
        if w["status"]:
            im.separator()
            wrapped(w["status"], (150, 220, 150, 255))

    def measure_per_laser(self):
        """Each laser's own power: the others must be dark while it is measured."""
        def job():
            src = self.src
            if src is None:
                return
            n = src.n_channels
            before_on = [src.emission(k + 1) for k in range(n)]
            before_source = src.source()
            was_exclusive = src.exclusive()
            self.monitor_busy = "measuring..."
            try:
                src.abort()
                src.set_source("CW")
                src.set_exclusive(True)  # one laser at a time: the others must be off
                src.all_off()
                time.sleep(0.5)
                dark = src.monitor_lux()
                out, note = {}, {}
                for k in range(n):
                    self.monitor_busy = "measuring %s..." % self.channels[k]["name"]
                    src.set_emission(k + 1, True)
                    time.sleep(0.5)
                    values = []
                    for _ in range(3):
                        values.append(src.monitor_lux())
                        time.sleep(0.15)
                    out[k] = sorted(values)[1] - dark
                    note[k] = "at %.0f %% power" % (100 * src.power(k + 1))
                    src.set_emission(k + 1, False)
                self.monitor_per_laser, self.monitor_note = out, note
                self.message = "power diode: " + ", ".join(
                    "%s %.1f a.u." % (self.channels[k]["name"], v) for k, v in sorted(out.items()))
            finally:
                self.monitor_busy = ""
                src.set_exclusive(was_exclusive)
                src.set_emissions({k + 1: on for k, on in enumerate(before_on)})
                self.enabled = list(before_on)
                self._enable_pushed_at = time.monotonic()
                self.resync()  # the table goes back to the MCU
        self.worker.submit(job, "power per laser")

    def strobe_test(self):
        """Switch the lasers on and off and see whether the diode follows: a working diode
        reads clearly more with light than without."""
        def job():
            src = self.src
            if src is None:
                return
            n = src.n_channels
            before_on = [src.emission(k + 1) for k in range(n)]
            before_source = src.source()
            self.monitor_busy = "testing the diode..."
            try:
                src.abort()
                src.set_source("CW")
                dark, lit = [], []
                for _ in range(3):
                    src.all_off()
                    time.sleep(0.45)
                    dark.append(src.monitor_lux())
                    src.set_emissions({k + 1: True for k in range(n)})
                    time.sleep(0.45)
                    lit.append(src.monitor_lux())
                src.all_off()
                d, l = sorted(dark)[1], sorted(lit)[1]
                ok = l > d + max(1.0, 0.2 * max(1.0, d))
                self.message = ("power diode %s: %.2f a.u. dark, %.2f a.u. with all lasers on"
                                % ("works" if ok else "sees no change", d, l))
            finally:
                self.monitor_busy = ""
                src.set_emissions({k + 1: on for k, on in enumerate(before_on)})
                self.enabled = list(before_on)
                self._enable_pushed_at = time.monotonic()
                self.resync()  # the table goes back to the MCU
        self.worker.submit(job, "diode test")

    def _mode_status(self):
        """What the instrument is doing. The table is uploaded and played by itself;
        OFF stops it, ON starts it again."""
        st = self.worker.status
        dev = st.get("source")
        if dev in ("CW", "SEQ") and not self._mode_pending \
                and st.get("t0", 0) > self._mode_done_at:
            self.mode = 1 if dev == "SEQ" else 0
        running = st.get("running")
        if self.stopped:
            text, colour = "stopped (press ON)", None
        elif running:
            text, colour = "sequence on the MCU (running)", (120, 220, 120, 255)
        elif self._sync_at is not None or self.worker.busy == "start":
            text, colour = "uploading the table...", None
        elif not any(self.enabled):
            text, colour = "idle (nothing ticked)", None
        else:
            text, colour = "sequence on the MCU (idle)", None
        label(text, colour=colour, dim=colour is None, last=True)

    def _sequence(self):
        n = len(self.channels)
        names = [c["name"] for c in self.channels]
        lo, hi = self.duration_limits()
        running = self.worker.status.get("running")
        st = self.worker.status
        if st:
            tm = st.get("timing", {})
            p = tm.get("period_us") or 1
            label("%s  cycles %d  %.3f ms  edges %d  late max %d us" % (
                "RUNNING" if running else "idle", st.get("cycles", 0), p / 1000.0,
                tm.get("edges", 0), tm.get("late_max_us", 0)), dim=not running, last=True)
            if not running and not any(self.enabled):  # wrapped: it must not widen the window
                wrapped("Nothing to play: tick a laser 'on' in Laser power.",
                        (230, 190, 90, 255))
        else:
            label("not connected", dim=True, last=True)
        _, run_ms = labelled_slider("run time", "s_run", int(self.run_s * 1000), 100, 3_600_000,
                                    200, allow_zero=True,
                                    fmt=lambda v: "%g s" % (v / 1000.0), col=110)
        if run_ms != int(self.run_s * 1000):
            self.run_s = run_ms / 1000.0
        im.same_line()
        _, self.run_s = self.num("run", "s", self.run_s, 0, 1e7, 70, float)
        im.same_line()
        cyc = self.cycles()
        label("endless" if cyc == 0 else "= %d cycles" % cyc, dim=True, last=True)
        im.separator()
        wrapped("The Sequence table is the sequence (steps %s .. %s, played by the MCU). "
                "Changing a preset below rewrites the table right away." % (fmt_us(lo), fmt_us(hi)))
        self._step_editor(n, names)
        self._total_period_field(n)
        im.separator()
        im.text("ALEX preset: each laser in turn, a dark gap after each")
        c1, self.on_us = labelled_slider("on-window", "s_on", self.on_us, lo, hi, 200, col=110)
        im.same_line()
        c2, self.on_us = self.num("on", "us", self.on_us, lo, hi, 80)
        c3, self.gap_us = labelled_slider("dark gap", "s_gap", self.gap_us, lo, hi, 200,
                                          allow_zero=True, col=110)
        im.same_line()
        c4, self.gap_us = self.num("gap", "us", self.gap_us, 0, hi, 80)
        if im.button("ALEX to table") or c1 or c2 or c3 or c4:
            self.apply_preset("alex")  # every change goes straight into the table
        im.separator()
        im.text("gapless preset: lasers back to back, each its own window")
        changed = False
        for k in range(n):
            im.color_button("##w%d" % k, hex_rgb(self.channels[k]["color"]), 0, (14, 14))
            im.same_line()
            c1, self.window_us[k] = labelled_slider(names[k], "s_win%d" % k,
                                                    self.window_us[k], lo, hi, 200, col=110)
            im.same_line()
            c2, self.window_us[k] = self.num("win%d" % k, "us", self.window_us[k], lo, hi, 80)
            changed = changed or c1 or c2
        if im.button("gapless to table") or changed:
            self.apply_preset("gapless")

    def _total_period_field(self, n):
        """Edit the whole period; the table's steps are rescaled to it."""
        period = seqcore.period_us(self.steps())
        lo, hi = self.duration_limits()
        m = max(1, len(self.custom))
        changed, new = labelled_slider("total period", "s_period", period, max(m, lo * m), hi, 200, col=110)
        im.same_line()
        c2, new2 = self.num("period", "us (Return)", period, m, 60000000, 90, live=False)
        if c2:
            changed, new = True, new2
        if not changed or new == period or not self.custom:
            return
        scale = new / float(period)
        for step in self.custom:  # rescale, never below the shortest step
            step[0] = max(lo, int(round(step[0] * scale)))
        self.custom[-1][0] = max(lo, new - sum(st[0] for st in self.custom[:-1]))
        self.num.buf = {k: v for k, v in self.num.buf.items() if not k.startswith("dur")}

    def _step_editor(self, n, names):
        names = self.lane_names()
        period = seqcore.period_us(self.steps())
        label("table: %d steps, %.3f ms" % (len(self.custom), period / 1000.0))
        im.same_line()
        if im.button("open Sequence table"):
            self.show_table = True
        label("as text", col=110)
        text_w = max(160.0, min(420.0, im.get_content_region_avail()[0] - 10.0))
        im.set_next_item_width(text_w)
        with flex(text_w - 160.0):
            _, self.custom_text, entered = text_field("##seqtext", self.custom_text,
                                                      "e.g. 1000 B+S; 100 -; 500 G+R; 2ms 1+3")
        if im.button("apply text") or entered:
            try:
                steps = steps_text.parse(self.custom_text, names)
                if len(steps) > seqcore.MAX_STEPS:
                    raise ValueError("too many steps (max %d)" % seqcore.MAX_STEPS)
                self.custom = self.rows_from_steps(steps)
                self.text_error = ""
            except ValueError as e:
                self.text_error = str(e)
        im.same_line()
        if im.button("to text"):
            self.custom_text = steps_text.format_steps(self.steps(), names)
            self.text_error = ""
        if self.text_error:
            wrapped(self.text_error, (255, 110, 110, 255))

    def draw_table(self, w, h):
        """Sequence table window: toolbar; the spreadsheet itself is an overlay below it."""
        sheet = self.sheet
        if im.small_button("insert row"):
            sheet.insert_row()
        im.same_line()
        if im.small_button("delete row"):
            sheet.delete_row()
        im.same_line()
        if im.small_button("duplicate"):
            sheet.duplicate_row()
        im.same_line()
        if im.small_button("up"):
            sheet.move_row(-1)
        im.same_line()
        if im.small_button("down"):
            sheet.move_row(1)
        im.same_line()
        if im.small_button("copy"):
            if sheet.clipboard_set:
                sheet.clipboard_set(sheet.copy_text())
        im.same_line()
        if im.small_button("paste"):
            if sheet.clipboard_get:
                try:
                    sheet.message = "pasted %d rows" % sheet.paste_text(sheet.clipboard_get() or "")
                except ValueError as e:
                    sheet.message = "paste: %s" % e
        if im.small_button("load CSV..."):
            self.open_steps_dialog("load")
        im.same_line()
        if im.small_button("save CSV..."):
            self.open_steps_dialog("save")
        im.same_line()
        period = sum(int(d) for d, _ in self.custom)
        label("%d steps, %.3f ms" % (len(self.custom), period / 1000.0), dim=True, last=True)
        if sheet.message:
            wrapped(sheet.message, (255, 190, 90, 255))
        _, cy = im.get_cursor_screen_pos()
        self.table_top = cy + 2.0
        from cmc_light.spreadsheet import HEAD_H, ROW_H

        # room for the spreadsheet (an overlay): all columns, the header and three rows
        im.dummy(sum(cw for _, cw in sheet.columns()) + 10.0, HEAD_H + 3 * ROW_H + 6.0)

    def _preview(self, w):
        editable = True  # the preview always shows (and edits) the sequence
        try:
            steps = self.steps()
            enabled = self.enabled
            powers = [p / 100.0 for p in self.power]
            pmode = self.power_mode if self.mode == 1 else "pwm"
            dith = seqcore.dithered(enabled, powers, pmode)
            factor = 1
            if any(dith):
                gp = list(range(4, 4 + len(enabled)))
                factor = seqcore.compile_program(steps, gp, list(enabled), powers, self.pwm_period,
                                                 self.min_pulse, power_mode=pmode)["cycle_factor"]
            _, intervals, duty = seqcore.channel_intervals(
                steps, enabled, powers, self.pwm_period, self.min_pulse, factor, pmode)
            period = seqcore.period_us(steps)
            if factor > 1:  # dithered lasers: show their whole windows, shade = share of lit periods
                wins = preview_edit.laser_windows(steps, len(enabled))
                intervals = [wins[k] if dith[k] else intervals[k][:] for k in range(len(enabled))]
        except Exception as e:
            wrapped(str(e), (255, 110, 110, 255))
            self._pv = None
            return
        if not any(self.enabled):
            im.text_colored((230, 190, 90, 255), "no laser is switched 'on' - nothing will be emitted")
        periods = 2
        lane_h, label_w = 22.0, 70.0
        x0, y0 = im.get_cursor_screen_pos()
        width = max(100.0, w - 20 - label_w)
        dl = im.get_window_draw_list()
        lanes = list(enumerate(self.channels))
        step_lane = 1 if editable else 0
        sync_lane = 1  # the sync output (D5), from the table's sync column
        n_lanes = step_lane + len(lanes) + sync_lane
        total = periods * period
        scale = width / float(total)
        xs = x0 + label_w

        def xpos(t):
            return xs + t * scale

        drag = getattr(self, "_pv_drag", None)
        hover = getattr(self, "_pv_hover", None)
        durations = [d for d, _ in steps]
        if editable:
            y = y0
            dl.add_text((x0, y + 3), (160, 165, 175, 255), "steps")
            t = 0
            for idx, (dur, mask) in enumerate(steps):
                for p in range(periods):
                    a, b = xpos(p * period + t), xpos(p * period + t + dur)
                    shade = (60, 64, 76, 255) if idx % 2 == 0 else (48, 52, 62, 255)
                    if mask == 0:
                        shade = (30, 32, 38, 255)
                    active = (drag and drag[0] == "move" and drag[1] == idx) or (hover == ("move", idx))
                    if active:
                        shade = (70, 110, 170, 255)
                    dl.add_rect_filled((a + 1, y + 3), (max(a + 2, b - 1), y + lane_h - 3), shade)
                t += dur
            for jdx, tb in preview_edit.boundaries(durations):
                for p in range(periods):
                    x = xpos(p * period + tb)
                    active = (drag and drag[0] == "edge" and drag[1] == jdx) or hover == ("edge", jdx)
                    col = (255, 210, 90, 255) if active else (150, 160, 180, 255)
                    dl.add_rect_filled((x - 2, y + 2), (x + 2, y + y0 - y0 + lane_h * n_lanes - 2), col) \
                        if active else dl.add_rect_filled((x - 1, y + 2), (x + 1, y + lane_h - 2), col)
        for row, (k, ch) in enumerate(lanes):
            y = y0 + (row + step_lane) * lane_h
            dl.add_text((x0, y + 3), (200, 200, 200, 255), ch["name"])
            dl.add_line((xpos(0), y + lane_h - 4), (xpos(total), y + lane_h - 4), (80, 80, 80, 255))
            col = hex_rgb(ch["color"])
            granted = preview_edit.laser_windows(steps, len(self.channels))[k] if editable else []
            for p in range(periods):
                for a_us, b_us in granted:  # the window the sequence grants, lightly
                    a, b = xpos(p * period + a_us), xpos(p * period + b_us)
                    light = hex_rgb(ch["color"], 70)
                    active = drag and drag[0].startswith("lwin") and drag[1] == k
                    dl.add_rect_filled((a, y + 3), (max(a + 1, b), y + lane_h - 3), light)
                    if active or (hover and hover[0].startswith("lwin") and hover[1] == k):
                        dl.add_rect((a, y + 3), (max(a + 1, b), y + lane_h - 3), (255, 210, 90, 255))
                lit_col = col if factor == 1 or not dith[k] else hex_rgb(ch["color"], int(90 + 165 * duty[k]))
                for a_us, b_us in intervals[k]:  # what is actually lit (PWM for power < 100 %)
                    if a_us >= period:
                        break
                    a, b = xpos(p * period + a_us), xpos(p * period + min(b_us, period))
                    dl.add_rect_filled((a, y + 5), (max(a + 1, b), y + lane_h - 5), lit_col)
        if sync_lane:
            y = y0 + (n_lanes - 1) * lane_h
            dl.add_text((x0, y + 3), (200, 200, 200, 255), "sync")
            dl.add_line((xpos(0), y + lane_h - 4), (xpos(total), y + lane_h - 4), (80, 80, 80, 255))
            n = len(self.channels)
            step_sync = preview_edit.laser_windows(steps, n + 1)[n]
            lit = preview_edit.merge_windows(step_sync)
            for p in range(periods):
                for a_us, b_us in lit:
                    a, b = xpos(p * period + a_us), xpos(p * period + b_us)
                    dl.add_rect_filled((a, y + 8), (max(a + 1, b), y + lane_h - 4), (230, 230, 230, 255))
                for a_us, b_us in step_sync:  # sync steps can be dragged like laser bars
                    a, b = xpos(p * period + a_us), xpos(p * period + b_us)
                    active = (drag and drag[0].startswith("lwin") and drag[1] == n) or \
                        (hover and hover[0].startswith("lwin") and hover[1] == n)
                    if active:
                        dl.add_rect((a, y + 3), (max(a + 1, b), y + lane_h - 3), (255, 210, 90, 255))
        for p in range(periods + 1):
            x = xpos(p * period)
            dl.add_line((x, y0), (x, y0 + n_lanes * lane_h), (120, 120, 120, 255))
        with flex(width - 160.0):  # the lanes stretch with the window
            im.dummy(label_w + width, n_lanes * lane_h + 4)
        hint = "; drag a bar to move a laser (or sync), its ends to change its length; bars may overlap"
        wrapped("%d periods of %.3f ms; achieved power: %s%s" % (
            periods, period / 1000.0, ", ".join("%.0f %%" % (100 * d) for d in duty), hint))
        if factor > 1:
            wrapped("whole windows: %s lit in that share of every %d periods (no gaps inside a window)"
                             % (", ".join("%s %d/%d" % (self.channels[k]["name"], round(duty[k] * factor), factor)
                                          for k in range(len(dith)) if dith[k]), factor))
        self._pv = dict(xs=xs, y0=y0, lane_h=lane_h, n_lanes=n_lanes, step_lane=step_lane, steps=steps,
                        sync_lane=sync_lane,
                        scale=scale, period=period, periods=periods, durations=durations,
                        intervals=intervals, editable=editable, width=width) if editable else None

    # -- dragging in the timing preview ----------------------------------------- #
    def _pv_target(self, px, py):
        pv = getattr(self, "_pv", None)
        if not pv:
            return None
        xs, y0, lh, scale = pv["xs"], pv["y0"], pv["lane_h"], pv["scale"]
        if not (xs - 6 <= px <= xs + pv["width"] + 6 and y0 <= py < y0 + pv["n_lanes"] * lh):
            return None
        t_abs = (px - xs) / scale
        period = pv["period"]
        row = int((py - y0) // lh) - pv["step_lane"]
        n = len(self.channels) + (1 if pv["sync_lane"] else 0)
        if 0 <= row < n:  # a laser (or the sync) lane: that lane's own windows
            t = t_abs % period
            wins = preview_edit.laser_windows(pv["steps"], len(self.channels) + 1)[row]
            px_mod = xs + t * scale
            for idx, (ws, we) in enumerate(wins):
                if abs(xs + ws * scale - px_mod) <= 5:
                    return ("lwin_edge", row, idx, "start")
                if abs(xs + we * scale - px_mod) <= 5:
                    return ("lwin_edge", row, idx, "end")
            for idx, (ws, we) in enumerate(wins):
                if ws <= t < we:
                    return ("lwin_move", row, idx)
            return None
        for jdx, tb in preview_edit.boundaries(pv["durations"]):
            for p in range(pv["periods"]):
                if abs((p * period + tb) * scale + xs - px) <= 5:
                    return ("edge", jdx)
        t = t_abs % period
        return ("move", preview_edit.step_at(pv["durations"], t))

    def preview_hover(self, px, py):
        self._pv_hover = self._pv_target(px, py)

    def preview_press(self, px, py):
        target = self._pv_target(px, py)
        if target is None:
            return False
        base_steps = [(d, sum(1 << k for k, b in enumerate(on) if b)) for d, on in self.custom_rows()]
        self._pv_drag = (target[0], target[1], px, [d for d, _ in self.custom], target, base_steps)
        return True

    def preview_drag(self, px):
        drag = getattr(self, "_pv_drag", None)
        pv = getattr(self, "_pv", None)
        if not drag or not pv:
            return
        kind, idx, x_start, base = drag[:4]
        dt = preview_edit.snap((px - x_start) / pv["scale"], sum(base))
        lo, _hi = self.duration_limits()
        if kind.startswith("lwin"):
            target, base_steps = drag[4], drag[5]
            n = len(self.channels) + 1  # lasers and the sync lane
            period = sum(base)
            wins = preview_edit.laser_windows(base_steps, n)
            if kind == "lwin_move":
                wins = preview_edit.move_window(wins, target[1], target[2], dt, period, lo)
            else:
                wins = preview_edit.resize_window(wins, target[1], target[2], target[3], dt, period, lo)
            steps = preview_edit.steps_from_windows(wins, period, lo)
            self.custom = self.rows_from_steps(steps)
            return
        if kind == "edge":
            new = preview_edit.drag_boundary(base, idx, dt, lo)
        else:
            new = preview_edit.move_step(base, idx, dt, lo)
        for step, d in zip(self.custom, new):
            step[0] = d
        self.num.buf = {k: v for k, v in self.num.buf.items() if not k.startswith("period")}

    def preview_release(self):
        self._pv_drag = None


# --------------------------------------------------------------------------- #
TOOLBAR_H = 30.0

QT_KEY_RETURN, QT_KEY_ENTER = 0x01000004, 0x01000005


def qt_key_text(key, text):
    """Text that should be *typed* for a key press.

    Qt attaches text to editing keys too (Backspace '\\x08', Delete '\\x7f', Tab...).
    emtk treats any text as typing, so Backspace/Delete did nothing. Special keys
    carry no text; Return keeps '\\r', which the fields use as 'confirm'.
    """
    if int(key) in (QT_KEY_RETURN, QT_KEY_ENTER):
        return "\r"
    if int(key) >= 0x01000000:
        return ""
    return "".join(c for c in (text or "") if c >= " " and c != "\x7f")


class App:
    """Window content: emtk MenuBar, a toolbar strip, and chimol-style panel windows."""

    def __init__(self, panel: LaserGui, on_exit=None, state_path=None, sensor_panel=None):
        import emtk
        from emtk.widgets.menus import Menu, MenuBar, MenuItem

        from cmc_light.windows import WindowManager

        self.panel = panel
        self.on_exit = on_exit
        from cmc_light.sense_gui import SensorPanel

        self.sensor = sensor_panel if sensor_panel is not None else SensorPanel(panel)
        if panel.on_scanned is None:
            panel.on_scanned = self.sensor.autoconnect
        self.toolbar_io, self.toolbar_storage = emtk.IO(), {}
        self.wm = WindowManager(top=MENU_H + TOOLBAR_H, state_path=state_path)
        self.items = {
            "save": MenuItem("Save settings...", "Ctrl+S"),
            "load": MenuItem("Load settings...", "Ctrl+O"),
            "exit": MenuItem("Exit", "Ctrl+Q"),
            "win_connection": MenuItem("Connection", checkable=True, checked=True),
            "win_lasers": MenuItem("Laser power", checkable=True, checked=True),
            "win_sequence": MenuItem("Sequence programmer", checkable=True, checked=True),
            "win_preview": MenuItem("Timing preview", checkable=True, checked=True),
            "win_table": MenuItem("Sequence table", checkable=True, checked=True),
            "win_sensor": MenuItem("Light sensor", checkable=True, checked=True),
            "win_beam": MenuItem("Beam profile", checkable=True, checked=True),
            "win_calibration": MenuItem("Sensor setup", checkable=True, checked=False),
            "win_corrections": MenuItem("Corrections", checkable=True, checked=False),
            "reset_layout": MenuItem("Reset window layout"),
            "about": MenuItem("About"),
            "tutorial": MenuItem("Step by step tutorial"),
            "help": MenuItem("Help", "F1"),
        }
        it = self.items
        self.menubar = MenuBar([
            Menu("File", [it["save"], it["load"], None, it["exit"]]),
            Menu("View", [it["win_connection"], it["win_lasers"], it["win_sequence"],
                          it["win_table"], it["win_preview"], None, it["win_sensor"], it["win_beam"],
                          it["win_calibration"], it["win_corrections"],
                          None, it["reset_layout"]]),
            Menu("Help", [it["about"], it["tutorial"], None, it["help"]]),
        ])
        self._size = (0.0, 0.0, 0.0, 0.0)
        self._built = False
        self._user_layout = False  # True once the user pressed anywhere: the layout is theirs
        self.popup = None  # (Popup, items, on_select)
        self._press_target = None  # "toolbar" | Window

    # -- windows --------------------------------------------------------------- #
    def _build_windows(self, w, h):
        from cmc_light.windows import Window

        from cmc_light.windows import GAP

        p, top = self.panel, self.wm.top
        # apart by a small gap: every window moves on its own until it is snapped onto another
        left_w = max(420.0, min(620.0, w * 0.46))
        right_x = left_w + GAP
        right_w = max(360.0, w - right_x)
        avail = h - top
        add = self.wm.add
        add(Window("connection", "Connection", 0.0, top, left_w, 130.0 - GAP, draw=p.draw_connection))
        add(Window("lasers", "Laser power", 0.0, top + 130.0, left_w, 240.0 - GAP, draw=p.draw_lasers,
                   min_w=380.0))
        add(Window("preview", "Timing preview", 0.0, top + 370.0, left_w,
                   max(160.0, avail - 370.0), draw=p.draw_preview))
        seq_h = max(300.0, avail * 0.55)
        add(Window("sequence", "Sequence programmer", right_x, top, right_w, seq_h - GAP,
                   draw=p.draw_sequence, min_w=380.0))
        add(Window("table", "Sequence table", right_x, top + seq_h, right_w,
                   max(200.0, avail - seq_h), draw=p.draw_table, overlay=self._table_overlay,
                   scroll=self._table_scroll, on_close=self._close_table, min_w=380.0))
        sp = self.sensor
        add(Window("sensor", "Light sensor", w - 560.0, top, 560.0, 380.0, draw=sp.draw_sensor, min_w=420.0))
        add(Window("beam", "Beam profile", w - 560.0, top + 384.0, 560.0, 420.0, draw=sp.draw_beam, min_w=420.0))
        add(Window("calibration", "Sensor setup", max(0.0, w - 620.0), top + 60.0, 560.0, 400.0,
                   draw=sp.draw_calibration, visible=False, on_close=self._close_calibration))
        add(Window("corrections", "Corrections", max(0.0, w - 660.0), top + 120.0, 520.0, 430.0,
                   draw=sp.draw_corrections, visible=False, on_close=self._close_corrections))
        add(Window("diodecal", "Power diode calibration", 60.0, top + 100.0, 540.0, 320.0,
                   draw=p.draw_diode_cal, visible=False, on_close=self._close_diode_cal))
        dialog = dict(visible=False, measure=False)  # dialogs fill whatever size they get
        add(Window("file", "File", (w - 580) / 2, top + 40.0, 580.0, 440.0,
                   draw=p.draw_file_dialog, modal=True, on_close=self._close_file, **dialog))
        add(Window("about", "About cmc-light", (w - 520) / 2, top + 60.0, 520.0, 280.0,
                   draw=p.draw_about, modal=True, on_close=self._close_about, **dialog))
        add(Window("tutorial", "Tutorial", max(0.0, w - 470.0), max(top, h - 290.0), 460.0, 270.0,
                   draw=p.draw_tutorial, on_close=self._close_tutorial, **dialog))
        add(Window("help", "Help", max(0.0, w - 700.0), top, 690.0, max(320.0, avail),
                   draw=p.draw_help, overlay=self._help_overlay, scroll=self._help_scroll,
                   on_close=self._close_help, **dialog))
        for key in ("file", "about", "tutorial", "help"):
            self.wm.get(key).visible = False  # dialogs never reopen from a saved layout
        self._built = True

    def _tile_defaults(self, w, h):
        """Default layout from what each window's contents need: columns with a small gap.

        Lasers | sequence | light sensor. When the main window is too narrow for the third
        column, the sensor windows sit over the right edge (move or hide them via View).
        """
        from cmc_light.windows import GAP

        wm, top = self.wm, self.wm.top
        get = wm.get
        left = [get("connection"), get("lasers"), get("preview")]
        middle = [get("sequence"), get("table")]
        right = [get("sensor"), get("beam")]
        left_w = max([win.content_w for win in left] + [w * 0.30])
        mid_w = max(win.content_w for win in middle)
        sensor_w = max([win.content_w for win in right] + [SENSOR_COLUMN_W])
        if w >= left_w + mid_w + SENSOR_COLUMN_W + 2 * GAP:  # a fixed rule: the layout must not flip
            mid_w = max(mid_w, w - left_w - sensor_w - 2 * GAP)
            sensor_x = left_w + mid_w + 2 * GAP
        else:
            mid_w = max(mid_w, w - left_w - GAP)
            sensor_x = max(0.0, w - sensor_w)
        placed = {}

        def column(wins, x, width):
            y = top
            for win in wins:
                # room for contents that arrive later (a sensor reading adds its table)
                need = max(win.content_h, RESERVED_H.get(win.key, 0.0))
                hh = need if win is not wins[-1] else max(need, h - y)
                placed[win.key] = (x, y, width, hh)
                y += hh + GAP

        column(left, 0.0, left_w)
        column(middle, left_w + GAP, mid_w)
        column(right, sensor_x, sensor_w)
        for key, (x, y, ww, hh) in placed.items():
            win = get(key)
            win.defaults.update(x=x, y=y, w=ww, h=hh)
            if key in wm._states:  # a saved layout wins over the default one
                continue
            win.x, win.y, win.w, win.h = x, y, ww, hh
            win.desired_w, win.desired_h = ww, hh
        wm.layout(w, h)

    def _close_calibration(self):
        self.sensor.show_calibration = False

    def _close_corrections(self):
        self.sensor.show_corrections = False

    def _close_diode_cal(self):
        self.panel.diode_cal_close()

    def _close_table(self):
        self.panel.show_table = False

    def _table_box(self, body):
        bx, by, bw, bh = body
        top = self.panel.table_top if self.panel.table_top is not None else by + 50.0
        top = max(by, min(top, by + bh - 30.0))
        return (bx + 4.0, top, bw - 8.0, by + bh - top - 4.0)

    def _table_overlay(self, painter, body):
        self.panel.sheet.draw(painter, *self._table_box(body))

    def _table_scroll(self, rows, px, py):
        sheet = self.panel.sheet
        x, y, w, h = sheet._box
        if x <= px < x + w and y <= py < y + h:
            sheet.scroll(rows)
            return True
        return False

    def _close_file(self):
        self.panel.file_dialog = None

    def _close_about(self):
        self.panel.show_about = False

    def _close_tutorial(self):
        self.panel.tutorial = None

    def _close_help(self):
        self.panel.show_help = False

    def _help_overlay(self, painter, body):
        hv = self.panel.help
        if hv is not None:
            hv.view.draw(painter, *hv.place(body))

    def _help_scroll(self, rows, px, py):
        hv = self.panel.help
        if hv is not None and hv.content_box is not None:
            bx, by, bw, bh = hv.content_box
            if bx <= px < bx + bw and by <= py < by + bh:
                hv.view.scroll(rows)
                return True
        return False

    def _sync_windows(self):
        """Dialog windows follow the panel's flags; menu ticks follow visibility."""
        p, wm = self.panel, self.wm
        for key, wanted in (("file", p.file_dialog is not None), ("about", p.show_about),
                            ("tutorial", p.tutorial is not None), ("help", p.show_help),
                            ("table", p.show_table), ("calibration", self.sensor.show_calibration),
                            ("corrections", self.sensor.show_corrections),
                            ("diodecal", p.show_diode_cal)):
            win = wm.get(key)
            if wanted and not win.visible:
                wm.show(key)
            elif not wanted and win.visible:
                win.visible = False
        if p.file_dialog is not None:
            wm.get("file").title = p.file_dialog.title
        for key in ("connection", "lasers", "sequence", "preview", "table", "sensor", "beam",
                    "calibration", "corrections"):
            self.items["win_" + key].checked = wm.get(key).visible

    # -- commands ------------------------------------------------------------- #
    def command(self, name):
        p = self.panel
        if name == "save":
            p.open_save_dialog()
        elif name == "load":
            p.open_load_dialog()
        elif name == "exit":
            if self.on_exit is not None:
                self.on_exit()
        elif name == "about":
            p.show_about = True
        elif name == "tutorial":
            p.start_tutorial()
        elif name == "help":
            p.show_help = True
        elif name.startswith("win_"):
            key = name[4:]
            win = self.wm.get(key)
            if key == "table":
                p.show_table = not win.visible
            if key == "calibration":
                self.sensor.show_calibration = not win.visible
            if key == "corrections":
                self.sensor.show_corrections = not win.visible
            self.wm.show(key, not win.visible)
        elif name == "reset_layout":
            self.wm.reset_layout()
            self._tile_defaults(*self.wm.size)
            for key in ("file", "about", "tutorial", "help"):
                self.wm.get(key).visible = False
        self._sync_windows()

    # -- host contract ---------------------------------------------------------- #
    def draw(self, painter, x, y, w, h):
        import emtk

        self._size = (x, y, w, h)
        if not self._built:
            self._build_windows(w, h)
        self._sync_windows()
        self.menubar.set_viewport(x + w, y + h)
        painter.fill_rect(x, y + MENU_H, w, TOOLBAR_H, (32, 34, 42, 255))
        with emtk.frame(painter, (x, y + MENU_H, w, TOOLBAR_H), io=self.toolbar_io,
                        storage=self.toolbar_storage):
            im.begin("toolbar", (x, y + MENU_H, w, TOOLBAR_H), im.WindowFlags.NO_TITLE_BAR)
            modal = self.wm.modal_window() is not None
            im.begin_disabled(modal)
            self.panel.draw_toolbar(w, TOOLBAR_H)
            im.end_disabled()
            im.end()
        self.wm.layout(w, h)
        self.wm.paint(painter)
        if not self._user_layout:  # until the user touches it, the default layout fits the contents
            self._tile_defaults(w, h)
        self._open_requested_dropdown()
        if self.popup is not None:
            self.popup[0].draw(painter, x, y, w, h)
        self.menubar.draw(painter, x, y, w, MENU_H)
        self._sync_windows()

    def _open_requested_dropdown(self):
        req, self.panel.dropdown_request = self.panel.dropdown_request, None
        if req is None:
            return
        from emtk.widgets.menus import MenuItem, Popup

        _key, (rx, ry, rw, rh), labels, current, on_select = req
        items = [MenuItem(label, checked=(i == current)) for i, label in enumerate(labels)]
        popup = Popup(items)
        popup.open_at(rx, ry + rh)
        self.popup = (popup, items, on_select)

    def _menu_open(self):
        return any(m.open for m in self.menubar.menus)

    def _ios(self):
        return [self.toolbar_io] + [win.io for win in self.wm.windows if win.io is not None]

    def hover(self, px, py, *_box):
        for io in self._ios():
            io.mouse_pos = (-1.0, -1.0)
        x, y, w, _h = self._size
        if y + MENU_H <= py < y + MENU_H + TOOLBAR_H:
            self.toolbar_io.mouse_pos = (px, py)
            return
        win, _part = self.wm.hit(px, py)
        self.panel._pv_hover = None
        if win is not None:
            win.io.mouse_pos = (px, py)
            if win.key == "preview":
                self.panel.preview_hover(px, py)

    def drag(self, px, py, *_box):
        if self.wm.drag(px, py):
            return
        target = self._press_target
        if target == "preview":
            self.panel.preview_drag(px)
            return
        if target == "toolbar":
            self.toolbar_io.mouse_pos = (px, py)
        elif target is not None:
            target.io.mouse_pos = (px, py)

    def press(self, px, py, *extra, **_kw):
        from emtk.events import SHIFT_MODIFIER

        self._user_layout = True  # the user acts: the layout is theirs from now on

        modifiers = int(extra[4]) if len(extra) > 4 else 0
        clicks = int(extra[5]) if len(extra) > 5 else 1
        x, y, w, _h = self._size
        if self.popup is not None:
            popup, items, on_select = self.popup
            result = popup.press(px, py, x, y, w, _h)
            if result.item is not None:
                on_select(items.index(result.item))
            if not popup.open:
                self.popup = None
            return  # a press while a dropdown is open only closes or picks
        result = self.menubar.press(px, py, x, y, w, MENU_H)
        if result.item is not None:
            for name, item in self.items.items():
                if item is result.item:
                    self.command(name)
            return
        if result.consumed or py < y + MENU_H:
            return
        if py < y + MENU_H + TOOLBAR_H:
            if self.wm.modal_window() is not None:
                return
            io, self._press_target = self.toolbar_io, "toolbar"
        else:
            win = self.wm.press(px, py, shift=bool(modifiers & SHIFT_MODIFIER), double=clicks >= 2)
            sheet = self.panel.sheet
            sheet.focused = False
            if win is None:
                self._press_target = None
                return
            if win.key == "preview" and self.panel.preview_press(px, py):
                self._press_target = "preview"
                return
            if win.key == "table":
                sx, sy, sw, sh = sheet._box
                if sx <= px < sx + sw and sy <= py < sy + sh:
                    sheet.press(px, py, time.monotonic())
                    self._press_target = None
                    return
            io, self._press_target = win.io, win
        io.mouse_pos = io.mouse_clicked_pos[0] = (px, py)
        io.mouse_clicked[0] = io.mouse_down[0] = True

    def release(self, *_a, **_kw):
        self.wm.release()
        target, self._press_target = self._press_target, None
        if target == "preview":
            self.panel.preview_release()
            return
        io = self.toolbar_io if target == "toolbar" else (target.io if target is not None else None)
        if io is not None and io.mouse_down[0]:
            io.mouse_down[0] = False
            io.mouse_released[0] = True

    def scroll(self, rows):
        # the wheel goes to the window under the pointer
        for win in reversed(self.wm.windows):
            if not win.visible:
                continue
            mx, my = win.io.mouse_pos
            if mx < 0:
                continue
            if win.scroll is not None and win.scroll(rows, mx, my):
                return
            win.io.mouse_wheel = -float(rows) / 3.0
            return

    def key(self, key, text="", modifiers=0):
        from emtk import keys
        from emtk.events import CONTROL_MODIFIER, META_MODIFIER

        if modifiers & (CONTROL_MODIFIER | META_MODIFIER) and (
                text.lower() in ("s", "o", "q") or key in (83, 79, 81)):
            name = {"s": "save", "o": "load", "q": "exit"}.get(text.lower()) or {
                83: "save", 79: "load", 81: "exit"}[key]
            self.command(name)
            return True
        if key == keys.KEY_F1:
            self.command("help")
            return True
        top = self.wm.top_window()
        if top is not None and top.key == "table" and self.panel.sheet.key(key, qt_key_text(key, text), modifiers):
            return True
        if top is not None and top.key == "help" and key in (keys.KEY_PAGE_UP, keys.KEY_PAGE_DOWN):
            if self.panel.help is not None:
                self.panel.help.scroll_pages(-1 if key == keys.KEY_PAGE_UP else 1)
            return True
        if key == keys.KEY_ESCAPE:
            if self.popup is not None:
                self.popup[0].close()
                self.popup = None
                return True
            if self._menu_open():
                self.menubar.close()
                return True
            if top is not None and top.closable and top.visible and top.key in ("file", "about", "tutorial", "help"):
                self.wm.close(top)
                self._sync_windows()
                return True
        target = top.io if top is not None else self.toolbar_io
        target.key = int(key)
        target.text = qt_key_text(key, text)
        return True


def run(autoconnect=None, debug=False):
    from qtpy import QtCore, QtWidgets

    from emtk.qt_host import ControlHost

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    panel = LaserGui(DeviceWorker(debug=debug), autoconnect=autoconnect)
    from cmc_light.gui_dialogs import SETTINGS_DIR

    app_ctl = App(panel, state_path=os.path.join(SETTINGS_DIR, "cmc-light.ini"))
    host = ControlHost(app_ctl)
    app_ctl.on_exit = host.close
    clip = app.clipboard()
    panel.sheet.clipboard_get = clip.text
    panel.sheet.clipboard_set = clip.setText
    host.setWindowTitle("cmc-light - ALEX laser source")
    host.setMouseTracking(True)
    geom = app_ctl.wm.main_window or {}
    screen = app.primaryScreen().availableGeometry()
    host.resize(int(geom.get("w", min(1700, screen.width()))), int(geom.get("h", min(950, screen.height()))))
    if "x" in geom and "y" in geom:
        host.move(int(geom["x"]), int(geom["y"]))

    def remember_main_window():
        g = host.geometry()
        app_ctl.wm.main_window = dict(x=host.x(), y=host.y(), w=g.width(), h=g.height())
        app_ctl.wm.persist()  # window layout and main window size, like imgui.ini

    app.aboutToQuit.connect(remember_main_window)
    timer = QtCore.QTimer()
    timer.timeout.connect(host.update)
    timer.start(50)
    host.show()
    try:
        return app.exec_() if hasattr(app, "exec_") else app.exec()
    finally:
        panel.worker.close()
        app_ctl.sensor.worker.close()
