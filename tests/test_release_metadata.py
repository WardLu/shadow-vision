import unittest
from pathlib import Path

from scripts.validate_release import validate_release_metadata


class ReleaseMetadataTest(unittest.TestCase):
    def test_current_release_metadata_is_consistent(self):
        metadata = validate_release_metadata(Path(__file__).parents[1], "v0.1.1")
        self.assertEqual(metadata["tag"], "v0.1.1")

    def test_rejects_wrong_tag(self):
        with self.assertRaisesRegex(ValueError, "必须匹配"):
            validate_release_metadata(Path(__file__).parents[1], "v0.1.0")


if __name__ == "__main__":
    unittest.main()
