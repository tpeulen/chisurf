"""Qt-free OS audio transport with true process pause/resume and cleanup."""

import os
import shutil
import signal
import subprocess
import tempfile
import time

from .core import _write_wav_mono


class NativeSoundPlayer:
    def __init__(self, command=None, clock=time.monotonic, spawn=subprocess.Popen):
        self.command = command
        self.clock = clock
        self.spawn = spawn
        self.process = None
        self.path = None
        self.duration = self.position = 0.0
        self.started = 0.0
        self.state = "stopped"
        self.error_log = None

    def load_audio(self, waveform, sample_rate):
        self.close()
        fd, self.path = tempfile.mkstemp(prefix="chisurf-audifier-", suffix=".wav")
        os.close(fd)
        try:
            _write_wav_mono(self.path, waveform, sample_rate)
            self.duration = len(waveform) / sample_rate
        except Exception:
            self.close()
            raise

    def _command(self):
        if self.command:
            return [*self.command, self.path]
        for name, options in (
            ("afplay", []),
            ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error"]),
            ("aplay", ["-q"]),
        ):
            executable = shutil.which(name)
            if executable:
                return [executable, *options, self.path]
        raise RuntimeError(
            "No native audio player is installed (afplay, ffplay or aplay). WAV export remains available."
        )

    def play(self):
        if self.state == "paused" and self.process is not None:
            self.process.send_signal(signal.SIGCONT)
            self.started = self.clock() - self.position
        else:
            if not self.path:
                raise ValueError("Render audio before playback.")
            self.stop()
            if self.error_log:
                self.error_log.close()
            self.error_log = tempfile.TemporaryFile()
            self.process = self.spawn(
                self._command(), stdout=subprocess.DEVNULL, stderr=self.error_log
            )
            self.started = self.clock()
        self.state = "playing"

    def poll(self):
        if self.state == "playing":
            self.position = min(self.duration, max(0, self.clock() - self.started))
            code = self.process.poll()
            if code is not None:
                self.state = "finished" if code == 0 else "error"
                if code:
                    self.error_log.seek(0)
                    detail = self.error_log.read(2048).decode(errors="replace").strip()
                    raise RuntimeError(f"Native audio player exited with status {code}: {detail}")
                self.position = self.duration
        return self.position, self.duration

    def pause(self):
        if self.state == "playing":
            self.poll()
            if self.state == "playing":
                self.process.send_signal(signal.SIGSTOP)
                self.state = "paused"

    def stop(self):
        if self.process and self.process.poll() is None:
            if self.state == "paused":
                self.process.send_signal(signal.SIGCONT)
            self.process.terminate()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
        self.process = None
        self.position = 0.0
        self.state = "stopped"

    def revert(self):
        playing = self.state == "playing"
        self.stop()
        if playing:
            self.play()

    def close(self):
        self.stop()
        if self.error_log:
            self.error_log.close()
            self.error_log = None
        if self.path:
            os.unlink(self.path)
            self.path = None
        self.duration = 0.0
