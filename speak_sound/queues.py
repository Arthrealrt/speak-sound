"""Keep live incoming speech recent instead of translating a stale backlog."""
import queue


class LatestQueue(queue.Queue):
    def put_nowait(self, item):
        try:
            super().put_nowait(item)
        except queue.Full:
            try:
                self.get_nowait()
            except queue.Empty:
                pass
            super().put_nowait(item)
