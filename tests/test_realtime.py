import threading
import unittest
from unittest.mock import Mock
import numpy as np

from speak_sound.realtime import RealtimeSink


class RealtimeTests(unittest.TestCase):
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

