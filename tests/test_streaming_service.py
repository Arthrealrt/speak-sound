import threading
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtCore import Qt
from speak_sound.config import Settings
from speak_sound.service import Service
import speak_sound.service as module


class StreamingServiceTests(unittest.TestCase):
    def exercise_preview(self, revised=False):
        model = Mock()
        model.recognize.side_effect = ['Enemy on the right', 'No enemies'] if revised else ['Enemy on the right']
        model.translate.side_effect = ['敌人在右边', '没有敌人'] if revised else ['敌人在右边']
        draft_seen, final_seen = threading.Event(), threading.Event()
        service = Service(Settings(receive_only=True, speak_incoming=False))
        previews, finals = [], []
        def preview(*args):
            previews.append(args)
            draft_seen.set()
        def final(*args):
            finals.append(args)
            final_seen.set()
        service.events.preview.connect(preview, Qt.ConnectionType.DirectConnection)
        service.events.transcript.connect(final, Qt.ConnectionType.DirectConnection)
        class Source(threading.Thread):
            def __init__(self, p, info, destination, stop, *args):
                super().__init__(daemon=True)
                self.destination, self.stop = destination, stop
            def run(self):
                self.destination.preview(b'first', time.monotonic())
                if draft_seen.wait(2):
                    self.destination.put_nowait(b'revised' if revised else b'first')
                self.stop.wait()
        with patch.object(module, 'LocalModels', return_value=model), patch.object(module.pa, 'PyAudio'), \
             patch.object(module, 'resolve', return_value={'index': 1}), patch.object(module, 'Capture', Source), \
             patch.object(module, 'play') as play:
            try:
                service.start()
                self.assertTrue(final_seen.wait(2))
                self.assertEqual(len(previews), 1)
                self.assertEqual(len(finals), 1)
                self.assertEqual(finals[0][2], '没有敌人' if revised else '敌人在右边')
                self.assertEqual(model.recognize.call_count, 2 if revised else 1)
                model.synthesize.assert_not_called()
                play.assert_not_called()
            finally:
                service.stop.set()
                service.thread.join(3)
            self.assertFalse(service.thread.is_alive())

    def test_exact_audio_preview_reused_and_never_spoken(self):
        self.exercise_preview()

    def test_later_negation_forces_new_recognition_and_translation(self):
        self.exercise_preview(revised=True)

    def test_preview_finishing_after_final_is_queued_never_overwrites_final_subtitle(self):
        model = Mock()
        entered, release, final_seen = threading.Event(), threading.Event(), threading.Event()
        def recognize(*args, **kwargs):
            entered.set()
            release.wait(2)
            return 'Enemy'
        model.recognize.side_effect = recognize
        model.translate.return_value = '敌人'
        service = Service(Settings(receive_only=True, speak_incoming=False))
        drafts = []
        service.events.preview.connect(lambda *args: drafts.append(args), Qt.ConnectionType.DirectConnection)
        service.events.transcript.connect(lambda *args: final_seen.set(), Qt.ConnectionType.DirectConnection)
        class Source(threading.Thread):
            def __init__(self, p, info, destination, stop, *args):
                super().__init__(daemon=True)
                self.destination, self.stop = destination, stop
            def run(self):
                self.destination.preview(b'same', time.monotonic())
                if entered.wait(2):
                    self.destination.put_nowait(b'same')
                release.set()
                self.stop.wait()
        with patch.object(module, 'LocalModels', return_value=model), patch.object(module.pa, 'PyAudio'), \
             patch.object(module, 'resolve', return_value={'index': 1}), patch.object(module, 'Capture', Source):
            try:
                service.start()
                self.assertTrue(final_seen.wait(2))
                self.assertFalse(drafts)
                self.assertEqual(model.recognize.call_count, 1)
            finally:
                service.stop.set()
                release.set()
                service.thread.join(3)

    def test_outgoing_virtual_playback_does_not_block_next_text_or_close_mic_gate(self):
        playing, release, second_text = threading.Event(), threading.Event(), threading.Event()
        mic_enabled = []
        settings = Settings(send_to_virtual=True, speak_incoming=False, monitor_outgoing=False,
            microphone='physical microphone', output_device='RadioVoice Output', push_to_talk=False)
        service = Service(settings)
        model = Mock()
        model.recognize.return_value = '我倒了'
        model.translate.return_value = "I'm down."
        model.synthesize.return_value = (np.zeros(320, np.float32), 16000)
        records = []
        def record(*args):
            records.append(args)
            if len(records) == 2:
                second_text.set()
        service.events.transcript.connect(record, Qt.ConnectionType.DirectConnection)
        class Source(threading.Thread):
            def __init__(self, p, info, destination, stop, enabled, *args):
                super().__init__(daemon=True)
                self.info, self.destination, self.stop, self.enabled = info, destination, stop, enabled
            def run(self):
                if self.info['role'] == 'microphone':
                    self.destination.put_nowait(b'first')
                    if playing.wait(2):
                        mic_enabled.append(self.enabled())
                        self.destination.put_nowait(b'second')
                self.stop.wait()
        def play(*args, **kwargs):
            playing.set()
            release.wait(2)
        with patch.object(module, 'LocalModels', return_value=model), patch.object(module.pa, 'PyAudio'), \
             patch.object(module, 'resolve', side_effect=lambda p, kind, key: {'role': kind, 'index': 1}), \
             patch.object(module, 'Capture', Source), patch.object(module, 'play', side_effect=play):
            try:
                service.start()
                self.assertTrue(second_text.wait(2), 'text waited for virtual playback')
                self.assertFalse(release.is_set())
                self.assertEqual(mic_enabled, [True])
            finally:
                service.stop.set()
                release.set()
                service.thread.join(3)
            self.assertFalse(service.thread.is_alive())
