from dataclasses import asdict, dataclass, fields
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    microphone: str = ""
    receive_device: str = ""
    output_device: str = ""
    asr_device: str = "cpu"
    tts: str = "openjtalk"
    voicevox_speaker: int = 1
    push_to_talk: bool = True
    screen: int = 0
    font_size: int = 28
    bottom_margin: int = 36
    subtitle_seconds: int = 10
    vad_aggressiveness: int = 2
    silence_ms: int = 400
    max_speech_seconds: float = 5.0

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
