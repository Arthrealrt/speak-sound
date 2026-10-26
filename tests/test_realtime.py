import threading
import unittest
from unittest.mock import Mock, patch
import queue
import numpy as np

from speak_sound.realtime import RealtimeSink, RealtimeVoice, MicrophoneTranslationFeed
from speak_sound.config import Settings


class RealtimeTests(unittest.TestCase):
    def test_translation_feed_flushes_on_ptt_release_and_ignores_disabled_audio(self):
        destination = queue.Queue(maxsize=2)
        feed = MicrophoneTranslationFeed(destination, Settings(), Mock())
        feed.vad = Mock(is_speech=lambda frame, rate: True)
        original = np.full(320, .25, np.float32)
        for _ in range(8):
            feed.push(original, 16000, True)
        feed.push(np.full(320, .9, np.float32), 16000, False)
        phrase = np.frombuffer(destination.get_nowait(), np.int16)
        self.assertEqual(len(phrase), 8 * 320)
        np.testing.assert_array_equal(phrase, 8191)
        for _ in range(10):
            feed.push(original, 16000, False)
        self.assertTrue(destination.empty())

    def test_same_microphone_feeds_original_to_translation_before_effect(self):
        stop, destination = threading.Event(), queue.Queue()
        settings = Settings(push_to_talk=False, voice_pitch=-5)
        mic = dict(defaultSampleRate=48000, maxInputChannels=1, index=1)
        original = np.full(960, 8192, np.int16).tobytes()
        p, stream = Mock(), Mock()
        def opened(**kwargs):
            kwargs['stream_callback'](original, 960, None, None)
            return stream
        p.open.side_effect = opened
        received, emitted = [], []
        def feed(samples, rate, enabled):
            received.append(samples.copy())
            self.assertTrue(enabled)
        def changed(samples, *args):
            samples.fill(.75)
            return samples
        def submit(samples, rate):
            emitted.append(samples.copy())
            stop.set()
        with patch('speak_sound.realtime.MicrophoneTranslationFeed') as feeder, \
             patch('speak_sound.realtime.VoiceProcessor') as processor, \
             patch('speak_sound.realtime.RealtimeSink') as sink:
            feeder.return_value.push.side_effect = feed
            processor.return_value.process.side_effect = changed
            sink.return_value.submit.side_effect = submit
            RealtimeVoice(p, mic, {}, None, settings, stop, threading.Event(), Mock(),
                          translation_destination=destination).run()
        p.open.assert_called_once()
        np.testing.assert_array_equal(received[0], .25)
        np.testing.assert_array_equal(emitted[0], .75)

    def test_callback_variable_frames_and_live_mute(self):
        volume = [.5]
        sink = RealtimeSink(Mock(), dict(defaultSampleRate=48000,maxOutputChannels=2,index=1),
                            threading.Event(), lambda: volume[0])
        sink.submit(np.full(960,.5,np.float32),48000)
        first,_ = sink.callback(None,240,None,None)
        self.assertEqual(len(first),240*2*2)
        np.testing.assert_array_equal(np.frombuffer(first,np.int16),8191)
        volume[0]=0
        second,_=sink.callback(None,720,None,None)
        self.assertFalse(any(second))

    def test_underrun_is_silent_and_queue_keeps_recent_audio(self):
        sink = RealtimeSink(Mock(),dict(defaultSampleRate=48000,maxOutputChannels=1,index=1),
                            threading.Event(),lambda:1)
        for value in (.1,.2,.3,.4):
            sink.submit(np.full(960,value,np.float32),48000)
        self.assertEqual(sink.queue.qsize(),3)
        data,_=sink.callback(None,960,None,None)
        self.assertAlmostEqual(float(np.mean(np.frombuffer(data,np.int16)))/32767,.2,places=3)
        sink.callback(None,1920,None,None)
        silence,_=sink.callback(None,960,None,None)
        self.assertFalse(any(silence))

