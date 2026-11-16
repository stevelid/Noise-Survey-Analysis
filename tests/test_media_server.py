"""Localhost media server for the browser audio backend (core/media_server.py)."""
import datetime
import http.client
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from noise_survey_analysis.core import media_server
from noise_survey_analysis.core.media_server import (
    MediaServer,
    NoAudio,
    build_clip,
    build_file_index,
    resolve_window,
)

T0 = 1_700_000_000_000.0  # epoch ms


def _write_tone(path, seconds, rate=8000, value=0.25):
    sf.write(str(path), np.full(int(seconds * rate), value, dtype=np.float32), rate, subtype='PCM_16')
    return str(path)


class ResolveWindowTests(unittest.TestCase):
    files = [("a.wav", T0, 60.0), ("b.wav", T0 + 90_000, 60.0)]

    def test_snaps_just_before_first_file_like_vlc(self):
        start, end, hits = resolve_window(self.files, T0 - 30_000, 10)
        self.assertEqual(start, T0)
        self.assertEqual(end, T0 + 10_000)
        self.assertEqual([h[0] for h in hits], ["a.wav"])

    def test_far_before_first_file_has_no_audio(self):
        with self.assertRaises(NoAudio):
            resolve_window(self.files, T0 - 120_000, 10)

    def test_after_last_file_has_no_audio(self):
        with self.assertRaises(NoAudio):
            resolve_window(self.files, T0 + 200_000, 10)

    def test_window_spanning_a_gap_hits_both_files(self):
        _, _, hits = resolve_window(self.files, T0 + 50_000, 60)
        self.assertEqual([h[0] for h in hits], ["a.wav", "b.wav"])

    def test_clamped_to_end_of_audio(self):
        _, end, _ = resolve_window(self.files, T0 + 140_000, 60)
        self.assertEqual(end, T0 + 150_000)


class BuildClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.a = _write_tone(folder / "a.wav", 60, value=0.25)
        self.b = _write_tone(folder / "b.wav", 60, value=-0.5)
        self.files = [(self.a, T0, 60.0), (self.b, T0 + 90_000, 60.0)]

    def test_frames_equal_rate_times_duration(self):
        clip = build_clip(self.files, T0 + 10_000, 20)
        self.assertEqual(clip.sample_rate, 8000)
        self.assertEqual(clip.frames, 8000 * 20)
        data, rate = sf.read(io.BytesIO(clip.wav), dtype='float32')
        self.assertEqual(rate, 8000)
        self.assertEqual(len(data), 8000 * 20)
        self.assertAlmostEqual(float(data.mean()), 0.25, places=3)
        self.assertEqual(clip.file_name, "a.wav")

    def test_stitches_across_files_with_silent_gap(self):
        clip = build_clip(self.files, T0 + 50_000, 60)
        data, _ = sf.read(io.BytesIO(clip.wav), dtype='float32')
        self.assertEqual(len(data), 8000 * 60)
        self.assertAlmostEqual(float(data[: 8000 * 10].mean()), 0.25, places=3)        # end of a.wav
        self.assertAlmostEqual(float(np.abs(data[8000 * 11: 8000 * 39]).max()), 0.0)   # 30 s gap
        self.assertAlmostEqual(float(data[8000 * 41:].mean()), -0.5, places=3)         # start of b.wav

    def test_build_file_index_uses_true_start_times(self):
        start = datetime.datetime.fromtimestamp(T0 / 1000, tz=datetime.timezone.utc)
        index = build_file_index({"P1": [(self.a, start, 60.0)], "P2": []})
        self.assertEqual(index, {"P1": [(self.a, T0, 60.0)]})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = _write_tone(Path(self.tmp.name) / "a.wav", 60)
        self.server = MediaServer()
        self.port = self.server.start()
        self.addCleanup(self.server.stop)
        self.token = self.server.register_session({"P1": [(path, T0, 60.0)]})

    def _get(self, query, headers=None, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, f"/clip?{query}", headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response, body

    def test_binds_localhost_only(self):
        self.assertEqual(self.server._server.server_address[0], "127.0.0.1")

    def test_clip_is_wav_with_cors_for_local_origin(self):
        response, body = self._get(f"pos=P1&start_ms={int(T0) + 5000}&dur_s=10&token={self.token}",
                                   headers={"Origin": "http://localhost:5105"})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "audio/wav")
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "http://localhost:5105")
        self.assertEqual(int(response.getheader("X-Clip-Frames")), 80000)
        self.assertEqual(int(response.getheader("X-Clip-Start-Ms")), int(T0) + 5000)
        self.assertEqual(len(body), 44 + 80000 * 2)

    def test_foreign_origin_gets_no_cors(self):
        response, _ = self._get(f"pos=P1&start_ms={int(T0)}&dur_s=1&token={self.token}",
                                headers={"Origin": "https://example.com"})
        self.assertEqual(response.status, 200)
        self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))

    def test_bad_token_is_refused(self):
        response, _ = self._get(f"pos=P1&start_ms={int(T0)}&dur_s=1&token=nope")
        self.assertEqual(response.status, 401)

    def test_unknown_position_and_no_audio_are_404(self):
        self.assertEqual(self._get(f"pos=P9&start_ms={int(T0)}&dur_s=1&token={self.token}")[0].status, 404)
        self.assertEqual(self._get(f"pos=P1&start_ms={int(T0) + 999_999}&dur_s=1&token={self.token}")[0].status, 404)

    def test_bad_numbers_are_400(self):
        self.assertEqual(self._get(f"pos=P1&start_ms=abc&dur_s=1&token={self.token}")[0].status, 400)

    def test_range_request(self):
        response, body = self._get(f"pos=P1&start_ms={int(T0)}&dur_s=1&token={self.token}",
                                   headers={"Range": "bytes=0-43"})
        self.assertEqual(response.status, 206)
        self.assertEqual(body[:4], b"RIFF")
        self.assertEqual(len(body), 44)

    def test_unregister_revokes_token(self):
        self.server.unregister_session(self.token)
        self.assertEqual(self._get(f"pos=P1&start_ms={int(T0)}&dur_s=1&token={self.token}")[0].status, 401)

    def test_module_unregister_does_not_start_a_server(self):
        saved = media_server._media_server
        media_server._media_server = None
        try:
            media_server.unregister_session("whatever")
            self.assertIsNone(media_server._media_server)
        finally:
            media_server._media_server = saved


if __name__ == "__main__":
    unittest.main()
