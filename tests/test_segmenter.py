import unittest

from speak_sound.segmenter import Segmenter


class SegmentationTests(unittest.TestCase):
    def test_silence_does_not_produce_transcript(self):
        s = Segmenter()
        for _ in range(500):
            self.assertIsNone(s.push(b"s", False))

    def test_preroll_preserves_word_onset_and_hangover(self):
        s = Segmenter(silence_ms=40, min_ms=40)
        s.push(b"a", False)
        s.push(b"b", True)
        s.push(b"c", True)
        self.assertIsNone(s.push(b"d", False))
        self.assertEqual(s.push(b"e", False), b"abcde")

    def test_key_release_flushes_and_discards_closed_gate_audio(self):
        s = Segmenter(min_ms=40)
        s.push(b"a", True)
        s.push(b"b", True)
        self.assertEqual(s.push(b"x", False, enabled=False), b"ab")
        for _ in range(10):
            self.assertIsNone(s.push(b"secret", True, enabled=False))
        s.push(b"c", True)
        s.push(b"d", True)
        self.assertEqual(s.flush(), b"cd")

    def test_short_click_is_discarded(self):
        s = Segmenter()
        s.push(b"click", True)
        self.assertIsNone(s.flush())

    def test_continuous_speech_is_bounded(self):
        s = Segmenter(max_seconds=.2, min_ms=40)
        results = [s.push(b"x", True) for _ in range(20)]
        self.assertEqual([r for r in results if r], [b"x" * 10, b"x" * 10])


if __name__ == "__main__":
    unittest.main()
