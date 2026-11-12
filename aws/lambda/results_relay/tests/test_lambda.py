import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ALLOWLIST_URL", "https://example.com/allowlist.yml")

from allowlist import AllowlistUnavailableError
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

    def test_allowlist_unavailable_returns_service_unavailable(self):
        with patch(
            "lambda_function._verify_oidc_token",
            return_value={"repository": "TorchedHat/pytorch-redhat-ci"},
        ), patch(
            "lambda_function.is_allowed",
            side_effect=AllowlistUnavailableError("unavailable"),
        ), patch("lambda_function._dispatch_to_receiver") as mock_dispatch:
            resp = lambda_handler(_make_event(body=VALID_PAYLOAD), None)

        self.assertEqual(resp["statusCode"], 503)
        self.assertEqual(
            json.loads(resp["body"]),
            {"error": "Authorization service unavailable; retry later"},
        )
        mock_dispatch.assert_not_called()

    def test_allowlist_failure_while_reading_policy_returns_service_unavailable(self):
        with patch(
            "lambda_function._verify_oidc_token",
            return_value={"repository": "TorchedHat/pytorch-redhat-ci"},
        ), patch("lambda_function.is_allowed", return_value=True), patch(
            "lambda_function.should_forward_to_hud",
            side_effect=AllowlistUnavailableError("unavailable"),
        ), patch("lambda_function._dispatch_to_receiver") as mock_dispatch:
            resp = lambda_handler(_make_event(body=VALID_PAYLOAD), None)

        self.assertEqual(resp["statusCode"], 503)
        mock_dispatch.assert_not_called()

    @patch("lambda_function._verify_oidc_token", return_value={})
    def test_no_repo_claim(self, _):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 403)

    @patch("lambda_function._dispatch_to_receiver", return_value=True)
    @patch("lambda_function.should_forward_to_hud", return_value=False)
    @patch("lambda_function._verify_oidc_token", return_value={"repository": "TorchedHat/pytorch-redhat-ci"})
    @patch("lambda_function.is_allowed", return_value=True)
    def test_valid_request(
        self, mock_allowed, mock_oidc, mock_forward, mock_dispatch
    ):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["message"], "Result received and dispatched")
        self.assertFalse(body["forward_to_hud"])
        mock_dispatch.assert_called_once_with(
            VALID_PAYLOAD, "TorchedHat/pytorch-redhat-ci", False
        )

    @patch("lambda_function._dispatch_to_receiver", return_value=True)
    @patch("lambda_function.should_forward_to_hud", return_value=True)
    @patch(
        "lambda_function._verify_oidc_token",
        return_value={"repository": "TorchedHat/pytorch-redhat-ci"},
    )
    @patch("lambda_function.is_allowed", return_value=True)
    def test_valid_request_with_hud_forwarding(
        self, mock_allowed, mock_oidc, mock_forward, mock_dispatch
    ):
        event = _make_event(body=VALID_PAYLOAD)
        resp = lambda_handler(event, None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(json.loads(resp["body"])["forward_to_hud"])
        mock_dispatch.assert_called_once_with(
            VALID_PAYLOAD, "TorchedHat/pytorch-redhat-ci", True
        )

    @patch("lambda_function._dispatch_to_receiver", return_value=False)
    @patch("lambda_function.should_forward_to_hud", return_value=False)
    @patch(
        "lambda_function._verify_oidc_token",
        return_value={"repository": "TorchedHat/pytorch-redhat-ci"},
    )
    @patch("lambda_function.is_allowed", return_value=True)
    def test_dispatch_failure_returns_bad_gateway(
        self, mock_allowed, mock_oidc, mock_forward, mock_dispatch
    ):
        resp = lambda_handler(_make_event(body=VALID_PAYLOAD), None)
        self.assertEqual(resp["statusCode"], 502)
        self.assertEqual(
            json.loads(resp["body"]), {"error": "Failed to dispatch result"}
        )

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
        self.assertTrue(_dispatch_to_receiver(VALID_PAYLOAD, "subinz1/CRCR", False))

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        self.assertIn("dispatches", call_args[0][0])
        sent = call_args[1]["json"]
        self.assertEqual(sent["event_type"], "external-ci-result")
        self.assertEqual(len(sent["client_payload"]), 2)
        self.assertEqual(sent["client_payload"]["result"], VALID_PAYLOAD)
        self.assertEqual(
            sent["client_payload"]["relay"]["source_repo"], "subinz1/CRCR"
        )
        self.assertFalse(sent["client_payload"]["relay"]["forward_to_hud"])

    @patch("lambda_function.http_requests.post")
    @patch("lambda_function.get_config")
    def test_dispatch_preserves_trusted_policy_fields(self, mock_config, mock_post):
        mock_config.return_value = MagicMock(
            github_token="ghp_test",
            dispatch_repo="TorchedHat/pytorch-redhat-ci",
        )
        mock_post.return_value = MagicMock(status_code=204)

        from lambda_function import _dispatch_to_receiver

        payload = {
            **VALID_PAYLOAD,
            "source_repo": "pytorch/pytorch",
            "forward_to_hud": True,
        }
        self.assertTrue(_dispatch_to_receiver(payload, "subinz1/CRCR", False))

        sent = mock_post.call_args[1]["json"]
        self.assertEqual(sent["client_payload"]["result"], payload)
        self.assertEqual(
            sent["client_payload"]["relay"]["source_repo"], "subinz1/CRCR"
        )
        self.assertFalse(sent["client_payload"]["relay"]["forward_to_hud"])

    @patch("lambda_function.http_requests.post")
    @patch("lambda_function.get_config")
    def test_dispatch_rejection_returns_false(self, mock_config, mock_post):
        mock_config.return_value = MagicMock(
            github_token="ghp_test",
            dispatch_repo="TorchedHat/pytorch-redhat-ci",
        )
        mock_post.return_value = MagicMock(status_code=422, text="Invalid request")

        from lambda_function import _dispatch_to_receiver

        self.assertFalse(_dispatch_to_receiver(VALID_PAYLOAD, "subinz1/CRCR", False))

    @patch("lambda_function.get_config")
    def test_dispatch_skips_without_token(self, mock_config):
        mock_config.return_value = MagicMock(github_token="")
        from lambda_function import _dispatch_to_receiver
        self.assertFalse(_dispatch_to_receiver(VALID_PAYLOAD, "subinz1/CRCR", False))


if __name__ == "__main__":
    unittest.main()
