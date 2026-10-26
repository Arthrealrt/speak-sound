import math
import queue
import threading

import numpy as np
import pyaudiowpatch as pa
from scipy.signal import resample_poly
import webrtcvad

from .segmenter import Segmenter


def device_key(p, device):
    api = p.get_host_api_info_by_index(device["hostApi"])["name"]
    return f'{api} | {device["name"]}'


def devices(p):
    result = {"microphone": [], "receive": [], "output": []}
    for device in p.get_device_info_generator():
        key = device_key(p, device)
        if device.get("isLoopbackDevice"):
            result["receive"].append((key, int(device["index"])))
        elif device["maxInputChannels"] > 0:
            result["microphone"].append((key, int(device["index"])))
        if device["maxOutputChannels"] > 0 and not device.get("isLoopbackDevice"):
            result["output"].append((key, int(device["index"])))
    return result


def resolve(p, kind, key):
    for name, index in devices(p)[kind]:
        if name == key:
            return p.get_device_info_by_index(index)
    raise ValueError(f"音频设备不存在，请刷新后重新选择：{key}")


def to_mono16(data, rate, channels):
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    samples = samples.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        gcd = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // gcd, rate // gcd)
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


class Capture(threading.Thread):
    def __init__(self, p, info, destination, stop, enabled, settings, report):
        super().__init__(name=f'capture-{info["index"]}', daemon=True)
        self.p, self.info, self.destination = p, info, destination
        self.stop, self.enabled, self.settings, self.report = stop, enabled, settings, report
        self.raw = queue.Queue(maxsize=25)
        self.dropped = threading.Event()

    def callback(self, data, frame_count, time_info, status):
        try:
            self.raw.put_nowait((data, self.enabled()))
        except queue.Full:
            self.dropped.set()
        return (None, pa.paComplete if self.stop.is_set() else pa.paContinue)

    def run(self):
        stream = None
        try:
            rate = int(self.info["defaultSampleRate"])
            channels = min(2, int(self.info["maxInputChannels"]))
            vad = webrtcvad.Vad(self.settings.vad_aggressiveness)
            segmenter = Segmenter(self.settings.silence_ms, self.settings.max_speech_seconds)
            stream = self.p.open(format=pa.paInt16, channels=channels, rate=rate,
                                 input=True, input_device_index=int(self.info["index"]),
                                 frames_per_buffer=round(rate * .02), stream_callback=self.callback)
            pending = b""
            while not self.stop.is_set():
                try:
                    data, enabled = self.raw.get(timeout=.1)
                except queue.Empty:
                    if not stream.is_active():
                        raise RuntimeError("音频设备已断开或停止，请重新选择设备")
                    continue
                if self.dropped.is_set():
                    self.dropped.clear()
                    segmenter = Segmenter(self.settings.silence_ms, self.settings.max_speech_seconds)
                    pending = b""
                    self.report("音频采集拥堵，已丢弃不完整语句")
                    while self.raw.qsize() > 1:
                        try:
                            self.raw.get_nowait()
                        except queue.Empty:
                            break
                    continue
                pending += to_mono16(data, rate, channels)
                while len(pending) >= 640:
                    frame, pending = pending[:640], pending[640:]
                    utterance = segmenter.push(frame, vad.is_speech(frame, 16000), enabled)
                    if utterance:
                        try:
                            self.destination.put_nowait(utterance)
                        except queue.Full:
                            self.report("翻译速度跟不上语音，已跳过一句；可换用更小的识别模型")
        except Exception as exc:
            self.report(f"音频采集失败：{exc}")
            self.stop.set()
        finally:
            if stream is not None:
                stream.stop_stream()
                stream.close()


def play(p, device, samples, sample_rate, stop, volume=lambda: 1.0):
    rate = int(device["defaultSampleRate"])
    channels = min(2, int(device["maxOutputChannels"]))
    if rate != sample_rate:
        gcd = math.gcd(rate, sample_rate)
        samples = resample_poly(samples, rate // gcd, sample_rate // gcd)
    samples = np.asarray(samples, dtype=np.float32)
    stream = p.open(format=pa.paInt16, channels=channels, rate=rate,
                    output=True, output_device_index=int(device["index"]))
    try:
        for offset in range(0, len(samples), rate // 50):
            if stop.is_set():
                break
            gain = max(0.0, min(1.0, float(volume())))
            pcm = (np.clip(samples[offset:offset + rate // 50] * gain, -1, 1) * 32767).astype(np.int16)
            stream.write(np.repeat(pcm[:, None], channels, axis=1).tobytes())
    finally:
        stream.stop_stream()
        stream.close()
