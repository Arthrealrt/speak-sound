import queue
import threading
import time

from PySide6.QtCore import QObject, Signal
import pyaudiowpatch as pa

from .audio import Capture, play, resolve
from .models import LocalModels


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
            mic = resolve(p, "microphone", self.settings.microphone)
            receive = resolve(p, "receive", self.settings.receive_device)
            output = resolve(p, "output", self.settings.output_device)
            if not any(marker in self.settings.output_device.lower() for marker in ("cable", "voicemeeter", "virtual")):
                raise ValueError("发送输出请选择虚拟音频线的播放端（例如 CABLE Input），避免把语音送往扬声器")
            incoming, outgoing = queue.Queue(maxsize=2), queue.Queue(maxsize=2)
            captures = [
                Capture(p, receive, incoming, self.stop, lambda: True, self.settings, self.events.status.emit),
                Capture(p, mic, outgoing, self.stop,
                        lambda: not self.sending.is_set() and (not self.settings.push_to_talk or self.talking.is_set()),
                        self.settings, self.events.status.emit),
            ]

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
                            "jpn_Jpan" if direction == "in" else "zho_Hans",
                            "zho_Hans" if direction == "in" else "jpn_Jpan")
                        if self.stop.is_set() or not translated:
                            continue
                        self.events.transcript.emit(direction, original, translated, time.monotonic() - started)
                        if direction == "in":
                            self.events.subtitle.emit(original, translated)
                        else:
                            self.sending.set()
                            try:
                                samples, rate = models.synthesize(translated)
                                if not self.stop.is_set():
                                    play(p, output, samples, rate, self.stop)
                            finally:
                                self.sending.clear()
                    except Exception as exc:
                        self.events.status.emit(f"处理失败：{exc}")

            children = captures + [threading.Thread(target=worker, args=(incoming, "in"), daemon=True),
                                    threading.Thread(target=worker, args=(outgoing, "out"), daemon=True)]
            for child in children:
                child.start()
            self.events.active.emit(True)
            self.events.status.emit("翻译运行中 · 按住 F8 说中文" if self.settings.push_to_talk else "翻译运行中 · 自动检测中文讲话")
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
