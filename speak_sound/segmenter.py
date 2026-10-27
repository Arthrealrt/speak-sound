"""20 ms VAD segmentation, independent from audio and AI dependencies."""
from collections import deque
import time


class Segmenter:
    def __init__(self, silence_ms=400, max_seconds=5.0, min_ms=160,
                 preview=None, wrap=None, preview_ms=900, clock=time.monotonic, zero_tail_only=False):
        self.silence_frames = max(1, silence_ms // 20)
        self.max_frames = max(1, int(max_seconds * 50))
        self.min_frames = max(1, min_ms // 20)
        self.preroll = deque(maxlen=10)
        self.frames = []
        self.voiced = 0
        self.quiet = 0
        self.preview, self.wrap, self.clock = preview, wrap, clock
        self.preview_frames = max(20, preview_ms // 20)
        self.last_preview = self.last_voice = 0
        self.speech_end = 0.
        self.pause_previewed = False
        self.zero_tail_only = zero_tail_only

    def push(self, frame: bytes, speech: bool, enabled=True):
        if not enabled:
            result = self.flush()
            self.preroll.clear()
            return result
        if not self.frames:
            if not speech:
                self.preroll.append(frame)
                return None
            self.frames = list(self.preroll)
            self.preroll.clear()
        self.frames.append(frame)
        self.voiced += int(speech)
        self.quiet = 0 if speech else self.quiet + 1
        if speech:
            self.last_voice = len(self.frames)
            self.speech_end = self.clock()
            self.pause_previewed = False
        if self.quiet >= self.silence_frames or len(self.frames) >= self.max_frames:
            return self.flush()
        if self.preview and self.voiced >= self.min_frames:
            periodic = len(self.frames) - self.last_preview >= self.preview_frames
            pause = self.quiet >= 3 and not self.pause_previewed
            safe = not self.zero_tail_only or (self.quiet >= 3 and
                all(item == bytes(len(item)) for item in self.frames[-3:]))
            if (periodic or pause) and safe:
                self.preview(self.snapshot(), self.speech_end)
                self.last_preview = len(self.frames)
                self.pause_previewed = self.quiet > 0
        return None

    def snapshot(self):
        # WebRTC can mark a quiet word ending as non-speech. Preserve every
        # nonzero frame, including those VAD called quiet; only digital zero
        # tails are interchangeable. This avoids clipping Japanese word endings.
        end = len(self.frames)
        while end and self.frames[end-1] == bytes(len(self.frames[end-1])):
            end -= 1
        return b"".join(self.frames[:end]) + bytes(5120)

    def flush(self):
        result = (self.snapshot() if self.preview else b"".join(self.frames)) if self.voiced >= self.min_frames else None
        if result and self.wrap:
            result = self.wrap(result, self.speech_end)
        self.frames = []
        self.voiced = self.quiet = 0
        self.last_preview = self.last_voice = 0
        self.pause_previewed = False
        return result


def make_segmenter(settings, destination):
    return Segmenter(settings.silence_ms, settings.max_speech_seconds,
        preview=getattr(destination, 'preview', None) if settings.streaming_enabled else None,
        wrap=getattr(destination, 'packet', None),
        preview_ms=max(settings.preview_interval_ms, getattr(destination, 'min_preview_ms', 0)),
        zero_tail_only=getattr(destination, 'zero_tail_only', False))
