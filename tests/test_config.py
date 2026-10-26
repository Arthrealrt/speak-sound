import tempfile
import unittest
from pathlib import Path

from speak_sound.config import Settings


class ConfigTests(unittest.TestCase):
    def test_language_filter_and_receive_timing_are_validated(self):
        settings = Settings(target_language='xx', incoming_language='en', speech_filter='bad',
                            incoming_silence_ms=-1, incoming_max_seconds=99)
        self.assertEqual(settings.target_language, 'ja')
        self.assertEqual(settings.incoming_language, 'en')
        self.assertEqual(settings.speech_filter, 'standard')
        self.assertEqual((settings.incoming_silence_ms, settings.incoming_max_seconds), (100, 6))
    def test_old_voice_changer_migrates_to_combined_route(self):
        self.assertEqual(Settings(operating_mode='voice_changer').operating_mode, 'live_translation')
        self.assertEqual(Settings().operating_mode, 'translation')
        self.assertTrue(Settings().voice_enabled)
        self.assertFalse(Settings().monitor_live_voice)

    def test_voice_controls_and_mode_are_bounded(self):
        settings = Settings(voice_pitch=100,voice_effect='unknown',send_volume=-1,operating_mode='unknown')
        self.assertEqual(settings.voice_pitch,12)
        self.assertEqual(settings.voice_effect,'clean')
        self.assertEqual(settings.send_volume,0)
        self.assertEqual(settings.operating_mode,'translation')

    def test_timing_volume_and_modes_are_bounded(self):
        settings = Settings(silence_ms=-1, max_speech_seconds=90, incoming_volume=150,
                            outgoing_volume=-2, speed_mode='bad', receive_mode='bad')
        self.assertEqual((settings.silence_ms, settings.max_speech_seconds), (100, 10))
        self.assertEqual((settings.incoming_volume, settings.outgoing_volume), (100, 0))
        self.assertEqual((settings.speed_mode, settings.receive_mode), ('balanced', 'device'))
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
