import unittest
import numpy as np

from speak_sound.voice import VoiceProcessor, process_utterance
from speak_sound.config import Settings


class VoiceTests(unittest.TestCase):
    def test_disabled_effect_preserves_original_samples(self):
        original = np.linspace(-.8, .8, 960, dtype=np.float32)
        actual = VoiceProcessor(48000).process(original, 5, "robot", enabled=False)
        np.testing.assert_array_equal(actual, original)

    def test_pitch_moves_frequency_and_preserves_duration(self):
        rate = 48000
        original = (.4 * np.sin(2*np.pi*440*np.arange(rate)/rate)).astype(np.float32)
        for pitch in (-5, 4, 8):
            processor = VoiceProcessor(rate)
            result = np.concatenate([processor.process(original[i:i+960], pitch) for i in range(0, rate, 960)])
            self.assertEqual(len(result), len(original))
            spectrum = np.abs(np.fft.rfft(result[rate//5:] * np.hanning(len(result[rate//5:]))))
            frequency = np.argmax(spectrum) * rate / len(result[rate//5:])
            self.assertLess(abs(frequency - 440 * 2 ** (pitch/12)), 15)

    def test_streaming_matches_one_buffer_and_remains_finite(self):
        original = np.random.default_rng(7).normal(0, .1, 12000).astype(np.float32)
        expected = VoiceProcessor(48000).process(original, -5, "robot")
        processor = VoiceProcessor(48000)
        actual = np.concatenate([processor.process(original[i:i+960], -5, "robot") for i in range(0, len(original), 960)])
        np.testing.assert_allclose(actual, expected, atol=2e-5)
        self.assertTrue(np.isfinite(actual).all())

    def test_radio_attenuates_low_frequency(self):
        rate = 48000
        processor = VoiceProcessor(rate)
        original = (.1 * np.sin(2*np.pi*50*np.arange(rate)/rate)).astype(np.float32)
        actual = processor.process(original, 0, "radio")
        self.assertLess(float(np.std(actual[4800:])), float(np.std(original))/20)

    def test_pitch_tail_is_flushed_for_translated_speech(self):
        settings = Settings(voice_enabled=True, voice_pitch=5)
        actual = process_utterance(np.ones(4800, np.float32)*.1, 48000, settings)
        self.assertGreater(len(actual), 4800)
        self.assertLess(len(actual), 10000)

