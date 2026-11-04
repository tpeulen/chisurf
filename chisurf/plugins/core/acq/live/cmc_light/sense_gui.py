"""The light sensor (cmc-sense camera) in the cmc-light GUI.

Two windows:

* **Light sensor**: connection, range control (auto exposure x gain, or manual),
  background mode, and the quantitative readouts per colour channel;
* **Beam profile**: the spot's position and 1-sigma ellipse on the sensor, x / y beam
  profiles, the signal history on a log scale (dynamic range), and the per-laser beam
  profiles taken by **Profile each laser**.

The sensor runs on its own worker thread, so it never slows the laser link.
"""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque

from emtk import im

from cmc_light.sense import CHANNELS, RANGE_STATES, Sensor, SenseError, find_sensors

SIMULATOR = "Simulator"
CH_COLOURS = {"R": (255, 80, 70, 255), "G": (70, 220, 100, 255), "B": (90, 140, 255, 255),
              "S": (230, 230, 230, 255)}
DIM = (128, 128, 128, 255)
WARN = (255, 190, 90, 255)
BAD = (255, 110, 110, 255)


def fmt_power(w):
    if w is None or not math.isfinite(w):
        return "-"
    for unit, scale in (("W", 1.0), ("mW", 1e-3), ("uW", 1e-6), ("nW", 1e-9), ("pW", 1e-12)):
        if abs(w) >= scale:
            return "%.3g %s" % (w / scale, unit)
    return "%.3g fW" % (w / 1e-15)


def fmt_sig(v):
    if v is None or not math.isfinite(v):
        return "-"
    if abs(v) >= 1e4 or (0 < abs(v) < 1e-2):
        return "%.3e" % v
    return "%.4g" % v


HISTORY_WINDOWS = (10.0, 30.0, 60.0, 300.0)  # selectable history spans (s)


