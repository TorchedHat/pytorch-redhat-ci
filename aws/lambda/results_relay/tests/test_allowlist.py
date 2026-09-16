import unittest
from unittest.mock import patch

from allowlist import clear_cache, is_allowed, should_forward_to_hud


SAMPLE_YAML = """
allowed_repos:
  - repo: TorchedHat/pytorch-redhat-ci
    forward_to_hud: true
  - repo: subinz1/CRCR
    forward_to_hud: false
  - torch-spyre/torch-spyre
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
    def test_forwarding_enabled_for_repo(self, mock_fetch):
        self.assertTrue(
            should_forward_to_hud("TorchedHat/pytorch-redhat-ci", "http://x")
        )

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_forwarding_disabled_for_testing_and_legacy_repos(self, mock_fetch):
        self.assertFalse(should_forward_to_hud("subinz1/CRCR", "http://x"))
        self.assertFalse(should_forward_to_hud("torch-spyre/torch-spyre", "http://x"))

    @patch("allowlist._fetch_allowlist_yaml", return_value=SAMPLE_YAML)
    def test_cache_reuse(self, mock_fetch):
        is_allowed("foo/bar", "http://x")
        should_forward_to_hud("foo/bar", "http://x")
        mock_fetch.assert_called_once()

    @patch("allowlist._fetch_allowlist_yaml", return_value="not_a_dict: true")
    def test_bad_yaml_format(self, mock_fetch):
        self.assertFalse(is_allowed("foo/bar", "http://x"))


if __name__ == "__main__":
    unittest.main()
