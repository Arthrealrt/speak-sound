"""Both translation directions must survive either microphone send route."""
import threading
import time
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PySide6.QtCore import Qt

from speak_sound.config import Settings
from speak_sound.service import Service
import speak_sound.service as module


class CombinedTests(unittest.TestCase):
    def test_slow_chinese_tts_does_not_block_next_subtitle(self):
        entered, release, second_subtitle = threading.Event(), threading.Event(), threading.Event()
        model = Mock()
        model.recognize.return_value = 'Enemy on the right'
        model.translate.return_value = '敌人在右边'
        def slow_tts(*args):
            entered.set()
            release.wait(3)
            return np.zeros(320, np.float32), 16000
        model.synthesize.side_effect = slow_tts
        class Source(threading.Thread):
            def __init__(self, p, info, destination, stop, *args):
                super().__init__(daemon=True)
                self.destination, self.stop = destination, stop
            def run(self):
                self.destination.put_nowait(b'first')
                if entered.wait(2):
                    self.destination.put_nowait(b'second')
                self.stop.wait()
        service = Service(Settings(receive_only=True, incoming_language='en'))
        subtitles = []
        def subtitle(*args):
            subtitles.append(args)
            if len(subtitles) == 2:
                second_subtitle.set()
        service.events.subtitle.connect(subtitle, Qt.ConnectionType.DirectConnection)
        with patch.object(module, 'LocalModels', return_value=model), patch.object(module.pa, 'PyAudio'), \
             patch.object(module, 'resolve', return_value={'index': 1}), \
             patch.object(module, 'Capture', Source), patch.object(module, 'play'):
            try:
                service.start()
                self.assertTrue(second_subtitle.wait(2), 'next subtitle waited for blocked TTS')
                self.assertFalse(release.is_set())
            finally:
                service.stop.set()
                release.set()
                service.thread.join(3)
            self.assertFalse(service.thread.is_alive())

    def run_combined(self, mode, monitor=True, target='ja', source='ja'):
        settings = Settings(operating_mode=mode, send_to_virtual=True,
                            microphone='physical microphone', output_device='RadioVoice Output',
                            listen_device='headphones', monitor_outgoing=monitor,
                            voice_enabled=True, voice_pitch=-5,
                            target_language=target, incoming_language=source)
        model = Mock()
        model.recognize.side_effect = lambda pcm, lang: '队友在右边' if lang == 'zh' else ('Enemy on the right' if lang == 'en' else '右にいます')
        model.translate.side_effect = lambda text, source, target: '队友在右边' if target == 'zh' else ('Enemy on the right' if target == 'en' else '右にいます')
        model.synthesize.side_effect = lambda text, lang='ja': (np.full(320, .4 if lang == 'zh' else .2, np.float32), 16000)
        captures, live_sends, played, transcripts, subtitles = [], [], [], [], []

        class Source(threading.Thread):
            def __init__(self, p, info, destination, stop, enabled, settings, report):
                super().__init__(daemon=True)
                self.destination, self.stop = destination, stop
                captures.append(info['role'])

            def run(self):
                self.destination.put(b'original unmodified PCM')
                self.stop.wait()

        class LiveSource(threading.Thread):
            def __init__(self, p, mic, output, listen, settings, stop, talking, report,
                         translation_destination, capture_enabled):
                super().__init__(daemon=True)
                self.destination, self.stop = translation_destination, stop
                captures.append('live_microphone')
                live_sends.append(output)

            def run(self):
                self.destination.put(b'original unmodified PCM')
                self.stop.wait()

        def play(p, info, samples, rate, stop, volume=lambda: 1):
            played.append((info['role'], float(np.mean(samples))))

        def effect(samples, rate, settings):
            self.assertEqual(settings.voice_pitch, -5)
            return samples * .5

        service = Service(settings)
        service.events.transcript.connect(lambda *args: transcripts.append(args), Qt.ConnectionType.DirectConnection)
        service.events.subtitle.connect(lambda *args: subtitles.append(args), Qt.ConnectionType.DirectConnection)
        with patch.object(module, 'LocalModels', return_value=model), patch.object(module.pa, 'PyAudio'), \
             patch.object(module, 'resolve', side_effect=lambda p, kind, key: {'role': key if kind == 'output' else kind}), \
             patch.object(module, 'Capture', Source), patch.object(module, 'RealtimeVoice', LiveSource), \
             patch.object(module, 'process_utterance', side_effect=effect) as dsp, patch.object(module, 'play', play):
            service.start()
            expected_plays = (3 if mode == 'translation' else 2) if monitor else 1
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline and (len(played) < expected_plays or len(transcripts) < 2):
                time.sleep(.01)
            service.stop.set()
            service.thread.join(3)
            self.assertFalse(service.thread.is_alive())
        self.assertEqual({item[0] for item in transcripts}, {'in', 'out'})
        self.assertEqual(subtitles, [('Enemy on the right' if source == 'en' else '右にいます', '队友在右边')])
        model.recognize.assert_any_call(b'original unmodified PCM', source)
        model.translate.assert_any_call('队友在右边', 'zh', target)
        self.assertIn(('headphones', .4), [(role, round(value, 1)) for role, value in played])
        self.assertEqual(captures.count('microphone') + captures.count('live_microphone'), 1)
        if mode == 'translation':
            self.assertIn(('RadioVoice Output', .1), [(role, round(value, 1)) for role, value in played])
            self.assertFalse(live_sends)
        else:
            self.assertEqual(len(live_sends), 1)
            self.assertNotIn('RadioVoice Output', [role for role, value in played])
        self.assertEqual(dsp.call_count, int(monitor or mode == 'translation'))
        if monitor:
            self.assertIn(('headphones', .1), [(role, round(value, 1)) for role, value in played])

    def test_translated_voice_effect_and_both_directions(self):
        self.run_combined('translation')

    def test_live_original_route_keeps_both_directions_and_japanese_monitor(self):
        self.run_combined('live_translation')

    def test_live_original_route_translates_even_without_japanese_monitor(self):
        self.run_combined('live_translation', monitor=False)

    def test_english_both_directions_keep_translated_voice_effect(self):
        self.run_combined('translation', target='en', source='en')

    def test_live_voice_with_english_translation_and_japanese_receiving(self):
        self.run_combined('live_translation', target='en', source='ja')


if __name__ == '__main__':
    unittest.main()
