"""Offline tests for openrouter_video_tool.

Runs with no network, no API key, and no OpenWebUI install: aiohttp is mocked and
the two OpenWebUI/FastAPI imports the tool makes at runtime are stubbed.

    python -m unittest discover -s tests -v

Most of these guard bugs that were live in v1.4 and cost real money to find, so
please keep them passing:

  * the API key was sent to every download host, including third-party CDNs
  * completed jobs with no `unsigned_urls` were dropped after being billed
  * `generate_audio=false` was never sent, so audio-default models couldn't be silenced
"""

import asyncio
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# --- stub the runtime imports the tool makes inside generate_video ---------------
_STATIC = tempfile.mkdtemp()
_ow = types.ModuleType("open_webui")
_owc = types.ModuleType("open_webui.config")
_owc.STATIC_DIR = _STATIC
sys.modules.setdefault("open_webui", _ow)
sys.modules.setdefault("open_webui.config", _owc)

if "fastapi.responses" not in sys.modules:
    _fa = types.ModuleType("fastapi")
    _far = types.ModuleType("fastapi.responses")

    class _HTMLResponse:
        def __init__(self, content=None, media_type=None, headers=None):
            self.content = content

    _far.HTMLResponse = _HTMLResponse
    sys.modules["fastapi"] = _fa
    sys.modules["fastapi.responses"] = _far

import aiohttp  # noqa: E402

import openrouter_video_tool as tool  # noqa: E402

JOB_ID = "JOB123"
CONTENT_URL = f"https://openrouter.ai/api/v1/videos/{JOB_ID}/content?index=0"


