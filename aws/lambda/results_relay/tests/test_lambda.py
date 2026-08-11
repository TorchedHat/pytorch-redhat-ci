import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ALLOWLIST_URL", "https://example.com/allowlist.yml")

from lambda_function import lambda_handler


def _make_event(body=None, method="POST", token="Bearer fake-token"):
    event = {
        "requestContext": {
            "http": {"method": method, "path": "/results"},
        },
        "headers": {"authorization": token},
        "body": json.dumps(body) if body else "",
    }
    return event


VALID_PAYLOAD = {
    "status": "completed",
    "conclusion": "success",
    "delivery_id": "abc123",
    "event_type": "external",
    "job_name": "test-job",
}


class TestLambdaHandler(unittest.TestCase):
    def test_wrong_method(self):
        event = _make_event(method="GET")
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 405)

    def test_missing_bearer(self):
        event = _make_event(token="")
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)

    @patch("lambda_function._verify_oidc_token", side_effect=Exception("bad"))
    def test_invalid_token(self, _):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 401)

    @patch("lambda_function._verify_oidc_token", return_value={"repository": "evil/repo"})
    @patch("lambda_function.is_allowed", return_value=False)
    def test_repo_not_allowed(self, *_):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)

    @patch("lambda_function._verify_oidc_token", return_value={})
    def test_no_repo_claim(self, _):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)

    @patch("lambda_function._dispatch_to_receiver")
    @patch("lambda_function._verify_oidc_token", return_value={"repository": "TorchedHat/pytorch-redhat-ci"})
    @patch("lambda_function.is_allowed", return_value=True)
    def test_valid_request(self, mock_allowed, mock_oidc, mock_dispatch):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["message"], "Result received and dispatched")
        mock_dispatch.assert_called_once()

    @patch("lambda_function._dispatch_to_receiver")
    @patch("lambda_function._verify_oidc_token", return_value={"repository": "TorchedHat/pytorch-redhat-ci"})
    @patch("lambda_function.is_allowed", return_value=True)
    def test_missing_required_fields(self, mock_allowed, mock_oidc, mock_dispatch):
        event = _make_event(body={"foo": "bar"})
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)
        mock_dispatch.assert_not_called()

    def test_invalid_json_body(self):
        event = _make_event()
        event["body"] = "not-json"
        with patch("lambda_function._verify_oidc_token", return_value={"repository": "ok/repo"}):
            with patch("lambda_function.is_allowed", return_value=True):
                resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 400)


class TestDispatch(unittest.TestCase):
    @patch("lambda_function.http_requests.post")
    @patch("lambda_function.get_config")
    def test_dispatch_sends_request(self, mock_config, mock_post):
        mock_config.return_value = MagicMock(
            github_token="ghp_test",
            dispatch_repo="TorchedHat/pytorch-redhat-ci",
        )
        mock_post.return_value = MagicMock(status_code=204)

        from lambda_function import _dispatch_to_receiver
        _dispatch_to_receiver(VALID_PAYLOAD, "subinz1/CRCR")

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("dispatches", call_args[0][0])
        sent = call_args[1]["json"]
        self.assertEqual(sent["event_type"], "external-ci-result")
        self.assertEqual(sent["client_payload"]["source_repo"], "subinz1/CRCR")

    @patch("lambda_function.get_config")
    def test_dispatch_skips_without_token(self, mock_config):
        mock_config.return_value = MagicMock(github_token="")
        from lambda_function import _dispatch_to_receiver
        _dispatch_to_receiver(VALID_PAYLOAD, "subinz1/CRCR")


if __name__ == "__main__":
    unittest.main()
