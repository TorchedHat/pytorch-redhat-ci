import json
import logging

import jwt
import requests as http_requests
from jwt import PyJWKClient

from allowlist import is_allowed
from config import GITHUB_ISSUER, GITHUB_JWKS_URI, get_config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(GITHUB_JWKS_URI)
    return _jwks_client


def _parse_event(event: dict) -> tuple[str, str, dict, str]:
    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path = event.get("requestContext", {}).get("http", {}).get("path", "")
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body", "")
    return method, path, headers, body


def _verify_oidc_token(token: str, audience: str) -> dict:
    client = _get_jwks_client()
    signing_key = client.get_signing_key_from_jwt(token)
    decoded = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=GITHUB_ISSUER,
    )
    return decoded


def _dispatch_to_receiver(payload: dict, source_repo: str) -> None:
    config = get_config()
    if not config.github_token:
        logger.warning("GITHUB_TOKEN not set — skipping repository_dispatch")
        return

    dispatch_url = (
        f"https://api.github.com/repos/{config.dispatch_repo}/dispatches"
    )
    dispatch_payload = {
        "event_type": "external-ci-result",
        "client_payload": {
            "source_repo": source_repo,
            **payload,
        },
    }

    resp = http_requests.post(
        dispatch_url,
        json=dispatch_payload,
        headers={
            "Authorization": f"token {config.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )
    if resp.status_code == 204:
        logger.info("repository_dispatch sent to %s", config.dispatch_repo)
    else:
        logger.error(
            "repository_dispatch failed: %d %s", resp.status_code, resp.text
        )


def _json_response(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event: dict, context: object) -> dict:
    method, path, headers, body = _parse_event(event)
    logger.info("Request: %s %s", method, path)

    if method != "POST":
        return _json_response(405, {"error": "Method not allowed"})

    auth_header = headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return _json_response(401, {"error": "Missing bearer token"})

    token = auth_header[len("Bearer "):]
    config = get_config()

    try:
        claims = _verify_oidc_token(token, config.audience)
    except Exception as e:
        logger.error("OIDC verification failed: %s", e)
        return _json_response(401, {"error": "Invalid authorization token"})

    source_repo = claims.get("repository", "")
    if not source_repo:
        return _json_response(403, {"error": "No repository claim in token"})

    if not is_allowed(source_repo, config.allowlist_url):
        logger.warning("Repo not in allowlist: %s", source_repo)
        return _json_response(403, {"error": "Repository not authorized"})

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return _json_response(400, {"error": "Invalid JSON body"})

    required_fields = ["status", "conclusion"]
    missing = [f for f in required_fields if f not in payload]
    if missing:
        return _json_response(
            400, {"error": f"Missing required fields: {missing}"}
        )

    logger.info(
        "Validated result from %s: status=%s conclusion=%s",
        source_repo, payload.get("status"), payload.get("conclusion"),
    )

    _dispatch_to_receiver(payload, source_repo)

    return _json_response(200, {
        "message": "Result received and dispatched",
        "source_repo": source_repo,
    })
