"""Render the native Qt UI, checking layout without capturing a microphone.

This is a Qt desktop application, so DOM/browser inspectors cannot measure it.
Snapshots use logical desktop dimensions, not mobile-web viewport sizes.
"""
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QScrollArea
from speak_sound.config import Settings
from speak_sound.ui import Window, create_application


def contrast(first, second):
    def luminance(color):
        rgb = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in rgb]
        return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    a, b = sorted((luminance(first), luminance(second)))
    return round((b + .05) / (a + .05), 2)


def main():
    output = ROOT / 'work/ui-v11'
    output.mkdir(parents=True, exist_ok=True)
    app = create_application([])
    reports, snapshots = [], []
    with patch.object(Settings, 'save'):
        window = Window()
        window.operating_mode.setCurrentIndex(window.operating_mode.findData('translation_only'))
        window.show()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        try:
            for width, height in ((880, 680), (1180, 860), (1440, 900)):
                window.resize(width, height)
                window.tabs.setCurrentIndex(0)
                for _ in range(3):
                    app.processEvents()
                for index, button in enumerate(window.nav_buttons):
                    button.click()
                    app.processEvents()
                    assert window.tabs.currentIndex() == index
                    assert window.page_title.text() == button.text()
                    assert window.start_button.isVisible()
                    assert window.incoming_volume.isVisible()
                window.tabs.setCurrentIndex(0)
                app.processEvents()
                assert window.mic.height() >= 32
                assert window.receive.height() >= 32
                assert all(area.horizontalScrollBar().maximum() == 0
                           for area in window.findChildren(QScrollArea))
                name = f'home-{width}.png'
                assert window.grab().save(str(output / name))
                snapshots.append(name)
                image = window.grab().toImage()
                ratio = window.devicePixelRatioF()
                assert image.pixelColor(round(10 * ratio), round(500 * ratio)).alpha() == 190
                assert image.pixelColor(round(200 * ratio), round(500 * ratio)).alpha() == 255
                reports.append(dict(width=width, height=height, stacked_audio_lanes=window.home.compact,
                    microphone_control_height=window.mic.height(),
                    live_controls_visible=window.incoming_volume.isVisible(),
                    horizontal_overflow=False))
            window.resize(1180, 860)
            for index, name in enumerate(('home', 'connection', 'playback', 'voice', 'speed', 'history', 'guide')):
                if index == 0:
                    continue
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                filename = name + '-1180.png'
                assert window.grab().save(str(output / filename))
                snapshots.append(filename)
            window.tabs.setCurrentIndex(0)
            window.bilingual.setChecked(True)
            report_path = ROOT / 'work/v11-preset-models.json'
            if report_path.exists():
                fixture = json.loads(report_path.read_text(encoding='utf-8'))['models'][4]['runs'][0]
                window.record('in', fixture['recognized'], fixture['translated'],
                              (fixture['asr_ms'] + fixture['mt_ms']) / 1000)
                window.translation_preview.direction.setText('双语对照 · 本地合成样例')
                app.processEvents()
                window.tabs.widget(0).ensureWidgetVisible(window.translation_preview)
                app.processEvents()
                assert window.translation_preview.original_column.isVisible()
                window.grab().save(str(output / 'bilingual.png'))
                window.overlay.display(fixture['recognized'], fixture['translated'])
                assert len(window.overlay.label.text().splitlines()) == 2
                overlay = window.overlay.grab().toImage()
                assert overlay.pixelColor(0, 0).alpha() == 0
                window.overlay.grab().save(str(output / 'bilingual-subtitle.png'))
                window.overlay.hide()
                snapshots.extend(['bilingual.png', 'bilingual-subtitle.png'])
            colors = {f'{ink} on {surface}': contrast(ink, surface)
                      for ink in ('#ffffff', '#b4b4b4', '#949494')
                      for surface in ('#000000', '#111111', '#262626')}
            assert min(colors.values()) >= 4.5
            family = QFontInfo(app.font()).family()
            assert 'Inter' in family
            result = dict(method='Native Qt rendering and object geometry checks; no DOM inspection',
                font=family, views=reports, contrast_ratios=colors, screenshots=snapshots,
                sidebar_alpha=190, workspace_alpha=255,
                physical_audio_capture=False, model_inference=False, user_config_written=False)
            (output / 'checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
        finally:
            window.volume_save.stop()
            window.close()


if __name__ == '__main__':
    main()
