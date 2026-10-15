from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    microphone: str = ""
    receive_device: str = ""
    receive_mode: str = "device"
    output_device: str = ""
    receive_only: bool = False
    send_to_virtual: bool = False
    listen_device: str = ""
    speak_incoming: bool = True
    monitor_outgoing: bool = True
    incoming_volume: int = 80
    outgoing_volume: int = 80
    playback_muted: bool = False
    speed_mode: str = "balanced"
    asr_threads: int = 4
    push_to_talk: bool = True
    screen: int = 0
    font_size: int = 28
    bottom_margin: int = 36
    subtitle_seconds: int = 10
    vad_aggressiveness: int = 2
    silence_ms: int = 400
    max_speech_seconds: float = 5.0

    def __post_init__(self):
        self.silence_ms = max(100, min(1500, int(self.silence_ms)))
        self.max_speech_seconds = max(1.0, min(10.0, float(self.max_speech_seconds)))
        self.incoming_volume = max(0, min(100, int(self.incoming_volume)))
        self.outgoing_volume = max(0, min(100, int(self.outgoing_volume)))
        self.asr_threads = max(1, min(16, int(self.asr_threads)))
        if self.speed_mode not in ("fast", "balanced"):
            self.speed_mode = "balanced"
        if self.receive_mode not in ("device", "process"):
            self.receive_mode = "device"

    @classmethod
    def load(cls, path=ROOT / "config.json"):
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in {f.name for f in fields(cls)}})

    def save(self, path=ROOT / "config.json"):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
