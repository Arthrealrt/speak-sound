import os
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from speak_sound.ui import Window, Subtitle, create_application
from speak_sound.config import Settings


class StreamingUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_application([])

    def setUp(self):
        self.saving = patch.object(Settings, 'save')
        self.saving.start()
        with patch.object(Settings, 'load', return_value=Settings()), patch.object(Window, 'refresh_devices'), \
             patch.object(Window, 'refresh_processes'):
            self.w = Window()
        self.w.show()
        self.app.processEvents()

    def tearDown(self):
        self.w.service = None
        self.w.volume_save.stop()
        self.w.close()
        self.saving.stop()

    def test_bilingual_switch_mirrors_and_saves_during_run(self):
        w = self.w
        w.service = object()
        w.bilingual.setChecked(True)
        w.record('in', 'リロード中', '正在换弹。', .1)
        self.app.processEvents()
        self.assertTrue(w.settings.subtitle_original)
        self.assertTrue(w.subtitle_original.isChecked())
        self.assertTrue(w.translation_preview.original_column.isVisible())
        self.assertIn('リロード', w.translation_preview.original.text())
        self.assertIn('换弹', w.translation_preview.translated.text())
        w.subtitle_original.setChecked(False)
        self.assertFalse(w.bilingual.isChecked())
        self.assertFalse(w.translation_preview.original_column.isVisible())

    def test_preview_marked_and_never_appended_to_history_or_shown_after_stop(self):
        w = self.w
        w.service = object()
        w.show_preview_translation('in', 'Enemy', '敌人')
        self.assertEqual(w.translation_preview.elapsed.text(), '预览，待确认')
        self.assertEqual(w.history.toPlainText(), '')
        w.stop_requested = True
        w.overlay.hide()
        w.show_preview_translation('in', 'Enemy left', '左侧敌人')
        w.show_subtitle('final', '最终')
        self.assertFalse(w.overlay.isVisible())
        self.assertEqual(w.translation_preview.source, 'Enemy')

    def test_bilingual_overlay_original_first_and_still_only_two_lines(self):
        overlay = Subtitle(Settings(subtitle_original=True))
        try:
            overlay.display('Enemy on the right.', '敌人在右边。' * 100)
            lines = overlay.label.text().splitlines()
            self.assertLessEqual(len(lines), 2)
            self.assertEqual(lines[0], 'Enemy on the right.')
            self.assertIn('敌人', lines[1])
        finally:
            overlay.close()

    def test_callout_preset_keeps_balanced_search_and_saves_controls(self):
        self.w.set_callout_timing()
        self.w.save()
        s = self.w.settings
        self.assertTrue(s.streaming_enabled)
        self.assertTrue(s.game_glossary)
        self.assertEqual(s.speed_mode, 'balanced')
        self.assertEqual(s.preview_interval_ms, 700)
        self.assertEqual(s.incoming_silence_ms, 160)
        self.assertFalse(s.headphones_mode)  # Never assume the user wears headphones.