class _FakeResp:
    def __init__(self, status=200, payload=None, body=b""):
        self.status, self._payload, self._body = status, payload, body

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)

    async def read(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _session_class(poll_payload, calls, submitted, models_payload=None, submit_status=200):
    """Build a fake ClientSession that records every request it is asked to make."""

    class _FakeSession:
        instances = 0

        def __init__(self, *a, **kw):
            type(self).instances += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def post(self, url, headers=None, json=None, **kw):
            calls.append(("POST", url, headers or {}))
            submitted.update(json or {})
            if submit_status != 200:
                return _FakeResp(submit_status, {"error": "bad request"})
            return _FakeResp(200, {"id": JOB_ID, "polling_url": f"https://openrouter.ai/api/v1/videos/{JOB_ID}"})

        def get(self, url, headers=None, **kw):
            calls.append(("GET", url, headers or {}))
            if url.endswith("/videos/models"):
                return _FakeResp(200, models_payload or {"data": []})
            if "/content" in url or url.endswith(".mp4"):
                return _FakeResp(200, body=b"\x00fake-mp4-bytes")
            return _FakeResp(200, poll_payload)

    return _FakeSession


class _ToolTestCase(unittest.TestCase):
    """Shared harness: swaps in a fake ClientSession for the duration of a call."""

    def _run(self, poll_payload, models_payload=None, submit_status=200, **kwargs):
        calls, submitted = [], {}
        fake = _session_class(poll_payload, calls, submitted, models_payload, submit_status)
        original = aiohttp.ClientSession
        aiohttp.ClientSession = fake
        try:
            t = tool.Tools()
            t.valves.OPENROUTER_API_KEY = "sk-or-TESTKEY"
            t.valves.POLL_INTERVAL_SECONDS = 0
            args = {"prompt": "a cat", "model_id": "google/veo-3.1", "aspect_ratio": "16:9"}
            args.update(kwargs)
            result = asyncio.run(t.generate_video(**args))
        finally:
            aiohttp.ClientSession = original
        return result, submitted, calls, fake.instances

    def _catalog(self, models_payload):
        calls, submitted = [], {}
        fake = _session_class({}, calls, submitted, models_payload)
        original = aiohttp.ClientSession
        aiohttp.ClientSession = fake
        try:
            t = tool.Tools()
            t.valves.OPENROUTER_API_KEY = "sk-or-TESTKEY"
            return asyncio.run(t.list_video_models())
        finally:
            aiohttp.ClientSession = original

    @staticmethod
    def _downloads(calls):
        return [c for c in calls if "/content" in c[1] or c[1].endswith(".mp4")]


class TestIsOpenRouterUrl(_ToolTestCase):
    """The host check gates the API key, so it must parse the URL, not prefix-match it."""

    def test_openrouter_urls_accepted(self):
        for url in (CONTENT_URL, "https://openrouter.ai/api/v1/videos/x"):
            self.assertTrue(tool._is_openrouter_url(url), url)

    def test_lookalike_domain_rejected(self):
        # "https://openrouter.ai" is a PREFIX of this, so startswith() would leak the key.
        self.assertFalse(tool._is_openrouter_url("https://openrouter.ai.evil.com/steal"))
        self.assertFalse(tool._is_openrouter_url("https://openrouter.aievil.com/steal"))

    def test_third_party_and_malformed_rejected(self):
        for url in (
            "https://cdn.provider.com/v.mp4",
            "http://openrouter.ai/x",  # no plaintext
            "https://evil.com/?u=https://openrouter.ai",
            "https://user:pw@evil.com/#https://openrouter.ai",
            "not a url",
            "",
        ):
            self.assertFalse(tool._is_openrouter_url(url), url)


class TestDownloadPath(_ToolTestCase):
    def test_falls_back_to_content_endpoint_when_no_unsigned_urls(self):
        # v1.4 dropped the video here -- veo-3.1-fast really does return this shape.
        result, _, calls, _ = self._run({"status": "completed"})
        self.assertIsInstance(result, tuple)
        self.assertEqual(self._downloads(calls)[0][1], CONTENT_URL)

    def test_prefers_unsigned_urls_when_present(self):
        url = "https://openrouter.ai/some/signed.mp4"
        _, _, calls, _ = self._run({"status": "completed", "unsigned_urls": [url]})
        self.assertEqual(self._downloads(calls)[0][1], url)

    def test_reports_error_when_completed_without_id_or_urls(self):
        calls, submitted = [], {}

        class _NoId(_session_class({"status": "completed"}, calls, submitted)):
            def post(self, url, headers=None, json=None, **kw):
                calls.append(("POST", url, headers or {}))
                return _FakeResp(200, {"polling_url": "https://openrouter.ai/api/v1/videos/x"})

        original = aiohttp.ClientSession
        aiohttp.ClientSession = _NoId
        try:
            t = tool.Tools()
            t.valves.OPENROUTER_API_KEY = "sk-or-TESTKEY"
            t.valves.POLL_INTERVAL_SECONDS = 0
            result = asyncio.run(t.generate_video(prompt="p", model_id="m"))
        finally:
            aiohttp.ClientSession = original
        self.assertIsInstance(result, str)
        self.assertIn("no video URLs", result)


class TestApiKeyIsNotLeaked(_ToolTestCase):
    def test_bearer_sent_to_openrouter_content_endpoint(self):
        _, _, calls, _ = self._run({"status": "completed"})
        self.assertEqual(self._downloads(calls)[0][2].get("Authorization"), "Bearer sk-or-TESTKEY")

    def test_bearer_never_sent_to_third_party_cdn(self):
        _, _, calls, _ = self._run(
            {"status": "completed", "unsigned_urls": ["https://cdn.provider.com/v.mp4"]}
        )
        self.assertNotIn("Authorization", self._downloads(calls)[0][2])

    def test_no_request_to_a_non_openrouter_host_carries_the_key(self):
        _, _, calls, _ = self._run(
            {"status": "completed", "unsigned_urls": ["https://openrouter.ai.evil.com/v.mp4"]}
        )
        leaked = [c for c in calls if "Authorization" in c[2] and not tool._is_openrouter_url(c[1])]
        self.assertEqual(leaked, [])


class TestPayload(_ToolTestCase):
    def test_generate_audio_false_is_sent_explicitly(self):
        # Explicit intent must reach the API: false silences controllable models (Veo, verified live).
        _, submitted, _, _ = self._run({"status": "completed"}, generate_audio=False)
        self.assertIs(submitted.get("generate_audio"), False)

    def test_generate_audio_true_is_sent(self):
        _, submitted, _, _ = self._run({"status": "completed"}, generate_audio=True)
        self.assertIs(submitted.get("generate_audio"), True)

    def test_generate_audio_omitted_when_unspecified(self):
        # Tri-state (v1.6): no expressed intent -> no key sent -> the model's own default
        # applies, matching the documented API semantics ("defaults to the endpoint's
        # generate_audio capability flag"). v1.5 sent explicit false here, silencing
        # audio-default models the user never asked to silence.
        _, submitted, _, _ = self._run({"status": "completed"})
        self.assertNotIn("generate_audio", submitted)

    def test_seed_is_sent_when_provided(self):
        for given, expected in ((1234, 1234), ("1234", 1234), (" 42 ", 42)):
            _, submitted, _, _ = self._run({"status": "completed"}, seed=given)
            self.assertEqual(submitted.get("seed"), expected, repr(given))

    def test_seed_omitted_by_default_and_on_garbage(self):
        _, submitted, _, _ = self._run({"status": "completed"})
        self.assertNotIn("seed", submitted)
        _, submitted, _, _ = self._run({"status": "completed"}, seed="not-a-number")
        self.assertNotIn("seed", submitted)

    def test_duration_accepts_plain_and_suffixed_values(self):
        for given, expected in (("4", 4), ("8s", 8), ("8 seconds", 8)):
            _, submitted, _, _ = self._run({"status": "completed"}, duration_seconds=given)
            self.assertEqual(submitted.get("duration"), expected, given)

    def test_non_numeric_duration_is_omitted_rather_than_raising(self):
        _, submitted, _, _ = self._run({"status": "completed"}, duration_seconds="abc")
        self.assertNotIn("duration", submitted)

    def test_provider_options_wrapper_shape(self):
        opts = {"google-vertex": {"parameters": {"negativePrompt": "blurry"}}}
        _, submitted, _, _ = self._run({"status": "completed"}, provider_options=opts)
        self.assertEqual(submitted.get("provider"), {"options": opts})


class TestFrameImages(_ToolTestCase):
    IMAGES = ["https://a/1.png", "https://a/2.png", "https://a/3.png"]

    def test_first_frame_orders_forwards(self):
        _, submitted, _, _ = self._run(
            {"status": "completed"}, image_mode="first_frame", image_urls=self.IMAGES[:2]
        )
        self.assertEqual(
            [f["frame_type"] for f in submitted["frame_images"]], ["first_frame", "last_frame"]
        )

    def test_last_frame_orders_backwards(self):
        _, submitted, _, _ = self._run(
            {"status": "completed"}, image_mode="last_frame", image_urls=self.IMAGES[:2]
        )
        self.assertEqual(
            [f["frame_type"] for f in submitted["frame_images"]], ["last_frame", "first_frame"]
        )

    def test_capped_at_two_frames(self):
        _, submitted, _, _ = self._run(
            {"status": "completed"}, image_mode="first_frame", image_urls=self.IMAGES
        )
        self.assertEqual(len(submitted["frame_images"]), 2)

    def test_reference_mode_uses_input_references(self):
        _, submitted, _, _ = self._run(
            {"status": "completed"}, image_mode="reference", image_urls=self.IMAGES
        )
        self.assertEqual(len(submitted["input_references"]), 3)
        self.assertNotIn("frame_images", submitted)


class TestSessionReuse(_ToolTestCase):
    def test_submit_poll_and_download_share_one_session(self):
        _, _, _, instances = self._run({"status": "completed"})
        self.assertEqual(instances, 1)


class TestErrorPaths(_ToolTestCase):
    def test_terminal_statuses_return_the_error(self):
        for status in ("failed", "cancelled", "expired"):
            result, _, _, _ = self._run({"status": status, "error": "content policy"})
            self.assertIsInstance(result, str)
            self.assertIn("content policy", result)

    def test_submit_error_is_reported(self):
        result, _, _, _ = self._run({"status": "completed"}, submit_status=400)
        self.assertIsInstance(result, str)
        self.assertIn("API Error 400", result)

    def test_missing_api_key_is_reported(self):
        t = tool.Tools()
        result = asyncio.run(t.generate_video(prompt="p", model_id="m"))
        self.assertIn("OPENROUTER_API_KEY", result)


class TestCatalogAudioReporting(_ToolTestCase):
    """generate_audio describes whether the PARAMETER is controllable, not whether the
    model has sound. Grok reports null and still returns a stereo AAC track, so null
    must not be rendered as "no audio"."""

    CATALOG = {
        "data": [
            {"id": "google/veo-3.1-fast", "generate_audio": True,
             "pricing_skus": {"duration_seconds_720p": "0.15"}},
            {"id": "minimax/hailuo-2.3", "generate_audio": False},
            {"id": "x-ai/grok-imagine-video", "generate_audio": None,
             "pricing_skus": {"cents_per_video_output_second_720p": "7"}},
        ]
    }

    def _audio_line(self, model_id):
        out = self._catalog(self.CATALOG)
        current = None
        for line in out.splitlines():
            if "Model ID" in line:
                current = line.split("`")[1]
            if "Supports Audio" in line and current == model_id:
                return line.split(": ", 1)[1].strip()
        raise AssertionError(f"no audio line for {model_id}")

    def test_true_is_reported_as_controllable(self):
        self.assertIn("controllable", self._audio_line("google/veo-3.1-fast").lower())

    def test_false_is_reported_as_no_audio(self):
        self.assertEqual(self._audio_line("minimax/hailuo-2.3"), "No")

    def test_null_is_not_reported_as_no_audio(self):
        line = self._audio_line("x-ai/grok-imagine-video").lower()
        self.assertIn("not controllable", line)
        self.assertNotEqual(line, "no")
        self.assertNotEqual(line, "false")


class TestCatalogPricing(_ToolTestCase):
    """pricing_skus are rendered raw per model — units vary by provider, so no
    normalization; a model without the field says Unknown rather than nothing."""

    CATALOG = TestCatalogAudioReporting.CATALOG

    def _pricing_line(self, model_id):
        out = self._catalog(self.CATALOG)
        current = None
        for line in out.splitlines():
            if "Model ID" in line:
                current = line.split("`")[1]
            if "Pricing SKUs" in line and current == model_id:
                return line
        raise AssertionError(f"no pricing line for {model_id}")

    def test_skus_rendered_raw(self):
        self.assertIn("duration_seconds_720p=0.15", self._pricing_line("google/veo-3.1-fast"))
        self.assertIn("cents_per_video_output_second_720p=7", self._pricing_line("x-ai/grok-imagine-video"))

    def test_units_warning_present(self):
        self.assertIn("units vary by provider", self._pricing_line("google/veo-3.1-fast"))

    def test_missing_pricing_reads_unknown(self):
        self.assertIn("Unknown", self._pricing_line("minimax/hailuo-2.3"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
