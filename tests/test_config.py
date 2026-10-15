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
