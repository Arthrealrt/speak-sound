import os
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog
from speak_sound.ui import Window, create_application
from speak_sound.config import Settings
from speak_sound.key_dialog import KeyDialog


class ShortcutUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or create_application([])

    def setUp(self):
        self.saving = patch.object(Settings, 'save')
        self.save_mock = self.saving.start()
        with patch.object(Window, 'refresh_devices'), patch.object(Window, 'refresh_processes'), \
                patch.object(Settings, 'load', return_value=Settings()):
            self.window = Window()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.service = None
        self.window.volume_save.stop()
        self.window.close()
        self.saving.stop()

    def test_dialog_captures_chord_and_enter_tab_without_accepting(self):
        dialog = KeyDialog((0x77,), self.window)
        dialog.show()
        QTest.keyClick(dialog, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(dialog.chord, (0x11, 0x10, 0x56))
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        self.assertEqual(dialog.chord, (0x0D,))
        self.assertTrue(dialog.isVisible())
        QTest.keyClick(dialog, Qt.Key.Key_Tab)
        self.assertEqual(dialog.chord, (0x09,))
        QTest.keyClick(dialog, Qt.Key.Key_Control)
        self.assertEqual(dialog.chord, (0x11,))
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)

    def test_dialog_captures_mouse_side_key(self):
        dialog = KeyDialog((0x77,), self.window)
        dialog.show()
        QTest.mouseClick(dialog, Qt.MouseButton.BackButton, Qt.KeyboardModifier.AltModifier, QPoint(20, 20))
        self.assertEqual(dialog.chord, (0x12, 0x05))
        dialog.reject()

    def test_keyboard_save_keeps_candidate_and_windows_combinations_are_rejected(self):
        dialog = KeyDialog((0x77,), self.window)
        dialog.show()
        QTest.keyClick(dialog, Qt.Key.Key_A, Qt.KeyboardModifier.MetaModifier)
        self.assertEqual(dialog.chord, (0x77,))
        QTest.keyClick(dialog, Qt.Key.Key_F9)
        QTest.keyClick(dialog, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(dialog.chord, (0x78,))
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)

    def test_accept_persists_and_updates_both_mode_labels_cancel_preserves(self):
        def choose(dialog):
            dialog.choose((0x11, 0x56))
            return QDialog.DialogCode.Accepted
        with patch.object(KeyDialog, 'exec', choose):
            self.window.choose_ptt_key()
        self.assertEqual(self.window.settings.ptt_keys, (0x11, 0x56))
        self.save_mock.assert_called()
        for mode in ('translation_only', 'translation', 'live_translation'):
            self.window.operating_mode.setCurrentIndex(self.window.operating_mode.findData(mode))
            self.assertIn('Ctrl + V', self.window.ptt.toolTip())
            self.assertIn('Ctrl + V', self.window.ptt_key.text())
        with patch.object(KeyDialog, 'exec', return_value=QDialog.DialogCode.Rejected):
            self.window.choose_ptt_key()
        self.assertEqual(self.window.settings.ptt_keys, (0x11, 0x56))
        self.assertFalse(self.window.binding_key)

    def test_global_poll_uses_chord_and_clears_on_release_capture_and_stop(self):
        w = self.window
        w.service = SimpleNamespace(talking=threading.Event())
        w.settings.ptt_keys = (0x11, 0x56)
        with patch.object(w.ptt_gate, 'pressed', return_value=True) as pressed:
            w.poll_ptt()
            self.assertTrue(w.service.talking.is_set())
            pressed.assert_called_with((0x11, 0x56))
            w.binding_key = True
            w.poll_ptt()
            self.assertFalse(w.service.talking.is_set())
            w.binding_key = False
            w.stop_requested = True
            w.poll_ptt()
            self.assertFalse(w.service.talking.is_set())
        w.stop_requested = False
        with patch.object(w.ptt_gate, 'pressed', return_value=False):
            w.poll_ptt()
            self.assertFalse(w.service.talking.is_set())
        with patch.object(KeyDialog, 'exec') as dialog:
            w.choose_ptt_key()
            dialog.assert_not_called()

    def test_sidebar_alpha_and_opaque_workspace(self):
        w = self.window
        self.assertTrue(w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground))
        self.assertTrue(w.windowFlags() & Qt.WindowType.FramelessWindowHint)
        image = w.grab().toImage()
        ratio = w.devicePixelRatioF()
        self.assertEqual(image.pixelColor(round(10 * ratio), round(500 * ratio)).alpha(), 190)
        self.assertEqual(image.pixelColor(round(200 * ratio), round(500 * ratio)).alpha(), 255)

    def test_hover_reverses_and_selection_remains_after_pointer_leaves(self):
        button = self.window.nav_buttons[1]
        button.animate(1)
        button.animation.setCurrentTime(80)
        partial = button.hover
        self.assertGreater(partial, 0)
        self.assertLess(partial, 1)
        button.animate(0)
        self.assertAlmostEqual(button.animation.startValue(), partial)
        button.animation.setCurrentTime(150)
        self.assertAlmostEqual(button.hover, 0)
        button.click()
        self.assertTrue(button.isChecked())
        self.assertEqual(self.window.tabs.currentIndex(), 1)
        QTest.keyClick(button, Qt.Key.Key_Space)
        self.assertTrue(button.isChecked())

    def test_window_controls_minimize_and_toggle_maximize(self):
        bar = self.window.title_bar
        bar.toggle_maximize()
        self.assertTrue(self.window.isMaximized())
        bar.toggle_maximize()
        self.assertFalse(self.window.isMaximized())
        bar.controls[0].click()
        self.assertTrue(self.window.isMinimized())
        self.window.showNormal()
