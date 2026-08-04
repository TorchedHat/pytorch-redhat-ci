#!/usr/bin/env python3
"""
Categorized test suites for PyTorch nightly CI on RHEL.

Based on upstream pytorch/pytorch test/run_test.py and tools/testing/discover_tests.py.
Each category groups test files by their hardware requirements and subsystem affinity.

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

# Each entry: (test_name, keyword_filter, estimated_minutes)
# test_name matches run_test.py's -i argument (relative to test/ without .py)
# keyword_filter is passed to -k when set.

CPU_TESTS: list[tuple[str, Optional[str], float]] = [
    # === Core tensor ops ===
    ("test_torch", None, 25),
    ("test_binary_ufuncs", None, 10),
    ("test_unary_ufuncs", None, 10),
    ("test_reductions", None, 10),
    ("test_indexing", None, 5),
    ("test_sort_and_select", None, 5),
    ("test_shape_ops", None, 5),
    ("test_scatter_gather_ops", None, 5),
    ("test_view_ops", None, 5),
    ("test_tensor_creation_ops", None, 5),
    ("test_type_promotion", None, 5),
    ("test_dlpack", None, 3),
    ("test_complex", None, 3),
    ("test_namedtensor", None, 5),
    # === Neural network ===
    ("test_nn", None, 30),
    ("nn/test_convolution", None, 5),
    ("nn/test_pooling", None, 5),
    ("nn/test_dropout", None, 2),
    ("nn/test_embedding", None, 3),
    ("nn/test_init", None, 3),
    ("nn/test_lazy_modules", None, 2),
    ("nn/test_module_hooks", None, 3),
    ("nn/test_load_state_dict", None, 3),
    ("nn/test_multihead_attention", None, 5),
    ("nn/test_packed_sequence", None, 2),
    ("nn/test_parametrization", None, 3),
    ("nn/test_pruning", None, 3),
    # === Autograd ===
    ("test_autograd", None, 20),
    ("test_autograd_fallback", None, 5),
    # === Modules & ops ===
    ("test_modules", None, 15),
    ("test_ops", None, 20),
    ("test_ops_gradients", None, 15),
    ("test_ops_fwd_gradients", None, 10),
    ("test_custom_ops", None, 5),
    ("test_native_mha", None, 5),
    # === Optimizers ===
    ("optim/test_optim", None, 10),
    ("optim/test_lrscheduler", None, 5),
    ("optim/test_swa_utils", None, 3),
    # === Serialization ===
    ("test_serialization", None, 10),
    # === Linear algebra ===
    ("test_linalg", None, 20),
    # === Spectral / sparse ===
    ("test_spectral_ops", None, 10),
    ("test_sparse", None, 15),
    ("test_sparse_csr", None, 10),
    ("test_sparse_semi_structured", None, 5),
    # === Misc core ===
    ("test_testing", None, 5),
    ("test_utils", None, 5),
    ("test_dataloader", None, 10),
    ("test_foreach", None, 10),
    ("test_masked", None, 5),
    ("test_maskedtensor", None, 5),
    ("test_nestedtensor", None, 10),
    ("test_dynamic_shapes", None, 10),
    ("test_fake_tensor", None, 5),
    ("test_functionalization", None, 5),
    ("test_prims", None, 5),
    ("test_proxy_tensor", None, 10),
    ("test_pytree", None, 3),
    ("test_dispatch", None, 5),
    ("test_python_dispatch", None, 5),
    ("test_subclass", None, 5),
    ("test_decomp", None, 15),
    ("test_expanded_weights", None, 5),
    ("test_logging", None, 3),
    ("test_segment_reductions", None, 3),
    ("test_transformers", None, 5),
    # === MKL/DNNL ===
    ("test_mkldnn", None, 10),
    ("test_mkldnn_fusion", None, 5),
    # === Higher-order ops ===
    ("higher_order_ops/test_invoke_subgraph", None, 3),
    ("higher_order_ops/test_local_map", None, 3),
    ("higher_order_ops/test_with_effects", None, 3),
    # === Profiler ===
    ("profiler/test_profiler", None, 10),
    ("profiler/test_execution_trace", None, 5),
    ("profiler/test_record_function", None, 3),
    # === JIT (subset) ===
    ("test_jit", None, 30),
    # === FX ===
    ("test_fx", None, 15),
    ("test_fx_passes", None, 5),
    ("test_fx_reinplace_pass", None, 3),
]

INDUCTOR_TESTS: list[tuple[str, Optional[str], float]] = [
    # === TorchInductor core ===
    ("inductor/test_torchinductor", None, 30),
    ("inductor/test_torchinductor_dynamic_shapes", None, 30),
    ("inductor/test_torchinductor_codegen_dynamic_shapes", None, 15),
    ("inductor/test_torchinductor_opinfo", None, 20),
    ("inductor/test_cpu_repro", None, 15),
    ("inductor/test_cpu_select_algorithm", None, 10),
    ("inductor/test_cpu_cpp_wrapper", None, 10),
    # === Inductor features ===
    ("inductor/test_fx_fusion", None, 10),
    ("inductor/test_pattern_matcher", None, 10),
    ("inductor/test_split_cat_fx_passes", None, 5),
    ("inductor/test_split_cat_fx_aten_passes", None, 5),
    ("inductor/test_compiled_autograd", None, 15),
    ("inductor/test_compiled_optimizers", None, 10),
    ("inductor/test_inductor_freezing", None, 10),
    ("inductor/test_mkldnn_pattern_matcher", None, 10),
    ("inductor/test_custom_post_grad_passes", None, 5),
    ("inductor/test_group_batch_fusion", None, 5),
    ("inductor/test_foreach", None, 5),
    ("inductor/test_benchmark_fusion", None, 5),
    ("inductor/test_combo_kernels", None, 5),
    ("inductor/test_cooperative_reductions", None, 5),
    ("inductor/test_inplacing_pass", None, 5),
    ("inductor/test_layout_optim", None, 5),
    ("inductor/test_memory_planning", None, 5),
    ("inductor/test_padding", None, 5),
    ("inductor/test_pad_mm", None, 5),
    ("inductor/test_control_flow", None, 5),
    ("inductor/test_auto_functionalize", None, 5),
    ("inductor/test_config", None, 3),
    ("inductor/test_smoke", None, 3),
    # === Dynamo ===
    ("dynamo/test_misc", None, 15),
    ("dynamo/test_repros", None, 10),
    ("dynamo/test_functions", None, 10),
    ("dynamo/test_modules", None, 10),
    ("dynamo/test_export", None, 10),
    ("dynamo/test_dynamic_shapes", None, 15),
    ("dynamo/test_subclasses", None, 10),
    ("dynamo/test_subgraphs", None, 5),
    ("dynamo/test_higher_order_ops", None, 10),
    ("dynamo/test_hooks", None, 5),
    ("dynamo/test_aot_autograd", None, 10),
    ("dynamo/test_activation_checkpointing", None, 5),
    ("dynamo/test_ctx_manager", None, 5),
    ("dynamo/test_decorators", None, 3),
    ("dynamo/test_logging", None, 3),
    ("dynamo/test_optimizers", None, 5),
    ("dynamo/test_recompiles", None, 5),
    ("dynamo/test_backends", None, 5),
    ("dynamo/test_compile", None, 5),
    ("dynamo/test_config", None, 3),
    ("dynamo/test_guard_manager", None, 5),
    ("dynamo/test_interop", None, 3),
    ("dynamo/test_sources", None, 3),
    ("dynamo/test_unspec", None, 5),
    ("dynamo/test_utils", None, 5),
    # === Export ===
    ("export/test_export", None, 15),
    ("export/test_export_strict", None, 10),
    ("export/test_serdes", None, 5),
    ("export/test_serialize", None, 5),
    ("export/test_passes", None, 5),
    ("export/test_unflatten", None, 5),
    ("export/test_dynamic_shapes", None, 10),
    ("export/test_converter", None, 5),
    ("export/test_hop", None, 5),
    ("export/test_verifier", None, 3),
    ("export/test_retraceability", None, 5),
    # === Functorch ===
    ("functorch/test_vmap", None, 15),
    ("functorch/test_eager_transforms", None, 10),
    ("functorch/test_aotdispatch", None, 10),
    ("functorch/test_control_flow", None, 5),
    ("functorch/test_ops", None, 10),
]

SGPU_TESTS: list[tuple[str, Optional[str], float]] = [
    # === CUDA core ===
    ("test_cuda", None, 15),
    ("test_cuda_primary_ctx", None, 3),
    ("test_cuda_expandable_segments", None, 5),
    ("test_cuda_sanitizer", None, 5),
    ("test_cuda_trace", None, 3),
    ("test_cuda_nvml_based_avail", None, 3),
    ("test_cuda_compatibility", None, 3),
    # === GPU compute ===
    ("test_matmul_cuda", None, 10),
    ("test_scaled_matmul_cuda", None, 5),
    # === Inductor GPU ===
    ("inductor/test_cuda_repro", None, 10),
    ("inductor/test_cudagraph_trees", None, 10),
    ("inductor/test_cudacodecache", None, 5),
    ("inductor/test_gpu_cpp_wrapper", None, 10),
    ("inductor/test_gpu_select_algorithm", None, 10),
    ("inductor/test_max_autotune", None, 10),
    ("inductor/test_move_constructors_to_gpu", None, 5),
    ("inductor/test_multi_kernel", None, 5),
    ("inductor/test_select_algorithm", None, 10),
    ("inductor/test_triton_kernels", None, 10),
    ("inductor/test_triton_heuristics", None, 5),
    ("inductor/test_fused_attention", None, 10),
    ("inductor/test_flex_attention", None, 10),
    ("inductor/test_flex_decoding", None, 5),
    ("inductor/test_fp8", None, 5),
    ("inductor/test_aot_inductor", None, 15),
    ("inductor/test_perf", None, 10),
    # === Dynamo CUDA ===
    ("dynamo/test_cudagraphs", None, 10),
]

MGPU_TESTS: list[tuple[str, Optional[str], float]] = [
    # === Multi-GPU core ===
    ("test_cuda_multigpu", None, 15),
    # === C10D backends ===
    ("distributed/test_c10d_common", None, 15),
    ("distributed/test_c10d_nccl", None, 30),
    ("distributed/test_c10d_gloo", None, 15),
    ("distributed/test_c10d_functional_native", None, 10),
    ("distributed/test_c10d_ops_nccl", None, 10),
    ("distributed/test_c10d_object_collectives", None, 5),
    ("distributed/test_c10d_pypg", None, 5),
    ("distributed/test_nccl", None, 10),
    # === Data Parallel / DDP ===
    ("distributed/test_data_parallel", None, 10),
    ("distributed/algorithms/ddp_comm_hooks/test_ddp_hooks", None, 10),
    # === FSDP (composable) ===
    ("distributed/_composable/fsdp/test_fully_shard_training", None, 20),
    ("distributed/_composable/fsdp/test_fully_shard_comm", None, 10),
    ("distributed/_composable/fsdp/test_fully_shard_init", None, 10),
    ("distributed/_composable/fsdp/test_fully_shard_state_dict", None, 10),
    ("distributed/_composable/fsdp/test_fully_shard_mixed_precision", None, 10),
    ("distributed/_composable/fsdp/test_fully_shard_frozen", None, 5),
    ("distributed/_composable/fsdp/test_fully_shard_compile", None, 10),
    ("distributed/_composable/fsdp/test_fully_shard_clip_grad_norm_", None, 5),
    ("distributed/_composable/fsdp/test_fully_shard_extensions", None, 5),
    # === FSDP (legacy) ===
    ("distributed/fsdp/test_fsdp_core", None, 20),
    ("distributed/fsdp/test_fsdp_grad_acc", None, 10),
    ("distributed/fsdp/test_fsdp_mixed_precision", None, 10),
    ("distributed/fsdp/test_fsdp_comm_hooks", None, 10),
    ("distributed/fsdp/test_fsdp_tp_integration", None, 10),
    ("distributed/fsdp/test_shard_utils", None, 5),
    # === Replicate ===
    ("distributed/_composable/test_replicate", None, 10),
    ("distributed/_composable/test_replicate_training", None, 5),
    ("distributed/_composable/test_replicate_with_compiler", None, 10),
    # === Pipeline parallelism ===
    ("distributed/pipelining/test_schedule", None, 10),
    ("distributed/pipelining/test_schedule_multiproc", None, 10),
    ("distributed/pipelining/test_pipe", None, 10),
    ("distributed/pipelining/test_stage", None, 5),
    ("distributed/pipelining/test_microbatch", None, 5),
    ("distributed/_composable/test_composability/test_pp_composability", None, 20),
    # === DTensor ===
    ("distributed/tensor/test_tensor_ops", None, 10),
    ("distributed/tensor/test_api", None, 10),
    ("distributed/tensor/test_random_ops", None, 5),
    ("distributed/tensor/test_attention", None, 5),
    ("distributed/tensor/test_view_ops", None, 10),
    ("distributed/tensor/debug/test_comm_mode", None, 5),
    # === Checkpoint ===
    ("distributed/checkpoint/test_checkpoint", None, 10),
    ("distributed/checkpoint/test_state_dict", None, 10),
    ("distributed/checkpoint/test_dtensor_checkpoint", None, 10),
    ("distributed/checkpoint/test_file_system_checkpoint", None, 10),
    ("distributed/checkpoint/test_file_system_checkpoint_cpu", None, 5),
    # === Inductor distributed ===
    ("distributed/test_inductor_collectives", None, 10),
    ("distributed/test_dynamo_distributed", None, 10),
    # === Misc distributed ===
    ("distributed/test_fake_pg", None, 5),
    ("distributed/test_multi_threaded_pg", None, 5),
    ("distributed/optim/test_zero_redundancy_optimizer", None, 10),
    ("distributed/test_functional_api", None, 5),
    ("distributed/_tools/test_fake_collectives", None, 3),
]

# Critical tests: always run regardless of delta determination.
# These cover core subsystem health and must never be skipped.
CRITICAL_CPU_TESTS: list[tuple[str, Optional[str], float]] = [
    ("test_torch", None, 25),
    ("test_autograd", None, 20),
    ("test_linalg", None, 20),
    ("test_sparse", None, 15),
    ("test_unary_ufuncs", None, 10),
    ("test_binary_ufuncs", None, 10),
]

CRITICAL_INDUCTOR_TESTS: list[tuple[str, Optional[str], float]] = [
    ("inductor/test_torchinductor", None, 30),
    ("inductor/test_cpu_repro", None, 15),
]

CRITICAL_SGPU_TESTS: list[tuple[str, Optional[str], float]] = [
    ("test_nn", None, 30),
    ("test_torch", None, 25),
    ("test_cuda", None, 15),
    ("test_ops", None, 20),
    ("test_unary_ufuncs", None, 10),
    ("test_binary_ufuncs", None, 10),
    ("test_autograd", None, 20),
]

CRITICAL_MGPU_TESTS: list[tuple[str, Optional[str], float]] = [
    ("distributed/test_c10d_common", None, 15),
    ("distributed/test_c10d_nccl", None, 30),
    ("distributed/test_distributed_spawn", None, 15),
]

CRITICAL_SUITES = {
    "cpu": CRITICAL_CPU_TESTS,
    "inductor": CRITICAL_INDUCTOR_TESTS,
    "sgpu": CRITICAL_SGPU_TESTS,
    "mgpu": CRITICAL_MGPU_TESTS,
}

# Tests that unconditionally require CUDA driver initialization
# and must be excluded from CPU and Inductor categories
CUDA_ONLY_TESTS = {
    "test_overrides",
    "test_cuda",
    "test_cuda_primary_ctx",
    "test_cuda_expandable_segments",
    "test_cuda_sanitizer",
    "test_cuda_trace",
    "test_cuda_nvml_based_avail",
    "test_cuda_compatibility",
    "test_cuda_multigpu",
    "test_matmul_cuda",
    "test_scaled_matmul_cuda",
}

SUITES = {
    "cpu": CPU_TESTS,
    "inductor": INDUCTOR_TESTS,
    "sgpu": SGPU_TESTS,
    "mgpu": MGPU_TESTS,
}


def _test_name(test_entry: str) -> str:
    """Convert test file reference to run_test.py test name."""
    name = test_entry
    if name.startswith("test/"):
        name = name[5:]
    if name.endswith(".py"):
        name = name[:-3]
    return name


def get_commands(suite: list[tuple[str, str | None, float]]) -> list[str]:
    """Return run_test.py commands for a test suite."""
    commands = []
    for test_name, kw_filter, _ in suite:
        name = _test_name(test_name)
        if kw_filter:
            commands.append(f'python test/run_test.py -i {name} -k "{kw_filter}"')
        else:
            commands.append(f"python test/run_test.py -i {name}")
    return commands


def get_estimated_minutes(suite: list[tuple[str, str | None, float]]) -> float:
    return sum(est for _, _, est in suite)


def main():
    parser = argparse.ArgumentParser(description="PyTorch RHEL CI test suites")
    parser.add_argument("category", nargs="?", choices=SUITES.keys(),
                        help="Test category to list")
    parser.add_argument("--all", action="store_true", help="Output all categories as JSON")
    parser.add_argument("--commands-only", action="store_true",
                        help="Output only commands, one per line")
    parser.add_argument("--critical", action="store_true",
                        help="Output only critical tests for the category")
    args = parser.parse_args()

    if args.all:
        output = {}
        for name, suite in SUITES.items():
            critical = CRITICAL_SUITES[name]
            output[name] = {
                "tests": [
                    {"name": n, "filter": k, "est_min": e}
                    for n, k, e in suite
                ],
                "commands": get_commands(suite),
                "estimated_minutes": get_estimated_minutes(suite),
                "critical_tests": [
                    {"name": n, "filter": k, "est_min": e}
                    for n, k, e in critical
                ],
                "critical_commands": get_commands(critical),
                "critical_estimated_minutes": get_estimated_minutes(critical),
            }
        print(json.dumps(output, indent=2))
        return

    if not args.category:
        parser.print_help()
        sys.exit(1)

    suite = CRITICAL_SUITES[args.category] if args.critical else SUITES[args.category]
    commands = get_commands(suite)

    if args.commands_only:
        for cmd in commands:
            print(cmd)
    else:
        label = "Critical" if args.critical else "Full"
        est = get_estimated_minutes(suite)
        print(f"Category: {args.category} ({label})")
        print(f"Tests: {len(suite)}")
        print(f"Estimated time: ~{est:.0f} min")
        print()
        for i, cmd in enumerate(commands, 1):
            print(f"  [{i:2d}] {cmd}")


if __name__ == "__main__":
    main()
