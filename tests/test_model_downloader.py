import hashlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
backend_dir = os.path.join(project_root, "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

import model_downloader


class _FakeResponse:
    """Minimal stand-in for a requests.Response used by download_model."""

    def __init__(self, status_code=200, content=b"", headers=None, location=None):
        self.status_code = status_code
        self._content = content
        self.headers = headers if headers is not None else {}
        if location is not None:
            self.headers["Location"] = location

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=1024):
        # Emit content in chunks of chunk_size bytes.
        data = self._content
        for i in range(0, len(data), chunk_size):
            yield data[i:i + chunk_size]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


class TestModelDownloader(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.dest = os.path.join(self.tmpdir, "face_landmarker.task")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_get(self, responses):
        """Make requests.get return successive FakeResponse objects."""
        calls = list(responses)

        def fake_get(url, **kwargs):
            self.assertIn("allow_redirects", kwargs)
            self.assertFalse(kwargs["allow_redirects"], "allow_redirects must be False")
            self.assertIn("timeout", kwargs)
            self.assertEqual(kwargs["timeout"], (10, 300))
            return calls.pop(0)

        return patch("model_downloader.requests.get", side_effect=fake_get)

    def test_existing_file_is_trusted_when_hash_not_pinned(self):
        with open(self.dest, "wb") as f:
            f.write(b"already here")
        with patch("model_downloader.EXPECTED_MODEL_SHA256", ""):
            self.assertTrue(model_downloader.download_model(self.dest))

    def test_existing_file_with_wrong_hash_is_redownloaded(self):
        with open(self.dest, "wb") as f:
            f.write(b"bad content")
        good = b"good content"
        good_resp = _FakeResponse(status_code=200, content=good,
                                  headers={"content-length": str(len(good))})
        with patch("model_downloader.EXPECTED_MODEL_SHA256", "a" * 64), \
             patch("model_downloader._sha256_of_file", return_value="b" * 64):
            with self._patch_get([good_resp]):
                # After re-download, _verify_model_hash(part_path) must succeed.
                with patch("model_downloader._verify_model_hash", side_effect=[False, True]):
                    self.assertTrue(model_downloader.download_model(self.dest))
        # The bad pre-existing file should have been removed and replaced.
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), good)

    def test_atomic_write_uses_part_file(self):
        content = b"x" * 10
        resp = _FakeResponse(status_code=200, content=content,
                             headers={"content-length": str(len(content))})
        # Pin the expected hash to this content so the real verification path
        # runs and the file is promoted atomically.
        with patch("model_downloader.EXPECTED_MODEL_SHA256", hashlib.sha256(content).hexdigest()):
            with self._patch_get([resp]):
                self.assertTrue(model_downloader.download_model(self.dest))
        self.assertTrue(os.path.exists(self.dest))
        # No leftover .part file.
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_size_cap_via_content_length(self):
        # content-length above cap -> abort before writing.
        resp = _FakeResponse(status_code=200, content=b"",
                             headers={"content-length": str(model_downloader.MAX_MODEL_BYTES + 1)})
        with self._patch_get([resp]):
            self.assertFalse(model_downloader.download_model(self.dest))
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_size_cap_during_stream(self):
        # content-length lies small but actual body exceeds the cap.
        big = b"a" * (model_downloader.MAX_MODEL_BYTES + 1)
        resp = _FakeResponse(status_code=200, content=big,
                             headers={"content-length": str(1024)})
        with self._patch_get([resp]):
            self.assertFalse(model_downloader.download_model(self.dest))
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_redirect_to_same_host_is_followed(self):
        content = b"redirected content"
        redirect = _FakeResponse(status_code=302, location=model_downloader.MODEL_URL + "?x=1")
        final = _FakeResponse(status_code=200, content=content,
                               headers={"content-length": str(len(content))})
        with patch("model_downloader.EXPECTED_MODEL_SHA256", hashlib.sha256(content).hexdigest()):
            with self._patch_get([redirect, final]):
                self.assertTrue(model_downloader.download_model(self.dest))
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), content)

    def test_redirect_to_foreign_host_is_rejected(self):
        redirect = _FakeResponse(status_code=302, location="https://evil.example.com/model.task")
        with self._patch_get([redirect]):
            self.assertFalse(model_downloader.download_model(self.dest))
        self.assertFalse(os.path.exists(self.dest))

    def test_redirect_missing_location_is_rejected(self):
        redirect = _FakeResponse(status_code=302, location=None)
        with self._patch_get([redirect]):
            self.assertFalse(model_downloader.download_model(self.dest))

    def test_too_many_redirects_aborts(self):
        # Six redirects in a row -> loop guard trips.
        redirects = [_FakeResponse(status_code=302, location=model_downloader.MODEL_URL + f"?{i}") for i in range(6)]
        with self._patch_get(redirects):
            self.assertFalse(model_downloader.download_model(self.dest))

    def test_http_error_returns_false_and_cleans_part(self):
        resp = _FakeResponse(status_code=500, content=b"",
                             headers={"content-length": "0"})
        with self._patch_get([resp]):
            self.assertFalse(model_downloader.download_model(self.dest))
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_downloaded_file_verified_before_promotion(self):
        content = b"some bytes"
        resp = _FakeResponse(status_code=200, content=content,
                              headers={"content-length": str(len(content))})
        with patch("model_downloader.EXPECTED_MODEL_SHA256", "c" * 64), \
             patch("model_downloader._verify_model_hash", return_value=False):
            with self._patch_get([resp]):
                self.assertFalse(model_downloader.download_model(self.dest))
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))


if __name__ == "__main__":
    unittest.main()