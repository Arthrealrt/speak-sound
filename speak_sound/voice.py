"""Local streaming voice effects, implemented with NumPy/SciPy (no model downloads)."""
import numpy as np
from scipy.signal import butter, sosfilt

PRESETS = {
    "natural": ("原声", 0.0, "clean"),
    "deep": ("低沉", -5.0, "clean"),
    "bright": ("明亮", 4.0, "clean"),
    "cartoon": ("卡通", 8.0, "clean"),
    "robot": ("机器人", 0.0, "robot"),
    "radio": ("电台", 0.0, "radio"),
}


class VoiceProcessor:
    """Two overlapping variable-delay read heads shift pitch without changing duration.

    Grain-based shifting has audible coloration; this is an effect, not identity
    cloning or formant-preserving AI conversion. State persists across callbacks.
    """
    def __init__(self, rate):
        self.rate = int(rate)
        self.window = max(16, round(self.rate * .08))
        self.minimum = max(2, round(self.rate * .005))
        self.history = np.zeros(self.window + self.minimum + 4, np.float32)
        self.phase = self.oscillator = 0.0
        self.sos = butter(3, [300, min(3400, self.rate * .45)], btype="bandpass", fs=self.rate, output="sos")
        self.filter_state = np.zeros((len(self.sos), 2))
        self.last = None

    def process(self, samples, pitch=0.0, effect="clean", enabled=True):
        samples = np.nan_to_num(np.asarray(samples, dtype=np.float32).reshape(-1), copy=True)
        if not len(samples):
            return samples
        if not enabled:
            self.last = None
            return np.clip(samples, -1, 1)
        pitch = max(-12.0, min(12.0, float(pitch)))
        key = (pitch, effect)
        if key != self.last:
            self.history.fill(0)
            self.phase = self.oscillator = 0.0
            self.filter_state.fill(0)
            self.last = key
        result = samples
        if abs(pitch) > .001:
            history_length = len(self.history)
            source = np.concatenate((self.history, samples))
            step = (1 - 2 ** (pitch / 12)) / self.window
            phase = (self.phase + step * np.arange(len(samples))) % 1
            second = (phase + .5) % 1
            positions = history_length + np.arange(len(samples))
            indices = np.arange(len(source))
            first_audio = np.interp(positions - self.minimum - phase * self.window, indices, source)
            second_audio = np.interp(positions - self.minimum - second * self.window, indices, source)
            weight = .5 - .5 * np.cos(2 * np.pi * phase)
            result = first_audio * weight + second_audio * (1 - weight)
            self.phase = (self.phase + step * len(samples)) % 1
            self.history = source[-history_length:].copy()
        if effect == "robot":
            positions = self.oscillator + np.arange(len(samples)) * (2 * np.pi * 55 / self.rate)
            result = result * (.3 + .7 * np.cos(positions))
            self.oscillator = (positions[-1] + 2 * np.pi * 55 / self.rate) % (2 * np.pi)
        elif effect == "radio":
            result, self.filter_state = sosfilt(self.sos, result, zi=self.filter_state)
            result = np.tanh(result * 2) / 1.2
        return np.clip(result, -.99, .99).astype(np.float32)


def process_utterance(samples, rate, settings):
    if not settings.voice_enabled:
        return samples
    processor = VoiceProcessor(rate)
    # Flush the effect tail while retaining every original spoken sample.
    padding = processor.window + processor.minimum if abs(settings.voice_pitch) > .001 else 0
    source = np.pad(np.asarray(samples, np.float32), (0, padding))
    return processor.process(source, settings.voice_pitch, settings.voice_effect)