class SensorWorker:
    """Owns the sensor: polls readings with profiles, runs commands off the GUI thread."""

    HISTORY_S = 300.0     # readings kept; the window shown is set in the GUI
    RECONNECT_S = 4.0     # how often to look for a sensor while none is connected
    STALL_S = 8.0         # no new frame for this long: take the link down and rebuild it

    def __init__(self, laser_source_getter=None, debug=False):
        self.laser_source = laser_source_getter or (lambda: None)
        self.debug = debug
        self.sensor: Sensor | None = None
        self.target = ""
        self.jobs: "queue.Queue" = queue.Queue()
        self.reading = None
        # (t, {channel: signal}, exposure, gain, saturated). A list, not a deque: the GUI
        # thread reads it while this thread appends, and appending to a list never moves
        # the items already there (trimming replaces the whole list instead).
        self.history = []
        self.history_s = 60.0  # how much is kept; the GUI sets it from the window it shows
        self.error = ""
        self.busy = ""
        self.found = {}  # port -> idn
        self.bin = 4            # transfer binning of the profiles
        self.profile_every = 2  # profiles on every n-th reading: the numbers stay snappy
        self.baud = 0           # link speed in use (0: unknown / simulator)
        self.stream = True      # let the camera push readings (fastest)
        self.auto_connect = True  # find and connect a sensor by itself, also after unplugging
        self.skip_ports = ()      # ports owned by other instruments (the laser)
        self.last_port = ""       # where a camera was found before (a silent board is
                                  # invisible to a scan, so this is the only way back)
        self._next_try = 0.0
        self._last_new = 0.0  # when the last new frame arrived (stall watchdog)
        self._polls = 0
        self.paused = False
        self.signal_fn = lambda r, c: r.signal(c)  # replaced by the calibrated signal
        self.on_connected = None  # called with the sensor whenever one starts delivering
        self._stop = False
        self.thread = None  # started with the first job: a GUI without a sensor costs nothing

    def submit(self, fn, label=""):
        self.jobs.put((fn, label))
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name="cmc-sense worker", daemon=True)
            self.thread.start()

    def close(self):
        self._stop = True
        if self.thread is not None:
            # long enough for a blocking readline to return: closing the port under the
            # worker thread leaves it reading a dead file descriptor
            self.thread.join(timeout=6)
        if self.sensor is not None:
            try:
                self.sensor.close()
            except Exception:
                pass
            self.sensor = None

    # -- jobs ---------------------------------------------------------------- #
    def connect(self, target, setup=None):
        self.disconnect()
        if target == SIMULATOR:
            self.sensor = Sensor.simulated(self.laser_source(), debug=self.debug)
        else:
            # This port was picked deliberately (by the user, by the scan, or because a
            # camera was there before), so a board that says nothing at either rate is
            # assumed to be a wedged camera and gets a reset rather than a shrug.
            # Remembered before the attempt, not after: a board that is silent or whose
            # port is briefly busy never turns up in a scan, and this is the only way
            # back to it.
            self.last_port = target
            self.sensor = Sensor.open(target, debug=self.debug, reset_if_silent=True)
        self.target = target
        self._start_readings(setup)

    def _start_readings(self, setup=None):
        """Settle a freshly connected (or freshly restarted) board into streaming.

        *setup* runs before the stream starts: its queries get the board to themselves,
        instead of competing with the readings it is already pushing.
        """
        self.sensor.errors()  # drop stale errors
        self.history = []
        self.reading = None
        self.baud = 0
        self._last_new = time.monotonic()  # the stall watchdog starts counting from here
        if hasattr(self.sensor.link, "serial"):
            self.baud = self.sensor.set_link_speed()  # faster link, falls back on its own
        if setup is not None:
            setup(self.sensor)
        if self.on_connected is not None:
            # the GUI reads the board's state here: it may have connected by itself, or
            # come back from a restart with everything at its defaults. Before the
            # stream starts, so these queries have the board to themselves.
            self.on_connected(self.sensor)
        if hasattr(self.sensor.link, "serial") and self.stream:
            try:  # the camera pushes readings after every analysed frame
                self.sensor.start_stream(bin=self.bin, profiles_every=self.profile_every)
            except Exception as e:
                print("[cmc-light] sensor stream not started: %s" % e, flush=True)
        print("[cmc-light] sensor connected to %s: %s" % (self.target, self.sensor.identity), flush=True)

    def resume_stream(self):
        """Make sure readings are being pushed again (anything that talks to the board
        may have stopped the stream on the way)."""
        s = self.sensor
        if s is not None and self.stream and not s.streaming and hasattr(s.link, "serial"):
            s.start_stream(bin=self.bin, profiles_every=self.profile_every)
            self._last_new = time.monotonic()

    RESTART_WAIT_S = 3.0  # boot + camera init before the board answers again

    def restart_reconnect(self, target, timeout=25.0, setup=None):
        """Pick the board up again after it restarted itself (a new frame size).

        The port stays open across the reboot: closing it toggles DTR/RTS, which can
        leave the board sitting in its bootloader, silent. Only if waiting on the open
        port fails is the port closed and opened again.
        """
        s = self.sensor
        if s is not None and getattr(s.link, "serial", None) is not None:
            try:
                s.wait_restart(timeout=timeout, boot_s=self.RESTART_WAIT_S)
                self._start_readings(setup)
                return
            except Exception as e:
                print("[cmc-light] sensor did not answer after restarting (%s):"
                      " reopening the port" % e, flush=True)
        if self.sensor is not None:
            self.sensor.close_quietly()
            self.sensor = None
            self.reading = None
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            try:
                self.connect(target, setup=setup)
                return
            except Exception as e:
                last = e
                time.sleep(1.0)
        raise SenseError("the sensor did not come back after the restart: %s" % last)

    def disconnect(self):
        if self.sensor is not None:
            try:
                self.sensor.stop_stream()
                if getattr(self, "baud", 0) and hasattr(self.sensor.link, "serial"):
                    self.sensor.set_link_speed(115200)  # leave the board at its start-up rate
            except Exception:
                pass
            try:
                self.sensor.close()
            finally:
                self.sensor = None
                self.target = ""
                self.reading = None

    def scan(self, skip=()):
        in_use = self.target if self.sensor is not None else None
        found = {p: i for p, i in find_sensors(skip=tuple(skip) + ((in_use,) if in_use else ()))}
        if in_use and in_use != SIMULATOR and self.sensor is not None:
            found[in_use] = self.sensor.identity
        self.found = found

    # -- loop ---------------------------------------------------------------- #
    def _run(self):
        # Nothing may get out of this loop: if the thread dies the GUI keeps its last
        # reading for ever and nothing reconnects - which looks exactly like a frozen
        # camera. Even the error handling below can raise (closing a port whose device
        # is gone), so the whole body is guarded.
        while not self._stop:
            try:
                try:
                    fn, label = self.jobs.get(timeout=0.02)
                except queue.Empty:
                    fn = None
                if fn is not None:
                    self._call(fn, label)
                elif self.sensor is None:
                    self._try_connect()
                    time.sleep(0.1)
                elif self.paused:
                    time.sleep(0.1)
                else:
                    self._call(self._poll, "")
            except Exception as e:
                self.error = "sensor worker: %s" % e
                print("[cmc-light] ERROR %s" % self.error, flush=True)
                time.sleep(0.2)

    def _call(self, fn, label):
        self.busy = label
        try:
            fn()
            if label:
                self.error = ""
                self._last_new = time.monotonic()  # a job blocks the poll loop: not a stall
        except Exception as e:  # report on stdout too, so problems can be debugged
            self.error = "%s: %s" % (label or "sensor", e)
            print("[cmc-light] ERROR sensor %s" % self.error, flush=True)
            if isinstance(e, (OSError,)) and self.sensor is not None:
                try:  # the port may already be unusable: dropping it must not throw
                    self.disconnect()
                except Exception:
                    self.sensor, self.target, self.reading = None, "", None
            time.sleep(0.2)
        finally:
            self.busy = ""

    def _try_connect(self):
        """Look for a sensor now and then, and connect the first one found."""
        if not self.auto_connect or time.monotonic() < self._next_try:
            return
        self._next_try = time.monotonic() + self.RECONNECT_S
        try:
            self.scan(skip=self.skip_ports)
            ports = sorted(self.found)
            if ports:
                self.connect(ports[0])
            elif self.last_port and self.last_port not in self.skip_ports:
                self.connect(self.last_port)  # silent there? it gets a reset
        except Exception as e:
            print("[cmc-light] sensor search: %s" % e, flush=True)

    def _poll(self):
        self._polls += 1
        if self.sensor.streaming:  # readings are pushed after every analysed frame
            r = self.sensor.latest()
            if r is None or (self.reading is not None and r.frame == self.reading.frame):
                if time.monotonic() - self._last_new > self.STALL_S:
                    self._rebuild_link()
                else:
                    time.sleep(0.005)
                return
        else:
            want_profiles = (self.profile_every <= 1 or self._polls % self.profile_every == 0
                             or self.reading is None)
            r = self.sensor.measure_all(self.bin) if want_profiles else self.sensor.measure()
            if not want_profiles and self.reading is not None:  # keep the profiles for the drawing
                r.prof_x, r.prof_y, r.bin = self.reading.prof_x, self.reading.prof_y, self.reading.bin
        self.reading = r
        now = self._last_new = time.monotonic()
        self.history.append((now, {c: self.signal_fn(r, c) for c in CHANNELS}, r.exposure, r.gain, r.saturated))
        keep = max(10.0, min(self.HISTORY_S, self.history_s * 1.2))
        if self.history[0][0] < now - keep:  # trim by replacing the list (readers keep theirs)
            cut = 0
            while cut < len(self.history) and self.history[cut][0] < now - keep:
                cut += 1
            self.history = self.history[cut:]
        if self.error.startswith("sensor:"):
            self.error = ""

    def _rebuild_link(self):
        """No reading for STALL_S: drop the link and build it again.

        A stalled stream cannot be told apart from a board that stopped sending, and
        both are cured the same way. Nothing is sent to the old link (it may be the
        thing that is broken), so the board is left at whatever baud rate it was on;
        opening tries both.
        """
        target = self.target
        print("[cmc-light] sensor: no reading for %.0f s, reconnecting" % self.STALL_S, flush=True)
        s = self.sensor
        if s is not None and getattr(s.link, "serial", None) is not None:
            try:  # a silent board wakes up from a reset over the auto-reset lines
                s.hard_reset()
                self._start_readings()
                return
            except Exception as e:
                print("[cmc-light] sensor reset did not help: %s" % e, flush=True)
        if self.sensor is not None:
            self.sensor.close_quietly()
            self.sensor = None
            self.reading = None
        self._last_new = time.monotonic()
        try:
            self.connect(target)
        except Exception as e:
            self.error = "sensor link lost: %s" % e  # _try_connect keeps looking
            self._next_try = time.monotonic() + 1.0

    def wait_settled(self, timeout=15.0, frames=2):
        """Readings until auto-ranging holds for *frames* frames in a row (worker thread only)."""
        end = time.monotonic() + timeout
        good, r = 0, None
        while time.monotonic() < end:
            r = self.sensor.measure_all(self.bin)
            self.reading = r
            good = good + 1 if r.range_state in (0, 2, 3) else 0
            if good >= frames:
                return r
        return r


