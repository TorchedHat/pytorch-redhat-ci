#!/usr/bin/env python3
"""
Diff-based targeted test selection for PyTorch.

Given two commits (old and new), fetches the diff from pytorch/pytorch and
maps changed files to the most specific test files/filters at the submodule
level. Outputs a list of test commands that cover exactly what changed.

Usage:
    python targeted_tests.py OLD_SHA NEW_SHA
    python targeted_tests.py OLD_SHA NEW_SHA --pytorch-dir /path/to/pytorch
    python targeted_tests.py OLD_SHA NEW_SHA --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


CATEGORIES = ("cpu", "inductor", "sgpu", "mgpu")

# Test file path prefix -> category
CATEGORY_RULES: list[tuple[str, str]] = [
    ("test/distributed/", "mgpu"),
    ("test/inductor/", "inductor"),
    ("test/dynamo/", "inductor"),
    ("test/export/", "inductor"),
    ("test/functorch/", "inductor"),
    ("test/test_cuda", "sgpu"),
]


def classify_test(test_file: str) -> str:
    """Classify a test file into cpu/inductor/sgpu/mgpu."""
    for prefix, cat in CATEGORY_RULES:
        if test_file.startswith(prefix):
            return cat
    return "cpu"


def _test_name(test_file: str) -> str:
    """Convert test file path to run_test.py name (e.g. test/test_cuda.py -> test_cuda)."""
    name = test_file.replace("test/", "", 1)
    if name.endswith(".py"):
        name = name[:-3]
    return name


@dataclass
class TestTarget:
    """A test command to run."""
    file: str
    filter: str | None = None
    reason: str = ""
    estimated_minutes: float = 5.0

    @property
    def category(self) -> str:
        return classify_test(self.file)

    @property
    def command(self) -> str:
        name = _test_name(self.file)
        if self.filter:
            return f'python test/run_test.py -i {name} -k "{self.filter}"'
        return f"python test/run_test.py -i {name}"


# ---------------------------------------------------------------------------
# Submodule → test mapping
# ---------------------------------------------------------------------------

# Each entry: (source_pattern, test_file, keyword_filter, estimated_minutes)
# source_pattern is matched against the changed file path.
# keyword_filter is used with pytest -k when the test file is large.

SUBMODULE_MAP: list[tuple[str, str, str | None, float]] = [
    # torch/nn/modules/ → specific test files + test_nn.py filtered
    ("torch/nn/modules/conv.py", "test/nn/test_convolution.py", None, 5),
    ("torch/nn/modules/conv.py", "test/test_nn.py", "conv", 3),
    ("torch/nn/modules/dropout.py", "test/nn/test_dropout.py", None, 2),
    ("torch/nn/modules/dropout.py", "test/test_nn.py", "dropout", 2),
    ("torch/nn/modules/pooling.py", "test/nn/test_pooling.py", None, 5),
    ("torch/nn/modules/pooling.py", "test/test_nn.py", "pool or MaxPool or AvgPool or AdaptiveMaxPool or LPPool or FractionalMaxPool", 3),
    ("torch/nn/modules/lazy.py", "test/nn/test_lazy_modules.py", None, 2),
    ("torch/nn/modules/module.py", "test/nn/test_module_hooks.py", None, 3),
    ("torch/nn/modules/module.py", "test/nn/test_load_state_dict.py", None, 3),
    ("torch/nn/modules/module.py", "test/test_nn.py", "module or register_buffer or register_parameter or named_modules or named_children or extra_state", 5),
    ("torch/nn/modules/rnn.py", "test/test_nn.py", "rnn or RNN or lstm or LSTM or gru or GRU or projections_lstm", 8),
    ("torch/nn/modules/batchnorm.py", "test/test_nn.py", "batchnorm or BatchNorm or sync_batchnorm", 5),
    ("torch/nn/modules/loss.py", "test/test_nn.py", "loss or bce or cross_entropy or mse or nll or ctc or CTCLoss or triplet or kl_div or margin or huber or gaussian_nll or poisson or cosine_embedding", 10),
    ("torch/nn/modules/activation.py", "test/test_nn.py", "relu or elu or selu or gelu or sigmoid or softmax or logsoftmax or tanh or hardshrink or softshrink or hardtanh or LeakyReLU or PReLU or Mish or SiLU or Threshold or hardswish or Softmin or Softmax2d", 8),
    ("torch/nn/modules/normalization.py", "test/test_nn.py", "layer_norm or LayerNorm or group_norm or GroupNorm or instance_norm or InstanceNorm or local_response_norm", 5),
    ("torch/nn/modules/transformer.py", "test/nn/test_multihead_attention.py", None, 5),
    ("torch/nn/modules/transformer.py", "test/test_nn.py", "transformer or Transformer or multihead", 5),
    ("torch/nn/modules/container.py", "test/test_nn.py", "Sequential or ModuleList or ModuleDict or ParameterList or ParameterDict", 5),
    ("torch/nn/modules/linear.py", "test/test_nn.py", "linear or bilinear or Linear or Bilinear", 3),
    ("torch/nn/modules/padding.py", "test/test_nn.py", "pad or ReflectionPad or ReplicationPad or ConstantPad or ZeroPad or CircularPad", 3),
    ("torch/nn/modules/upsampling.py", "test/test_nn.py", "upsample or Upsample or interpolate", 3),
    ("torch/nn/modules/sparse.py", "test/nn/test_embedding.py", None, 3),
    ("torch/nn/modules/sparse.py", "test/test_nn.py", "embedding or Embedding or EmbeddingBag or sparse", 3),
    ("torch/nn/modules/flatten.py", "test/test_nn.py", "flatten or Flatten or Unflatten", 2),
    ("torch/nn/modules/pixelshuffle.py", "test/test_nn.py", "pixel_shuffle or PixelShuffle or PixelUnshuffle", 2),
    ("torch/nn/modules/fold.py", "test/test_nn.py", "fold or unfold or Fold or Unfold", 2),
    ("torch/nn/modules/distance.py", "test/test_nn.py", "pdist or pairwise or cosine_similarity or PairwiseDistance", 2),
    ("torch/nn/modules/channelshuffle.py", "test/test_nn.py", "channel_shuffle or ChannelShuffle", 1),
    ("torch/nn/modules/instancenorm.py", "test/test_nn.py", "instance_norm or InstanceNorm", 3),
    ("torch/nn/modules/adaptive.py", "test/test_nn.py", "adaptive or AdaptiveLogSoftmax", 2),

    # torch/nn/init.py
    ("torch/nn/init.py", "test/nn/test_init.py", None, 3),

    # torch/nn/utils/
    ("torch/nn/utils/parametrize.py", "test/nn/test_parametrization.py", None, 3),
    ("torch/nn/utils/prune.py", "test/nn/test_pruning.py", None, 3),
    ("torch/nn/utils/rnn.py", "test/nn/test_packed_sequence.py", None, 2),
    ("torch/nn/utils/spectral_norm.py", "test/test_nn.py", "spectral_norm", 2),
    ("torch/nn/utils/weight_norm.py", "test/test_nn.py", "weight_norm", 2),

    # torch/nn/attention/
    ("torch/nn/attention/", "test/nn/test_multihead_attention.py", None, 5),

    # torch/autograd/
    ("torch/autograd/", "test/test_autograd.py", None, 30),
    ("torch/autograd/profiler", "test/test_autograd.py", "profiler", 10),
    ("torch/autograd/gradcheck.py", "test/test_autograd.py", "gradcheck", 5),

    # torch/optim/
    ("torch/optim/adam.py", "test/optim/test_optim.py", "Adam", 5),
    ("torch/optim/sgd.py", "test/optim/test_optim.py", "SGD", 5),
    ("torch/optim/adamw.py", "test/optim/test_optim.py", "AdamW", 5),
    ("torch/optim/lr_scheduler.py", "test/optim/test_lrscheduler.py", None, 5),
    ("torch/optim/", "test/optim/test_optim.py", None, 15),

    # torch/_inductor/
    ("torch/_inductor/", "test/inductor/test_torchinductor.py", None, 30),
    ("torch/_inductor/codegen/", "test/inductor/test_torchinductor.py", "codegen", 15),
    ("torch/_inductor/fx_passes/", "test/inductor/test_fx_fusion.py", None, 10),
    ("torch/_inductor/scheduler.py", "test/inductor/test_torchinductor.py", "scheduler", 10),
    ("torch/_inductor/compile_fx.py", "test/inductor/test_torchinductor.py", "compile", 10),

    # torch/_dynamo/
    ("torch/_dynamo/", "test/dynamo/test_misc.py", None, 15),
    ("torch/_dynamo/", "test/dynamo/test_repros.py", None, 10),
    ("torch/_dynamo/guards.py", "test/dynamo/test_misc.py", "guard", 5),
    ("torch/_dynamo/symbolic_convert.py", "test/dynamo/test_misc.py", None, 15),

    # torch/_export/
    ("torch/_export/", "test/export/test_export.py", None, 15),
    ("torch/export/", "test/export/test_export.py", None, 15),

    # torch/_functorch/
    ("torch/_functorch/", "test/functorch/test_vmap.py", None, 15),
    ("torch/_functorch/", "test/functorch/test_eager_transforms.py", None, 10),

    # torch/distributed/
    ("torch/distributed/fsdp/", "test/distributed/fsdp/test_fsdp_core.py", None, 20),
    ("torch/distributed/_tensor/", "test/distributed/_tensor/test_dtensor.py", None, 15),
    ("torch/distributed/pipeline/", "test/distributed/test_c10d_common.py", None, 10),
    ("torch/distributed/", "test/distributed/test_c10d_common.py", None, 15),

    # torch/sparse/
    ("torch/sparse/", "test/test_sparse.py", None, 15),
    ("torch/sparse/", "test/test_sparse_csr.py", None, 10),

    # torch/linalg/
    ("torch/linalg/", "test/test_linalg.py", None, 20),

    # torch/fft/
    ("torch/fft/", "test/test_spectral_ops.py", None, 10),

    # Core tensor ops (aten/)
    ("aten/src/ATen/native/Linear.cpp", "test/test_nn.py", "linear or bilinear", 3),
    ("aten/src/ATen/native/Loss.cpp", "test/test_nn.py", "loss or nll or cross_entropy", 5),
    ("aten/src/ATen/native/Convolution.cpp", "test/nn/test_convolution.py", None, 5),
    ("aten/src/ATen/native/Pool", "test/nn/test_pooling.py", None, 5),
    ("aten/src/ATen/native/RNN.cpp", "test/test_nn.py", "rnn or RNN or lstm or LSTM", 5),
    ("aten/src/ATen/native/BatchNorm", "test/test_nn.py", "batchnorm or BatchNorm", 5),
    ("aten/src/ATen/native/Activation", "test/test_nn.py", "relu or elu or selu or gelu or sigmoid or softmax or tanh", 5),
    ("aten/src/ATen/native/Normalization", "test/test_nn.py", "layer_norm or group_norm or instance_norm", 5),
    ("aten/src/ATen/native/Embedding", "test/nn/test_embedding.py", None, 3),
    ("aten/src/ATen/native/UpSample", "test/test_nn.py", "upsample or interpolate", 3),
    ("aten/src/ATen/native/GridSample", "test/test_nn.py", "grid_sample", 3),
    ("aten/src/ATen/native/Dropout.cpp", "test/nn/test_dropout.py", None, 2),
    ("aten/src/ATen/native/Sorting.cpp", "test/test_sort_and_select.py", None, 5),
    ("aten/src/ATen/native/ReduceOps.cpp", "test/test_reductions.py", None, 10),
    ("aten/src/ATen/native/UnaryOps.cpp", "test/test_unary_ufuncs.py", None, 10),
    ("aten/src/ATen/native/BinaryOps.cpp", "test/test_binary_ufuncs.py", None, 10),
    ("aten/src/ATen/native/TensorShape.cpp", "test/test_torch.py", "reshape or view or permute or transpose or expand or contiguous", 5),
    ("aten/src/ATen/native/Copy.cpp", "test/test_torch.py", "copy", 3),
    ("aten/src/ATen/native/Fill.cpp", "test/test_torch.py", "fill or zero or ones", 3),
    ("aten/src/ATen/native/IndexingUtils.h", "test/test_indexing.py", None, 5),
    ("aten/src/ATen/native/Indexing.cpp", "test/test_indexing.py", None, 5),
    ("aten/src/ATen/native/SpectralOps.cpp", "test/test_spectral_ops.py", None, 5),
    ("aten/src/ATen/native/LinearAlgebra.cpp", "test/test_linalg.py", None, 10),
    ("aten/src/ATen/native/Scalar.cpp", "test/test_torch.py", "scalar", 2),

    # CUDA kernels
    ("aten/src/ATen/native/cuda/", "test/test_cuda.py", None, 15),

    # Core torch/ files
    ("torch/tensor.py", "test/test_torch.py", None, 30),
    ("torch/_C/", "test/test_torch.py", None, 30),
    ("torch/serialization.py", "test/test_serialization.py", None, 10),
    ("torch/jit/", "test/test_jit.py", None, 20),
    ("torch/onnx/", "test/onnx/test_onnx_opset.py", None, 15),
    ("torch/cuda/", "test/test_cuda.py", None, 15),
    ("torch/testing/", "test/test_testing.py", None, 5),
    ("torch/utils/data/", "test/test_dataloader.py", None, 10),
    ("torch/utils/checkpoint.py", "test/test_autograd.py", "checkpoint", 5),
    ("torch/profiler/", "test/profiler/test_profiler.py", None, 10),

    # Build / codegen — test_codegen lives under tools/test/ and is not
    # registered in run_test.py, so we skip it here.
]


# Files/patterns that don't need tests
SKIP_PATTERNS = [
    r"\.md$",
    r"\.rst$",
    r"\.txt$",
    r"LICENSE",
    r"\.gitignore",
    r"\.github/",
    r"docs/",
    r"benchmarks/",
    r"scripts/",
    r"\.circleci/",
    r"\.ci/",
    r"CODEOWNERS",
    r"\.flake8",
    r"mypy",
    r"\.pre-commit",
]


def should_skip(filepath: str) -> bool:
    return any(re.search(p, filepath) for p in SKIP_PATTERNS)


def get_changed_files(pytorch_dir: str, old_sha: str, new_sha: str) -> list[str]:
    """Get list of files changed between two commits."""
    result = subprocess.run(
        ["git", "diff", "--name-only", old_sha, new_sha],
        capture_output=True, text=True, check=True,
        cwd=pytorch_dir,
    )
    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    return files


def clone_or_fetch_pytorch(pytorch_dir: str | None, old_sha: str, new_sha: str) -> str:
    """Ensure we have a pytorch checkout with both commits available."""
    if pytorch_dir and Path(pytorch_dir).exists():
        subprocess.run(
            ["git", "fetch", "origin", old_sha, new_sha],
            cwd=pytorch_dir, capture_output=True, check=False,
        )
        return pytorch_dir

    tmpdir = tempfile.mkdtemp(prefix="pytorch-targeted-")
    print(f"Cloning pytorch/pytorch (shallow) into {tmpdir}...", file=sys.stderr)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout",
         "https://github.com/pytorch/pytorch.git", tmpdir],
        check=True,
    )
    subprocess.run(
        ["git", "fetch", "origin", old_sha, new_sha],
        cwd=tmpdir, check=True,
    )
    return tmpdir


def map_changes_to_tests(changed_files: list[str]) -> list[TestTarget]:
    """Map changed files to test targets using the submodule map."""
    targets: dict[str, TestTarget] = {}
    unmapped: list[str] = []

    for filepath in changed_files:
        if should_skip(filepath):
            continue

        matched = False
        for src_pattern, test_file, kw_filter, est_min in SUBMODULE_MAP:
            if filepath.startswith(src_pattern) or src_pattern in filepath:
                key = f"{test_file}::{kw_filter or '*'}"
                if key not in targets:
                    targets[key] = TestTarget(
                        file=test_file,
                        filter=kw_filter,
                        reason=filepath,
                        estimated_minutes=est_min,
                    )
                else:
                    targets[key].reason += f", {filepath}"
                matched = True

        if not matched:
            unmapped.append(filepath)

    return list(targets.values()), unmapped


def format_output(targets: list[TestTarget], unmapped: list[str],
                  changed_files: list[str], old_sha: str, new_sha: str,
                  as_json: bool = False) -> str:
    """Format the output."""
    if as_json:
        return json.dumps({
            "old_sha": old_sha,
            "new_sha": new_sha,
            "changed_files": changed_files,
            "targets": [
                {
                    "file": t.file,
                    "filter": t.filter,
                    "command": t.command,
                    "reason": t.reason,
                    "estimated_minutes": t.estimated_minutes,
                }
                for t in targets
            ],
            "unmapped_files": unmapped,
            "total_estimated_minutes": sum(t.estimated_minutes for t in targets),
        }, indent=2)

    lines = []
    lines.append(f"Diff: {old_sha[:10]}..{new_sha[:10]}")
    lines.append(f"Changed files: {len(changed_files)}")
    lines.append(f"Mapped to {len(targets)} test target(s)")
    lines.append("")

    total_est = sum(t.estimated_minutes for t in targets)
    lines.append(f"Estimated total time: ~{total_est:.0f} min")
    lines.append("")
    lines.append("=" * 72)
    lines.append("TEST COMMANDS")
    lines.append("=" * 72)

    for i, t in enumerate(targets, 1):
        lines.append("")
        lines.append(f"  [{i}] {t.command}")
        lines.append(f"      Reason: {t.reason}")
        lines.append(f"      Est: ~{t.estimated_minutes:.0f} min")

    if unmapped:
        lines.append("")
        lines.append("=" * 72)
        lines.append(f"UNMAPPED FILES ({len(unmapped)}) — may need manual inspection")
        lines.append("=" * 72)
        for f in unmapped:
            lines.append(f"  {f}")

    # Shell-ready commands
    lines.append("")
    lines.append("=" * 72)
    lines.append("COPY-PASTE COMMANDS")
    lines.append("=" * 72)
    lines.append("")
    for t in targets:
        lines.append(t.command)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Find targeted PyTorch tests for a commit range.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s abc1234 def5678
  %(prog)s abc1234 def5678 --pytorch-dir ~/pytorch
  %(prog)s abc1234 def5678 --json
  %(prog)s abc1234 def5678 --commands-only
        """,
    )
    parser.add_argument("old_sha", help="Old commit SHA (base)")
    parser.add_argument("new_sha", help="New commit SHA (head)")
    parser.add_argument(
        "--pytorch-dir",
        help="Path to existing pytorch/pytorch checkout (avoids cloning)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--commands-only", action="store_true",
        help="Output only the test commands, one per line",
    )
    parser.add_argument(
        "--category", choices=CATEGORIES,
        help="Filter tests to a specific category (cpu, inductor, sgpu, mgpu)",
    )
    args = parser.parse_args()

    pytorch_dir = clone_or_fetch_pytorch(args.pytorch_dir, args.old_sha, args.new_sha)
    changed_files = get_changed_files(pytorch_dir, args.old_sha, args.new_sha)

    if not changed_files:
        print("No files changed between the two commits.", file=sys.stderr)
        sys.exit(0)

    targets, unmapped = map_changes_to_tests(changed_files)

    if args.category:
        targets = [t for t in targets if t.category == args.category]

    if args.commands_only:
        for t in targets:
            print(t.command)
    else:
        print(format_output(targets, unmapped, changed_files,
                            args.old_sha, args.new_sha, as_json=args.json))


if __name__ == "__main__":
    main()
