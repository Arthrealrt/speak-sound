import queue
import threading
import time
from dataclasses import replace

from PySide6.QtCore import QObject, Signal
import pyaudiowpatch as pa

from .audio import Capture, play, resolve
from .models import LocalModels
from .routing import require_open_output, require_physical_microphone, is_virtual_microphone
from .playback import FeedbackGate, LocalPlayback
from .process_audio import ProcessCapture
from .realtime import RealtimeVoice
from .voice import process_utterance
from .queues import LatestQueue
from .streaming import SpeechQueue, ResultCache, PreviewBusy


class Events(QObject):
    status = Signal(str)
    subtitle = Signal(str, str)
    transcript = Signal(str, str, str, float)
    preview = Signal(str, str, str)
    metrics = Signal(object)
    active = Signal(bool)
    finished = Signal()


class Service:
    def __init__(self, settings, process_target=None):
        self.settings = settings
        self.process_target = process_target
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
            live = self.settings.operating_mode == "live_translation"
            translation_only = self.settings.operating_mode == "translation_only"
            if not self.settings.receive_only:
                require_physical_microphone(self.settings.microphone)
            models = LocalModels(self.settings, self.events.status.emit, self.stop.is_set)
            if self.stop.is_set():
                return
            p = pa.PyAudio()
            receive = None
            if self.settings.receive_mode == "process":
                if self.process_target is None or not self.process_target.alive():
                    raise ValueError("请选择仍在运行的接收进程")
            else:
                if is_virtual_microphone(self.settings.receive_device):
                    raise ValueError("接收不能选择本软件的发送声卡，以防循环翻译")
                receive = resolve(p, "receive", self.settings.receive_device)
            mic = output = None
            if not self.settings.receive_only:
                mic = resolve(p, "microphone", self.settings.microphone)
            if not self.settings.receive_only and self.settings.send_to_virtual:
                output = resolve(p, "output", self.settings.output_device)
                require_open_output(self.settings.output_device)
            local = listen = None
            if self.settings.speak_incoming or (not self.settings.receive_only and
                    (self.settings.monitor_outgoing or (live and self.settings.monitor_live_voice))):
                listen = resolve(p, "output", self.settings.listen_device)
                if self.settings.listen_device == self.settings.output_device and output is not None:
                    raise ValueError("本地试听请选择耳机，不能与虚拟麦克风播放端使用同一设备")
                def volume(direction):
                    if self.settings.playback_muted:
                        return 0.0
                    return (self.settings.incoming_volume if direction == "in" else self.settings.outgoing_volume) / 100
                if self.settings.speak_incoming or (not self.settings.receive_only and self.settings.monitor_outgoing):
                    local = LocalPlayback(p, listen, self.stop, self.feedback, play, self.events.status.emit, volume)
            # Re-running Whisper on every short prefix adds contention. Preserve
            # 60 ms pause previews, but space continuous Whisper work by >=1.8 s.
            incoming = SpeechQueue(maxsize=1, min_preview_ms=1800, zero_tail_only=True)
            outgoing = SpeechQueue(maxsize=2, latest=False,
                                   min_preview_ms=0 if models.zh_asr is not None else 1800,
                                   zero_tail_only=models.zh_asr is None)
            incoming_speech = LatestQueue(maxsize=1)
            outgoing_speech = queue.Queue(maxsize=2)
            receiving_settings = replace(self.settings, silence_ms=self.settings.incoming_silence_ms,
                                         max_speech_seconds=self.settings.incoming_max_seconds)
            if self.settings.receive_mode == "process":
                captures = [ProcessCapture(self.process_target, incoming, self.stop, receiving_settings, self.events.status.emit)]
            else:
                captures = [Capture(p, receive, incoming, self.stop, lambda: not self.feedback.paused(), receiving_settings, self.events.status.emit)]
            if not self.settings.receive_only:
                if live:
                    captures.append(RealtimeVoice(p, mic, output,
                        listen if self.settings.monitor_live_voice else None,
                        self.settings, self.stop, self.talking, self.events.status.emit,
                        translation_destination=outgoing, capture_enabled=lambda: self.settings.headphones_mode or not self.feedback.paused()))
                else:
                    captures.append(Capture(p, mic, outgoing, self.stop,
                        lambda: (self.settings.headphones_mode or not self.feedback.paused())
                                and (not self.settings.push_to_talk or self.talking.is_set()),
                        self.settings, self.events.status.emit))

            def worker(q, direction):
                cache = ResultCache()
                while not self.stop.is_set():
                    try:
                        packet = q.get(timeout=.1)
                    except queue.Empty:
                        continue
                    try:
                        started = time.monotonic()
                        source = self.settings.incoming_language if direction == 'in' else 'zh'
                        target = 'zh' if direction == 'in' else self.settings.target_language
                        cached = cache.get(packet.pcm)
                        asr_ms = mt_ms = 0.
                        if cached:
                            original, translated = cached
                        else:
                            kwargs = {} if packet.final else {'preview': True}
                            original = models.recognize(packet.pcm, source, **kwargs)
                            recognized_at = time.monotonic()
                            if not original or self.stop.is_set():
                                continue
                            translated = models.translate(original, source, target, **kwargs)
                            translated_at = time.monotonic()
                            asr_ms, mt_ms = (recognized_at - started) * 1000, (translated_at - recognized_at) * 1000
                            if original and translated:
                                cache.put(packet.pcm, (original, translated))
                        if not original or self.stop.is_set():
                            continue
                        if self.stop.is_set() or not translated:
                            continue
                        if not packet.final:
                            if q.current(packet):
                                self.events.preview.emit(direction, original, translated)
                            continue  # Speculation is never spoken or written to history.
                        metrics = dict(direction=direction, queue_ms=max(0, (started - packet.created) * 1000),
                            asr_ms=asr_ms, mt_ms=mt_ms, reused_preview=bool(cached),
                            final_to_text_ms=(time.monotonic() - packet.created) * 1000,
                            estimated_end_to_text_ms=(time.monotonic() - packet.speech_end) * 1000 if packet.speech_end else None)
                        self.events.metrics.emit(metrics)
                        self.events.transcript.emit(direction, original, translated, time.monotonic() - started)
                        if direction == "in":
                            self.events.subtitle.emit(original, translated)
                            if self.settings.speak_incoming:
                                incoming_speech.put_nowait(translated)
                        else:
                            if live and not self.settings.monitor_outgoing:
                                continue  # Translation text still appears; the virtual mic carries live original speech.
                            try:
                                outgoing_speech.put_nowait((translated, time.monotonic()))
                            except queue.Full:
                                self.events.status.emit('我方译音发送积压，已跳过一句播报；译文仍保留。请缩短报点。')
                    except PreviewBusy:
                        continue  # Finals take priority; the next preview replaces this one.
                    except Exception as exc:
                        self.events.status.emit(f"处理失败：{exc}")

            def speak_outgoing():
                while not self.stop.is_set():
                    try:
                        translated, queued_at = outgoing_speech.get(timeout=.1)
                    except queue.Empty:
                        continue
                    # Drop stale voice callouts instead of saying an obsolete position.
                    if time.monotonic() - queued_at > 3:
                        self.events.status.emit('我方译音等待超过 3 秒，已跳过过时播报；译文仍保留。')
                        continue
                    try:
                        begin = time.monotonic()
                        samples, rate = models.synthesize(translated, self.settings.target_language)
                        if not translation_only:
                            samples = process_utterance(samples, rate, self.settings)
                        self.events.metrics.emit(dict(direction='out_voice', tts_ms=(time.monotonic()-begin)*1000,
                            voice_queue_ms=(begin-queued_at)*1000))
                        if not self.stop.is_set():
                            if self.settings.monitor_outgoing:
                                local.submit(samples, rate, 'out')
                            if self.settings.send_to_virtual and not live:
                                play(p, output, samples, rate, self.stop,
                                    volume=lambda: 0 if self.settings.send_muted else self.settings.send_volume / 100)
                    except Exception as exc:
                        self.events.status.emit(f'我方译音播放失败：{exc}')

            def speak_received():
                while not self.stop.is_set():
                    try:
                        text = incoming_speech.get(timeout=.1)
                    except queue.Empty:
                        continue
                    if self.settings.playback_muted or self.settings.incoming_volume <= 0:
                        continue
                    try:
                        samples, rate = models.synthesize(text, "zh")
                        if not self.stop.is_set():
                            local.submit(samples, rate)
                    except Exception as exc:
                        self.events.status.emit(f"中文播报失败：{exc}")

            children = captures + [threading.Thread(target=worker, args=(incoming, "in"), daemon=True)]
            if self.settings.speak_incoming:
                children.append(threading.Thread(target=speak_received, name="incoming-tts", daemon=True))
            if not self.settings.receive_only:
                children.append(threading.Thread(target=worker, args=(outgoing, "out"), daemon=True))
                children.append(threading.Thread(target=speak_outgoing, name='outgoing-tts', daemon=True))
            if local is not None:
                children.insert(0, local)
            for child in children:
                child.start()
            self.events.active.emit(True)
            incoming_name = "英语" if self.settings.incoming_language == "en" else "日语"
            target_name = "英语" if self.settings.target_language == "en" else "日语"
            if self.settings.receive_only:
                self.events.status.emit("队友翻译运行中 · " + incoming_name + " → 中文字幕" + ("及中文播报" if self.settings.speak_incoming else ""))
            else:
                route = ("实时原声变声发送，译文继续显示/试听" if live
                         else "中文 → " + target_name + "译音" +
                            (" → 变声" if self.settings.voice_enabled and not translation_only else ""))
                self.events.status.emit(("独立双向翻译运行中（不变声） · " if translation_only else "双向翻译运行中 · ") + route +
                    (" · 虚拟麦克风发送已开启" if self.settings.send_to_virtual else " · 本地试听"))
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
