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
    operating_mode: str = "translation"
    voice_enabled: bool = True
    monitor_live_voice: bool = False
    voice_pitch: float = 0.0
    voice_effect: str = "clean"
    send_volume: int = 100
    send_muted: bool = False

    def __post_init__(self):
        self.silence_ms = max(100, min(1500, int(self.silence_ms)))
        self.max_speech_seconds = max(1.0, min(10.0, float(self.max_speech_seconds)))
        self.incoming_volume = max(0, min(100, int(self.incoming_volume)))
        self.outgoing_volume = max(0, min(100, int(self.outgoing_volume)))
        self.asr_threads = max(1, min(16, int(self.asr_threads)))
        self.voice_pitch = max(-12.0, min(12.0, float(self.voice_pitch)))
        self.send_volume = max(0, min(100, int(self.send_volume)))
        if self.voice_effect not in ("clean", "robot", "radio"):
            self.voice_effect = "clean"
        if self.operating_mode == "voice_changer":
            self.operating_mode = "live_translation"
        if self.operating_mode not in ("translation", "live_translation"):
            self.operating_mode = "translation"
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
