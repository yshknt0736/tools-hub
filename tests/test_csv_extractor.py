"""Core CSV regression checks; run with python -m unittest discover -s tests."""
import csv
import importlib.util
import pathlib
import tempfile
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "csv-extractor" / "src" / "csv_extractor.py"
spec = importlib.util.spec_from_file_location("csv_extractor", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CsvCoreTests(unittest.TestCase):
    def test_ranges_are_validated_and_constant_size(self):
        self.assertEqual(module.parse_row_ranges("1-3, 3-999999999"), [(0, 999999998)])
        self.assertTrue(module.row_selected(999999998, [(0, 999999998)]))
        self.assertFalse(module.row_selected(999999999, [(0, 999999998)]))
        for bad in ("0", "2-1", "1-", "1,,2", "abc", "2-3-4"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                module.parse_row_ranges(bad)

    def test_streaming_handles_multiline_and_duplicate_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / "sample.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["", "", ""])
                writer.writerow(["A", "A", "B"])
                writer.writerow(["first\nline", "x", "1"])
                writer.writerow(["second", "y", "2"])
            dummy = type("Dummy", (), {"_cancel": threading.Event()})()
            rows = list(module.App._iter_rows(
                dummy, [0, 1], [(1, 1)], None,
                str(source), "utf-8", csv.excel, 2, ["A", "A", "B"]))
            self.assertEqual(rows, [["A", "A"], ["second", "y"]])


if __name__ == "__main__":
    unittest.main()
