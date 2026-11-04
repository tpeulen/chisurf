"""Python interface to the cmc-light ALEX source (SCPI over USB serial or WiFi).

    from cmc_light import LaserSource

    with LaserSource.open("/dev/cu.wchusbserial10") as src:   # or LaserSource.simulated()
        src.set_power(1, 0.6)                 # blue at 60 % relative power
        src.set_power(3, 0.3)                 # red at 30 %
        for ch in (1, 2, 3):
            src.set_emission(ch, True)
        src.load_alex(on_us=500, gap_us=50)   # 500 us per laser, 50 us dark
        src.set_sync_width(100)               # marker pulse on the sync output
        src.start()
        ...
        src.abort()

    LaserSource.open_tcp("cmc-light.local")   # raw SCPI socket, TCP port 5025
    find_instruments()                         # [(serial port, *IDN? reply), ...]
"""

import re
import threading
import time

try:
    from . import seqcore
except (ImportError, ValueError):
    from cmc_light import seqcore


class ScpiError(RuntimeError):
    pass


class CommunicationError(ScpiError):
    """Timeout or garbled exchange; the link was resynchronised."""


ERROR_LINE = re.compile(r'^-?\d+,"')


class SerialTransport:
    link = "USB"
    # measured: 8..18 ms per command incl. error check (docs/SCPI.md, help "Timing limits")
    live_interval_s = 0.020
    def __init__(self, port, baudrate=115200, timeout=1.0):
        import serial

        s = serial.Serial()
        s.port = port
        s.baudrate = baudrate
        s.timeout = timeout
        s.write_timeout = timeout
        s.dtr = False  # do not reset the board (auto-reset circuit)
        s.rts = False
        s.exclusive = True  # a second program on the same port corrupts both conversations
        try:
            s.open()
        except Exception as e:
            if "exclusive" in str(e).lower() or "resource temporarily unavailable" in str(e).lower() \
                    or getattr(e, "errno", None) in (11, 35):
                raise OSError("%s is in use by another program (close other cmc-light windows "
                              "or serial terminals)" % port) from e
            raise
        self.serial = s

    def write(self, line):
        self.serial.write((line + "\n").encode())

    def readline(self):
        raw = self.serial.readline()
        if not raw:
            raise TimeoutError("no reply from instrument")
        return raw.decode(errors="replace").strip()

    def drain(self):
        self.serial.reset_input_buffer()

    def close(self):
        self.serial.close()