class SensorPanel:
    """GUI state and drawing of the sensor windows."""

    def __init__(self, laser_panel, worker: SensorWorker | None = None, autoconnect=None):
        self.laser = laser_panel
        self.worker = worker or SensorWorker(lambda: laser_panel.src)
        self.targets = [SIMULATOR]
        self.target = 0
        self.auto_range = True
        self.exposure = 100
        self.gain = 0
        self.background = "EDGE"
        self.resolution = "QVGA"
        self.bin_px = 2  # analyse every bin_px-th pixel: fewer pixels, faster readings
        self.channel = "S"
        self.show = {c: c == "S" for c in CHANNELS}
        self.show["R"] = self.show["G"] = self.show["B"] = True
        self.spot_photometry = True
        self.history_s = 30.0  # the signal history window shown
        self.worker.history_s = self.history_s
        self.show_corrections = False
        self.profiles = {}  # laser index -> reading taken with only that laser on
        self.profiling = ""
        self.message = ""
        self.hover = None
        from cmc_light.sense_cal import Calibration

        self.cal = Calibration()
        self.cal_path = None
        self.cal_laser = 0         # laser used for calibration steps / power display
        self.ref_power_uw = 100.0  # reference power at the sensor, from a power meter
        self.cal_log = deque(maxlen=6)
        self.show_calibration = False
        self.cal_report = ""
        self.worker.signal_fn = lambda r, c: self.cal.signal(r, c, self.spot_photometry)
        self.worker.on_connected = self.adopt_sensor
        if autoconnect:
            self.connect(autoconnect)

    @property
    def sensor(self):
        return self.worker.sensor

    # -- actions ------------------------------------------------------------- #
    def connect(self, target):
        def job():
            self.worker.connect(target)
            if target not in self.targets:
                self.targets.append(target)
            self.target = self.targets.index(target)
        self.worker.submit(job, "connect sensor")

    def adopt_sensor(self, s):
        """Read the board's state into the panel.

        Called for every connection, including the ones the worker makes on its own
        (a camera plugged in later, a reconnect, a board that came back from its
        restart with everything at its defaults) - otherwise the panel would go on
        showing what some earlier board was set to.
        """
        target = self.worker.target
        if target and target not in self.targets:
            self.targets.append(target)
        if target:
            self.target = self.targets.index(target)
        self.auto_range = s.auto_range()
        self.exposure, self.gain = s.exposure(), s.gain()
        self.background = s.background()
        self.resolution = s.resolution()
        if s.binning() != self.bin_px:
            s.set_binning(self.bin_px)  # the default: 2x2 is about twice as fast as every pixel
        self.bin_px = s.binning()
        if self.cal_path is None or s.identity not in str(self.cal_path):
            self._load_calibration(s)

    # -- calibration --------------------------------------------------------- #
    def _settings_dir(self):
        from cmc_light.gui_dialogs import SETTINGS_DIR

        return SETTINGS_DIR

    def _load_calibration(self, s):
        """The calibration file of this sensor (by serial number), and its response tables on the chip."""
        import os

        from cmc_light.sense_cal import Calibration, calibration_path

        self.cal_path = calibration_path(self._settings_dir(), s.identity)
        self.cal = Calibration(sensor=s.identity)
        if os.path.isfile(self.cal_path):
            try:
                self.cal = Calibration.load(self.cal_path)
                if self.cal.response and s.query("CAL:LUT:STAT?") != "CUSTOM":
                    for c, lut in self.cal.response.items():
                        s.write("CAL:LUT %s,%s" % (c, ",".join(str(v) for v in lut)))
                self.message = "calibration loaded: %s" % os.path.basename(self.cal_path)
            except Exception as e:
                self.message = "calibration file unreadable: %s" % e
                print("[cmc-light] ERROR %s" % self.message, flush=True)

    def _save_calibration(self):
        if self.cal_path:
            self.cal.created = time.strftime("%Y-%m-%d %H:%M")
            self.cal.save(self.cal_path)

    def _cal_job(self, label, fn):
        """Run a calibration step on the sensor thread: polling paused, laser state restored."""
        def job():
            s, src = self.worker.sensor, self.laser.src
            if s is None or src is None:
                raise SenseError("connect the laser and the sensor first")
            self.worker.paused = True
            self.cal_log.clear()
            try:
                fn(s, src)
                self._save_calibration()
            except Exception as e:
                self.cal_report = "%s failed: %s" % (label, e)
                raise
            finally:
                s.set_auto_range(self.auto_range)
                if not self.auto_range:
                    s.set_exposure(int(self.exposure))
                    s.set_gain(int(self.gain))
                self.worker.paused = False
        self.worker.submit(job, label)

    def calibrate_response(self):
        from cmc_light import sense_cal

        def run(s, src):
            rep = sense_cal.measure_response(s, src, self.cal_laser, progress=self.cal_log.append,
                                             keep=self.cal.response)
            self.cal.response = rep["luts"]
            self.cal.exposure_table = rep.get("exposure_table", self.cal.exposure_table)
            self.cal.response_report = {k: v for k, v in rep.items() if k in ("laser", "method", "errors",
                                                                               "linearity_worst", "check")}
            worst = rep.get("linearity_worst")
            self.cal_report = "%s measured %s (tables: %s); linearity %s" % (
                self.laser.channels[self.cal_laser]["name"], "".join(rep["measured"]),
                "".join(sorted(rep["luts"])),
                "worst %.1f %%" % (100 * worst) if worst is not None else "not checked")
        self._cal_job("calibrating the response", run)

    def calibrate_gain(self):
        from cmc_light import sense_cal

        def run(s, src):
            self.cal.gain_table = sense_cal.measure_gain(s, src, self.cal_laser, progress=self.cal_log.append)
            self.cal_report = "gain factors for settings 0..%d" % (len(self.cal.gain_table) - 1)
        self._cal_job("calibrating the gain", run)

    def measure_pulses(self):
        from cmc_light import sense_cal

        def run(s, src):
            res = sense_cal.measure_pulse_response(s, src, self.cal_laser, progress=self.cal_log.append)
            t = res["threshold_us"]
            name = self.laser.channels[self.cal_laser]["name"]
            self.cal_report = "%s: no light below ~%s us pulses" % (name, "%.0f" % t if t else "?")
            self.cal.response_report.setdefault("pulse_threshold_us", {})[name] = t
        self._cal_job("measuring the laser pulse response", run)

    def set_absolute(self):
        from cmc_light import sense_cal

        r = self.worker.reading
        name = self.laser.channels[self.cal_laser]["name"]
        if r is None or not r.has_spot():
            self.message = "no spot to calibrate against: switch on only the %s laser" % name
            return
        try:
            a = sense_cal.set_absolute(self.cal, r, name, self.ref_power_uw * 1e-6)
            self._save_calibration()
            self.cal_report = "absolute: %s %.3e W per unit (reference %.4g uW)" % (name, a["w_per_unit"], self.ref_power_uw)
        except ValueError as e:
            self.message = str(e)

    def reset_calibration(self):
        from cmc_light.sense_cal import Calibration

        def job():
            s = self.worker.sensor
            if s is not None:
                s.write("CAL:LUT:RES")
                self.cal = Calibration(sensor=s.identity)
                self._save_calibration()
            self.cal_report = "calibration reset"
        self.worker.submit(job, "reset calibration")

    def autoconnect(self, found_ports):
        """Connect the first sensor found: from the laser's scan, else a scan of its own
        (the camera may still run at the fast link speed, which that scan also tries)."""
        sensors = sorted(p for p, idn in found_ports.items() if idn.startswith("CMC,SENSE"))
        lasers = tuple(p for p, idn in found_ports.items() if idn.startswith("CMC,LIGHT"))
        self.targets = [SIMULATOR] + sensors
        self.worker.skip_ports = lasers  # the laser's port is not probed for sensors

        def job():
            found = sensors
            if not found:
                self.worker.scan(skip=lasers)
                found = sorted(self.worker.found)
                self.targets = [SIMULATOR] + found
            if found:
                self.worker.connect(found[0])
                if found[0] not in self.targets:
                    self.targets.append(found[0])
                self.target = self.targets.index(found[0])
                s = self.worker.sensor
                self.auto_range, self.exposure, self.gain = s.auto_range(), s.exposure(), s.gain()
                self.background, self.resolution = s.background(), s.resolution()
                if s.binning() != self.bin_px:
                    s.set_binning(self.bin_px)
                self._load_calibration(s)
            elif self.laser.src is not None and self.laser.src.link == "simulator":
                self.worker.auto_connect = False  # the simulated laser gets the simulated sensor
                self.worker.connect(SIMULATOR)
        self.worker.submit(job, "find the light sensor")

    def rescan(self):
        def job():
            laser_port = getattr(getattr(self.laser.src, "t", None), "port", None)
            self.worker.scan(skip=(laser_port,) if laser_port else ())
            self.targets = [SIMULATOR] + sorted(self.worker.found)
        self.worker.submit(job, "scan for sensors")

    def push_range(self):
        auto, exp, gain = self.auto_range, int(self.exposure), int(self.gain)

        def job():
            s = self.worker.sensor
            if s is None:
                return
            if auto:
                s.set_auto_range(True)
            else:
                s.set_exposure(exp)
                s.set_gain(gain)
        self.worker.submit(job, "sensor range")

    def push_binning(self):
        b = int(self.bin_px)
        self.worker.submit(lambda: self.worker.sensor and self.worker.sensor.set_binning(b), "pixel binning")

    res_pending = False  # a frame-size change is in flight (the board is restarting)

    def push_resolution(self):
        """A new frame size restarts the camera board (~3 s): reconnect afterwards."""
        res, target, want_bin = self.resolution, self.worker.target, int(self.bin_px)
        self.res_pending = True

        def job():
            try:
                s = self.worker.sensor
                if s is None:
                    return
                if not s.set_resolution(res):  # stops the stream, no restart if unchanged
                    self.resolution = s.resolution()
                    return

                def setup(sen):  # while the board is not streaming yet
                    self.resolution = sen.resolution()
                    if sen.binning() != want_bin:  # the restart forgot it: the GUI wins
                        sen.set_binning(want_bin)
                    self.bin_px = sen.binning()
                    sen.set_auto_range(self.auto_range)
                self.worker.restart_reconnect(target, setup=setup)
            finally:
                self.res_pending = False
                # whatever happened above, the board must be pushing readings again
                try:
                    self.worker.resume_stream()
                except Exception as e:
                    print("[cmc-light] could not restart the readings: %s" % e, flush=True)
        self.worker.submit(job, "frame size (board restarts)")

    def push_background(self):
        mode = self.background
        self.worker.submit(lambda: self.worker.sensor and self.worker.sensor.set_background(mode), "background")

    def acquire_dark(self):
        """Dark frame with every laser off (lasers restored afterwards)."""
        laser = self.laser

        def job():
            src, s = laser.src, self.worker.sensor
            if s is None:
                return
            before = [src.emission(k + 1) for k in range(src.n_channels)] if src else []
            try:
                if src:
                    src.all_off()
                time.sleep(0.3)
                s.acquire_dark(8)
                s.set_background("DARK")
                self.background = "DARK"
            finally:
                if src:
                    src.set_emissions({k + 1: on for k, on in enumerate(before)})
        self.worker.submit(job, "dark frame (lasers off)")

    def _adopt_laser_state(self, states):
        """Put the laser panel's boxes back to what the measurement restored.

        Polls that were started while the measurement had other lasers on must not
        overwrite them, so they are marked as older than this moment.
        """
        self.laser.enabled = list(states)
        self.laser._enable_pushed_at = time.monotonic()

    def measure_background(self):
        """Signal with every laser off: stray light and dark current, subtracted from readings."""
        def run(s, src):
            n = src.n_channels
            before = [src.emission(k + 1) for k in range(n)]
            try:
                src.abort()
                src.all_off()
                time.sleep(0.4)
                readings = [r for r in (self.worker.wait_settled(frames=1) for _ in range(3)) if r]
                bg = {}
                for c in CHANNELS:
                    vals = sorted(self.cal.signal(r, c, self.spot_photometry) for r in readings)
                    bg[c] = vals[len(vals) // 2] if vals else 0.0
            finally:
                src.set_emissions({k + 1: on for k, on in enumerate(before)})
                self._adopt_laser_state(before)
            # only now, with the lasers back as they were, does the result become visible
            self.cal.background = bg
            self.cal_report = "background: " + ", ".join("%s %s" % (c, fmt_sig(bg[c])) for c in "RGB")
        self._cal_job("measuring the background", run)

    def measure_crosstalk(self):
        """Each laser alone: its share of the R, G, B channels (the crosstalk matrix)."""
        from cmc_light.sense_cal import crosstalk_matrix

        laser = self.laser

        def run(s, src):
            n = src.n_channels
            before_on = [src.emission(k + 1) for k in range(n)]
            before_source = src.source()
            try:
                src.abort()
                src.set_source("CW")
                s.set_auto_range(True)
                signals, profiles, saturated = {}, {}, []
                powers = [src.power(k + 1) for k in range(n)]
                for k in range(n):
                    name = laser.channels[k]["name"]
                    self.profiling = name
                    power = 1.0  # measure the shape at full power, dim only if it saturates
                    src.set_power(k + 1, power)
                    src.set_emissions({j + 1: j == k for j in range(n)})
                    time.sleep(0.25)
                    r = self.worker.wait_settled()
                    # a saturated spot has no colour: every channel clips, which flattens the
                    # row. Dim the laser until it fits (the row is a shape, so this is free).
                    while r.saturated and power > 0.02:
                        power = max(0.02, power / 2.0)
                        src.set_power(k + 1, power)
                        self.cal_log.append("%s saturated: trying %.0f %% power" % (name, 100 * power))
                        time.sleep(0.25)
                        r = self.worker.wait_settled()
                    if r.saturated:
                        saturated.append(name)
                    profiles[k] = r
                    signals[name] = {c: self.cal.signal(r, c, self.spot_photometry)
                                     - self.cal.background_signal(c) for c in "RGB"}
                    self.cal_log.append("%s at %.0f %%: R %s  G %s  B %s" % (
                        name, 100 * power, fmt_sig(signals[name]["R"]), fmt_sig(signals[name]["G"]),
                        fmt_sig(signals[name]["B"])))
                for k, p in enumerate(powers):
                    src.set_power(k + 1, p)
                matrix = crosstalk_matrix(signals)
            finally:
                self.profiling = ""
                src.set_emissions({k + 1: on for k, on in enumerate(before_on)})
                self._adopt_laser_state(before_on)
                if before_source != "CW":
                    src.set_source(before_source)
            # the lasers are back as they were before the result appears
            self.cal.crosstalk = matrix
            self.profiles = profiles
            self.cal_report = "crosstalk: " + "; ".join(
                "%s %s" % (name, "/".join("%.0f %%" % (100 * share[c]) for c in "RGB"))
                for name, share in sorted(matrix.items()))
            if saturated:
                self.cal_report += "  -- still saturated: %s (attenuate the beam)" % ", ".join(saturated)
        self._cal_job("measuring the crosstalk", run)

    def profile_each_laser(self):
        """For every laser: only that laser on (CW, its power), auto-range, take a reading
        with profiles. The lasers' previous state is restored."""
        laser = self.laser

        def job():
            src, s = laser.src, self.worker.sensor
            if src is None or s is None:
                raise SenseError("connect the laser and the sensor first")
            n = src.n_channels
            before_on = [src.emission(k + 1) for k in range(n)]
            before_source = src.source()
            self.worker.paused = True
            try:
                src.abort()
                src.set_source("CW")
                s.set_auto_range(True)
                results = {}
                for k in range(n):
                    self.profiling = laser.channels[k]["name"]
                    src.set_emissions({j + 1: j == k for j in range(n)})
                    time.sleep(0.2)
                    r = self.worker.wait_settled()
                    results[k] = r
                self.profiles = results
                self.message = "beam profiles of %d lasers taken" % len(results)
            finally:
                self.profiling = ""
                src.set_emissions({k + 1: on for k, on in enumerate(before_on)})
                self._adopt_laser_state(before_on)
                if before_source != "CW":
                    src.set_source(before_source)
                if not self.auto_range:
                    s.set_exposure(int(self.exposure))
                    s.set_gain(int(self.gain))
                self.worker.paused = False
        self.worker.submit(job, "profiling each laser")

    # -- windows ------------------------------------------------------------- #
    def draw_sensor(self, w, h):
        from cmc_light.gui import label, labelled_slider, wrapped

        worker, r = self.worker, self.worker.reading
        # connection row
        labels = [t if t == SIMULATOR else "%s  [%s]" % (t, worker.found.get(t, "?").split(",")[1]
                                                          if "," in worker.found.get(t, "") else t)
                  for t in self.targets]
        self.target = min(self.target, len(labels) - 1)
        connected = self.sensor is not None
        im.begin_disabled(connected)
        self.laser.dropdown("sensor_device", labels[self.target], 230, labels, self.target,
                            lambda i: setattr(self, "target", i))
        im.same_line()
        if im.button("Scan##sensor_scan", (44, 0)):
            self.rescan()
        im.end_disabled()
        im.same_line()
        if not connected:
            if im.button("Connect##sensor_connect", (80, 0)):
                self.worker.auto_connect = self.targets[self.target] != SIMULATOR
                self.connect(self.targets[self.target])
        elif im.button("Disconnect##sensor_disconnect", (90, 0)):
            worker.auto_connect = False  # an explicit disconnect stays disconnected
            worker.submit(worker.disconnect, "disconnect sensor")
        if connected:
            label(self.sensor.identity, dim=True, last=True)
        if worker.busy:
            label("(%s...)" % worker.busy, dim=True, last=True)
        if worker.error:
            wrapped(worker.error, BAD)
        if self.message:
            wrapped(self.message, DIM)
        im.separator()

        # range
        changed = False
        c, self.auto_range = im.checkbox("auto range (exposure x gain)", self.auto_range)
        changed |= c
        if not self.auto_range:
            c1, self.exposure = labelled_slider("exposure", "s_exp", self.exposure, 1, 1200, 200,
                                                fmt=lambda v: "%d lines (~%.1f ms)" % (v, 0.2 * v), col=90)
            c2, gain = labelled_slider("gain", "s_gain", self.gain + 1, 1, 31, 200,
                                       fmt=lambda v: "%d" % (v - 1), col=90)
            if c2:
                self.gain = gain - 1
            changed |= c1 or c2
        if changed:
            self.push_range()
        label("pixels", col=90)
        for i, (res, text) in enumerate((("QVGA", "320x240"), ("QQVGA", "160x120"))):
            if i:
                im.same_line()
            # a second click while the board is restarting starts a restart inside a
            # restart, and then it really does not come back: ignore clicks until done
            if im.radio_button("%s##res%d" % (text, i), self.resolution == res) \
                    and self.resolution != res and not self.res_pending:
                self.resolution = res
                self.push_resolution()
        if self.res_pending:
            im.same_line()
            label("(restarting the camera...)", dim=True)
        im.same_line()
        label("bin", dim=True)
        for b in (1, 2, 4):
            im.same_line()
            if im.radio_button("%dx%d##bin%d" % (b, b, b), self.bin_px == b) and self.bin_px != b:
                self.bin_px = b
                self.push_binning()
        r = self.worker.reading
        if r is not None:
            hist = list(self.worker.history)
            rate = 0.0
            if len(hist) >= 3:
                span = hist[-1][0] - hist[0][0]
                rate = (len(hist) - 1) / span if span > 0 else 0.0
            label("%d x %d px analysed, %.1f camera fps, %.1f readings/s" % (
                r.width // max(1, r.bin_px), r.height // max(1, r.bin_px), r.fps, rate), dim=True, last=True)
        im.separator()

        if r is None:
            label("no reading yet", dim=True, last=True)
            return
        state_col = WARN if r.range_state in (2, 3) else (DIM if r.range_state == 1 else (120, 220, 120, 255))
        label("exposure %d lines  gain %d (x%.2f)  %.1f fps" % (r.exposure, r.gain, r.gain_x, r.fps))
        label(RANGE_STATES.get(r.range_state, "?"), colour=state_col, last=not r.saturated)
        if r.saturated:
            im.same_line()
            label("%d saturated px" % r.saturated, colour=BAD, last=True)
        # readout table
        from cmc_light.sense_cal import d4sigma_um

        name = self.laser.channels[min(self.cal_laser, len(self.laser.channels) - 1)]["name"]
        has_abs = name in self.cal.absolute
        cols = ("", "signal", "power (%s)" % name if has_abs else "peak", "centroid x, y px",
                "D4sigma um", "angle")
        widths = (26, 100, 100, 120, 120, 50)
        x0 = 0.0  # same_line(offset) is measured from the window's left edge
        for i, (text, wd) in enumerate(zip(cols, widths)):
            if i:
                im.same_line(x0 + sum(widths[:i]))
            label(text, dim=True, last=i == len(cols) - 1)
        for ch in CHANNELS:
            st = r.ch[ch]
            spot = r.has_spot(ch)
            sig = self.cal.signal(r, ch, self.spot_photometry)
            if has_abs and ch == self.cal.absolute[name].get("channel", "S"):
                third = fmt_power(sig * self.cal.absolute[name]["w_per_unit"])
            else:
                third = "%.0f" % st["peak"] if not has_abs else "-"
            d_major, d_minor = d4sigma_um(r, ch)
            vals = (ch, fmt_sig(sig), third,
                    "%.1f, %.1f" % (st["cx"], st["cy"]) if spot else "-",
                    "%.0f x %.0f" % (d_major, d_minor) if spot else "-",
                    "%.0f" % st["angle"] if spot else "-")
            for i, (text, wd) in enumerate(zip(vals, widths)):
                if i:
                    im.same_line(x0 + sum(widths[:i]))
                label(text, colour=CH_COLOURS[ch] if i == 0 else None, last=i == len(vals) - 1)
        wrapped("signal: %s / exposure x gain%s. D4sigma: 4 x second moment (%.0f um/px)." % (
                    "spot, local background" if self.spot_photometry else "frame",
                    ", linearised" if self.cal.response else "", self.cal.pixel_um(r.width)))
        if im.small_button("setup / calibration..."):
            self.show_calibration = True
        im.same_line()
        if im.small_button("corrections..."):
            self.show_corrections = True

    def draw_calibration(self, w, h):
        from cmc_light.gui import label, wrapped

        wrapped("Calibrate with one laser at a time; the steps switch the lasers themselves and restore "
                "them afterwards. 1: pixel response (exposure sweep, continuous light). 2: gain factors. "
                "3: absolute: switch on only that laser, measure its power at the sensor position with a "
                "power meter, type it in, press set.", DIM)
        im.separator()
        label("background", col=90)
        for i, (mode, text) in enumerate((("EDGE", "frame border"), ("DARK", "dark frame"), ("NONE", "none"))):
            if i:
                im.same_line()
            if im.radio_button("%s##bg%d" % (text, i), self.background == mode) and self.background != mode:
                self.background = mode
                self.push_background()
        im.same_line()
        if im.small_button("take dark frame"):
            self.acquire_dark()
        c, self.spot_photometry = im.checkbox("spot photometry (local background around the spot)",
                                              self.spot_photometry)
        im.separator()
        label("laser", col=90)
        for k, ch in enumerate(self.laser.channels):
            im.same_line()
            if im.radio_button("%s##cal%d" % (ch["name"], k), self.cal_laser == k):
                self.cal_laser = k
        busy = bool(self.worker.busy)
        im.begin_disabled(busy)
        if im.small_button("1 response"):
            self.calibrate_response()
        im.same_line()
        if im.small_button("2 gain"):
            self.calibrate_gain()
        im.same_line()
        if im.small_button("laser pulse response"):
            self.measure_pulses()
        im.same_line()
        if im.small_button("reset##cal"):
            self.reset_calibration()
        _, self.ref_power_uw = self.laser.num("ref_uw", "3 absolute: power at the sensor", self.ref_power_uw,
                                              1e-6, 1e6, 90, float)
        im.same_line()
        label("uW", dim=True)
        if im.small_button("set for %s" % self.laser.channels[self.cal_laser]["name"]):
            self.set_absolute()
        im.end_disabled()
        c = self.cal
        status = "response: %s   gain: %s   absolute: %s" % (
            "linearised (%s)" % "".join(sorted(c.response)) if c.response else "raw codes",
            "measured" if c.gain_table else "nominal",
            ", ".join(sorted(c.absolute)) or "none")
        label(status, dim=True, last=True)
        if self.cal_report:
            wrapped(self.cal_report, WARN if "failed" in self.cal_report else DIM)
        for line in list(self.cal_log)[-2:]:
            label(line, dim=True, last=True)

    def draw_corrections(self, w, h):
        """Raw signals, the background and crosstalk matrices (editable or measured with
        the lasers), and the corrected per-laser signals."""
        from cmc_light.gui import hex_rgb, label, wrapped

        r = self.worker.reading
        cal = self.cal
        names = [ch["name"] for ch in self.laser.channels]
        colours = {ch["name"]: hex_rgb(ch["color"]) for ch in self.laser.channels}
        col_w = 96.0
        busy = bool(self.worker.busy)

        wrapped("Each colour channel of the camera sees a mixture of the lasers. The crosstalk "
                "matrix holds each laser's share of R, G, B (its column sums to 1); the corrected "
                "signals below solve the mixture for the lasers.", DIM)
        im.separator()

        # raw signal, background, background-corrected signal: one column per channel
        chans = ("R", "G", "B", "S")
        label("channel", dim=True, col=90)
        for i, c in enumerate(chans):
            im.same_line(90 + i * col_w)
            label(c, colour=CH_COLOURS[c], last=i == len(chans) - 1)
        label("raw signal", col=90)
        for i, c in enumerate(chans):
            im.same_line(90 + i * col_w)
            label(fmt_sig(cal.signal(r, c, self.spot_photometry)) if r else "-", last=i == len(chans) - 1)
        label("background", col=90)
        for i, c in enumerate(chans):
            im.same_line(90 + i * col_w)
            im.set_next_item_width(col_w - 12)
            _, value = self.laser.num("bg_%s" % c, "", cal.background.get(c, 0.0), -1e12, 1e12,
                                      col_w - 14, float, fmt="%.4g")
            if value != cal.background.get(c, 0.0):
                cal.background[c] = value
        label("bg corrected", col=90)
        for i, c in enumerate(chans):
            im.same_line(90 + i * col_w)
            value = (cal.signal(r, c, self.spot_photometry) - cal.background_signal(c)) if r else None
            label(fmt_sig(value) if r else "-", last=i == len(chans) - 1)
        im.begin_disabled(busy)
        if im.small_button("measure with the lasers off"):
            self.measure_background()
        im.same_line()
        if im.small_button("clear##bg"):
            cal.background = {}
        im.end_disabled()

        # crosstalk matrix: a column per laser, a row per channel
        im.separator()
        label("crosstalk", col=90)
        for i, name in enumerate(names):
            im.same_line(90 + i * col_w)
            label(name, colour=colours[name], last=i == len(names) - 1)
        for c in "RGB":
            label(c, colour=CH_COLOURS[c], col=90)
            for i, name in enumerate(names):
                im.same_line(90 + i * col_w)
                share = cal.crosstalk.get(name, {}).get(c, 1.0 if c == "RGB"[min(i, 2)] else 0.0)
                _, value = self.laser.num("ct_%s_%s" % (name, c), "", share, 0.0, 1.0,
                                          col_w - 14, float, fmt="%.4f")
                if value != share:
                    cal.crosstalk.setdefault(name, {})[c] = value
        im.begin_disabled(busy)
        if im.small_button("auto: measure with each laser"):
            self.measure_crosstalk()
        im.same_line()
        if im.small_button("clear##ct"):
            cal.crosstalk = {}
            self.num_reset()
        im.end_disabled()
        if self.profiling:
            im.same_line()
            label("measuring %s..." % self.profiling, colour=WARN, last=True)

        # crosstalk-corrected signals, per laser
        im.separator()
        corrected = cal.corrected(r, self.spot_photometry) if r else {}
        label("crosstalk corrected", col=90)
        im.same_line(90)
        label("signal", dim=True)
        im.same_line(90 + col_w)
        label("power", dim=True, last=True)
        if not corrected:
            label("measure or type a crosstalk matrix", dim=True, last=True)
        for name, value in corrected.items():
            label(name, colour=colours.get(name), col=90)
            im.same_line(90)
            label(fmt_sig(value))
            im.same_line(90 + col_w)
            a = cal.absolute.get(name)
            label(fmt_power(value * a["w_per_unit"]) if a else "-", last=True)
        if self.cal_report:
            wrapped(self.cal_report, WARN if "failed" in self.cal_report else DIM)

    MAX_HISTORY_POINTS = 200  # drawn points per channel: enough for a 500 px wide plot

    def window_history(self):
        """The readings of the chosen window, oldest first, thinned to a drawable number.

        Cached per reading: the window is redrawn many times per reading, and walking the
        stored readings every frame is what made the window slower the longer it ran.
        """
        history = self.worker.history
        if not history:
            return []
        key = (history[-1][0], self.history_s, len(history))
        if getattr(self, "_hist_key", None) == key:
            return self._hist_cache
        cutoff = history[-1][0] - self.history_s
        picked = []
        for item in reversed(history):  # from the newest back to the window's start
            if item[0] < cutoff:
                break
            picked.append(item)
        step = max(1, len(picked) // self.MAX_HISTORY_POINTS)
        self._hist_key, self._hist_cache = key, picked[::step][::-1]
        return self._hist_cache

    def num_reset(self):
        """Forget typed matrix values so the fields show the stored ones again."""
        self.laser.num.buf = {k: v for k, v in self.laser.num.buf.items()
                              if not k.startswith(("ct_", "bg_"))}

    def draw_beam(self, w, h):
        """Beam profiler layout: the spot map in the middle (contour ellipses at 1, 2 and 3
        sigma per colour), the x projection below it and the y projection beside it, both
        aligned with the map; the signal history underneath."""
        from cmc_light.gui import flex, hex_rgb, label

        r = self.worker.reading
        for i, c in enumerate(CHANNELS):
            if i:
                im.same_line()
            _, self.show[c] = im.checkbox("%s##show%s" % (c, c), self.show[c])
        im.same_line()
        if im.button("Profile each laser"):
            self.profile_each_laser()
        if self.profiles:
            im.same_line()
            if im.small_button("clear##profiles"):
                self.profiles = {}
        label("history", dim=True)
        for span in HISTORY_WINDOWS:
            im.same_line()
            text = "%gs" % span if span < 60 else "%gm" % (span / 60)
            if im.radio_button("%s##hist%g" % (text, span), self.history_s == span):
                self.history_s = span
                self.worker.history_s = span  # keep only what is shown
        if self.profiling:
            im.same_line()
            label("profiling %s..." % self.profiling, colour=WARN, last=True)
        if r is None:
            label("no reading yet", dim=True, last=True)
            return

        series = []  # (label, reading, channel, colour) drawn in the map and both projections
        for c in CHANNELS:
            if self.show[c]:
                series.append((c, r, c, CH_COLOURS[c]))
        for k, pr in sorted(self.profiles.items()):
            series.append((self.laser.channels[k]["name"], pr, "S", hex_rgb(self.laser.channels[k]["color"])))

        dl = im.get_window_draw_list()
        avail_w, avail_h = im.get_content_region_avail()
        avail = max(240.0, avail_w)
        side = 0.26  # projection plots: this fraction of the map size
        aspect = r.height / float(r.width)
        below = 84.0 + (22.0 * (len(self.profiles) + 2) if self.profiles else 0.0)  # history, table
        MIN_MAP_W = 150.0
        map_w = min(avail / (1.0 + side) - 8.0, 520.0,
                    max(MIN_MAP_W, (avail_h - below - 8.0) / ((1.0 + side) * aspect)))
        map_w = max(MIN_MAP_W, map_w)
        map_h = map_w * aspect
        proj_w, proj_h = map_w * side, map_h * side
        x0, y0 = im.get_cursor_screen_pos()
        sc = map_w / float(r.width)
        frame_col, grid_col, bg_col = (90, 94, 110, 255), (40, 42, 52, 255), (18, 19, 23, 255)

        # --- the map: sensor frame, grid every 40 px, contour ellipses ---
        dl.add_rect_filled((x0, y0), (x0 + map_w, y0 + map_h), bg_col)
        for gx in range(40, r.width, 40):
            dl.add_line((x0 + gx * sc, y0), (x0 + gx * sc, y0 + map_h), grid_col)
        for gy in range(40, r.height, 40):
            dl.add_line((x0, y0 + gy * sc), (x0 + map_w, y0 + gy * sc), grid_col)
        dl.add_rect((x0, y0), (x0 + map_w, y0 + map_h), frame_col)
        for name, reading, ch, col in series:
            st = reading.ch[ch]
            if not reading.has_spot(ch):
                continue
            cx, cy = x0 + st["cx"] * sc, y0 + st["cy"] * sc
            rot = math.radians(st["angle"])
            for n_sigma, alpha in ((1, 255), (2, 170), (3, 90)):
                faded = (col[0], col[1], col[2], alpha)
                dl.add_ellipse((cx, cy), (max(1.0, n_sigma * st["sx"] * sc), max(1.0, n_sigma * st["sy"] * sc)),
                               faded, rot, 48, 1.5 if n_sigma == 1 else 1.0)
            dl.add_line((cx - 6, cy), (cx + 6, cy), col)
            dl.add_line((cx, cy - 6), (cx, cy + 6), col)
        dl.add_text((x0 + 4, y0 + 2), DIM, "%dx%d px" % (r.width, r.height))

        # --- x projection below the map, y projection beside it (same pixel axes) ---
        bx, by = x0, y0 + map_h + 4
        dl.add_rect_filled((bx, by), (bx + map_w, by + proj_h), bg_col)
        dl.add_rect((bx, by), (bx + map_w, by + proj_h), frame_col)
        rx, ry = x0 + map_w + 4, y0
        dl.add_rect_filled((rx, ry), (rx + proj_w, ry + map_h), bg_col)
        dl.add_rect((rx, ry), (rx + proj_w, ry + map_h), frame_col)
        for name, reading, ch, col in series:
            px, py = reading.prof_x.get(ch, []), reading.prof_y.get(ch, [])
            b = max(1, reading.bin) * max(1, reading.bin_px)  # profile point spacing, in frame px
            if len(px) >= 2:
                peak = max(px) if max(px) > 0 else 1.0  # each colour to its own peak
                pts = [(bx + (i + 0.5) * b * sc, by + proj_h - 2 - max(0.0, v) / peak * (proj_h - 6))
                       for i, v in enumerate(px)]
                dl.add_polyline(pts, col, 0, 1.5)
            if len(py) >= 2:
                peak = max(py) if max(py) > 0 else 1.0
                pts = [(rx + 2 + max(0.0, v) / peak * (proj_w - 6), ry + (i + 0.5) * b * sc)
                       for i, v in enumerate(py)]
                dl.add_polyline(pts, col, 0, 1.5)
        dl.add_text((bx + 4, by + 2), DIM, "x")
        dl.add_text((rx + 4, ry + 2), DIM, "y")
        # the corner: centre and width of every series
        tx, ty = rx, by
        for j, (name, reading, ch, col) in enumerate(series[:max(0, int((proj_h - 4) // 14))]):
            st = reading.ch[ch]
            text = "%s %.0f,%.0f  %.1f" % (name[:5], st["cx"], st["cy"], st["sx"]) if reading.has_spot(ch) else name[:5]
            dl.add_text((tx + 2, ty + j * 14), col, text)
        # the map grows with the window in both directions: only its minimum size counts
        with flex(max(0.0, (map_w - MIN_MAP_W) * (1.0 + side)),
                  max(0.0, (map_w - MIN_MAP_W) * aspect * (1.0 + side))):
            im.dummy(map_w + 4 + proj_w, map_h + 4 + proj_h + 4)

        # --- signal history, log scale: the dynamic range over time ---
        # only the chosen window, and at most MAX_HISTORY_POINTS of it: walking the whole
        # stored history every frame made the window slower the longer it had been running
        hist = self.window_history()
        hx, hy = im.get_cursor_screen_pos()
        hw, hh = map_w + 4 + proj_w, 70.0
        dl.add_rect_filled((hx, hy), (hx + hw, hy + hh), bg_col)
        dl.add_rect((hx, hy), (hx + hw, hy + hh), frame_col)
        if len(hist) >= 2:
            t_end = hist[-1][0]
            span = self.history_s
            lo_v, hi_v = None, None  # one pass for the decade range
            for _t, sig, *_rest in hist:
                for c in CHANNELS:
                    if not self.show[c]:
                        continue
                    v = sig[c]
                    if v > 0:
                        lo_v = v if lo_v is None or v < lo_v else lo_v
                        hi_v = v if hi_v is None or v > hi_v else hi_v
            if lo_v is not None:
                lo_d = math.floor(math.log10(lo_v))
                hi_d = math.ceil(math.log10(hi_v))
                if hi_d - lo_d < 2:
                    lo_d, hi_d = lo_d - 1, hi_d + 1
                for d in range(lo_d, hi_d + 1):
                    yy = hy + hh - 4 - (d - lo_d) / float(hi_d - lo_d) * (hh - 8)
                    dl.add_line((hx, yy), (hx + hw, yy), grid_col)
                    dl.add_text((hx + 3, yy - 13), DIM, "1e%d" % d)
                for c in CHANNELS:
                    if not self.show[c]:
                        continue
                    pts = [(hx + hw - (t_end - t) / span * hw,
                            hy + hh - 4 - (math.log10(sig[c]) - lo_d) / float(hi_d - lo_d) * (hh - 8))
                           for t, sig, *_ in hist if sig[c] > 0]
                    if len(pts) >= 2:
                        dl.add_polyline(pts, CH_COLOURS[c], 0, 1.5)
                dl.add_text((hx + hw - 210, hy + 2), DIM, "signal, log scale, last %s"
                            % ("%.0f s" % span if span < 60 else "%g min" % (span / 60)))
        with flex(max(0.0, hw - MIN_MAP_W * (1.0 + side))):
            im.dummy(hw, hh + 4)
        if self.profiles:
            label("per laser (only that laser on):", dim=True, last=True)
            cols = ("", "signal", "centre x, y", "sigma", "state")
            widths = (70, 90, 100, 90, 110)
            for i, text in enumerate(cols):
                if i:
                    im.same_line(sum(widths[:i]))
                label(text, dim=True, last=i == len(cols) - 1)
            for k, pr in sorted(self.profiles.items()):
                st = pr.ch["S"]
                ok = pr.has_spot()
                vals = (self.laser.channels[k]["name"], fmt_sig(pr.signal("S", self.spot_photometry)),
                        "%.1f, %.1f" % (st["cx"], st["cy"]) if ok else "no spot",
                        "%.1f x %.1f" % (st["sx"], st["sy"]) if ok else "-",
                        pr.state + (" (%d sat)" % pr.saturated if pr.saturated else ""))
                for i, text in enumerate(vals):
                    if i:
                        im.same_line(sum(widths[:i]))
                    label(text, colour=hex_rgb(self.laser.channels[k]["color"]) if i == 0 else
                          (BAD if (i == 4 and pr.saturated) else None), last=i == len(vals) - 1)
