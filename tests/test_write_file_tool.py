import os
import tempfile
import unittest

from app.tool.write_file_tool import write_file


class WriteFileToolTests(unittest.TestCase):
    def test_write_file_rejects_existing_file_without_overwrite_or_append(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("old")

            result = write_file.entrypoint(file_path=path, content="new")

            self.assertIn("already exists", result)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "old")

    def test_write_file_overwrite_replaces_existing_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("old")

            result = write_file.entrypoint(file_path=path, content="new", overwrite=True)

            self.assertIn("Successfully wrote", result)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "new")

    def test_write_file_append_adds_to_existing_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("hello")

            result = write_file.entrypoint(file_path=path, content=" world", append=True)

            self.assertIn("Successfully appended", result)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "hello world")

    def test_write_file_append_creates_file_when_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")

            result = write_file.entrypoint(file_path=path, content="hello", append=True)

            self.assertIn("Successfully appended", result)
            with open(path, "r", encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "hello")

    def test_write_file_rejects_append_and_overwrite_together(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")

            result = write_file.entrypoint(file_path=path, content="hello", append=True, overwrite=True)

            self.assertIn("cannot both be True", result)


if __name__ == "__main__":
    unittest.main()
