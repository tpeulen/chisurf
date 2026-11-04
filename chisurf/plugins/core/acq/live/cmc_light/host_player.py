"""Play a step sequence from the computer (live control), step by step.

For sequences that do not need MCU timing: each step switches the lasers'
emission with SCPI commands, on an absolute schedule so timing does not drift.
Relative power still comes from the MCU's continuous PWM. The shortest useful
step is the link's live interval (USB ~20 ms, WiFi ~100 ms); timing is only as
good as the operating system's sleep plus the command round trip, and the worst
lateness is measured and reported.
"""

from __future__ import annotations

import threading
import time


class HostPlayer:
    CHECK_EVERY = 25  # read the instrument's error queue every N steps
    def __init__(self, src, steps, enabled, cycles=0, clock=time.monotonic, sleep=time.sleep):
        self.src = src
        self.steps = [(int(d), int(m)) for d, m in steps]
        self.enabled = list(enabled)
        self.cycles_max = int(cycles)
        self.clock = clock
        self.sleep = sleep
        self.cycles = 0
        self.steps_played = 0
        self.late_max_ms = 0.0
        self.error = ""
        self._stop = threading.Event()
        self._thread = None

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not self.steps:
            raise ValueError("sequence is empty")
        self._thread = threading.Thread(target=self._run, name="cmc-light host player", daemon=True)
        self._thread.start()
        return self

    def stop(self, wait=True):
        self._stop.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=5)

    def _wait_until(self, deadline):
        """Sleep coarse, then finish with short sleeps: OS sleep overshoots by ~1 ms."""
        while not self._stop.is_set():
            left = deadline - self.clock()
            if left <= 0:
                return True
            self.sleep(min(left - 0.002, 0.05) if left > 0.004 else 0.0002)
        return False

    def _run(self):
        src = self.src
        n = len(self.enabled)
        state = [None] * n
        try:
            src.set_source("CW")
            t = self.clock()
            while not self._stop.is_set():
                for dur, mask in self.steps:
                    changes = {}
                    for k in range(n):
                        want = bool(self.enabled[k] and (mask >> k) & 1)
                        if state[k] != want:
                            changes[k + 1] = want
                            state[k] = want
                    self.steps_played += 1
                    # one SCPI line per step; the error queue is read only every few steps
                    check = self.steps_played % self.CHECK_EVERY == 0
                    batch = getattr(src, "set_emissions", None)
                    if batch is not None:
                        batch(changes, check=check)
                    else:
                        for ch, on in changes.items():
                            src.set_emission(ch, on)
                    late = (self.clock() - t) * 1000.0
                    if late > self.late_max_ms:
                        self.late_max_ms = late
                    t += dur / 1e6
                    if not self._wait_until(t):
                        break
                else:
                    self.cycles += 1
                    if self.cycles_max and self.cycles >= self.cycles_max:
                        break
                    continue
                break
        except Exception as e:  # report, and fall through to switch off
            self.error = str(e)
            print("[cmc-light] ERROR host player: %s" % e, flush=True)
        finally:
            for k in range(n):
                try:
                    src.set_emission(k + 1, False)
                except Exception:
                    pass
