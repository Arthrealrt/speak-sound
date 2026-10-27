"""WASAPI process-tree capture. Never fall back to recording the whole device."""
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np
import psutil
import webrtcvad

from .audio import to_mono16
from .segmenter import make_segmenter


@dataclass(frozen=True)
class ProcessTarget:
    pid: int
    created: float
    name: str

    def alive(self):
        try:
            process = psutil.Process(self.pid)
            return process.is_running() and process.create_time() == self.created
        except (psutil.Error, OSError):
            return False


def running_processes():
    targets = []
    own_tree = {os.getpid(), *(p.pid for p in psutil.Process().parents())}
    for process in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            info = process.info
            if info["pid"] > 4 and info["pid"] not in own_tree and info["name"] and info["create_time"]:
                targets.append(ProcessTarget(info["pid"], info["create_time"], info["name"]))
        except (psutil.Error, OSError):
            continue
    return sorted(targets, key=lambda item: (item.name.lower(), item.pid))


def open_process_loopback(target, factory=None):
    if not target or not target.alive():
        raise ValueError("目标进程已退出或 PID 已变化，请刷新并重新选择")
    if target.pid in {os.getpid(), *(p.pid for p in psutil.Process().parents())}:
        raise ValueError("不能选择本软件或其祖先进程，以防译音循环")
    if factory is None:
        if sys.platform != "win32" or sys.getwindowsversion().build < 22000:
            raise RuntimeError("按进程接收需要 Windows 11")
        # The pinned MIT extension exposes a native status check; its high-level
        # wrapper hides fallback to system-wide capture, so use the native API.
        from proctap._native import ProcessLoopback
        factory = ProcessLoopback
    native = factory(target.pid)
    if not native.is_process_specific():
        reason = native.get_last_error() or "WASAPI 进程接口不可用"
        native.stop()
        raise RuntimeError(f"进程隔离采集失败，已拒绝整机回退：{reason}")
    return native


class ProcessCapture(threading.Thread):
    def __init__(self, target, destination, stop, settings, report):
        super().__init__(name=f"capture-process-{target.pid}", daemon=True)
        self.target, self.destination, self.stop = target, destination, stop
        self.settings, self.report = settings, report

    def run(self):
        native = None
        try:
            native = open_process_loopback(self.target)
            fmt = native.get_format()
            rate, channels, bits = (int(fmt[key]) for key in ("sample_rate", "channels", "bits_per_sample"))
            if bits not in (16, 32) or channels < 1:
                raise ValueError(f"不支持的进程音频格式：{fmt}")
            native.start()
            self.report(f"已隔离接收 {self.target.name} · PID {self.target.pid} 及子进程")
            vad = webrtcvad.Vad(self.settings.vad_aggressiveness)
            segmenter = make_segmenter(self.settings, self.destination)
            pending = b""
            checked = last_data = time.monotonic()
            while not self.stop.is_set():
                now = time.monotonic()
                if now - checked >= .25:
                    if not self.target.alive():
                        raise RuntimeError("目标进程已退出；请刷新并重新选择，不会自动采集其他进程")
                    checked = now
                data = native.read()
                if data:
                    if bits == 32:
                        data = (np.clip(np.frombuffer(data, np.float32), -1, 1) * 32767).astype(np.int16).tobytes()
                    pending += to_mono16(data, rate, channels)
                    last_data = now
                elif now - last_data >= .02:
                    # WASAPI may stop producing packets when the target is idle.
                    # Advance VAD silence so the last phrase is still submitted.
                    pending += bytes(640)
                    last_data = now
                else:
                    self.stop.wait(.005)
                    continue
                while len(pending) >= 640:
                    frame, pending = pending[:640], pending[640:]
                    utterance = segmenter.push(frame, vad.is_speech(frame, 16000))
                    if utterance:
                        try:
                            self.destination.put_nowait(utterance)
                        except queue.Full:
                            self.report("翻译积压，已跳过一句；可选择快速模式或延长分段")
        except Exception as exc:
            self.report(f"进程音频采集失败：{exc}")
            self.stop.set()
        finally:
            if native is not None:
                native.stop()
