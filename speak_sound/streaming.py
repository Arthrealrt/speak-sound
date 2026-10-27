"""Bounded speculative work. Only completed speech can reach playback/history."""
from collections import deque, OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import queue
import threading
import time


class PreviewBusy(Exception):
    pass


class PriorityLock:
    """Pending final jobs always go before another preview; inference is not preempted."""
    def __init__(self):
        self.condition = threading.Condition()
        self.active = False
        self.waiting = 0

    @contextmanager
    def hold(self, preview=False):
        with self.condition:
            if preview:
                if self.active or self.waiting:
                    raise PreviewBusy()
            else:
                self.waiting += 1
                try:
                    while self.active:
                        self.condition.wait()
                finally:
                    self.waiting -= 1
            self.active = True
        try:
            yield
        finally:
            with self.condition:
                self.active = False
                self.condition.notify_all()


@dataclass(frozen=True)
class SpeechPacket:
    pcm: bytes
    final: bool = True
    turn: int = 0
    created: float = 0.
    speech_end: float = 0.


class SpeechQueue:
    """One replaceable preview, a bounded final lane, and stale-preview suppression."""
    def __init__(self, maxsize=1, latest=True, clock=time.monotonic, min_preview_ms=0, zero_tail_only=False):
        self.maxsize, self.latest, self.clock = maxsize, latest, clock
        self.min_preview_ms = min_preview_ms
        self.zero_tail_only = zero_tail_only
        self.condition = threading.Condition()
        self.finals = deque()
        self.partial = None
        self.turn = 0

    def packet(self, pcm, speech_end):
        return SpeechPacket(pcm, speech_end=speech_end)

    def preview(self, pcm, speech_end):
        with self.condition:
            self.partial = SpeechPacket(pcm, False, self.turn, self.clock(), speech_end)
            self.condition.notify()

    def put_nowait(self, value):
        with self.condition:
            if len(self.finals) >= self.maxsize:
                if not self.latest:
                    # An unqueued final still invalidates its old preview.
                    self.partial = None
                    self.turn += 1
                    raise queue.Full()
                self.finals.popleft()
            item = value if isinstance(value, SpeechPacket) else SpeechPacket(value)
            self.finals.append(replace(item, final=True, turn=self.turn, created=self.clock()))
            self.turn += 1
            self.partial = None
            self.condition.notify()

    def put(self, value):
        self.put_nowait(value)

    def invalidate_preview(self):
        with self.condition:
            self.partial = None
            self.turn += 1

    def get(self, timeout=.1):
        end = self.clock() + timeout
        with self.condition:
            while not self.finals and self.partial is None:
                left = end - self.clock()
                if left <= 0:
                    raise queue.Empty()
                self.condition.wait(left)
            if self.finals:
                return self.finals.popleft()
            item, self.partial = self.partial, None
            return item

    def current(self, item):
        with self.condition:
            return item.turn == self.turn and not self.finals


class ResultCache:
    """A final may reuse exactly the same PCM, never a matching text prefix."""
    def __init__(self, limit=4):
        self.limit = limit
        self.values = OrderedDict()

    def get(self, pcm):
        key = hashlib.sha256(pcm).digest()
        value = self.values.get(key)
        if value is not None:
            self.values.move_to_end(key)
        return value

    def put(self, pcm, value):
        key = hashlib.sha256(pcm).digest()
        self.values[key] = value
        self.values.move_to_end(key)
        while len(self.values) > self.limit:
            self.values.popitem(last=False)
