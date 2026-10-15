"""Offline synthetic smoke test. Does not capture or send microphone audio."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pyaudiowpatch as pa

from speak_sound.audio import devices, to_mono16
from speak_sound.config import ROOT, Settings
from speak_sound.models import LocalModels


def main():
    with pa.PyAudio() as p:
        available = devices(p)
    results = {"devices": {kind: [name for name, _ in values] for kind, values in available.items()}}
    model = LocalModels(Settings(), print)
    results["zh_to_ja"] = model.translate("队友在右边，一起走吧。", "zh", "ja")
    results["ja_to_zh"] = model.translate("敵が右にいます。一緒に行こう。", "ja", "zh")
    samples, rate = model.synthesize("敵が右にいます。一緒に行こう。")
    assert samples.size > rate // 2 and np.max(np.abs(samples)) > .001, "TTS returned silent audio"
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
    results["synthesized_seconds"] = len(samples) / rate
    results["ja_recognized"] = model.recognize(to_mono16(pcm, rate, 1), "ja")
    assert all(results[key] for key in ("zh_to_ja", "ja_to_zh", "ja_recognized")), results
    assert "右" in results["zh_to_ja"], "Chinese→Japanese dropped the direction in the test sentence"
    assert "右" in results["ja_to_zh"] and any(word in results["ja_to_zh"] for word in ("敌", "敵")), \
        "Japanese→Chinese dropped enemy/direction information in the test sentence"
    (ROOT / "verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
