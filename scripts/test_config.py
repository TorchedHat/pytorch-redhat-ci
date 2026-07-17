#!/usr/bin/env python3
"""
Categorized test suites for PyTorch nightly CI on RHEL.

Derived from the submodule-level mapping in pytorch-targeted-tests.
Each category groups related test files that can run in parallel jobs.

Usage:
    python test_config.py cpu          # list cpu test commands
    python test_config.py inductor     # list inductor test commands
    python test_config.py sgpu         # list single-gpu test commands
    python test_config.py mgpu         # list multi-gpu test commands
    python test_config.py --all        # list all categories as JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

# Each entry: (test_file, keyword_filter, estimated_minutes, description)
# keyword_filter is passed to pytest -k when set.

CPU_TESTS: list[tuple[str, Optional[str], float, str]] = [
    # Core tensor operations
    ("test/test_torch.py", "test_dir or test_type or test_dtypes or test_scalar", 5, "core tensor ops"),
    ("test/test_torch.py", "reshape or view or permute or transpose or expand or contiguous", 5, "tensor shape ops"),
    ("test/test_torch.py", "copy or fill or zero or ones", 3, "tensor fill/copy"),
    # Neural network modules
    ("test/nn/test_convolution.py", None, 5, "convolution"),
    ("test/nn/test_pooling.py", None, 5, "pooling"),
    ("test/nn/test_dropout.py", None, 2, "dropout"),
    ("test/nn/test_embedding.py", None, 3, "embedding"),
    ("test/nn/test_init.py", None, 3, "weight init"),
    ("test/nn/test_lazy_modules.py", None, 2, "lazy modules"),
    ("test/nn/test_module_hooks.py", None, 3, "module hooks"),
    ("test/nn/test_load_state_dict.py", None, 3, "state dict loading"),
    ("test/nn/test_multihead_attention.py", None, 5, "multihead attention"),
    ("test/nn/test_packed_sequence.py", None, 2, "packed sequence"),
    ("test/nn/test_parametrization.py", None, 3, "parametrization"),
    ("test/nn/test_pruning.py", None, 3, "pruning"),
    ("test/test_nn.py", "linear or bilinear or Linear or Bilinear", 3, "nn linear"),
    ("test/test_nn.py", "conv", 3, "nn conv"),
    ("test/test_nn.py", "batchnorm or BatchNorm", 5, "nn batchnorm"),
    ("test/test_nn.py", "loss or bce or cross_entropy or mse or nll", 5, "nn loss"),
    ("test/test_nn.py", "relu or elu or selu or gelu or sigmoid or softmax or tanh", 5, "nn activation"),
    ("test/test_nn.py", "layer_norm or LayerNorm or group_norm or GroupNorm", 3, "nn normalization"),
    ("test/test_nn.py", "rnn or RNN or lstm or LSTM or gru or GRU", 5, "nn rnn"),
    ("test/test_nn.py", "transformer or Transformer or multihead", 5, "nn transformer"),
    ("test/test_nn.py", "embedding or Embedding or EmbeddingBag", 3, "nn embedding"),
    # Autograd
    ("test/test_autograd.py", "gradcheck", 5, "autograd gradcheck"),
    ("test/test_autograd.py", "checkpoint", 5, "autograd checkpoint"),
    # Optimizers
    ("test/optim/test_optim.py", "Adam or SGD or AdamW", 5, "optimizers"),
    ("test/optim/test_lrscheduler.py", None, 5, "lr schedulers"),
    # Serialization
    ("test/test_serialization.py", None, 10, "serialization"),
    # Linear algebra
    ("test/test_linalg.py", None, 20, "linalg"),
    # Indexing, sorting, reductions
    ("test/test_indexing.py", None, 5, "indexing"),
    ("test/test_sort_and_select.py", None, 5, "sorting"),
    ("test/test_reductions.py", None, 10, "reductions"),
    # Unary/binary ops
    ("test/test_unary_ufuncs.py", None, 10, "unary ops"),
    ("test/test_binary_ufuncs.py", None, 10, "binary ops"),
    # Spectral / sparse
    ("test/test_spectral_ops.py", None, 10, "FFT/spectral"),
    ("test/test_sparse.py", None, 15, "sparse tensors"),
    ("test/test_sparse_csr.py", None, 10, "sparse CSR"),
    # Misc
    ("test/test_testing.py", None, 5, "testing utils"),
]

INDUCTOR_TESTS: list[tuple[str, Optional[str], float, str]] = [
    ("test/inductor/test_torchinductor.py", "test_simple", 10, "inductor basic"),
    ("test/inductor/test_torchinductor.py", "codegen", 15, "inductor codegen"),
    ("test/inductor/test_fx_fusion.py", None, 10, "fx fusion passes"),
    ("test/dynamo/test_misc.py", "guard", 5, "dynamo guards"),
    ("test/dynamo/test_misc.py", None, 15, "dynamo misc"),
    ("test/dynamo/test_repros.py", None, 10, "dynamo repros"),
    ("test/export/test_export.py", None, 15, "torch.export"),
    ("test/functorch/test_vmap.py", None, 15, "functorch vmap"),
    ("test/functorch/test_eager_transforms.py", None, 10, "functorch eager transforms"),
]

SGPU_TESTS: list[tuple[str, Optional[str], float, str]] = [
    ("test/test_cuda.py", None, 15, "CUDA core"),
    ("test/test_torch.py", "cuda", 10, "tensor ops on CUDA"),
    ("test/test_nn.py", "cuda", 10, "nn modules on CUDA"),
    ("test/test_autograd.py", "cuda", 10, "autograd on CUDA"),
    ("test/inductor/test_torchinductor.py", "cuda", 15, "inductor CUDA"),
]

MGPU_TESTS: list[tuple[str, Optional[str], float, str]] = [
    ("test/distributed/test_c10d_common.py", None, 15, "c10d common"),
    ("test/distributed/test_c10d_nccl.py", None, 15, "c10d NCCL"),
    ("test/distributed/fsdp/test_fsdp_core.py", None, 20, "FSDP core"),
    ("test/distributed/_tensor/test_dtensor.py", None, 15, "DTensor"),
]

SUITES = {
    "cpu": CPU_TESTS,
    "inductor": INDUCTOR_TESTS,
    "sgpu": SGPU_TESTS,
    "mgpu": MGPU_TESTS,
}


def _test_name(test_file: str) -> str:
    """Convert test file path to run_test.py test name (e.g. test/test_cuda.py -> test_cuda)."""
    name = test_file.replace("test/", "", 1)
    if name.endswith(".py"):
        name = name[:-3]
    return name


def get_commands(suite: list[tuple[str, str | None, float, str]]) -> list[str]:
    """Return run_test.py commands for a test suite."""
    commands = []
    for test_file, kw_filter, _, _ in suite:
        name = _test_name(test_file)
        if kw_filter:
            commands.append(f'python test/run_test.py -i {name} -k "{kw_filter}"')
        else:
            commands.append(f"python test/run_test.py -i {name}")
    return commands


def get_estimated_minutes(suite: list[tuple[str, str | None, float, str]]) -> float:
    return sum(est for _, _, est, _ in suite)


def main():
    parser = argparse.ArgumentParser(description="PyTorch RHEL CI test suites")
    parser.add_argument("category", nargs="?", choices=SUITES.keys(),
                        help="Test category to list")
    parser.add_argument("--all", action="store_true", help="Output all categories as JSON")
    parser.add_argument("--commands-only", action="store_true",
                        help="Output only commands, one per line")
    args = parser.parse_args()

    if args.all:
        output = {}
        for name, suite in SUITES.items():
            output[name] = {
                "tests": [
                    {"file": f, "filter": k, "est_min": e, "desc": d}
                    for f, k, e, d in suite
                ],
                "commands": get_commands(suite),
                "estimated_minutes": get_estimated_minutes(suite),
            }
        print(json.dumps(output, indent=2))
        return

    if not args.category:
        parser.print_help()
        sys.exit(1)

    suite = SUITES[args.category]
    commands = get_commands(suite)

    if args.commands_only:
        for cmd in commands:
            print(cmd)
    else:
        est = get_estimated_minutes(suite)
        print(f"Category: {args.category}")
        print(f"Tests: {len(suite)}")
        print(f"Estimated time: ~{est:.0f} min")
        print()
        for i, (f, k, e, d) in enumerate(suite, 1):
            cmd = commands[i - 1]
            print(f"  [{i:2d}] {cmd}")
            print(f"       # {d} (~{e:.0f} min)")


if __name__ == "__main__":
    main()
