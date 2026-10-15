import queue
import threading
import unittest
import numpy as np
from unittest.mock import Mock, patch

from speak_sound.process_audio import ProcessTarget, ProcessCapture, open_process_loopback
from speak_sound.config import Settings


class ProcessAudioTests(unittest.TestCase):
    def test_float_stereo_capture_becomes_segmented_mono_pcm(self):
        stop = threading.Event()
        class StopQueue(queue.Queue):
            def put_nowait(self, item):
                super().put_nowait(item)
                stop.set()
        destination = StopQueue()
        native = Mock()
        native.get_format.return_value = dict(sample_rate=48000, channels=2, bits_per_sample=32)
        native.read.return_value = np.full((48000, 2), .25, np.float32).tobytes()
        target = Mock(pid=123, alive=lambda: True)
        with patch('speak_sound.process_audio.open_process_loopback', return_value=native), \
             patch('speak_sound.process_audio.webrtcvad.Vad') as vad:
            vad.return_value.is_speech.return_value = True
            capture = ProcessCapture(target, destination, stop, Settings(max_speech_seconds=1), lambda text: None)
            capture.start()
            capture.join(timeout=2)
        self.assertFalse(capture.is_alive())
        pcm = np.frombuffer(destination.get_nowait(), np.int16)
        self.assertEqual(len(pcm), 16000)
        self.assertLess(abs(float(np.mean(pcm)) - 8191), 20)
        native.stop.assert_called_once()

    def test_pid_reuse_does_not_match(self):
        with patch('speak_sound.process_audio.psutil.Process') as process:
            process.return_value.create_time.return_value = 20
            process.return_value.is_running.return_value = True
            self.assertFalse(ProcessTarget(123, 10, 'game.exe').alive())

    def test_never_accepts_whole_system_fallback(self):
        native = Mock()
        native.is_process_specific.return_value = False
        with self.assertRaisesRegex(RuntimeError, '拒绝整机回退'):
            open_process_loopback(Mock(alive=lambda: True, pid=123), lambda pid: native)
        native.start.assert_not_called()
        native.stop.assert_called_once()

    def test_exited_target_never_opens_native_capture(self):
        factory = Mock()
        with self.assertRaises(ValueError):
            open_process_loopback(Mock(alive=lambda: False), factory)
        factory.assert_not_called()

    def test_target_exit_stops_service_and_releases_capture(self):
        stop = threading.Event()
        native = Mock()
        native.get_format.return_value = dict(sample_rate=48000, channels=2, bits_per_sample=32)
        native.read.return_value = None
        target = Mock(pid=123, alive=lambda: False)
        reports = []
        with patch('speak_sound.process_audio.open_process_loopback', return_value=native):
            capture = ProcessCapture(target, queue.Queue(), stop, Settings(), reports.append)
            capture.start()
            capture.join(timeout=2)
        self.assertFalse(capture.is_alive())
        self.assertTrue(stop.is_set())
        self.assertTrue(any('目标进程已退出' in text for text in reports))
        native.stop.assert_called_once()
