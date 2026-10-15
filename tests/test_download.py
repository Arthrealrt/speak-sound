import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import requests
    from tools import download_models as downloader
    DOWNLOAD_AVAILABLE = True
except ImportError:
    DOWNLOAD_AVAILABLE = False


class Response:
    def __init__(self, chunks, status=200):
        self.status_code = status
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


@unittest.skipUnless(DOWNLOAD_AVAILABLE, "download dependencies not installed")
class DownloadTests(unittest.TestCase):
    def download(self, folder, responses, payload=b"abcdef"):
        metadata = SimpleNamespace(size=len(payload), etag=hashlib.sha256(payload).hexdigest())
        with patch.object(downloader, "get_hf_file_metadata", return_value=metadata), \
             patch.object(downloader.requests, "get", side_effect=responses) as get, \
             patch.object(downloader.time, "sleep"):
            downloader.download_weights("test/model", folder)
        return get

    def test_completed_file_is_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "model.bin").write_bytes(b"abcdef")
            get = self.download(folder, [])
            get.assert_not_called()

    def test_interruption_resumes_without_losing_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            get = self.download(folder, [Response([b"abc", requests.ConnectionError()]),
                                         Response([b"def"], status=206)])
            self.assertEqual(get.call_args_list[1].kwargs["headers"], {"Range": "bytes=3-"})
            self.assertEqual((folder / "model.bin").read_bytes(), b"abcdef")

    def test_server_ignoring_range_restarts_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "model.bin.part").write_bytes(b"abc")
            self.download(folder, [Response([b"abcdef"])])
            self.assertEqual((folder / "model.bin").read_bytes(), b"abcdef")

    def test_hash_mismatch_never_publishes_corrupted_model(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaisesRegex(IOError, "SHA256"):
                self.download(folder, [Response([b"xxxxxx"]) for _ in range(5)])
            self.assertFalse((folder / "model.bin").exists())
            self.assertFalse((folder / "model.bin.part").exists())
