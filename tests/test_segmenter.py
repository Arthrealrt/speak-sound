import unittest

from speak_sound.segmenter import Segmenter


class SegmentationTests(unittest.TestCase):
    def test_shorter_silence_submits_earlier(self):
        for silence, expected in ((200, 10), (400, 20), (1500, 75)):
            with self.subTest(silence=silence):
                segmenter = Segmenter(silence_ms=silence)
                for _ in range(10):
                    segmenter.push(b'v', True)
                for index in range(expected):
                    result = segmenter.push(b's', False)
                    self.assertEqual(result is not None, index == expected - 1)

    def test_adjustable_long_sentence_limit(self):
        for seconds in (1, 3, 10):
            with self.subTest(seconds=seconds):
                segmenter = Segmenter(max_seconds=seconds)
                results = [segmenter.push(b'v', True) for _ in range(int(seconds * 50))]
                self.assertTrue(all(result is None for result in results[:-1]))
                self.assertIsNotNone(results[-1])

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
