import unittest
from speak_sound.subtitles import subtitle_pages
from speak_sound.queues import LatestQueue


class SubtitleTests(unittest.TestCase):
    def test_long_text_has_bounded_pages_and_rows(self):
        pages = subtitle_pages('敌人在右边。' * 10000, len, 20)
        self.assertEqual(len(pages), 4)
        self.assertTrue(all(len(page.splitlines()) <= 2 for page in pages))
        self.assertTrue(all(len(line) <= 20 for page in pages for line in page.splitlines()))
        self.assertTrue(pages[-1].endswith('…'))

    def test_newlines_and_html_do_not_escape_plain_text_rows(self):
        pages = subtitle_pages('<b>敌人</b>\n\n在\t右边', len, 100)
        self.assertEqual(pages, ['<b>敌人</b> 在 右边'])
        self.assertEqual(subtitle_pages('   ', len, 10), [])

    def test_recent_incoming_audio_replaces_stale_waiting_phrase(self):
        q = LatestQueue(maxsize=1)
        q.put_nowait('old')
        q.put_nowait('new')
        self.assertEqual(q.get_nowait(), 'new')
        self.assertTrue(q.empty())
