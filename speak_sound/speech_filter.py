"""Local speech gating and conservative rejection of pathological ASR output.

This detects speech, not the identity of its speaker. NPC dialogue can pass.
"""
import re
import numpy as np


class SpeechFilter:
    def __init__(self, mode="standard"):
        self.mode = mode

    def apply(self, samples):
        if self.mode == "off":
            return samples
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        chunks = get_speech_timestamps(samples, VadOptions(
            threshold=.7 if self.mode == "strict" else .55,
            min_speech_duration_ms=220 if self.mode == "strict" else 160,
            min_silence_duration_ms=120, speech_pad_ms=100))
        if not chunks:
            return np.empty(0, np.float32)
        return np.concatenate([samples[item["start"]:item["end"]] for item in chunks])


def plausible_transcript(segments, seconds, strict=False):
    accepted = [item.text.strip() for item in segments
                if item.no_speech_prob < (.5 if strict else .6)
                and item.avg_logprob >= (-.8 if strict else -1.)
                and item.compression_ratio <= 2.4]
    text = " ".join(accepted).strip()
    if not text or len(text) > max(48, seconds * 28):
        return ""
    # Long repeated phrases are a common silence/music hallucination.
    compact = re.sub(r"[\W_]+", "", text).lower()
    if len(compact) >= 48 and re.search(r"(.{2,24})\1{3,}", compact):
        return ""
    return text
