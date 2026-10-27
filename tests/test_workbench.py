"""Exercise native navigation, reparented controls and run-state safety without audio."""
import os
import threading
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFontInfo
from speak_sound.ui import Window, create_application
from speak_sound.config import Settings
from speak_sound.service import Events


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or create_application([])

    def setUp(self):
        self.saving = patch.object(Settings, 'save')
        self.saving.start()
        with patch.object(Window, 'refresh_devices'), patch.object(Window, 'refresh_processes'), \
             patch.object(Settings, 'load', return_value=Settings()):
            self.window = Window()
        self.window.show()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def tearDown(self):
        self.window.volume_save.stop()
        self.window.close()
        self.saving.stop()

    def test_all_navigation_survives_deleting_the_old_shell(self):
        for index, button in enumerate(self.window.nav_buttons):
            button.click()
            self.app.processEvents()
            self.assertEqual(self.window.tabs.currentIndex(), index)
            self.assertEqual(self.window.page_title.text(), button.text())
            self.assertTrue(self.window.start_button.isVisible())
            self.assertTrue(self.window.incoming_volume.isVisible())

    def test_narrow_window_scrolls_without_compressing_device_controls(self):
        w = self.window
        for width, height, compact in ((880, 680, True), (1180, 860, False), (1440, 900, False)):
            w.resize(width, height)
            self.app.processEvents()
            self.app.processEvents()
            self.assertEqual(w.home.compact, compact)
            self.assertGreaterEqual(w.mic.height(), 32)
            self.assertGreaterEqual(w.receive.height(), 32)
            self.assertTrue(w.incoming_volume.isVisible())
            self.assertLess(w.live_volume_panel.geometry().bottom(), w.centralWidget().height())

    def test_run_locks_device_settings_but_leaves_live_controls_and_navigation_available(self):
        w = self.window
        for combo, name in ((w.mic, 'physical microphone'), (w.receive, 'headphone loopback'),
                            (w.output, 'RadioVoice Output'), (w.listen, 'headphones')):
            combo.addItem(name)
            combo.setCurrentIndex(0)
        w.send_virtual.setChecked(True)
        w.operating_mode.setCurrentIndex(w.operating_mode.findData('translation'))
        class FakeService:
            def __init__(self, *args):
                self.events = Events()
                self.stop, self.talking = threading.Event(), threading.Event()
            def start(self):
                pass
        with patch('speak_sound.ui.Service', FakeService), \
             patch('speak_sound.ui.QMessageBox.information', side_effect=lambda *args: self.fail(str(args[1:]))):
            w.start()
        service = w.service
        try:
            self.assertIsNotNone(service)
            self.assertFalse(w.mic.isEnabled())
            self.assertFalse(w.speech_filter.isEnabled())
            self.assertFalse(w.font_size.isEnabled())
            self.assertFalse(w.speed.isEnabled())
            self.assertFalse(w.operating_mode.isEnabled())
            self.assertTrue(w.send_volume.isEnabled())
            self.assertTrue(w.mute.isEnabled())
            self.assertTrue(w.voice_pitch.isEnabled())
            w.nav_buttons[3].click()
            self.assertEqual(w.tabs.currentIndex(), 3)
            service.events.active.emit(True)
            self.assertEqual(w.run_badge.text(), '翻译中')
        finally:
            service.events.finished.emit()
        self.assertTrue(w.mic.isEnabled())
        self.assertTrue(w.speech_filter.isEnabled())
        self.assertTrue(w.font_size.isEnabled())

    def test_latest_translation_is_real_and_bounded(self):
        w = self.window
        value = '敌人在右边，跟紧我。' * 100
        w.record('in', '<original>', value, 1.25)
        self.assertEqual(w.translation_preview.target, value)
        self.assertLessEqual(len(w.translation_preview.translated.text().splitlines()), 2)
        self.assertEqual(w.translation_preview.elapsed.text(), '识别与翻译 1.2 秒')
        self.assertIn('<original>', w.history.toPlainText())

    def test_process_source_replaces_device_field(self):
        w = self.window
        w.receive_mode.setCurrentIndex(w.receive_mode.findData('process'))
        self.assertTrue(w.process_field.isVisible())
        self.assertFalse(w.receive_device_field.isVisible())
        w.receive_mode.setCurrentIndex(w.receive_mode.findData('device'))
        self.assertTrue(w.receive_device_field.isVisible())
        self.assertFalse(w.process_field.isVisible())

    def test_bundled_font_is_loaded_without_network(self):
        self.assertIn('Inter', QFontInfo(self.app.font()).family())
