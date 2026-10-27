import queue
import threading
import time
import unittest
from speak_sound.config import Settings
from speak_sound.segmenter import make_segmenter
from speak_sound.streaming import SpeechQueue, PriorityLock, PreviewBusy, ResultCache


class StreamingTests(unittest.TestCase):
    def test_pause_preview_is_identical_to_final_and_never_contains_closed_gate_audio(self):
        q = SpeechQueue()
        s = make_segmenter(Settings(silence_ms=160), q)
        for _ in range(15):
            s.push(b'v' * 640, True)
        for _ in range(3):
            s.push(bytes(640), False)
        preview = q.get()
        self.assertFalse(preview.final)
        final = s.push(b'private' * 100, True, enabled=False)
        self.assertEqual(preview.pcm, final.pcm)
        self.assertNotIn(b'private', final.pcm)
        q.put_nowait(final)
        self.assertFalse(q.current(preview))

    def test_resumed_speech_changes_pcm_so_prediction_cannot_be_reused(self):
        q = SpeechQueue()
        s = make_segmenter(Settings(silence_ms=160), q)
        for _ in range(12):
            s.push(b'a' * 640, True)
        for _ in range(3):
            s.push(bytes(640), False)
        preview = q.get()
        for _ in range(12):
            s.push(b'b' * 640, True)
        final = s.flush()
        self.assertNotEqual(preview.pcm, final.pcm)
        cache = ResultCache()
        cache.put(preview.pcm, ('enemy', '敌人'))
        self.assertIsNone(cache.get(final.pcm))

    def test_vad_quiet_phonemes_are_preserved_instead_of_trimming_word_endings(self):
        q = SpeechQueue()
        s = make_segmenter(Settings(silence_ms=160), q)
        for _ in range(12):
            s.push(b'a' * 640, True)
        for _ in range(3):
            s.push(bytes(640), False)
        preview = q.get()
        quiet_phoneme = b'\x01\x00' * 320
        s.push(quiet_phoneme, False)
        final = s.flush()
        self.assertIn(quiet_phoneme, final.pcm)
        self.assertNotEqual(preview.pcm, final.pcm)

    def test_expensive_recognizer_does_not_preview_noisy_or_audible_word_endings(self):
        q = SpeechQueue(zero_tail_only=True)
        s = make_segmenter(Settings(silence_ms=300), q)
        for _ in range(12):
            s.push(b'a' * 640, True)
        for _ in range(5):
            s.push(b'\x01\x00' * 320, False)
        with self.assertRaises(queue.Empty):
            q.get(.001)
        for _ in range(3):
            s.push(bytes(640), False)
        self.assertFalse(q.get().final)

    def test_final_priority_latest_preview_and_stale_suppression(self):
        q = SpeechQueue(maxsize=1)
        q.preview(b'old', 1)
        q.preview(b'latest', 2)
        self.assertEqual(q.get().pcm, b'latest')
        q.preview(b'draft', 3)
        draft = q.get()
        q.put_nowait(b'first final')
        q.put_nowait(b'latest final')
        self.assertFalse(q.current(draft))
        self.assertEqual(q.get().pcm, b'latest final')
        with self.assertRaises(queue.Empty):
            q.get(timeout=.001)
        q.preview(b'corrupt prefix', 4)
        draft = q.get()
        q.invalidate_preview()
        self.assertFalse(q.current(draft))

    def test_full_outgoing_queue_invalidates_unsubmitted_preview(self):
        q = SpeechQueue(maxsize=1, latest=False)
        q.put_nowait(b'first')
        q.preview(b'next preview', 1)
        with self.assertRaises(queue.Full):
            q.put_nowait(b'overflow final')
        self.assertEqual(q.get().pcm, b'first')
        with self.assertRaises(queue.Empty):
            q.get(timeout=.001)

    def test_streaming_off_preserves_original_audio_and_click_is_rejected(self):
        q = SpeechQueue()
        s = make_segmenter(Settings(streaming_enabled=False), q)
        for _ in range(10):
            s.push(b'x' * 640, True)
        final = s.flush()
        self.assertEqual(final.pcm, b'x' * 6400)
        s.push(b'click', True)
        self.assertIsNone(s.flush())
        with self.assertRaises(queue.Empty):
            q.get(timeout=.001)

    def test_final_waiter_prevents_new_speculative_work(self):
        lock = PriorityLock()
        waiting, done = threading.Event(), threading.Event()
        def final():
            waiting.set()
            with lock.hold():
                done.set()
        with lock.hold(preview=True):
            thread = threading.Thread(target=final)
            thread.start()
            self.assertTrue(waiting.wait(1))
            with self.assertRaises(PreviewBusy):
                with lock.hold(preview=True):
                    self.fail('preview acquired a busy model')
            self.assertFalse(done.is_set())
        self.assertTrue(done.wait(1))
        thread.join(1)

    def test_cache_is_bounded_and_not_a_prefix_match(self):
        cache = ResultCache(limit=2)
        for word in (b'one', b'two', b'three'):
            cache.put(word, (word, word))
        self.assertIsNone(cache.get(b'one'))
        self.assertIsNone(cache.get(b'three more'))
        self.assertEqual(cache.get(b'three'), (b'three', b'three'))
