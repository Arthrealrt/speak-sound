import unittest

try:
    import numpy as np
    from speak_sound.audio import to_mono16
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
