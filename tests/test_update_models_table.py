"""Offline tests for the README models-table generator (no network).

Exercises the pure formatting helpers and the marker splice — the parts with
real logic. The live fetch is not tested here (it's a thin urllib call).

    python -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import update_models_table as u  # noqa: E402


class TestDurations(unittest.TestCase):
    def test_single(self):
        self.assertEqual(u.fmt_durations([8]), "8s")

    def test_contiguous_range(self):
        self.assertEqual(u.fmt_durations([1, 2, 3, 4, 5]), "1–5s")
        self.assertEqual(u.fmt_durations(list(range(3, 16))), "3–15s")

    def test_two_non_contiguous(self):
        self.assertEqual(u.fmt_durations([5, 10]), "5 or 10s")

    def test_sparse_list(self):
        self.assertEqual(u.fmt_durations([4, 8, 12, 16, 20]), "4, 8, 12, 16, 20s")

    def test_unsorted_input(self):
        self.assertEqual(u.fmt_durations([8, 4, 6]), "4, 6, 8s")

    def test_empty(self):
        self.assertEqual(u.fmt_durations([]), "Any")
        self.assertEqual(u.fmt_durations(None), "Any")


class TestResolution(unittest.TestCase):
    def test_picks_highest(self):
        self.assertEqual(u.max_resolution(["480p", "720p", "1080p"]), "1080p")

    def test_4k_is_bolded(self):
        self.assertEqual(u.max_resolution(["720p", "1080p", "4K"]), "**4K**")

    def test_order_independent(self):
        self.assertEqual(u.max_resolution(["1080p", "480p", "720p"]), "1080p")

    def test_empty_is_any(self):
        self.assertEqual(u.max_resolution(None), "Any")
        self.assertEqual(u.max_resolution([]), "Any")


class TestAudioSymbol(unittest.TestCase):
    def test_three_states(self):
        # Distinguishing null from false is the whole point (the v1.5/v1.6 lesson).
        self.assertEqual(u.audio_symbol(True), "✅")
        self.assertEqual(u.audio_symbol(False), "❌")
        self.assertEqual(u.audio_symbol(None), "➖")


class TestSplice(unittest.TestCase):
    DOC = f"intro\n{u.START}\nOLD TABLE\n{u.END}\noutro\n"

    def test_replaces_only_between_markers(self):
        out = u.splice(self.DOC, "NEW TABLE")
        self.assertIn(f"{u.START}\nNEW TABLE\n{u.END}", out)
        self.assertTrue(out.startswith("intro\n"))
        self.assertTrue(out.endswith("outro\n"))
        self.assertNotIn("OLD TABLE", out)

    def test_missing_markers_raises(self):
        with self.assertRaises(SystemExit):
            u.splice("no markers here", "TABLE")


class TestBuildTable(unittest.TestCase):
    MODELS = [
        {"id": "z/last", "supported_resolutions": ["720p"], "supported_durations": [5],
         "supported_aspect_ratios": ["16:9"], "generate_audio": None},
        {"id": "a/first", "supported_resolutions": ["1080p", "4K"], "supported_durations": [4, 6, 8],
         "supported_aspect_ratios": ["16:9", "9:16"], "generate_audio": True},
    ]

    def test_sorted_by_id_deterministic(self):
        rows = u.build_table(self.MODELS).splitlines()
        # header, separator, then models alphabetically by id
        self.assertTrue(rows[2].startswith("| `a/first`"))
        self.assertTrue(rows[3].startswith("| `z/last`"))

    def test_row_shape(self):
        rows = u.build_table(self.MODELS).splitlines()
        self.assertIn("| `a/first` | **4K** | 4, 6, 8s | 16:9, 9:16 | ✅ |", rows)

    def test_none_aspect_is_any(self):
        m = [{"id": "x/y", "supported_resolutions": ["1080p"], "supported_durations": [1, 2, 3],
              "supported_aspect_ratios": None, "generate_audio": None}]
        self.assertIn("| 1–3s | Any | ➖ |", u.build_table(m))


if __name__ == "__main__":
    unittest.main(verbosity=2)
