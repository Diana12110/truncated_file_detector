"""Unit tests for truncated_file_detector.core.

Run with::

    PYTHONPATH=src python -m unittest discover -s tests

Every test is deterministic: we build real temporary files on disk and assert
on exact integer sizes, never on timing or floats.
"""

import json
import os
import tempfile
import unittest

from truncated_file_detector import TruncationResult, detect_truncation


class _TempFile:
    """Context manager that writes exact bytes to a temp file."""

    def __init__(self, data: bytes, dir_path: str, name: str):
        self._data = data
        self._dir = dir_path
        self._name = name
        self.path = os.path.join(dir_path, name)

    def __enter__(self) -> str:
        with open(self.path, "wb") as fh:
            fh.write(self._data)
        return self.path

    def __exit__(self, *exc) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)


class TestDetectTruncation(unittest.TestCase):
    def setUp(self) -> None:
        # Use a fresh temp dir per test so there is zero cross-test leakage.
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- happy path ----------------------------------------------------

    def test_file_matches_declared_size(self) -> None:
        with _TempFile(b"x" * 10, self.dir, "a.bin"):
            manifest = {"a.bin": 10}
            results = detect_truncation(manifest, base_dir=self.dir)
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertFalse(r.is_truncated)
        self.assertEqual(r.declared_size, 10)
        self.assertEqual(r.actual_size, 10)

    def test_file_is_truncated(self) -> None:
        with _TempFile(b"x" * 3, self.dir, "a.bin"):
            results = detect_truncation({"a.bin": 10}, base_dir=self.dir)
        self.assertTrue(results[0].is_truncated)
        self.assertEqual(results[0].actual_size, 3)

    def test_missing_file_is_truncated(self) -> None:
        results = detect_truncation({"missing.bin": 5}, base_dir=self.dir)
        r = results[0]
        self.assertTrue(r.is_truncated)
        self.assertEqual(r.actual_size, 0)

    # --- edge cases we genuinely handle -------------------------------

    def test_zero_declared_size_never_truncated(self) -> None:
        with _TempFile(b"", self.dir, "empty.bin"):
            results = detect_truncation({"empty.bin": 0}, base_dir=self.dir)
        self.assertFalse(results[0].is_truncated)

    def test_oversized_file_not_flagged(self) -> None:
        # A file larger than declared is out of scope: not truncated.
        with _TempFile(b"x" * 20, self.dir, "big.bin"):
            results = detect_truncation({"big.bin": 10}, base_dir=self.dir)
        self.assertFalse(results[0].is_truncated)

    def test_float_size_accepted_if_whole_number(self) -> None:
        with _TempFile(b"x" * 4, self.dir, "a.bin"):
            results = detect_truncation({"a.bin": 4.0}, base_dir=self.dir)
        self.assertEqual(results[0].declared_size, 4)
        self.assertFalse(results[0].is_truncated)

    def test_absolute_path_ignores_base_dir(self) -> None:
        with _TempFile(b"y" * 2, self.dir, "abs.bin") as p:
            results = detect_truncation({p: 5}, base_dir="/nonexistent")
        self.assertTrue(results[0].is_truncated)
        self.assertEqual(results[0].path, p)

    def test_manifest_json_file(self) -> None:
        with _TempFile(b"z" * 1, self.dir, "c.bin"):
            manifest_path = os.path.join(self.dir, "manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump({"c.bin": 8}, fh)
            results = detect_truncation(manifest_path, base_dir=self.dir)
        self.assertTrue(results[0].is_truncated)
        os.remove(manifest_path)

    def test_results_preserve_manifest_order(self) -> None:
        manifest = {"first.bin": 1, "second.bin": 1, "third.bin": 1}
        results = detect_truncation(manifest, base_dir=self.dir)
        self.assertEqual([r.path for r in results], ["first.bin", "second.bin", "third.bin"])

    def test_result_is_namedtuple(self) -> None:
        with _TempFile(b"", self.dir, "a.bin"):
            results = detect_truncation({"a.bin": 0}, base_dir=self.dir)
        # namedtuple supports both index and attribute access
        r = results[0]
        self.assertEqual(r[0], "a.bin")
        self.assertEqual(r.path, r[0])
        self.assertIsInstance(r, TruncationResult)

    # --- validation errors --------------------------------------------

    def test_negative_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            detect_truncation({"a.bin": -1}, base_dir=self.dir)

    def test_non_integer_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            detect_truncation({"a.bin": 1.5}, base_dir=self.dir)

    def test_bool_size_raises(self) -> None:
        # bool is a subclass of int in Python; we reject it explicitly.
        with self.assertRaises(ValueError):
            detect_truncation({"a.bin": True}, base_dir=self.dir)

    def test_string_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            detect_truncation({"a.bin": "10"}, base_dir=self.dir)

    def test_manifest_json_not_object_raises(self) -> None:
        manifest_path = os.path.join(self.dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump([1, 2, 3], fh)
        with self.assertRaises(ValueError):
            detect_truncation(manifest_path, base_dir=self.dir)
        os.remove(manifest_path)

    def test_empty_manifest_returns_empty_list(self) -> None:
        self.assertEqual(detect_truncation({}, base_dir=self.dir), [])


if __name__ == "__main__":
    unittest.main()
