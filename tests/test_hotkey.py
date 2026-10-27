import json
import tempfile
import unittest
from pathlib import Path
from speak_sound.config import Settings
from speak_sound.hotkey import normalize_chord, chord_text, PushToTalkGate


class HotkeyTests(unittest.TestCase):
    def test_legacy_config_and_invalid_bindings_fall_back_to_f8(self):
        for value in (None, [], [True], [0], [0x5B], [65, 66], 'F9', [0x77] * 5):
            self.assertEqual(Settings(ptt_keys=value).ptt_keys, (0x77,))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps({'push_to_talk': True}), encoding='utf-8')
            self.assertEqual(Settings.load(path).ptt_keys, (0x77,))

    def test_canonical_chord_survives_json_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            config = Settings(ptt_keys=[0x56, 0x10, 0x11, 0x11])
            config.save(path)
            loaded = Settings.load(path)
            self.assertEqual(loaded.ptt_keys, (0x11, 0x10, 0x56))
            self.assertEqual(chord_text(loaded.ptt_keys), 'Ctrl + Shift + V')
            self.assertEqual(chord_text([0x12, 5]), 'Alt + 鼠标侧键 1')

    def test_all_keys_required_release_flushes_and_rebind_requires_release(self):
        gate = PushToTalkGate()
        held = {0x11, 0x56}
        read = lambda key: key in held
        chord = (0x11, 0x56)
        self.assertFalse(gate.pressed(chord, read))
        held.clear()
        self.assertFalse(gate.pressed(chord, read))
        held.add(0x11)
        self.assertFalse(gate.pressed(chord, read))
        held.add(0x56)
        self.assertTrue(gate.pressed(chord, read))
        held.remove(0x56)
        self.assertFalse(gate.pressed(chord, read))
        held.add(0x56)
        self.assertTrue(gate.pressed(chord, read))
        gate.reset()
        self.assertFalse(gate.pressed(chord, read))

    def test_mouse_and_single_modifier_bindings(self):
        self.assertEqual(normalize_chord([5]), (5,))
        self.assertEqual(normalize_chord([0x11]), (0x11,))
