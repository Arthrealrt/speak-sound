"""Check the Windows compositor against a synthetic background, without audio.

Run on Windows with QT_QPA_PLATFORM=windows. Only this tool's own test windows
are captured. No global keyboard input, microphone, model or driver is opened.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidget
from speak_sound.config import Settings
from speak_sound.ui import Window, create_application
from speak_sound.key_dialog import KeyDialog


def main():
    if sys.platform != 'win32' or os.environ.get('QT_QPA_PLATFORM') != 'windows':
        raise RuntimeError('Requires Windows desktop and QT_QPA_PLATFORM=windows')
    output = ROOT / 'work/ui-v10'
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    # Every pixel behind the tested app belongs to our synthetic background.
    background = QWidget()
    background.setWindowTitle('Speak Sound synthetic compositor test')
    background.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
    background.setStyleSheet('background: #2673c8;')
    available = app.primaryScreen().availableGeometry()
    background.setGeometry(available)
    background.show()
    with patch.object(Settings, 'save'), patch.object(Settings, 'load', return_value=Settings()), \
            patch.object(Window, 'refresh_devices'), patch.object(Window, 'refresh_processes'):
        window = Window()
        window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        window.resize(min(1180, available.width() - 40), min(860, available.height() - 40))
        window.move(available.topLeft() + QPoint(20, 20))
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            QTest.qWait(250)
            user32 = ctypes.windll.user32
            user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
            user32.SendMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.SendMessageW.restype = wintypes.LPARAM
            rect = wintypes.RECT()
            user32.GetWindowRect(int(window.winId()), ctypes.byref(rect))
            # Real WM_NCHITTEST calls exercise native resize dispatch.
            def hit(x, y):
                return user32.SendMessageW(int(window.winId()), 0x84, 0, (x & 0xFFFF) | ((y & 0xFFFF) << 16))
            assert hit(rect.left + 1, rect.top + 1) == 13
            assert hit(rect.right - 2, rect.bottom - 2) == 17
            assert hit(rect.left + 1, (rect.top + rect.bottom) // 2) == 10
            # A layered HWND's private DC returns black on Windows. Capture only
            # its rectangle on the compositor, backed entirely by our test host.
            capture = window.windowHandle().screen().grabWindow(0, window.x(), window.y(), window.width(), window.height())
            image = capture.toImage()
            ratio = capture.devicePixelRatio()
            color = image.pixelColor(round(10 * ratio), round(500 * ratio))
            # Alpha 190 over RGB(38,115,200), allowing compositor rounding.
            expected = [round(fg * 190 / 255 + bg * 65 / 255) for fg, bg in zip((12,14,17),(38,115,200))]
            actual = [color.red(), color.green(), color.blue()]
            assert max(abs(a - b) for a, b in zip(actual, expected)) <= 3, (actual, expected)
            assert capture.save(str(output / 'windows-composited.png'))
            button = window.nav_buttons[1]
            QTest.mouseMove(button, button.rect().center())
            QTest.qWait(180)
            assert button.hover > .99
            assert window.grab().save(str(output / 'hover.png'))
            QTest.mouseMove(window.title_bar, QPoint(10, 10))
            QTest.qWait(180)
            assert button.hover < .01
            window.title_bar.toggle_maximize()
            QTest.qWait(100)
            assert window.isMaximized()
            window.title_bar.toggle_maximize()
            QTest.qWait(100)
            assert not window.isMaximized()
            dialog = KeyDialog((0x11, 0x10, 0x56), window)
            dialog.show()
            QTest.qWait(80)
            assert dialog.grab().save(str(output / 'shortcut-dialog.png'))
            dialog.reject()
            result = dict(compositor_pixel=actual, expected_pixel=expected, sidebar_alpha=190,
                native_resize_hit_test=True, hover_enter_leave=True, maximize_restore=True,
                physical_audio_capture=False, user_config_written=False)
            (output / 'windows-checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result))
        finally:
            window.volume_save.stop()
            window.close()
            background.close()


if __name__ == '__main__':
    main()
