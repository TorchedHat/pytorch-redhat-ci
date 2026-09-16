import time

import requests
import yaml


_cached_policies: dict[str, bool] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 900  # 15 minutes


def _fetch_allowlist_yaml(url: str) -> str:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text


def _load_repo_policies(url: str) -> dict[str, bool]:
    global _cached_policies, _cache_ts
    now = time.time()
    if _cached_policies is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_policies

    raw = _fetch_allowlist_yaml(url)
    data = yaml.safe_load(raw)
    policies = {}
    if isinstance(data, dict):
        for entry in data.get("allowed_repos", []):
            if isinstance(entry, str):
                policies[entry.lower()] = False
            elif isinstance(entry, dict):
                repo = entry.get("repo")
                if isinstance(repo, str):
                    policies[repo.lower()] = entry.get("forward_to_hud") is True
    _cached_policies = policies
    _cache_ts = now
    return policies


def is_allowed(repo: str, url: str) -> bool:
    return repo.lower() in _load_repo_policies(url)


def should_forward_to_hud(repo: str, url: str) -> bool:
    return _load_repo_policies(url).get(repo.lower(), False)


def clear_cache() -> None:
    global _cached_policies, _cache_ts
    _cached_policies = None
    _cache_ts = 0.0
