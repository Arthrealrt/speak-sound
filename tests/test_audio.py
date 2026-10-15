import unittest
import threading

try:
    import numpy as np
    from speak_sound.audio import to_mono16, play
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False


@unittest.skipUnless(AUDIO_AVAILABLE, "audio dependencies not installed")
class AudioConversionTests(unittest.TestCase):
    def test_stereo_opposite_signals_cancel_when_downmixed(self):
        frame = np.tile(np.array([1000, -1000], dtype=np.int16), (960, 1))
        mono = np.frombuffer(to_mono16(frame.tobytes(), 48000, 2), dtype=np.int16)
        self.assertEqual(mono.size, 320)
        self.assertTrue(np.all(mono == 0))

    def test_common_device_rates_produce_exact_vad_frame_length(self):
        for rate in (16000, 32000, 44100, 48000):
            with self.subTest(rate=rate):
                samples = np.zeros(rate // 50, dtype=np.int16)
                self.assertEqual(len(to_mono16(samples.tobytes(), rate, 1)), 640)

    def test_resampling_keeps_speech_band_frequency(self):
        rate = 48000
        samples = (12000 * np.sin(2 * np.pi * 440 * np.arange(rate) / rate)).astype(np.int16)
        mono = np.frombuffer(to_mono16(samples.tobytes(), rate, 1), dtype=np.int16)
        peak = np.argmax(np.abs(np.fft.rfft(mono)))
        self.assertEqual(peak, 440)

    def test_play_resamples_and_interleaves_stereo(self):
        writes = []
        closed = []

        class Stream:
            def write(self, data): writes.append(data)
            def stop_stream(self): pass
            def close(self): closed.append(True)

        class Audio:
            def open(self, **kwargs): return Stream()

        play(Audio(), {"defaultSampleRate": 48000, "maxOutputChannels": 2, "index": 1},
             np.zeros(320, dtype=np.float32), 16000, threading.Event())
        self.assertEqual(sum(map(len, writes)), 960 * 2 * 2)
        self.assertEqual(closed, [True])
