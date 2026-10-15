"""Bounded local playback, with feedback suppression for mixed WASAPI loopback."""
import queue
import threading
import time


class FeedbackGate:
    def __init__(self, clock=time.monotonic, tail_seconds=.3):
        self.clock, self.tail_seconds = clock, tail_seconds
        self.active = threading.Event()
        self.until = 0.0

    def begin(self):
        self.active.set()

    def end(self):
        self.until = self.clock() + self.tail_seconds
        self.active.clear()

    def paused(self):
        return self.active.is_set() or self.clock() < self.until


class LocalPlayback(threading.Thread):
    def __init__(self, p, device, stop, gate, play, report, volume=None):
        super().__init__(name="local-translation-playback", daemon=True)
        self.p, self.device, self.stop, self.gate = p, device, stop, gate
        self.play, self.report = play, report
        self.queue = queue.Queue(maxsize=2)
        self.volume = volume

    def submit(self, samples, rate, direction="in"):
        if self.stop.is_set():
            return False
        try:
            self.queue.put_nowait((samples, rate, direction))
            return True
        except queue.Full:
            self.report("本地译音播放积压，已跳过一句试听；字幕和虚拟麦克风发送不受影响")
            return False

    def run(self):
        while not self.stop.is_set():
            try:
                samples, rate, direction = self.queue.get(timeout=.1)
            except queue.Empty:
                continue
            if self.stop.is_set():
                break
            self.gate.begin()
            try:
                if self.volume is None:
                    self.play(self.p, self.device, samples, rate, self.stop)
                else:
                    self.play(self.p, self.device, samples, rate, self.stop,
                              volume=lambda: self.volume(direction))
            except Exception as exc:
                self.report(f"本地译音播放失败：{exc}")
            finally:
                self.gate.end()
