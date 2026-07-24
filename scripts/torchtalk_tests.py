#!/usr/bin/env python3
"""
Structural test determination via C++ call graph analysis.

Uses C++ call graph and binding analysis to find tests affected
by changes between two commits. Works by:
  1. Getting changed files via git diff
  2. Extracting C++ symbols from changed files
  3. Walking the call graph to find all callers
  4. Mapping callers to Python API bindings
  5. Resolving bindings to test files/classes

Outputs test commands compatible with run_test.py, one per line.

Usage:
    python torchtalk_tests.py OLD_SHA NEW_SHA --pytorch-dir /pytorch
    python torchtalk_tests.py OLD_SHA NEW_SHA --pytorch-dir /pytorch --category cpu
    python torchtalk_tests.py OLD_SHA NEW_SHA --pytorch-dir /pytorch --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional


CATEGORIES = ("cpu", "inductor", "sgpu", "mgpu")

CATEGORY_RULES: list[tuple[str, str]] = [
    ("test/distributed/", "mgpu"),
    ("test/inductor/", "inductor"),
    ("test/dynamo/", "inductor"),
    ("test/export/", "inductor"),
    ("test/functorch/", "inductor"),
    ("test/test_cuda", "sgpu"),
]


def classify_test(test_file: str) -> str:
    for prefix, cat in CATEGORY_RULES:
        if test_file.startswith(prefix):
            return cat
    return "cpu"


def _test_name(test_file: str) -> str:
    """Convert test file path to run_test.py format."""
    name = test_file.replace("test/", "", 1)
    if name.endswith(".py"):
        name = name[:-3]
    return name


def get_changed_files(pytorch_dir: str, old_sha: str, new_sha: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", old_sha, new_sha],
        capture_output=True,
        text=True,
        check=True,
        cwd=pytorch_dir,
    )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def get_cpp_changed_files(changed_files: list[str]) -> list[str]:
    """Filter to only C++/CUDA files for structural analysis."""
    cpp_exts = (".cpp", ".cc", ".cxx", ".cu", ".cuh", ".h", ".hpp")
    return [f for f in changed_files if any(f.endswith(ext) for ext in cpp_exts)]


def run_torchtalk_affected(
    pytorch_dir: str, cpp_files: list[str], depth: int = 3
) -> list[dict]:
    """Run structural affected-test analysis on changed C++ files.

    Depth can be overridden via STRUCTURAL_ANALYSIS_DEPTH environment variable.
    Returns a list of {"file": str, "included_classes": list[str]} dicts.
    """
    import os

    env_depth = os.environ.get("STRUCTURAL_ANALYSIS_DEPTH")
    if env_depth and env_depth.isdigit():
        depth = int(env_depth)

    try:
        from torchtalk.indexer import build_index, _state
        from torchtalk.analysis.affected import affected_tests, symbols_in_file
    except ImportError as e:
        print(
            f"Structural analyzer not installed ({e}), skipping",
            file=sys.stderr,
        )
        return []
    except Exception as e:
        print(
            f"Structural analyzer import failed ({e}), skipping",
            file=sys.stderr,
        )
        return []

    build_index(pytorch_dir, wait_for_cpp=True)

    if _state.cpp_extractor is None:
        print("C++ call graph not available, skipping", file=sys.stderr)
        return []

    all_funcs: list[str] = []
    for cpp_file in cpp_files:
        result = symbols_in_file(cpp_file, _state.cpp_extractor)
        for func_info in result.get("functions", []):
            all_funcs.append(func_info["function"])

    if not all_funcs:
        print(
            f"No C++ symbols found in {len(cpp_files)} changed files",
            file=sys.stderr,
        )
        return []

    print(
        f"Analyzing {len(all_funcs)} C++ symbols from "
        f"{len(cpp_files)} files (depth={depth})",
        file=sys.stderr,
    )

    result = affected_tests(
        funcs=all_funcs,
        cpp_extractor=_state.cpp_extractor,
        by_cpp_name=_state.by_cpp_name,
        test_classes=_state.test_classes,
        test_files=_state.test_files,
        opinfo_registry=_state.opinfo_registry,
        opinfo_alias_map=_state.opinfo_alias_map,
        opinfo_test_files=_state.opinfo_test_files,
        test_attr_index=_state.test_attr_index,
        python_profiling=_state.python_profiling or None,
        decomp_alias_map=_state.decomp_alias_map or None,
        backward_to_forward=_state.backward_to_forward or None,
        native_functions=_state.native_functions or None,
        native_implementations=_state.native_implementations or None,
        kernel_impl_to_op=_state.kernel_impl_to_op or None,
        dispatch_to_op=_state.dispatch_to_op or None,
        bindings_by_file=_state.bindings_by_file or None,
        ops_by_file=_state.ops_by_file or None,
        symbol_to_file=_state.symbol_to_file or None,
        depth=depth,
    )

    print(
        f"Walked {result['callers_walked']} callers, "
        f"matched {len(result['bindings_matched'])} bindings, "
        f"found {len(result['python_apis'])} APIs -> "
        f"{len(result['test_runs'])} test files",
        file=sys.stderr,
    )

    return result.get("test_runs", [])


def test_runs_to_commands(
    test_runs: list[dict], category: Optional[str] = None
) -> list[str]:
    """Convert structural analysis test_runs output to run_test.py commands."""
    commands: list[str] = []
    seen: set[str] = set()

    for run in test_runs:
        test_file = run["file"]
        if not test_file.startswith("test/") or not test_file.endswith(".py"):
            continue

        cat = classify_test(test_file)
        if category and cat != category:
            continue

        name = _test_name(test_file)
        classes = run.get("included_classes", [])

        if classes:
            # Run specific test classes via -k filter
            filter_expr = " or ".join(classes[:10])
            key = f"{name}::{filter_expr}"
            if key not in seen:
                seen.add(key)
                commands.append(
                    f'python test/run_test.py -i {name} -k "{filter_expr}"'
                )
        else:
            # Run the whole file
            key = name
            if key not in seen:
                seen.add(key)
                commands.append(f"python test/run_test.py -i {name}")

    return commands


def main():
    parser = argparse.ArgumentParser(
        description="Structural test determination for PyTorch (C++ call graph).",
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
        help="Filter output to a specific test category",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Call graph walk depth (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (raw structural analysis result)",
    )
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="Output only run_test.py commands, one per line",
    )
    args = parser.parse_args()

    pytorch_dir = args.pytorch_dir
    if not Path(pytorch_dir).exists():
        print(f"Error: {pytorch_dir} does not exist", file=sys.stderr)
        sys.exit(1)

    changed_files = get_changed_files(pytorch_dir, args.old_sha, args.new_sha)
    if not changed_files:
        print("No files changed between commits", file=sys.stderr)
        sys.exit(0)

    cpp_files = get_cpp_changed_files(changed_files)
    if not cpp_files:
        print(
            f"No C++/CUDA files in {len(changed_files)} changed files, "
            "nothing for structural analysis",
            file=sys.stderr,
        )
        sys.exit(0)

    print(
        f"Found {len(cpp_files)} C++/CUDA files out of "
        f"{len(changed_files)} total changed files",
        file=sys.stderr,
    )

    test_runs = run_torchtalk_affected(pytorch_dir, cpp_files, depth=args.depth)

    if args.json:
        print(json.dumps(test_runs, indent=2))
        return

    commands = test_runs_to_commands(test_runs, category=args.category)

    if args.commands_only:
        for cmd in commands:
            print(cmd)
    else:
        print(f"\nStructural Analysis Results:")
        print(f"  Changed C++ files: {len(cpp_files)}")
        print(f"  Test files found:  {len(test_runs)}")
        print(f"  Commands generated: {len(commands)}")
        if args.category:
            print(f"  Category filter:   {args.category}")
        print()
        for cmd in commands:
            print(f"  {cmd}")


if __name__ == "__main__":
    main()
