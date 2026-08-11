import unittest
from unittest.mock import patch

from allowlist import _load_allowed_repos, clear_cache, is_allowed


SAMPLE_YAML = """
allowed_repos:
  - TorchedHat/pytorch-redhat-ci
  - subinz1/CRCR
"""


class TestAllowlist(unittest.TestCase):
    def setUp(self):
        clear_cache()

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_is_allowed_match(self, mock_fetch):
        self.assertTrue(is_allowed("TorchedHat/pytorch-redhat-ci", "http://x"))

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_is_allowed_case_insensitive(self, mock_fetch):
        self.assertTrue(is_allowed("torchedhat/pytorch-redhat-ci", "http://x"))

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_is_not_allowed(self, mock_fetch):
        self.assertFalse(is_allowed("evil/repo", "http://x"))

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_cache_reuse(self, mock_fetch):
        is_allowed("foo/bar", "http://x")
        is_allowed("foo/bar", "http://x")
        mock_fetch.assert_called_once()

    @patch("allowlist._fetch_allowlist_yaml", return_value="not_a_dict: true")
    def test_bad_yaml_format(self, mock_fetch):
        self.assertFalse(is_allowed("foo/bar", "http://x"))


if __name__ == "__main__":
    unittest.main()