class TcpTransport:
    """Raw SCPI socket (LXI port 5025): one command per line, replies end with newline."""

    link = "WiFi"
    live_interval_s = 0.100  # estimate for the ESP8266 access point, not measured yet

    def __init__(self, host, port=5025, timeout=2.0):
        import socket

        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(timeout)
        self._timeout = timeout
        self._buf = b""

    def write(self, line):
        self.sock.sendall((line + "\n").encode())

    def readline(self):
        import socket

        while b"\n" not in self._buf:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                raise TimeoutError("no reply from instrument")
            if not chunk:
                raise ConnectionError("instrument closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode(errors="replace").strip()

    def drain(self):
        import socket

        self._buf = b""
        self.sock.settimeout(0.05)
        try:
            while self.sock.recv(4096):
                pass
        except (socket.timeout, BlockingIOError):
            pass
        finally:
            self.sock.settimeout(self._timeout)

    def close(self):
        self.sock.close()


class SimTransport:
    link = "simulator"
    live_interval_s = 0.0
    def __init__(self, instrument=None):
        try:
            from .sim import make_instrument
        except (ImportError, ValueError):
            from cmc_light.sim import make_instrument

        self.instrument = instrument or make_instrument()
        self._replies = []

    def write(self, line):
        r = self.instrument.handle(line)
        if r is not None:
            self._replies.append(r)

    def readline(self):
        if not self._replies:
            raise TimeoutError("no reply from instrument")
        return self._replies.pop(0)

    def drain(self):
        self._replies.clear()

    def close(self):
        pass


class DebugTransport:
    """Echo every SCPI line to stdout (``LaserSource(..., debug=True)``)."""

    def __init__(self, transport, prefix="[scpi]"):
        self.inner = transport
        self.prefix = prefix
        self.link = getattr(transport, "link", "?")
        self.live_interval_s = getattr(transport, "live_interval_s", 0.0)

    def write(self, line):
        print("%s >> %s" % (self.prefix, line), flush=True)
        self.inner.write(line)

    def readline(self):
        try:
            r = self.inner.readline()
        except Exception as e:
            print("%s << (%s)" % (self.prefix, e), flush=True)
            raise
        print("%s << %s" % (self.prefix, r), flush=True)
        return r

    def drain(self):
        self.inner.drain()

    def close(self):
        self.inner.close()


class LaserSource:
    """High-level, thread-safe SCPI client. Channels are numbered from 1."""

    def __init__(self, transport, check_errors=True, debug=False):
        self.t = DebugTransport(transport) if debug else transport
        self.check_errors = check_errors
        self.lock = threading.RLock()
        self.identity = self._handshake()
        self.n_channels = int(self.query("SYSTem:CHANnels?"))
        self.channels = [self._channel_info(k) for k in range(1, self.n_channels + 1)]

    @property
    def link(self):
        """'USB', 'WiFi' or 'simulator'."""
        return getattr(self.t, "link", "?")

    @property
    def live_interval_s(self):
        """Shortest sensible spacing of live (computer-driven) updates on this link."""
        return getattr(self.t, "live_interval_s", 0.0)

    # -- construction ------------------------------------------------------
    @classmethod
    def open(cls, port, baudrate=115200, **kw):
        return cls(SerialTransport(port, baudrate), **kw)

    @classmethod
    def open_tcp(cls, host, port=5025, **kw):
        """Connect over WiFi, e.g. LaserSource.open_tcp("cmc-light.local")."""
        return cls(TcpTransport(host, port), **kw)

    @classmethod
    def simulated(cls, **kw):
        return cls(SimTransport(), **kw)

    def close(self):
        self.t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.abort()
            self.all_off()
        finally:
            self.close()

    # -- raw SCPI ----------------------------------------------------------
    def _handshake(self, attempts=6):
        """Find the instrument; tolerates a board that is still booting."""
        last = None
        with self.lock:
            for _ in range(attempts):
                self.t.drain()
                self.t.write("*IDN?")
                try:
                    # skip late replies / boot chatter until an identity line arrives
                    for _ in range(20):
                        reply = self.t.readline()
                        if reply.startswith("CMC,"):
                            # replies to earlier attempts may still be on the way
                            time.sleep(0.3)
                            self.t.drain()
                            self.t.write("*CLS")
                            return reply
                        last = reply
                except TimeoutError as e:
                    last = e
                time.sleep(0.3)
        raise ScpiError("no cmc-light SCPI instrument found (last reply: %r)" % (last,))

    def write(self, cmd):
        with self.lock:
            self._io(cmd, reply=False)

    def query(self, cmd):
        with self.lock:
            return self._io(cmd, reply=True)

    def _io(self, cmd, reply):
        """Send one command; on a timeout or an out-of-step reply, resynchronise and raise."""
        try:
            self.t.write(cmd)
            r = self.t.readline() if reply else None
            if self.check_errors:
                self._raise_errors(cmd)
            return r
        except (TimeoutError, OSError) as e:
            self._resync()
            raise CommunicationError("%s: %s (link resynchronised, command may not have run)"
                                     % (cmd, e))

    def errors(self):
        out = []
        with self.lock:
            for _ in range(20):
                self.t.write("SYSTem:ERRor?")
                r = self._error_line()
                if r.startswith("0,"):
                    return out
                out.append(r)
        return out

    def _error_line(self):
        r = self.t.readline()
        if not ERROR_LINE.match(r):
            # a late reply to an earlier command: the stream is out of step
            self._resync()
            raise CommunicationError("reply out of step (got %r where an error line was "
                                     "expected); link resynchronised" % r)
        return r

    def _raise_errors(self, cmd):
        self.t.write("SYSTem:ERRor?")
        r = self._error_line()
        if not r.startswith("0,"):
            rest = self.errors()
            raise ScpiError("%s -> %s" % (cmd, "; ".join([r] + rest)))

    def _resync(self, timeout=2.0):
        """Drop stale replies and realign on a *OPC? marker."""
        marker_deadline = time.monotonic() + timeout
        while time.monotonic() < marker_deadline:
            try:
                time.sleep(0.05)
                self.t.drain()
                self.t.write("*OPC?")
                while True:
                    if self.t.readline() == "1":
                        time.sleep(0.05)
                        self.t.drain()
                        return True
            except (TimeoutError, OSError):
                continue
        return False

    # -- channels ----------------------------------------------------------
    def _channel_info(self, k):
        return dict(
            index=k,
            name=self.query("SYSTem%d:INFormation:MODel?" % k),
            wavelength=int(self.query("SYSTem%d:INFormation:WAVelength?" % k)),
            color=self.query("SYSTem%d:INFormation:COLor?" % k),
        )

    def set_emission(self, ch, on):
        self.write("SOURce%d:AM:STATe %s" % (ch, "ON" if on else "OFF"))

    def set_emissions(self, states, check=True):
        """Switch several lasers in one SCPI line: {channel: on}. One round trip."""
        if not states:
            return
        line = ";".join("SOURce%d:AM:STATe %s" % (ch, "ON" if on else "OFF")
                        for ch, on in sorted(states.items()))
        with self.lock:
            if check:
                self.write(line)
            else:
                self.t.write(line)

    def emission(self, ch):
        return self.query("SOURce%d:AM:STATe?" % ch) == "ON"

    def set_power(self, ch, fraction):
        """Relative power 0..1 (pulse-width modulation of the TTL line)."""
        self.write("SOURce%d:POWer:LEVel:IMMediate:AMPLitude %.4f" % (ch, fraction))

    def power(self, ch):
        return float(self.query("SOURce%d:POWer:LEVel:IMMediate:AMPLitude?" % ch))

    def duty(self, ch):
        """Achieved relative power after timing quantisation."""
        return float(self.query("SOURce%d:POWer:DUTY?" % ch))

    def set_pwm_period(self, us):
        self.write("SOURce:PWM:PERiod %d" % us)

    def pwm_period(self):
        return int(self.query("SOURce:PWM:PERiod?"))

    def set_min_pulse(self, us):
        self.write("SOURce:PWM:MINimum %d" % us)

    def min_pulse(self):
        return int(self.query("SOURce:PWM:MINimum?"))

    def set_power_mode(self, mode):
        """How relative power < 1 is made in sequence mode (CW always uses PWM):
        'PWM' (pulse-width modulation inside every window) or 'CYCLes' (cycle
        dithering: windows stay solid, lit in a fraction of the periods)."""
        self.write("SOURce:PWM:MODE %s" % mode)

    def power_mode(self):
        """'PWM' or 'CYCL'."""
        return self.query("SOURce:PWM:MODE?")

    def set_source(self, source):
        """'CW' (lasers follow emission state) or 'SEQ' (lasers follow the sequence)."""
        self.write("SOURce:AM:SOURce %s" % source)

    def source(self):
        return self.query("SOURce:AM:SOURce?")

    # -- sequences ---------------------------------------------------------
    def load_alex(self, on_us, gap_us=0):
        self.write("SEQuence:ALEX %d,%d" % (on_us, gap_us))

    def load_steps(self, steps):
        """steps: [(duration_us, channel_mask), ...]; bit 0 = channel 1."""
        with self.lock:
            self.write("SEQuence:CLEar")
            for dur, mask in steps:
                self.write("SEQuence:STEP:APPend %d,%d" % (dur, mask))

    def steps(self):
        r = self.query("SEQuence:STEP:LIST?")
        return [tuple(int(v) for v in s.split(",")) for s in r.split(";") if s]

    def set_cycles(self, n):
        self.write("SEQuence:CYCLes %d" % n)

    def set_sync_width(self, us):
        self.write("SEQuence:SYNC:WIDTh %d" % us)

    def start(self):
        self.write("SEQuence:STARt")

    def abort(self):
        self.write("ABORt")

    def running(self):
        return self.query("SEQuence:STATe?") == "RUN"

    def cycles_done(self):
        return int(self.query("SEQuence:COUNt?"))

    # -- power monitor (light sensor on the instrument's I2C bus) ----------- #
    def monitor_present(self):
        return self.query("SENSe:POWer:PRESent?") == "1"

    def monitor_lux(self):
        """What the internal diode reads: the total power of whatever is emitting."""
        reply = self.query("SENSe:POWer?")
        return float("nan") if reply.startswith("nan") else float(reply)

    def monitor_gain(self, value=None):
        if value is None:
            reply = self.query("SENSe:POWer:GAIN?")
            return None if reply.startswith("nan") else int(reply)
        self.write("SENSe:POWer:GAIN %d" % int(value))

    def monitor_mode(self, mode=None):
        if mode is None:
            return self.query("SENSe:POWer:MODE?")
        self.write("SENSe:POWer:MODE %s" % mode)

    def i2c_pins(self, sda=None, scl=None):
        if sda is None:
            return self.query("SYSTem:I2C:PINS?")
        self.write("SYSTem:I2C:PINS %d,%d" % (int(sda), int(scl)))

    def i2c_scan(self):
        return [a for a in self.query("SYSTem:I2C:SCAN?").split(",") if a]

    def set_exclusive(self, on):
        """One laser at a time: for measuring a single laser's power."""
        self.write("SOURce:EXCLusive %s" % ("ON" if on else "OFF"))

    def exclusive(self):
        return self.query("SOURce:EXCLusive?") == "ON"

    def timing(self):
        late, edges, period = (int(v) for v in self.query("SEQuence:TIMing?").split(","))
        return dict(late_max_us=late, edges=edges, period_us=period)

    def all_off(self):
        with self.lock:
            self.write("ABORt")
            self.write("SOURce:AM:SOURce CW")
            for k in range(1, self.n_channels + 1):
                self.write("SOURce%d:AM:STATe OFF" % k)

    # -- WiFi (stored on the instrument; takes effect after apply_wlan) -----
    def set_wlan(self, ssid, password=""):
        """Join this network from now on ("" = own access point 'cmc-light')."""
        with self.lock:
            self.write('SYSTem:COMMunicate:WLAN:SSID "%s"' % ssid.replace('"', '""'))
            self.write('SYSTem:COMMunicate:WLAN:PASSword "%s"' % password.replace('"', '""'))

    def apply_wlan(self):
        """Reconnect with the stored settings (drops a TCP connection to the instrument)."""
        self.t.write("SYSTem:COMMunicate:WLAN:APPLy")

    def wlan(self):
        ssid = self.query("SYSTem:COMMunicate:WLAN:SSID?")
        return dict(ssid=ssid[1:-1].replace('""', '"'),
                    mode=self.query("SYSTem:COMMunicate:WLAN:MODE?"),
                    address=self.query("SYSTem:COMMunicate:WLAN:ADDRess?"))

    # -- local preview -----------------------------------------------------
    @staticmethod
    def preview(steps, enabled, powers, pwm_period_us=1000, min_pulse_us=20):
        """Same timing the instrument will play: (period_us, intervals, duty)."""
        return seqcore.channel_intervals(steps, enabled, powers, pwm_period_us, min_pulse_us)


def find_instruments(timeout=0.4):
    """Serial ports with a cmc-light instrument: [(port, idn), ...].

    Probes every port with *IDN? without resetting the boards (DTR/RTS low).
    """
    import serial
    from serial.tools import list_ports

    found = []
    for info in list_ports.comports():
        name = info.device
        if "Bluetooth" in name or "debug-console" in name:
            continue
        try:
            s = serial.Serial()
            s.port = name
            s.baudrate = 115200
            s.timeout = timeout
            s.write_timeout = timeout
            s.dtr = False
            s.rts = False
            s.open()
        except (OSError, serial.SerialException):
            continue
        try:
            s.reset_input_buffer()
            s.write(b"\n*IDN?\n")
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                line = s.readline().decode(errors="replace").strip()
                if line.startswith("CMC,"):
                    found.append((name, line))
                    break
        except (OSError, serial.SerialException):
            pass
        finally:
            s.close()
    return found
