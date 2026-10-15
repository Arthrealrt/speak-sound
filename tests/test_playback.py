import threading
import unittest

from speak_sound.playback import FeedbackGate, LocalPlayback


class PlaybackTests(unittest.TestCase):
    def test_feedback_gate_covers_playback_and_tail(self):
        now = [1.0]
        gate = FeedbackGate(clock=lambda: now[0])
        self.assertFalse(gate.paused())
        gate.begin()
        self.assertTrue(gate.paused())
        gate.end()
        now[0] += .2
        self.assertTrue(gate.paused())
        now[0] += .2
        self.assertFalse(gate.paused())

    def test_local_queue_is_bounded_and_rejects_after_stop(self):
        stop = threading.Event()
        messages = []
        player = LocalPlayback(None, None, stop, FeedbackGate(), lambda *args: None, messages.append)
        self.assertTrue(player.submit([0], 16000))
        self.assertTrue(player.submit([0], 16000))
        self.assertFalse(player.submit([0], 16000))
        self.assertEqual(len(messages), 1)
        stop.set()
        self.assertFalse(player.submit([0], 16000))

    def test_playback_gates_capture_and_stops_cleanly(self):
        stop = threading.Event()
        gate = FeedbackGate()
        observed = []

        def play(*args):
            observed.append(gate.paused())
            stop.set()

        player = LocalPlayback(None, None, stop, gate, play, lambda message: None)
        player.submit([0], 16000)
        player.start()
        player.join(timeout=2)
        self.assertFalse(player.is_alive())
        self.assertEqual(observed, [True])
        self.assertFalse(gate.active.is_set())
