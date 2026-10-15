"""20 ms VAD segmentation, independent from audio and AI dependencies."""
from collections import deque


class Segmenter:
    def __init__(self, silence_ms=400, max_seconds=5.0, min_ms=160):
        self.silence_frames = max(1, silence_ms // 20)
        self.max_frames = max(1, int(max_seconds * 50))
        self.min_frames = max(1, min_ms // 20)
        self.preroll = deque(maxlen=10)
        self.frames = []
        self.voiced = 0
        self.quiet = 0

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
        if self.quiet >= self.silence_frames or len(self.frames) >= self.max_frames:
            return self.flush()
        return None

    def flush(self):
        result = b"".join(self.frames) if self.voiced >= self.min_frames else None
        self.frames = []
        self.voiced = self.quiet = 0
        return result
