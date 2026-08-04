# pytorch-redhat-ci

Red Hat's downstream CI for [PyTorch](https://github.com/pytorch/pytorch), building and testing on **RHEL (Red Hat Enterprise Linux)**. Integrated with PyTorch's upstream CI via [Cross-Repository CI Relay (CRCR)](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorchs-out-of-tree-backends/).

## How It Works

```
pytorch/pytorch
  │
  ├─ PR events ──▶ repository_dispatch (via CRCR) ──▶ rhel96-build-test.yml [disabled]
  │
  └─ nightly branch ──▶ cron schedule ──▶ crcr-nightly.yml [active]
                                              │
                                              ├─ Extracts source main SHA from nightly commit
                                              ├─ Builds PyTorch in RHEL 9.6 container (podman)
                                              ├─ Runs delta-based test determination
                                              └─ Executes categorized tests (cpu, inductor, sgpu, mgpu)
```

## Platforms

| Runner | OS | Status |
|--------|-----|--------|
| `linux.rhel96` | RHEL 9.6 | Active |

## Workflows

### `crcr-nightly.yml` — Nightly RHEL 9.6 Build & Test (Active)

Runs daily at 04:00 UTC via cron, or manually via `workflow_dispatch`.

**Pipeline: `build → determine-tests → cpu-tests → inductor-tests → sgpu-tests → mgpu-tests`** (sequential)

