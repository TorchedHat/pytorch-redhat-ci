#!/usr/bin/env python3
"""
Unified test determination: merges results from targeted_tests.py and TorchTalk.

Takes the UNION of both tools' outputs to maximize test coverage:
  - targeted_tests.py: fast file-path heuristic (good for Python changes)
  - torchtalk_tests.py: structural call graph (good for C++/CUDA changes)

Deduplicates, categorizes, and outputs final test commands.

Usage:
    python merge_test_results.py OLD_SHA NEW_SHA --pytorch-dir /pytorch
    python merge_test_results.py OLD_SHA NEW_SHA --pytorch-dir /pytorch --category cpu
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


CATEGORIES = ("cpu", "inductor", "sgpu", "mgpu")


def run_targeted_tests(
    old_sha: str, new_sha: str, pytorch_dir: str, category: Optional[str]
) -> list[str]:
    """Run targeted_tests.py and capture its output."""
    script = Path(__file__).parent / "targeted_tests.py"
    if not script.exists():
        print("targeted_tests.py not found, skipping heuristic pass", file=sys.stderr)
        return []

    cmd = [
        sys.executable,
        str(script),
        old_sha,
        new_sha,
        "--pytorch-dir",
        pytorch_dir,
        "--commands-only",
    ]
    if category:
        cmd.extend(["--category", category])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"targeted_tests.py exited with code {result.returncode}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        return []

    return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]


def run_torchtalk_tests(
    old_sha: str, new_sha: str, pytorch_dir: str, category: Optional[str]
) -> list[str]:
    """Run torchtalk_tests.py and capture its output.

    Returns empty list if TorchTalk is not available (graceful degradation).
    """
    script = Path(__file__).parent / "torchtalk_tests.py"
    if not script.exists():
        print("torchtalk_tests.py not found, skipping structural pass", file=sys.stderr)
        return []

    # Quick check: is torchtalk importable?
    check = subprocess.run(
        [sys.executable, "-c", "import torchtalk"],
        capture_output=True,
    )
    if check.returncode != 0:
        print(
            "torchtalk package not installed, skipping structural pass",
            file=sys.stderr,
        )
        return []

    cmd = [
        sys.executable,
        str(script),
        old_sha,
        new_sha,
        "--pytorch-dir",
        pytorch_dir,
        "--commands-only",
    ]
    if category:
        cmd.extend(["--category", category])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"torchtalk_tests.py exited with code {result.returncode}",
            file=sys.stderr,
        )
        if result.stderr:
            print(f"  stderr: {result.stderr.strip()}", file=sys.stderr)
        return []

    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            if line.strip():
                print(f"  [torchtalk] {line.strip()}", file=sys.stderr)

    return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]


def merge_commands(list_a: list[str], list_b: list[str]) -> list[str]:
    """Merge two command lists, deduplicating while preserving order."""
    seen: set[str] = set()
    merged: list[str] = []
    for cmd in list_a + list_b:
        if cmd not in seen:
            seen.add(cmd)
            merged.append(cmd)
    return merged


def main():
    parser = argparse.ArgumentParser(
        description="Unified test determination: targeted_tests + TorchTalk union.",
    )
    parser.add_argument("old_sha", help="Old commit SHA (base)")
    parser.add_argument("new_sha", help="New commit SHA (head)")
    parser.add_argument(
        "--pytorch-dir",
        required=True,
        help="Path to pytorch/pytorch checkout",
    )
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        help="Filter to a specific test category",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Output only commands, one per line",
    )
    args = parser.parse_args()

    if not Path(args.pytorch_dir).exists():
        print(f"Error: {args.pytorch_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    print("=== Heuristic pass (targeted_tests.py) ===", file=sys.stderr)
    heuristic = run_targeted_tests(
        args.old_sha, args.new_sha, args.pytorch_dir, args.category
    )
    print(f"  Found {len(heuristic)} commands", file=sys.stderr)

    print("=== Structural pass (TorchTalk) ===", file=sys.stderr)
    structural = run_torchtalk_tests(
        args.old_sha, args.new_sha, args.pytorch_dir, args.category
    )
    print(f"  Found {len(structural)} commands", file=sys.stderr)

    merged = merge_commands(heuristic, structural)
    overlap = len(heuristic) + len(structural) - len(merged)

    print(f"=== Merged: {len(merged)} unique commands ===", file=sys.stderr)
    if overlap > 0:
        print(f"  ({overlap} duplicates removed)", file=sys.stderr)

    if args.commands_only:
        for cmd in merged:
            print(cmd)
    else:
        print(f"\nUnified Test Determination Results:")
        print(f"  Heuristic (targeted_tests.py): {len(heuristic)} commands")
        print(f"  Structural (TorchTalk):        {len(structural)} commands")
        print(f"  Merged (union):                {len(merged)} commands")
        if overlap > 0:
            print(f"  Overlap (deduped):             {overlap}")
        if args.category:
            print(f"  Category filter:               {args.category}")
        print()
        for cmd in merged:
            print(f"  {cmd}")


if __name__ == "__main__":
    main()
