"""cmc-sense: an ESP32-CAM as a quantitative light sensor (client side).

The camera firmware (``firmware/esp32cam/cmc_sense``) never sends images. Each frame
is analysed on the chip and read here as numbers over the USB serial cable:

* per colour channel R, G, B and S (= R+G+B): background, noise, peak, integrated
  signal (``sum``), spot centroid ``cx, cy``, principal widths ``sx, sy`` and angle;
* x / y beam profiles (column / row sums of the background-subtracted frame);
* the exposure and gain the frame was taken with.

``Reading.signal(c)`` normalises the integrated signal to exposure x gain, which is
what makes the readout comparable across the sensor's auto-ranging steps (large
dynamic range). The SCPI commands are documented in ``docs/SENSE.md``.
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field

CHANNELS = ("R", "G", "B", "S")
STATS = ("bg", "noise", "peak", "sum", "npix", "cx", "cy", "sx", "sy", "angle", "spot_sum", "spot_bg", "spot_px")
BAUD = 115200  # the board always starts here; SYST:BAUD switches to FAST_BAUD
FAST_BAUD = 460800  # measured best on the CH340: 230400 does not work, 921600 is unreliable
RANGE_STATES = {0: "in range", 1: "adjusting", 2: "too bright", 3: "too dark"}
FULL_SCALE = {"R": 255, "G": 255, "B": 255, "S": 765}


class SenseError(RuntimeError):
    pass


@dataclass
class Reading:
    frame: int
    t_ms: int
    fps: float
    exposure: int
    gain: int
    gain_x: float
    saturated: int
    range_state: int
    width: int
    height: int
    bin_px: int  # the camera analysed every bin_px-th pixel (in x and y)
    ch: dict  # channel -> {stat: value}
    prof_x: dict = field(default_factory=dict)  # channel -> [values]
    prof_y: dict = field(default_factory=dict)
    bin: int = 1
    t_host: float = 0.0

    @classmethod
    def parse(cls, line, fields):
        values = line.strip().split(",")
        if len(values) != len(fields):
            raise SenseError("measurement has %d values, expected %d: %r" % (len(values), len(fields), line[:80]))
        d = dict(zip(fields, values))
        ch = {c: {s: float(d["%s_%s" % (c, s)]) for s in STATS} for c in CHANNELS}
        return cls(frame=int(float(d["frame"])), t_ms=int(float(d["t_ms"])), fps=float(d["fps"]),
                   exposure=int(float(d["exposure"])), gain=int(float(d["gain"])),
                   gain_x=float(d["gain_x"]), saturated=int(float(d["saturated"])),
                   range_state=int(float(d["range_state"])), width=int(float(d["width"])),
                   height=int(float(d["height"])), bin_px=int(float(d.get("bin", 1))), ch=ch,
                   t_host=time.monotonic())

    def signal(self, c="S", spot=True):
        """Integrated signal per unit exposure x gain (relative power reaching the sensor).

        ``spot=True``: the spot's photometry with a local background (robust to stray
        light); ``False``: the whole frame minus the border level."""
        value = self.ch[c]["spot_sum"] if spot else self.ch[c]["sum"]
        return value / max(1e-9, self.exposure * self.gain_x)

    def has_spot(self, c="S"):
        """A spot clearly above stray light and noise (not just hot pixels)."""
        st = self.ch[c]
        noise = max(st["noise"], 0.5)
        return (st["cx"] >= 0 and st["peak"] > 20 * noise
                and st["spot_sum"] > 10 * noise * math.sqrt(max(1.0, st["spot_px"])))

    @property
    def state(self):
        return RANGE_STATES.get(self.range_state, "?")


# --------------------------------------------------------------------------- #
class SerialLink:
    """Serial connection to the camera board. DTR/RTS stay low: they reset the board."""

    def __init__(self, port, baudrate=BAUD, timeout=4.0):
        import serial

        s = serial.Serial()
        s.port, s.baudrate, s.timeout, s.write_timeout = port, baudrate, timeout, timeout
        s.dtr = False
        s.rts = False
        s.exclusive = True
        s.open()
        self.serial = s
        self.port = port
        time.sleep(0.05)
        s.reset_input_buffer()

    def write(self, line):
        self.serial.write((line + "\n").encode())

    def readline(self):
        raw = self.serial.readline()
        if not raw:
            raise SenseError("no reply from the sensor (timeout)")
        return raw.decode(errors="replace").strip()

    def close(self):
        try:
            self.serial.close()
        except Exception:
            pass  # the device may already be gone: there is nothing left to close


def checked(line):
    """Strip and verify the "*HH" checksum of a data line (sum of bytes before '*' mod 256)."""
    body, star, tail = line.rpartition("*")
    if not star:
        return line  # replies without a checksum (settings, identity)
    if len(tail) != 2 or (sum(body.encode()) & 0xFF) != int(tail, 16):
        raise SenseError("corrupted reply (checksum): %r" % line[:60])
    return body


class Sensor:
    """SCPI client of a cmc-sense camera (serial link or the simulator)."""

    _streaming = False
    _replies = None       # reply queue while the reader thread owns the port
    _restarting = False   # the board was told to reboot: nothing may be sent to it
    _reader = None        # the stream reader thread
    _stream_error = ""    # what stopped the reader, reported by latest()
    _stream_latest = None

    def __init__(self, link, debug=False):
        self.link = link
        self.debug = debug
        self.lock = threading.Lock()
        self.identity = self._hello()
        if not self.identity.startswith("CMC,SENSE"):
            raise SenseError("not a cmc-sense sensor: %r" % self.identity)
        self.fields = self.query("MEAS:FIEL?").split(",")

    def _hello(self):
        """Identify the board, stopping a stream a previous session may have left running.

        Short timeouts: the wrong baud rate must be ruled out quickly (the caller tries
        the other one), not after several seconds.
        """
        port = getattr(self.link, "serial", None)
        normal = port.timeout if port is not None else None
        if port is not None:
            port.timeout = 0.5
        try:
            return self._hello_attempts()
        finally:
            if port is not None:
                port.timeout = normal

    def _hello_attempts(self):
        port = getattr(self.link, "serial", None)
        idn = ""
        for attempt in range(3):
            try:
                self.link.write("MEAS:STRE OFF")
            except Exception:
                pass
            # Wait until the board has really gone quiet: clearing the host's buffer is
            # not enough, the board's own TX buffer keeps pushing a stream for a while,
            # and a leftover line would be read as the answer to the next query.
            self._drain(quiet_s=0.4, deadline_s=1.5)
            try:
                self.link.write("*IDN?")
            except Exception:
                continue
            for _ in range(20):  # the answer may follow a few leftover lines
                try:
                    line = self.link.readline()
                except SenseError:
                    break
                if line.startswith("CMC,"):
                    return line
                idn = line or idn
        return idn

    def _drain(self, quiet_s=0.3, deadline_s=3.0):
        """Read and throw away whatever arrives until nothing has come for *quiet_s*.

        Returns True when the link fell quiet, False when *deadline_s* ran out first
        (the board is still streaming: the caller has to try again).
        """
        port = getattr(self.link, "serial", None)
        if port is None:
            return True
        normal, end = port.timeout, time.monotonic() + deadline_s
        port.timeout = quiet_s
        try:
            while time.monotonic() < end:
                if not port.readline():
                    try:
                        port.reset_input_buffer()
                    except Exception:
                        pass
                    return True
            return False
        except Exception:
            return False
        finally:
            port.timeout = normal

    @classmethod
    def open(cls, port, debug=False, bauds=(BAUD, FAST_BAUD), reset_if_silent=False):
        """Connect, trying the start-up rate first and then the fast one (the board keeps
        the rate a previous session switched it to until it is re-plugged).

        *reset_if_silent* resets a board that answers at neither rate. Closing a serial
        port toggles DTR/RTS, and on the ESP32-CAM-MB those lines drive IO0 and EN: a
        board can be left sitting in its bootloader, where it says nothing at all and
        cannot be found by scanning. Only pass it for a port known to carry a camera.
        """
        last = None
        for baud in bauds:
            link = SerialLink(port, baudrate=baud)
            try:
                return cls(link, debug=debug)
            except Exception as e:
                last = e
                link.close()
        if not reset_if_silent:
            raise last
        link = SerialLink(port, baudrate=BAUD)
        try:
            sensor = cls.__new__(cls)
            sensor.link, sensor.debug, sensor.lock = link, debug, threading.Lock()
            sensor.hard_reset()
            sensor.fields = sensor.query("MEAS:FIEL?").split(",")
            print("[cmc-light] the sensor was silent and has been reset", flush=True)
            return sensor
        except Exception:
            link.close()
            raise last

    @classmethod
    def simulated(cls, laser=None, debug=False):
        return cls(SimLink(laser), debug=debug)

    # -- low level -------------------------------------------------------- #
    def write(self, cmd):
        with self.lock:
            if self.debug:
                print("[sense] >", cmd, flush=True)
            self.link.write(cmd)

    def query(self, cmd, lines=1, timeout=5.0):
        with self.lock:
            if self.debug:
                print("[sense] >", cmd, flush=True)
            self.link.write(cmd)
            if getattr(self, "_streaming", False) and self._replies is not None:
                import queue as _queue  # replies come from the reader thread

                out = []
                for _ in range(lines):
                    try:
                        out.append(self._replies.get(timeout=timeout))
                    except _queue.Empty:
                        if lines > 1 or not cmd.endswith("?"):
                            raise SenseError("no reply from the sensor (timeout): %s" % cmd)
                        # one reply lost in the stream: ask again rather than give up
                        self.link.write(cmd)
                        try:
                            out.append(self._replies.get(timeout=timeout))
                        except _queue.Empty:
                            raise SenseError("no reply from the sensor (timeout): %s" % cmd)
            else:
                # Stream lines all start with "#", replies never do. The board can still
                # be emptying its buffer after "MEAS:STRE OFF", so skip what is left of
                # the stream instead of mistaking it for the answer.
                out = []
                for _ in range(lines):
                    line = self.link.readline()
                    for _ in range(200):
                        if not line.startswith("#"):
                            break
                        line = self.link.readline()
                    out.append(line)
            if self.debug:
                print("[sense] <", out[0][:120], flush=True)
            return out[0] if lines == 1 else out

    # -- streaming ---------------------------------------------------------- #
    # The camera pushes a reading after every analysed frame ("#M..." lines, profiles as
    # "#XR..." / "#YR..."), so readings arrive at the analysis rate instead of costing a
    # request round trip (which waits for the camera's frame boundary).

    def start_stream(self, bin=4, profiles_every=2):
        import queue as _queue

        self.stop_stream()
        self._replies = _queue.Queue()
        self._stream_latest = None
        self._stream_partial = None
        self._stream_error = ""
        self._streaming = True
        self._reader = threading.Thread(target=self._read_stream, name="cmc-sense stream", daemon=True)
        self._reader.start()
        self.write("MEAS:STRE ON,%d,%d" % (int(bin), int(profiles_every)))
        self._stream_bin = int(bin)

    def stop_stream(self):
        import queue as _queue

        if not getattr(self, "_streaming", False):
            return
        self._streaming = False
        try:
            self.link.write("MEAS:STRE OFF")
            time.sleep(0.2)
        except Exception:
            pass
        reader = getattr(self, "_reader", None)
        if reader is not None:
            reader.join(timeout=2)
        self._reader = None
        # A fresh queue, not None: replies the reader collected belong to commands that
        # are already answered (left in the queue they would be handed out as the answer
        # to the next query), and a reader that outlived the join above must still have
        # somewhere harmless to put what it reads.
        self._replies = _queue.Queue()
        self._drain(quiet_s=0.3, deadline_s=2.0)

    @property
    def streaming(self):
        return getattr(self, "_streaming", False)

    def latest(self):
        """The most recent streamed reading (None until one arrives)."""
        if self._stream_error:
            err, self._stream_error = self._stream_error, ""
            self._streaming = False
            raise SenseError(err)
        reader = getattr(self, "_reader", None)
        if self._streaming and reader is not None and not reader.is_alive():
            # the reader gave up (the link dropped): without this the same reading
            # would be handed out for ever and the GUI would simply stop updating
            self._streaming = False
            raise SenseError("the reading stream stopped")
        return self._stream_latest

    def _read_stream(self):
        while self._streaming:
            try:
                raw = self.link.serial.readline()
            except Exception as e:
                self._stream_error = "%s: %s" % (type(e).__name__, e)
                return
            if not raw:
                continue
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            if line.startswith("#"):
                try:
                    self._stream_line(line)
                except Exception:  # a damaged line must never stop the stream
                    pass
            else:
                replies = self._replies  # swapped out when the stream is stopped
                if replies is not None:
                    replies.put(line)

    def _stream_line(self, line):
        try:
            line = checked(line)  # the checksum covers the whole line, prefix included
        except SenseError:
            return  # a dropped byte: skip this line, the next frame follows in ~50 ms
        kind, body = line[:2], line[2:]
        if kind == "#M":
            r = Reading.parse(body, self.fields)
            r.bin = getattr(self, "_stream_bin", 4)
            prev = self._stream_partial or self._stream_latest
            if prev is not None:  # keep the profiles until new ones arrive
                r.prof_x, r.prof_y = prev.prof_x, prev.prof_y
            self._stream_partial = r
            self._stream_latest = r
        elif kind in ("#X", "#Y") and body[:1] in ("R", "G", "B", "S"):
            r = self._stream_partial
            if r is None:
                return
            values = [float(v) for v in body[1:].split(",") if v]
            (r.prof_x if kind == "#X" else r.prof_y)[body[0]] = values

    def errors(self):
        errs = []
        for _ in range(8):
            e = self.query("SYST:ERR?")
            if e.startswith("0,"):
                break
            errs.append(e)
        return errs

    def close(self):
        try:
            self.stop_stream()
        except Exception:
            pass
        try:
            self.link.close()
        except Exception:
            pass

    # -- measurements ------------------------------------------------------ #
    RETRIES = 3

    def _resync(self):
        """After a corrupted reply: drop what is buffered and realign on a known reply."""
        time.sleep(0.3)
        reset = getattr(getattr(self.link, "serial", None), "reset_input_buffer", None)
        if reset:
            reset()
        self.query("*OPC?")

    def wait_reading(self, fresh=True, timeout=5.0):
        """A streamed reading: the next one pushed (``fresh``) or the last that arrived."""
        last = self._stream_latest
        if not fresh and last is not None:
            return last
        after = last.frame if last is not None else -1
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            r = self.latest()
            if r is not None and r.frame != after:
                return r
            time.sleep(0.002)
        raise SenseError("no reading from the stream (timeout)")

    def measure(self, fresh=True):
        """A reading; ``fresh=False`` takes the latest analysed frame without waiting."""
        if self.streaming:  # the camera pushes readings: asking for one would collide
            return self.wait_reading(fresh)
        for attempt in range(self.RETRIES):
            line = self.query("MEAS?" if fresh else "MEAS:LAST?")
            if not line:
                raise SenseError("no measurement: %s" % "; ".join(self.errors()))
            try:
                return Reading.parse(checked(line), self.fields)
            except (SenseError, ValueError):
                if attempt == self.RETRIES - 1:
                    raise
                self._resync()

    def measure_all(self, bin=4, fresh=True):
        """A reading with x / y profiles of all channels (binned)."""
        if self.streaming:  # the stream already carries the profiles
            return self.wait_reading(fresh)
        for attempt in range(self.RETRIES):
            lines = self.query("MEAS:ALL%s? %d" % ("" if fresh else ":LAST", bin), lines=9)
            if not lines[0]:
                raise SenseError("no measurement: %s" % "; ".join(self.errors()))
            try:
                lines = [checked(line) for line in lines]
                r = Reading.parse(lines[0], self.fields)
                r.bin = bin
                nx = -(-(r.width // r.bin_px) // bin)  # camera binning, then transfer binning
                ny = -(-(r.height // r.bin_px) // bin)
                for i, c in enumerate(CHANNELS):
                    r.prof_x[c] = [float(v) for v in lines[1 + i].split(",") if v]
                    r.prof_y[c] = [float(v) for v in lines[5 + i].split(",") if v]
                    if len(r.prof_x[c]) != nx or len(r.prof_y[c]) != ny:
                        raise SenseError("profile has the wrong length")
                return r
            except (SenseError, ValueError):
                if attempt == self.RETRIES - 1:
                    raise
                self._resync()

    # -- settings ---------------------------------------------------------- #
    def set_auto_range(self, on):
        self.write("SENS:RANG:AUTO %s" % ("ON" if on else "OFF"))

    def auto_range(self):
        return self.query("SENS:RANG:AUTO?") == "1"

    def set_exposure(self, lines):
        self.write("SENS:EXP %d" % int(lines))

    def exposure(self):
        return int(self.query("SENS:EXP?"))

    def set_gain(self, gain):
        self.write("SENS:GAIN %d" % int(gain))

    def gain(self):
        return int(self.query("SENS:GAIN?"))

    def set_background(self, mode):
        self.write("SENS:BACK %s" % mode)

    def background(self):
        return self.query("SENS:BACK?")

    def acquire_dark(self, frames=8):
        self.write("SENS:BACK:DARK:ACQ %d" % frames)
        self.query("*OPC?")  # waits until the dark frames are taken

    def set_link_speed(self, baud=FAST_BAUD):
        """Switch the serial link to a faster rate (the board starts at 115200 again)."""
        serial_port = getattr(self.link, "serial", None)
        if serial_port is None or serial_port.baudrate == baud:
            return serial_port.baudrate if serial_port else 0
        was_streaming = self.streaming
        self.stop_stream()
        try:
            self.query("SYST:BAUD %d" % baud)
            serial_port.baudrate = baud
            time.sleep(0.3)
            serial_port.reset_input_buffer()
            if not self.query("*IDN?").startswith("CMC,SENSE"):
                raise SenseError("no reply at %d baud" % baud)
        except Exception:  # back to the safe rate
            serial_port.baudrate = BAUD
            time.sleep(0.3)
            serial_port.reset_input_buffer()
            try:
                self.query("*IDN?")
            except Exception:
                pass
            baud = BAUD
        if was_streaming:
            self.start_stream()
        return baud

    def set_binning(self, bin_px):
        """Analyse every bin_px-th pixel (1, 2, 4, 8): fewer pixels, faster readings."""
        self.write("SENS:BIN %d" % int(bin_px))

    def binning(self):
        return int(self.query("SENS:BIN?"))

    def set_threshold(self, fraction):
        self.write("SENS:THR %g" % fraction)

    def resolution(self):
        return self.query("SENS:RES?")

    BOOT_MARKERS = ("ets ", "rst:0x", "boot:0x", "entry 0x", "load:0x")

    def _await_boot(self, seconds=4.0):
        """True once the board's ROM boot banner appears: proof that it really restarted.

        The banner comes out at 115200, so the link must be at that rate to read it.
        """
        port = getattr(self.link, "serial", None)
        if port is None:
            return True
        normal, end = port.timeout, time.monotonic() + seconds
        port.timeout = 0.3
        try:
            while time.monotonic() < end:
                raw = port.readline()
                if raw and any(m in raw.decode(errors="replace") for m in self.BOOT_MARKERS):
                    return True
            return False
        finally:
            port.timeout = normal

    def set_resolution(self, res):
        """Set the frame size: the board stores it and restarts itself.

        The command is confirmed by watching for the boot banner, because a lost
        SENS:RES looks exactly like a board that restarted and then went quiet - and
        the client would wait for a reboot that never happened. The link is put back
        to 115200 first: that is where the board comes up, and where the banner is
        readable. Returns False when the size was already set, True after the restart.
        """
        if self.streaming:
            self.stop_stream()
        if self.resolution() == res:
            return False
        if getattr(self.link, "serial", None) is not None:
            self.set_link_speed(BAUD)
        for _ in range(3):
            self.write("SENS:RES %s" % res)
            if self._await_boot(4.0):
                self._restarting = True
                return True
            self._drain(0.3, 1.0)
            if self.resolution() == res:
                return False  # it was already this size after all: nothing to restart for
        raise SenseError("the sensor did not restart for the new frame size")

    def wait_restart(self, timeout=20.0, boot_s=2.5):
        """Wait for the board to come back from a restart, keeping the port open.

        The port is deliberately *not* closed and reopened: the USB-serial chip stays
        enumerated across the board's reboot, and closing the port toggles DTR/RTS,
        which drive EN and IO0 through the auto-reset circuit. That transient can drop
        the board into the ROM bootloader, where it is silent and no reconnect ever
        succeeds (the camera looked dead until the board was reset by hand).
        """
        port = getattr(self.link, "serial", None)
        if port is None:
            raise SenseError("this sensor has no serial link to wait for")
        self._streaming = False
        reader = getattr(self, "_reader", None)
        if reader is not None:
            reader.join(timeout=2)
        self._reader = None
        self._replies = None
        port.baudrate = BAUD  # a restarted board is back at its start-up rate
        time.sleep(boot_s)    # the rest of the boot log, then the camera comes up
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self._drain(quiet_s=0.4, deadline_s=2.0)
            try:
                idn = self._hello()
            except Exception:
                idn = ""
            if idn.startswith("CMC,SENSE"):
                self.identity = idn
                self._restarting = False
                return idn
            time.sleep(0.5)
        raise SenseError("the sensor did not answer after its restart")

    def hard_reset(self, timeout=10.0):
        """Reset the board over the auto-reset lines (what unwedges a silent board).

        RTS drives EN (reset) and DTR drives IO0; IO0 must stay high or the board comes
        up in the bootloader instead of the application.
        """
        port = getattr(self.link, "serial", None)
        if port is None:
            raise SenseError("this sensor has no serial link to reset")
        self._streaming = False
        self._reader = None
        self._replies = None
        port.dtr = False   # IO0 high: run the application
        port.rts = True    # EN low: hold in reset
        time.sleep(0.2)
        port.rts = False
        return self.wait_restart(timeout=timeout)

    def close_quietly(self):
        """Close without sending anything: for a board that is restarting or gone."""
        self._streaming = False
        reader = getattr(self, "_reader", None)
        if reader is not None:
            reader.join(timeout=1)
        self._reader = None
        try:
            self.link.close()
        except Exception:
            pass


USB_SERIAL_HINTS = ("usbserial", "usbmodem", "wchusb", "SLAB_USBtoUART", "ttyUSB", "ttyACM")


def find_sensors(ports=None, timeout=0.5, skip=()):
    """Serial ports with a cmc-sense camera: [(port, idn), ...].

    Only USB-serial ports are probed: opening a Bluetooth port costs seconds.
    """
    import serial

    if ports is None:
        from serial.tools import list_ports

        ports = [p.device for p in list_ports.comports()
                 if any(hint in p.device for hint in USB_SERIAL_HINTS)]
    found = []
    for port in ports:
        if port in skip:
            continue
        for baud in (BAUD, FAST_BAUD):  # the board may still run at the fast rate
            try:
                s = serial.Serial()
                s.port, s.baudrate, s.timeout = port, baud, timeout
                s.dtr = s.rts = False
                s.exclusive = True
                s.open()
            except Exception:
                break
            hit = None
            try:
                s.write(b"\nMEAS:STRE OFF\n")  # a session may have left the stream running
                time.sleep(0.25)
                s.reset_input_buffer()
                s.write(b"*IDN?\n")
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    line = s.readline().decode(errors="replace").strip()
                    if line.startswith("CMC,SENSE"):
                        hit = line
                        break
            except Exception:
                pass
            finally:
                s.close()
            if hit:
                found.append((port, hit))
                break
    return found


# --------------------------------------------------------------------------- #
class SimLink:
    """A simulated camera looking at the (simulated) lasers.

    Each laser makes a Gaussian spot with its own position, width and colour
    response; brightness follows the laser's emission and relative power. The
    firmware's auto-ranging, background and analysis are reproduced closely enough
    to exercise the GUI and the calibration code.
    """

    SPOTS = [  # laser index -> spot centre (fraction of the frame), sigma (px), RGB response
        dict(x=0.40, y=0.26, sigma=9.0, rgb=(0.10, 0.35, 1.00)),
        dict(x=0.39, y=0.55, sigma=7.5, rgb=(0.15, 1.00, 0.30)),
        dict(x=0.39, y=0.56, sigma=8.5, rgb=(1.00, 0.20, 0.10)),
    ]
    BRIGHTNESS = 400.0  # peak code per 300 exposure lines at full power and gain 1
    SIZES = {"QQVGA": (160, 120), "QVGA": (320, 240), "CIF": (400, 296), "VGA": (640, 480)}
    stored_size = "QVGA"  # the board keeps the frame size in flash across the restart

    def __init__(self, laser=None, width=None, height=None, seed=1):
        self.laser = laser
        self.res = self.stored_size
        default_w, default_h = self.SIZES[self.res]
        self.width, self.height = width or default_w, height or default_h
        self.exposure, self.gain, self.auto = 300, 0, True
        self.bin_px = 1
        self.bg_mode, self.thr = "EDGE", 0.2
        self.frame = 0
        self.errors = []
        self.out = []
        self.rng = random.Random(seed)
        self.t0 = time.monotonic()
        self.last = None
        self.dark = False

    def close(self):
        pass

    def readline(self):
        if not self.out:
            raise SenseError("no reply from the sensor (timeout)")
        return self.out.pop(0)

    # emulation of the firmware's analysis, on a coarse analytic model
    def _lasers(self):
        src = self.laser
        if src is None:
            return []
        out = []
        for k in range(min(3, src.n_channels)):
            try:
                on = src.emission(k + 1)
                p = src.power(k + 1)
            except Exception:
                on, p = False, 0.0
            if on and p > 0:
                out.append((k, p))
        return out

    GAIN_X = [1.0, 1.0625, 1.5, 2.0, 2.25, 2.5, 2.75, 4.0, 4.25, 4.5, 4.75, 5.0, 5.25, 5.5, 5.75,
              16.0, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0]

    def _analyse(self):
        self.frame += 1
        scale = self.exposure * self.GAIN_X[self.gain] * self.BRIGHTNESS / 300.0
        w, h = self.width, self.height
        ch = {}
        bg = {"R": 4.0, "G": 4.0, "B": 3.0}
        sat = 0
        spots = self._lasers()
        prof_x = {c: [0.0] * w for c in CHANNELS}
        prof_y = {c: [0.0] * h for c in CHANNELS}
        for i, c in enumerate("RGB"):
            peak_raw = bg[c]
            vol, mx, my, mxx, myy = 0.0, 0.0, 0.0, 0.0, 0.0
            for k, p in spots:
                sp = self.SPOTS[k]
                amp = p * sp["rgb"][i] * scale
                sig = sp["sigma"]
                cx, cy = sp["x"] * w, sp["y"] * h
                clipped = min(amp, 255.0 - bg[c])
                if amp > 255.0 - bg[c]:
                    sat += int(2 * math.pi * sig * sig * math.log(amp / (255.0 - bg[c])))
                volume = 2 * math.pi * sig * sig * amp
                if amp > clipped:  # clipping loses the part above full scale
                    volume -= 2 * math.pi * sig * sig * (amp - clipped - clipped * math.log(amp / clipped))
                vol += volume
                mx += volume * cx
                my += volume * cy
                mxx += volume * (cx * cx + sig * sig)
                myy += volume * (cy * cy + sig * sig)
                peak_raw = max(peak_raw, bg[c] + clipped)
                gx = [math.exp(-0.5 * ((x - cx) / sig) ** 2) for x in range(w)]
                gy = [math.exp(-0.5 * ((y - cy) / sig) ** 2) for y in range(h)]
                nx, ny = sum(gx) or 1.0, sum(gy) or 1.0
                for x in range(w):
                    prof_x[c][x] += volume * gx[x] / nx
                for y in range(h):
                    prof_y[c][y] += volume * gy[y] / ny
            noise = 0.5 + 0.002 * scale
            tot = vol + self.rng.gauss(0, noise * math.sqrt(w * h))
            st = dict(bg=bg[c], noise=noise, peak=round(peak_raw) - bg[c], sum=tot, npix=0,
                      cx=-1.0, cy=-1.0, sx=0.0, sy=0.0, angle=0.0, spot_sum=0.0, spot_bg=0.0, spot_px=0)
            if st["peak"] > 5 * noise and spots:
                cxm, cym = mx / vol, my / vol
                st.update(npix=int(vol / max(1.0, st["peak"])), cx=cxm + self.rng.gauss(0, 0.05),
                          cy=cym + self.rng.gauss(0, 0.05),
                          sx=math.sqrt(max(0.0, mxx / vol - cxm * cxm)), sy=math.sqrt(max(0.0, myy / vol - cym * cym)))
                half = 3 * st["sx"] + 3
                st.update(spot_sum=vol * 0.997 + self.rng.gauss(0, noise * 2 * half), spot_bg=bg[c],
                          spot_px=int((2 * half) ** 2))
            ch[c] = st
        s = dict(bg=sum(ch[c]["bg"] for c in "RGB"), noise=sum(ch[c]["noise"] for c in "RGB"),
                 peak=sum(ch[c]["peak"] for c in "RGB"), sum=sum(ch[c]["sum"] for c in "RGB"))
        wsum = sum(max(0.0, ch[c]["sum"]) for c in "RGB" if ch[c]["cx"] >= 0) or 1.0
        valid = [c for c in "RGB" if ch[c]["cx"] >= 0]
        s.update(npix=max([ch[c]["npix"] for c in "RGB"] + [0]),
                 cx=sum(ch[c]["cx"] * max(0.0, ch[c]["sum"]) for c in valid) / wsum if valid else -1.0,
                 cy=sum(ch[c]["cy"] * max(0.0, ch[c]["sum"]) for c in valid) / wsum if valid else -1.0,
                 sx=max([ch[c]["sx"] for c in valid] + [0.0]), sy=max([ch[c]["sy"] for c in valid] + [0.0]),
                 angle=0.0, spot_sum=sum(ch[c]["spot_sum"] for c in "RGB"),
                 spot_bg=sum(ch[c]["spot_bg"] for c in "RGB"), spot_px=max(ch[c]["spot_px"] for c in "RGB"))
        ch["S"] = s
        for i in range(w):
            prof_x["S"][i] = prof_x["R"][i] + prof_x["G"][i] + prof_x["B"][i]
        for j in range(h):
            prof_y["S"][j] = prof_y["R"][j] + prof_y["G"][j] + prof_y["B"][j]
        used = (self.exposure, self.gain)
        top = max(ch[c]["peak"] + ch[c]["bg"] for c in "RGB")
        state = 0
        if self.auto:
            exp, gain = self.exposure, self.gain
            if sat > 0 or top >= 235:
                if gain > 0:
                    gain = max(0, gain - 4)
                else:
                    exp = max(1, exp // 2)
            elif top < 90:
                f = min(4.0, 160.0 / max(8.0, top))
                if exp < 1200:
                    exp = min(1200, max(exp + 1, int(exp * f + 0.5)))
                elif gain < 30:
                    gain = min(30, gain + 2)
            if (exp, gain) != (self.exposure, self.gain):
                self.exposure, self.gain, state = exp, gain, 1
            elif sat > 0 or top >= 235:
                state = 2
            elif top < 90:
                state = 3
        fps = 8.0
        self.last = (used, sat, state, ch, prof_x, prof_y, fps)

    def _measurement_line(self):
        (exp, gain), sat, state, ch, _px, _py, fps = self.last
        head = [self.frame, int((time.monotonic() - self.t0) * 1000), "%.1f" % fps, exp, gain,
                "%.4f" % self.GAIN_X[gain], sat, state, self.width, self.height, self.bin_px]
        vals = []
        for c in CHANNELS:
            st = ch[c]
            vals += ["%.2f" % st["bg"], "%.2f" % st["noise"], "%.2f" % st["peak"], "%.1f" % st["sum"],
                     str(int(st["npix"])), "%.3f" % st["cx"], "%.3f" % st["cy"], "%.3f" % st["sx"],
                     "%.3f" % st["sy"], "%.2f" % st["angle"], "%.1f" % st["spot_sum"], "%.2f" % st["spot_bg"],
                     str(int(st["spot_px"]))]
        return ",".join(str(v) for v in head + vals)

    def write(self, line):
        line = line.strip()
        head, _, arg = line.partition(" ")
        head = head.upper()
        out = self.out
        if head == "*IDN?":
            out.append("CMC,SENSE-CAM-SIM,SIM,1.0")
        elif head == "*OPC?":
            out.append("1")
        elif head == "*RST":
            self.exposure, self.gain, self.auto, self.bg_mode, self.thr = 300, 0, True, "EDGE", 0.2
        elif head in ("SYST:ERR?", "SYSTEM:ERROR?"):
            out.append(self.errors.pop(0) if self.errors else '0,"No error"')
        elif head == "MEAS:FIEL?":
            out.append(",".join(["frame", "t_ms", "fps", "exposure", "gain", "gain_x", "saturated", "range_state",
                                 "width", "height", "bin"] + ["%s_%s" % (c, s) for c in CHANNELS for s in STATS]))
        elif head in ("MEAS?", "MEAS:LAST?"):
            self._analyse()
            out.append(self._measurement_line())
        elif head in ("MEAS:ALL?", "MEAS:ALL:LAST?"):
            b = max(1, int(arg or 4))
            self._analyse()
            out.append(self._measurement_line())
            _u, _s, _st, _ch, px, py, _f = self.last
            for prof in (px, py):
                for c in CHANNELS:
                    vals = prof[c][::self.bin_px]
                    out.append(",".join("%.1f" % sum(vals[i:i + b]) for i in range(0, len(vals), b)))
        elif head == "SENS:EXP":
            self.exposure, self.auto = max(1, min(1200, int(arg))), False
        elif head == "SENS:EXP?":
            out.append(str(self.exposure))
        elif head == "SENS:GAIN":
            self.gain, self.auto = max(0, min(30, int(arg))), False
        elif head == "SENS:GAIN?":
            out.append(str(self.gain))
        elif head == "SENS:RANG:AUTO":
            self.auto = arg.upper() in ("ON", "1")
        elif head == "SENS:RANG:AUTO?":
            out.append("1" if self.auto else "0")
        elif head == "SENS:BACK":
            self.bg_mode = arg.upper()
        elif head == "SENS:BACK?":
            out.append(self.bg_mode)
        elif head == "SENS:BACK:DARK:ACQ":
            self.dark = True
        elif head == "MEAS:STRE":
            self.stream = not arg.upper().startswith("OFF")
        elif head == "MEAS:STRE?":
            out.append("%d,4,2" % (1 if getattr(self, "stream", False) else 0))
        elif head == "SENS:BIN":
            self.bin_px = max(1, int(arg))
        elif head == "SENS:BIN?":
            out.append(str(self.bin_px))
        elif head == "SENS:THR":
            self.thr = float(arg)
        elif head == "SENS:RES":
            v = arg.upper()
            if v not in self.SIZES:
                self.errors.append('-224,"Illegal parameter value"')
            elif v != self.res:
                # like the board: the size is stored and it restarts, which loses
                # everything set at run time (binning, the stream, the range)
                SimLink.stored_size = v
                self.res = v
                self.width, self.height = self.SIZES[v]
                self.bin_px, self.stream, self.auto = 1, False, True
                self.exposure, self.gain = 300, 0
        elif head == "SENS:RES?":
            out.append(self.res)
        elif head == "CAL:LUT":
            self.lut_custom = True
        elif head == "CAL:LUT:RES":
            self.lut_custom = False
        elif head == "CAL:LUT:STAT?":
            out.append("CUSTOM" if getattr(self, "lut_custom", False) else "IDENTITY")
        else:
            self.errors.append('-113,"Undefined header; %s"' % line)