#### Build (`linux.rhel96`, 10h timeout)
- Fetches the two most recent commits from `pytorch/pytorch`'s `nightly` branch
- Extracts the **source `main` SHA** from the nightly release commit message (nightly commits embed the original `main` SHA in parentheses)
- Builds PyTorch from source inside a RHEL 9.6 UBI container using `podman build`
- RHEL subscription credentials are passed via BuildKit `--secret` mounts (never appear in image layers or `docker history`)
- Produces a tagged container image (`rhel9-pytorch-nightly:<sha>`) for downstream test jobs
- **Pushes to [Quay.io](https://quay.io/repository/aipcc/pytorch)** with a reproducible tag:
  ```
  quay.io/aipcc/pytorch:rhel9_6_pytorch_nightly_main_git<7char_sha>_cuda13_0
  ```
  Tag components: `rhel9_6` (OS), `nightly` (pipeline), `main` (PyTorch branch), `git<sha>` (commit), `cuda13_0` (CUDA version)

#### Determine-tests (`linux.rhel96`, 10h timeout)
- Computes the diff between the current and previous source SHAs
- Runs `merge_test_results.py` inside the built container (heuristic + structural call graph analysis)
- Validates discovered test names against `run_test.py`'s accepted test list
- Excludes CUDA-only tests (e.g., `test_overrides`) from `cpu` and `inductor` categories
- Outputs base64-encoded, categorized test lists (cpu, inductor, sgpu, mgpu)
- Falls back to full test suite (from `test_config.py`) if delta produces no results

#### Test Jobs (`linux.rhel96`, 24h job timeout, 30m per-command timeout)

| Job | Category | GPU Requirement | Runs After |
|-----|----------|-----------------|------------|
| `cpu-tests` | CPU-only PyTorch tests | None | `determine-tests` |
| `inductor-tests` | TorchInductor + Dynamo + Export | None | `cpu-tests` |
| `sgpu-tests` | Single-GPU tests | ≥ 1 GPU | `inductor-tests` |
| `mgpu-tests` | Multi-GPU + distributed tests | ≥ 2 GPUs | `sgpu-tests` |

Each test job:
- **Mounts the command list as a file** into the container (`-v /tmp/<job>_test_commands.txt:/tmp/test_commands.txt:ro`) — avoids shell quoting issues with `bash -c` argument passing
- **Writes each command to `/tmp/_run.sh`** and executes via `bash /tmp/_run.sh` — preserves `-k` filter quoting (e.g., `-k "TestA or TestB"`) that would otherwise be mangled by nested `eval`
- Uses **single-quoted `bash -c '...'`** for the outer podman shell — eliminates escape gymnastics
- Wraps each command with `timeout 1800` (30 minutes) to prevent individual hangs from blocking the pipeline
- Runs with `CONTINUE_THROUGH_ERROR=True`, collecting pass/fail counts and printing a `:::SUMMARY:::` block
- Streams output in real-time via `tee` (no buffering)
- **Reports accurate job status**: a final "Fail job if tests failed" step checks the test step's `outcome` and exits with code 1 if there were failures, ensuring the job conclusion is `failure` despite `continue-on-error: true` on the test step

### `rhel96-build-test.yml` — PR Build & Sanity Tests (Disabled)

Triggered by CRCR `repository_dispatch` (`pull_request` type). Currently disabled (`.disabled` suffix) while the nightly workflow is being stabilized. Will be re-enabled once nightly is promoted to L2+.

**Build job:**
- Checks out `pytorch/pytorch` at the dispatched SHA
- Builds PyTorch from source on RHEL

**Sanity test job:**
- `import torch` verification
- Tensor ops and dtype checks
- Autograd backward pass
- Model serialization round-trip
- Core `test_torch.py` smoke tests

## CRCR Integration Level

Currently at **L1** — nightly builds and tests run, but results are not yet reported back to the [PyTorch HUD](https://hud.pytorch.org). Once the nightly workflow is stable, this will be promoted to L2+ with HUD callback reporting.

## Test Determination

The nightly workflow uses a dual-strategy approach for delta-based test selection:

| Tool | Strategy | Best For |
|------|----------|----------|
| `targeted_tests.py` | File-path heuristic mapping | Python file changes, test moves |
| `structural_tests.py` | C++ call graph + binding analysis | C++ kernel/op changes |
| `merge_test_results.py` | Union of both + dedup | Combined coverage |
| `test_config.py` | Static full suite (fallback) | When delta produces nothing |

The unified merger (`merge_test_results.py`) runs both tools and deduplicates results. If the structural analyzer is not installed or its index is unavailable, the system gracefully falls back to heuristic-only mode.

Test commands are validated against `run_test.py`'s accepted test list before execution to filter out invalid entries. Tests that unconditionally require a CUDA driver (e.g., `test_overrides`) are excluded from CPU and Inductor categories.

### Critical Tests

A fixed set of critical tests always runs regardless of what the delta determines. These cover core subsystem health and are prepended to the delta results (deduplicated):

| Category | Critical Tests |
|----------|---------------|
| **cpu** | `test_torch`, `test_autograd`, `test_linalg`, `test_sparse`, `test_unary_ufuncs`, `test_binary_ufuncs` |
| **inductor** | `inductor/test_torchinductor`, `inductor/test_cpu_repro` |
| **sgpu** | `test_nn`, `test_torch`, `test_cuda`, `test_ops`, `test_unary_ufuncs`, `test_binary_ufuncs`, `test_autograd` |
| **mgpu** | `distributed/test_c10d_common`, `distributed/test_c10d_nccl`, `distributed/test_distributed_spawn` |

To list critical tests for a category: `python scripts/test_config.py cpu --critical --commands-only`

**Environment variables:**
- `STRUCTURAL_ANALYSIS_DEPTH` — Override call graph walk depth (default: 3)
- `CONTINUE_THROUGH_ERROR` — Set to `True` inside containers; allows all tests to run even if some fail

## Directory Structure

```
.github/workflows/
  crcr-nightly.yml              # Active nightly pipeline
  rhel96-build-test.yml.disabled # PR workflow (disabled)

docker/
  Dockerfile.rhel9              # RHEL 9.6 UBI build image (conda, CUDA, PyTorch from source)

scripts/
  merge_test_results.py         # Unified test merger (heuristic + structural)
  targeted_tests.py             # File-path heuristic test selector
  torchtalk_tests.py            # Structural call graph analyzer wrapper
  test_config.py                # Static categorized test suites (full-suite fallback)
  requirements-structural.txt   # Dependencies for structural analysis
```

## Prerequisites

1. The `linux.rhel96` self-hosted runner must be registered and online
2. `podman` must be available on the runner for container-based builds
3. **RHEL subscription secrets** must be configured in the repo:
   - `RHEL_SUBSCRIPTION_ACTIVATION_KEY`
   - `RHEL_SUBSCRIPTION_ORG_ID`
4. **Quay.io registry secrets** must be configured for image pushing:
   - `QUAY_USERNAME` — Quay.io robot account or username
   - `QUAY_PASSWORD` — Quay.io password or token
5. This repo must be on the [CRCR allowlist](https://github.com/pytorch/test-infra) to receive dispatches:
   ```yaml
   L2:
     - TorchedHat/pytorch-redhat-ci
   ```
6. For GPU test jobs, the runner must have NVIDIA GPUs with drivers installed

## Related Resources

- [Quay.io Container Registry](https://quay.io/repository/aipcc/pytorch)
- [CRCR Blog Post](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorchs-out-of-tree-backends/)
- [CRCR Relay Lambda](https://github.com/pytorch/test-infra/tree/main/aws/lambda/cross_repo_ci_relay)
- [Callback Action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback)
- [crcr-test (in-org health check repo)](https://github.com/pytorch/crcr-test)
- [PyTorch HUD — CRCR Summary](https://hud.pytorch.org/crcr)
- [RFC-0056: CRCR Nightly & Periodic CI](https://github.com/pytorch/rfcs/pull/98)
