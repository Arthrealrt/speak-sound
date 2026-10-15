import queue
import threading
import time

from PySide6.QtCore import QObject, Signal
import pyaudiowpatch as pa

from .audio import Capture, play, resolve
from .models import LocalModels
from .routing import require_open_output
from .playback import FeedbackGate, LocalPlayback


class Events(QObject):
    status = Signal(str)
    subtitle = Signal(str, str)
    transcript = Signal(str, str, str, float)
    active = Signal(bool)
    finished = Signal()


class Service:
    def __init__(self, settings):
        self.settings = settings
        self.events = Events()
        self.stop = threading.Event()
        self.talking = threading.Event()
        self.sending = threading.Event()
        self.feedback = FeedbackGate()
        self.thread = threading.Thread(target=self.run, name="translation-service", daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        p = None
        children = []
        try:
            models = LocalModels(self.settings, self.events.status.emit, self.stop.is_set)
            if self.stop.is_set():
                return
            p = pa.PyAudio()
            receive = resolve(p, "receive", self.settings.receive_device)
            mic = output = None
            if not self.settings.receive_only:
                mic = resolve(p, "microphone", self.settings.microphone)
            if not self.settings.receive_only and self.settings.send_to_virtual:
                output = resolve(p, "output", self.settings.output_device)
                require_open_output(self.settings.output_device)
            local = None
            if self.settings.speak_incoming or (not self.settings.receive_only and self.settings.monitor_outgoing):
                listen = resolve(p, "output", self.settings.listen_device)
                if self.settings.listen_device == self.settings.output_device and output is not None:
                    raise ValueError("本地试听请选择耳机，不能与虚拟麦克风播放端使用同一设备")
                local = LocalPlayback(p, listen, self.stop, self.feedback, play, self.events.status.emit)
            incoming, outgoing = queue.Queue(maxsize=2), queue.Queue(maxsize=2)
            captures = [
                Capture(p, receive, incoming, self.stop, lambda: not self.feedback.paused(), self.settings, self.events.status.emit),
            ]
            if not self.settings.receive_only:
                captures.append(Capture(p, mic, outgoing, self.stop,
                    lambda: not self.sending.is_set() and not self.feedback.paused()
                            and (not self.settings.push_to_talk or self.talking.is_set()),
                    self.settings, self.events.status.emit))

            def worker(q, direction):
                while not self.stop.is_set():
                    try:
                        pcm = q.get(timeout=.1)
                    except queue.Empty:
                        continue
                    try:
                        started = time.monotonic()
                        original = models.recognize(pcm, "ja" if direction == "in" else "zh")
                        if not original or self.stop.is_set():
                            continue
                        translated = models.translate(original,
                            "ja" if direction == "in" else "zh",
                            "zh" if direction == "in" else "ja")
                        if self.stop.is_set() or not translated:
                            continue
                        self.events.transcript.emit(direction, original, translated, time.monotonic() - started)
                        if direction == "in":
                            self.events.subtitle.emit(original, translated)
                            if self.settings.speak_incoming:
                                samples, rate = models.synthesize(translated, "zh")
                                if not self.stop.is_set():
                                    local.submit(samples, rate)
                        else:
                            self.sending.set()
                            try:
                                samples, rate = models.synthesize(translated)
                                if not self.stop.is_set():
                                    if self.settings.monitor_outgoing:
                                        local.submit(samples, rate)
                                    if self.settings.send_to_virtual:
                                        play(p, output, samples, rate, self.stop)
                            finally:
                                self.sending.clear()
                    except Exception as exc:
                        self.events.status.emit(f"处理失败：{exc}")

            children = captures + [threading.Thread(target=worker, args=(incoming, "in"), daemon=True)]
            if not self.settings.receive_only:
                children.append(threading.Thread(target=worker, args=(outgoing, "out"), daemon=True))
            if local is not None:
                children.insert(0, local)
            for child in children:
                child.start()
            self.events.active.emit(True)
            if self.settings.receive_only:
                self.events.status.emit("队友翻译运行中 · 日语 → 中文字幕" + ("及中文播报" if self.settings.speak_incoming else ""))
            else:
                route = "发送到虚拟麦克风" if self.settings.send_to_virtual else "仅本地试听，不向游戏发送"
                self.events.status.emit(("按住 F8 说中文 · " if self.settings.push_to_talk else "自动检测中文讲话 · ") + route)
            self.stop.wait()
        except Exception as exc:
            self.events.status.emit(f"无法启动：{exc}")
        finally:
            self.stop.set()
            # Workers may still be inside inference. Keep their models/audio owner alive until they finish.
            for child in children:
                if child.ident is not None:
                    child.join()
            if p is not None:
                p.terminate()
            self.events.active.emit(False)
            self.events.finished.emit()
