import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from speak_sound.config import Settings
from speak_sound.ui import Window, create_application


class CombinedUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_application([])

    def test_both_routes_keep_incoming_process_selection_and_japanese_monitor(self):
        with patch.object(Window, 'refresh_devices'), patch.object(Window, 'refresh_processes'), \
             patch.object(Settings, 'load', return_value=Settings()):
            window = Window()
        try:
            for route in ('translation', 'live_translation'):
                window.operating_mode.setCurrentIndex(window.operating_mode.findData(route))
                self.assertTrue(window.receive_mode.isEnabled())
                self.assertTrue(window.receive_only.isEnabled())
                self.assertTrue(window.incoming_voice.isEnabled())
                self.assertEqual(window.outgoing_monitor.text(), '试听我说中文后生成的日语')
                window.receive_mode.setCurrentIndex(window.receive_mode.findData('process'))
                self.assertTrue(window.process.isEnabled())
                self.assertFalse(window.receive.isEnabled())
                window.receive_only.setChecked(True)
                self.assertFalse(window.mic.isEnabled())
                self.assertFalse(window.send_virtual.isEnabled())
                window.receive_only.setChecked(False)
                self.assertTrue(window.mic.isEnabled())
        finally:
            window.volume_save.stop()
            window.close()
