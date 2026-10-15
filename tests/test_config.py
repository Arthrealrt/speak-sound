import tempfile
import unittest
from pathlib import Path

from speak_sound.config import Settings


class ConfigTests(unittest.TestCase):
    def test_chinese_names_roundtrip_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            settings = Settings(microphone="麦克风（USB）", screen=1)
            settings.save(path)
            self.assertEqual(Settings.load(path), settings)
            path.write_text('{"future": true, "font_size": 40}', encoding="utf-8")
            self.assertEqual(Settings.load(path).font_size, 40)

    def test_missing_file_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(Settings.load(Path(directory) / "missing.json"), Settings())

    def test_legacy_closed_backend_options_are_not_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text('{"tts":"voicevox","asr_device":"cuda","voicevox_speaker":1}', encoding="utf-8")
            settings = Settings.load(path)
            self.assertFalse(settings.send_to_virtual)
            self.assertFalse(hasattr(settings, "tts"))
            self.assertFalse(hasattr(settings, "asr_device"))
