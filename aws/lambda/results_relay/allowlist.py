import time

import requests
import yaml


_cached_repos: set[str] | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 900  # 15 minutes


def _fetch_allowlist_yaml(url: str) -> str:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text


def _load_allowed_repos(url: str) -> set[str]:
    global _cached_repos, _cache_ts
    now = time.time()
    if _cached_repos is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cached_repos

    raw = _fetch_allowlist_yaml(url)
    data = yaml.safe_load(raw)
    repos = set()
    if isinstance(data, dict):
        for entry in data.get("allowed_repos", []):
            if isinstance(entry, str):
                repos.add(entry.lower())
    _cached_repos = repos
    _cache_ts = now
    return repos


def is_allowed(repo: str, url: str) -> bool:
    allowed = _load_allowed_repos(url)
    return repo.lower() in allowed


def clear_cache() -> None:
    global _cached_repos, _cache_ts
    _cached_repos = None
    _cache_ts = 0.0
