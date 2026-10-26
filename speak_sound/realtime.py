"""Bounded, continuous microphone -> effects -> virtual microphone/monitor path."""
import math
import queue
import threading

import numpy as np
import pyaudiowpatch as pa
from scipy.signal import resample_poly
import webrtcvad

from .voice import VoiceProcessor
from .segmenter import Segmenter


def resample(samples, source_rate, target_rate):
    if source_rate == target_rate:
        return samples
    divisor = math.gcd(source_rate, target_rate)
    return resample_poly(samples, target_rate // divisor, source_rate // divisor).astype(np.float32)


class RealtimeSink:
    def __init__(self, p, info, stop, volume):
        self.rate = int(info["defaultSampleRate"])
        self.channels = min(2, int(info["maxOutputChannels"]))
        self.stop, self.volume = stop, volume
        self.queue = queue.Queue(maxsize=3)
        self.pending = b""
        self.stream = p.open(format=pa.paInt16, channels=self.channels, rate=self.rate,
                             output=True, output_device_index=int(info["index"]),
                             frames_per_buffer=round(self.rate * .02), stream_callback=self.callback)

    def submit(self, samples, rate):
        samples = resample(samples, rate, self.rate)
        data = np.repeat(samples[:, None], self.channels, axis=1).astype(np.float32).tobytes()
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.queue.put_nowait(data)
            except queue.Full:
                pass

    def callback(self, unused, frame_count, time_info, status):
        needed = frame_count * self.channels * 4
        while len(self.pending) < needed:
            try:
                self.pending += self.queue.get_nowait()
            except queue.Empty:
                break
        data, self.pending = self.pending[:needed], self.pending[needed:]
        data += bytes(needed - len(data))
        gain = max(0.0, min(1.0, float(self.volume())))
        samples = np.frombuffer(data, np.float32)
        pcm = (np.clip(samples * gain, -1, 1) * 32767).astype(np.int16).tobytes()
        return pcm, pa.paComplete if self.stop.is_set() else pa.paContinue

    def close(self):
        try:
            self.stream.stop_stream()
        finally:
            self.stream.close()


class MicrophoneTranslationFeed:
    """Segment the original microphone in parallel with the streaming voice effect."""
    def __init__(self, destination, settings, report):
        self.destination, self.report = destination, report
        self.vad = webrtcvad.Vad(settings.vad_aggressiveness)
        self.segmenter = Segmenter(settings.silence_ms, settings.max_speech_seconds)
        self.pending = b""

    def push(self, samples, rate, enabled):
        mono = resample(samples, rate, 16000)
        self.pending += (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()
        while len(self.pending) >= 640:
            frame, self.pending = self.pending[:640], self.pending[640:]
            phrase = self.segmenter.push(frame, self.vad.is_speech(frame, 16000), enabled)
            if phrase:
                try:
                    self.destination.put_nowait(phrase)
                except queue.Full:
                    self.report("我方翻译积压，已跳过一句；实时变声仍继续发送")


class RealtimeVoice(threading.Thread):
    def __init__(self, p, mic, output, listen, settings, stop, talking, report,
                 translation_destination=None, capture_enabled=lambda: True):
        super().__init__(name="realtime-voice-changer", daemon=True)
        self.p, self.mic, self.output, self.listen = p, mic, output, listen
        self.settings, self.stop, self.talking, self.report = settings, stop, talking, report
        self.raw = queue.Queue(maxsize=4)
        self.dropped = threading.Event()
        self.translation_destination = translation_destination
        self.capture_enabled = capture_enabled

    def callback(self, data, frame_count, time_info, status):
        enabled = self.capture_enabled() and (not self.settings.push_to_talk or self.talking.is_set())
        try:
            self.raw.put_nowait((data, enabled))
        except queue.Full:
            self.dropped.set()
        return None, pa.paComplete if self.stop.is_set() else pa.paContinue

    def run(self):
        stream = None
        sinks = []
        try:
            if self.output is not None:
                sinks.append(RealtimeSink(self.p, self.output, self.stop,
                    lambda: 0 if self.settings.send_muted else self.settings.send_volume / 100))
            if self.listen is not None:
                sinks.append(RealtimeSink(self.p, self.listen, self.stop,
                    lambda: 0 if self.settings.playback_muted else self.settings.outgoing_volume / 100))
            if not sinks and self.translation_destination is None:
                raise ValueError("请启用虚拟麦克风输出或本地监听")
            rate = int(self.mic["defaultSampleRate"])
            channels = min(2, int(self.mic["maxInputChannels"]))
            processor = VoiceProcessor(48000)
            feed = (MicrophoneTranslationFeed(self.translation_destination, self.settings, self.report)
                    if self.translation_destination is not None else None)
            stream = self.p.open(format=pa.paInt16, channels=channels, rate=rate,
                                 input=True, input_device_index=int(self.mic["index"]),
                                 frames_per_buffer=round(rate * .02), stream_callback=self.callback)
            self.report("实时变声与双向翻译运行中 · " + ("按住 F8 发送原声变声，同时翻译" if self.settings.push_to_talk else "连续发送原声变声，同时翻译"))
            while not self.stop.is_set():
                try:
                    data, enabled = self.raw.get(timeout=.1)
                except queue.Empty:
                    if not stream.is_active():
                        raise RuntimeError("麦克风已断开")
                    continue
                if any(not sink.stream.is_active() for sink in sinks):
                    raise RuntimeError("输出设备已断开")
                if self.dropped.is_set():
                    self.dropped.clear()
                    while self.raw.qsize() > 1:
                        try:
                            self.raw.get_nowait()
                        except queue.Empty:
                            break
                    processor = VoiceProcessor(48000)
                    if feed is not None:
                        feed = MicrophoneTranslationFeed(self.translation_destination, self.settings, self.report)
                    self.report("实时音频处理拥堵，已跳过积压音频")
                    continue
                samples = np.frombuffer(data, np.int16).astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768
                if feed is not None:
                    feed.push(samples, rate, enabled)
                if not enabled:
                    samples.fill(0)
                samples = resample(samples, rate, 48000)
                changed = processor.process(samples, self.settings.voice_pitch, self.settings.voice_effect,
                                            self.settings.voice_enabled)
                for sink in sinks:
                    sink.submit(changed, 48000)
        except Exception as exc:
            self.report(f"实时变声失败：{exc}")
            self.stop.set()
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                finally:
                    stream.close()
            for sink in sinks:
                sink.close()
