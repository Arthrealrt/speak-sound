"""Manage only this application's local USB/IP cable; never alter boot policy."""
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time

from .config import ROOT
from .default_audio import DefaultAudioGuard

ATTACHED_PORT = re.compile(r"successfully\s+attached\s+to\s+port\s+(\d+)", re.I)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_usbip():
    candidates = [Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "USBip/usbip.exe",
                  Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "usbip-win2/usbip.exe"]
    for path in candidates:
        if path.is_file():
            return str(path)
    return shutil.which("usbip.exe")


def own_ports(output):
    result, current = [], None
    for line in output.splitlines():
        match = re.match(r"\s*Port\s+(\d+):", line, re.I)
        if match:
            current = int(match[1])
        elif current is not None and re.search(r"usbip://127\.0\.0\.1:32401/1-1(?:\s|$)", line):
            result.append(current)
            current = None
    return result


class VirtualMicrophone:
    def __init__(self):
        self.process = None
        self.port = None
        self.executable = None
        self.log = None

    @property
    def connected(self):
        return self.process is not None and self.process.poll() is None and self.port is not None

    def command(self, *args):
        result = subprocess.run([self.executable, "-t", "32401", *args], capture_output=True,
                                creationflags=CREATE_NO_WINDOW, timeout=15)
        output = (result.stdout + result.stderr).decode("utf-8", errors="replace").strip()
        if result.returncode:
            raise RuntimeError(output or f"usbip 返回 {result.returncode}")
        return output

    def start(self):
        if self.connected:
            return
        helper = ROOT / "bin/speak-sound-mic.exe"
        if not helper.is_file():
            raise FileNotFoundError("缺少虚拟声卡后端，请运行 drivers/build_virtual_mic.ps1")
        self.executable = find_usbip()
        if not self.executable:
            raise FileNotFoundError("尚未安装签名 USB/IP 驱动，请先运行 drivers/setup_virtual_mic.ps1")
        try:
            (ROOT / "logs").mkdir(exist_ok=True)
            self.log = (ROOT / "logs/virtual-mic.log").open("ab")
            self.process = subprocess.Popen([str(helper)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self.log, creationflags=CREATE_NO_WINDOW)
            ready = queue.Queue(maxsize=1)
            threading.Thread(target=lambda: ready.put(self.process.stdout.readline()), daemon=True).start()
            try:
                line = ready.get(timeout=5)
            except queue.Empty:
                raise RuntimeError("虚拟声卡后端启动超时") from None
            if b'"ready":true' not in line:
                raise RuntimeError("虚拟声卡启动失败，32401 端口可能被占用；详见 logs/virtual-mic.log")
            with DefaultAudioGuard() as defaults:
                output = self.command("attach", "-r", "127.0.0.1", "-b", "1-1")
                match = ATTACHED_PORT.search(output)
                if match:
                    self.port = int(match[1])
                else:
                    ports = own_ports(self.command("port"))
                    if len(ports) != 1:
                        raise RuntimeError("USB/IP 未返回可确认的设备端口，已停止虚拟声卡")
                    self.port = ports[0]
                for _ in range(10):
                    time.sleep(.15)
                    defaults.restore()
        except Exception:
            self.stop()
            raise

    def stop(self):
        try:
            if self.port is not None and self.executable:
                # Check ownership immediately before detach. Never detach every USB device.
                if self.port in own_ports(self.command("port")):
                    self.command("detach", "-p", str(self.port))
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass
        finally:
            self.port = None
            if self.process is not None:
                if self.process.stdin:
                    self.process.stdin.close()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                if self.process.stdout:
                    self.process.stdout.close()
                self.process = None
            if self.log is not None:
                self.log.close()
                self.log = None
