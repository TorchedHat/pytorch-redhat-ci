import os
from dataclasses import dataclass


GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_JWKS_URI = (
    "https://token.actions.githubusercontent.com/.well-known/jwks"
)


@dataclass(frozen=True)
class RelayConfig:
    allowlist_url: str
    audience: str
    dispatch_repo: str
    github_token: str

    @classmethod
    def from_env(cls) -> "RelayConfig":
        allowlist_url = os.environ.get("ALLOWLIST_URL", "")
        if not allowlist_url:
            raise RuntimeError("ALLOWLIST_URL environment variable is required")
        return cls(
            allowlist_url=allowlist_url,
            audience=os.environ.get("AUDIENCE", "rhel-results-relay"),
            dispatch_repo=os.environ.get("DISPATCH_REPO", "TorchedHat/pytorch-redhat-ci"),
            github_token=os.environ.get("GITHUB_TOKEN", ""),
        )


_config: RelayConfig | None = None


def get_config() -> RelayConfig:
    global _config
    if _config is None:
        _config = RelayConfig.from_env()
    return _config
