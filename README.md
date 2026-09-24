# PyTorch Red Hat CI

Red Hat's downstream CI for [PyTorch](https://github.com/pytorch/pytorch), building and testing on **RHEL (Red Hat Enterprise Linux)**. Integrated with PyTorch's upstream CI via [Cross-Repository CI Relay (CRCR)](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorchs-out-of-tree-backends/).

## How It Works

```
pytorch/pytorch
  │
  ├─ PR events ──▶ repository_dispatch (via CRCR) ──▶ rhel96-build-test.yml [disabled]
  │
  ├─ nightly branch ──▶ cron schedule ──▶ crcr-nightly.yml [active, CUDA + CPU]
  │                                           │
  │                                           ├─ Extracts source main SHA from nightly commit
  │                                           ├─ Builds CUDA and CPU images in parallel
  │                                           ├─ Determines CPU and CUDA test lists independently
  │                                           └─ Reports CPU and CUDA test stages to CRCR/HUD
  │
  └─ nightly SHA ──▶ workflow_dispatch ──▶ crcr-nightly-rocm.yml [manual, ROCm]
                                              │
                                              ├─ Builds PyTorch in RHEL 9.6 ROCm container
                                              ├─ Runs sanity or critical ROCm tests
                                              └─ HUD/CRCR callbacks currently disabled (PUSH_TO_HUD=false)

```

## Platforms

| Runner | OS | Accelerator | Status |
|--------|-----|-------------|--------|
| `linux.rhel96` | RHEL 9.6 | CUDA | Active |
| `linux.rhel96-rocm` | RHEL 9.6 | ROCm | Active (manual validation) |
| `linux.rhel96-cpu` | RHEL 9.6 | CPU | Active nightly validation |

## Workflows

### `crcr-nightly.yml` — Nightly RHEL 9.6 Build & Test (Active)

Runs daily at 08:30 UTC via cron, or manually via `workflow_dispatch`.

**Pipeline:** CPU and CUDA builds start in parallel. Their determination and test branches are independent:

```text
cpu-build → determine-cpu-tests → cpu-tests
build → determine-cuda-tests → inductor-tests → sgpu-tests → mgpu-tests
```

#### Manual Dispatch

The workflow can be triggered manually from the Actions tab.

| Input | Description | Default |
|-------|-------------|---------|
| `sha` | pytorch/pytorch SHA to build against (leave empty for latest nightly) | _(empty = latest nightly)_ |
| `run_scope` | CPU/CUDA build-only validation or its test pipeline | `all` |
| `no_cache` | Force both image builds to use `podman --no-cache` for this manual run | `false` |
| `forward_to_hud` | Forward this manual run's results to HUD | `true` |

**Run scope options:**

| Selection | What runs |
|-----------|-----------|
| `all` | CPU and CUDA builds, then every CPU/CUDA test stage (same as cron) |
| `cpu` | CPU build, CPU determination, and CPU tests |
| `cuda` | CUDA build, CUDA determination, then the serial CUDA test chain |
| `cpu-build-only` | CPU build only |
| `cuda-build-only` | CUDA build only |

Cron-triggered runs always execute all stages, force `podman --no-cache` for both builds, and forward results to HUD. Manual results are forwarded by default; deselect `forward_to_hud` to keep a validation run out of HUD. The run title displays a non-default scope or cache mode.

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

#### CPU Build (`linux.rhel96-cpu`, 10h timeout)

- Starts in parallel with the CUDA build and uses `docker/Dockerfile.rhel9-cpu`.
- Produces a CPU-only image verified with `torch.version.cuda is None`.
- Pushes the independent tag `quay.io/aipcc/pytorch:rhel9_6_pytorch_nightly_main_git<7char_sha>_cpu`.
- A Quay upload failure is reported but does not fail the build job; downstream jobs reuse a local image when available.

#### Test determination (`linux.rhel96-cpu` and `linux.rhel96`, 10h timeout)

`determine-cpu-tests` and `determine-cuda-tests` run after their respective builds. Each uses `merge_test_results.py` inside its matching image for `delta` selection, validates discovered test names against `run_test.py`, and produces base64-encoded commands for its branch.

`sanity`, `critical`, and `full` use the configured lists from `test_config.py`. `delta` merges affected commands with the category's critical suite; when no previous SHA or no usable affected command is available, it falls back to that critical suite.

#### Test Jobs (up to 24h job timeout)

| Job | Category | GPU Requirement | Per-command timeout | Runs After |
|-----|----------|-----------------|---------------------|------------|
| `cpu-tests` | CPU-only PyTorch tests | None | 2 hours | `determine-cpu-tests` |
| `inductor-tests` | TorchInductor + Dynamo + Export | None | 2 hours | `determine-cuda-tests` |
| `sgpu-tests` | Single-GPU tests | ≥ 1 GPU | 2 hours | `inductor-tests` |
| `mgpu-tests` | Multi-GPU + distributed tests | ≥ 2 GPUs | 12 hours | `sgpu-tests` |

Each test job:
- **Mounts the command list as a file** into the container (`-v /tmp/<job>_test_commands.txt:/tmp/test_commands.txt:ro`) — avoids shell quoting issues with `bash -c` argument passing
- **Writes each command to `/tmp/_run.sh`** and executes via `bash /tmp/_run.sh` — preserves `-k` filter quoting (e.g., `-k "TestA or TestB"`) that would otherwise be mangled by nested `eval`
- Uses **single-quoted `bash -c '...'`** for the outer podman shell — eliminates escape gymnastics
- Wraps each command with `timeout` to prevent individual hangs from blocking the pipeline (2 hours for cpu/inductor/sgpu, 12 hours for mgpu)
- Runs with `CONTINUE_THROUGH_ERROR=True`, collecting pass/fail counts and printing a `:::SUMMARY:::` block
- Streams output in real-time via `tee` (no buffering)
- **Reports accurate job status**: a final "Fail job if tests failed" step checks the test step's `outcome` and exits with code 1 if there were failures, ensuring the job conclusion is `failure` despite `continue-on-error: true` on the test step

### `crcr-nightly-rocm.yml` — RHEL 9.6 ROCm Build & Test (Manual)

Triggered only via `workflow_dispatch` while the `linux.rhel96-rocm` (MI355X / gfx950) runner and image are being validated. Cron and HUD reporting will be enabled after manual soak.

**Pipeline: `rocm-build → determine-tests → inductor-tests → sgpu-tests → mgpu-tests`**

Same category split as CUDA (`scripts/test_config.py`), sized for a multi-GPU MI355X host.

#### Manual Dispatch

| Input | Description | Default |
|-------|-------------|---------|
| `sha` | pytorch/pytorch SHA to build against (leave empty for latest nightly) | _(empty = latest nightly)_ |
| `test_tier` | `sanity` / `critical` lists from `test_config.py`, or `build-only` | `critical` |
| `test_categories` | `all` / `inductor` / `sgpu` / `mgpu` | `all` |
| `no_cache` | Force `podman --no-cache` full rebuild (keep on until the ROCm image is validated) | `true` |

| Selection | What runs |
|-----------|-----------|
| `sanity` + `all` | Build + short sanity lists for inductor, sgpu, mgpu |
| `critical` + `all` | Build + critical inductor / sgpu / mgpu suites (default) |
| `critical` + `sgpu` | Build + sgpu only (skips inductor/mgpu jobs) |
| `build-only` | Build only, skip tests |

#### ROCm Build (`linux.rhel96-rocm`, 10h timeout)
- Resolves the source `main` SHA from `pytorch/pytorch` nightly (or uses the manual `sha` input)
- Builds PyTorch from source with `USE_ROCM=1` / `USE_CUDA=0` via `docker/Dockerfile.rhel9-rocm`
- Pins **ROCm 7.14.0** via `amdgpu-install` / `rocmradeon/el9/26.13` (classic `rocm/el9/7.14*` 404s)
- Defaults to `--no-cache` so a green build is a real compile (set `no_cache=false` later for faster rebuilds)
- Verifies the image can `import torch` with a non-empty `torch.version.hip` before push
- Pushes to Quay with tag:
  ```
  quay.io/aipcc/pytorch:rhel9_6_pytorch_nightly_main_git<7char_sha>_rocm7_14_0
  ```

#### Determine-tests (`linux.rhel96-rocm`)
- Resolves inductor / sgpu / mgpu command lists from `scripts/test_config.py` (`--sanity` or `--critical`)
- No delta/heuristic path yet (full tier lists every run)

#### ROCm Test Jobs (`linux.rhel96-rocm`, 24h timeout each)

| Job | Category | GPU requirement | Per-command timeout |
|-----|----------|-----------------|---------------------|
| `inductor-tests` | TorchInductor | optional (≥1 for GPU paths) | 2h |
| `sgpu-tests` | Single-GPU (`HIP_VISIBLE_DEVICES=0`) | ≥ 1 | 2h (+ quick sanity gate) |
| `mgpu-tests` | Multi-GPU / distributed (RCCL via `test_c10d_nccl`) | ≥ 2 | 12h |

Shared behavior:
- Podman: `--ipc=host` + `/dev/kfd` + `/dev/dri` (no `--shm-size`)
- `CONTINUE_THROUGH_ERROR=True`; summaries report *completed with failures* (no hard job fail on suite failures)
- **HUD/CRCR callbacks are disabled** (`PUSH_TO_HUD=false`) until the pipeline is manually validated

### `rhel96-build-test.yml` — PR Build & Sanity Tests (Disabled)

Triggered by CRCR `repository_dispatch` (`pull_request` type). Currently disabled (`.disabled` suffix) while the nightly workflow is being stabilized. Will be re-enabled once nightly results are consistently stable.

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

Currently at **L2** — nightly builds and tests run daily, with results reported back to the [PyTorch HUD](https://hud.pytorch.org/crcr/TorchedHat/pytorch-redhat-ci) via the CRCR callback action. Each pipeline stage (build, cpu, inductor, sgpu, mgpu) reports its conclusion individually, giving per-job visibility on the HUD dashboard.

### HUD Reporting

Each job in the nightly pipeline sends a `completed` callback to the PyTorch CRCR relay with `event-type: nightly` and `delivery-id` set to the resolved pytorch/pytorch source SHA. The following job names appear on HUD:

| Job | HUD `job-name` |
|-----|----------------|
| CUDA build | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / build` |
| CPU build | `linux-rhel9.6-cpu-py3.12-x86_64 / build` |
| CPU tests | `linux-rhel9.6-cpu-py3.12-x86_64 / test (cpu, linux.rhel96-cpu)` |
| inductor-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (inductor, linux.rhel96)` |
| sgpu-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (sgpu, linux.rhel96)` |
| mgpu-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (mgpu, linux.rhel96)` |

GPU test jobs only report to CRCR when GPUs are actually available on the runner — skipped tests are not reported, avoiding misleading `success` entries on HUD.

ROCm jobs (`rocm-build`, `rocm-tests`) intentionally do **not** report to HUD yet: `PUSH_TO_HUD=false` in `crcr-nightly-rocm.yml`. Flip that flag once the ROCm pipeline has been manually validated.

### External Results Relay

The results relay accepts submissions from GitHub Actions repositories whose OIDC
tokens are listed in `config/rhel_allowlist.yml`. Submission authorization and
HUD forwarding are separate: the Lambda determines `forward_to_hud` from this
file, so a sender cannot opt itself into HUD.

Use `forward_to_hud: false` while onboarding or validating a new partner. Its
results are received and shown in the receiver workflow, but are not forwarded
to CRCR/HUD. Enable forwarding only after the partner is ready:

```yaml
allowed_repos:
  - repo: partner-org/partner-repo
    forward_to_hud: false
```

### L2 Promotion Criteria

This repo was promoted to L2 after meeting the following criteria from [RFC-0050](https://github.com/pytorch/rfcs/blob/main/RFC-0050-Cross-Repository-CI-Relay-for-PyTorch-Out-of-Tree-Backends.md):

| Criterion | Status |
|-----------|--------|
| Nightly callback success rate ≥ 80% | Met |
| Results visible on PyTorch HUD | Met |
| Timeout rate < 1% | Met |
| Active for ≥ 1 month | Met |

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
  crcr-nightly.yml              # Active CUDA nightly pipeline
  crcr-nightly-rocm.yml         # Manual ROCm build/test (HUD disabled)
  rhel96-build-test.yml.disabled # PR workflow (disabled)

docker/
  Dockerfile.rhel9              # RHEL 9.6 UBI build image (conda, CUDA, PyTorch from source)
  Dockerfile.rhel9-rocm         # RHEL 9.6 UBI build image (conda, ROCm, PyTorch from source)

scripts/
  merge_test_results.py         # Unified test merger (heuristic + structural)
  targeted_tests.py             # File-path heuristic test selector
  torchtalk_tests.py            # Structural call graph analyzer wrapper
  test_config.py                # Static categorized test suites (full-suite fallback)
  requirements-structural.txt   # Dependencies for structural analysis
```

## Prerequisites

1. The `linux.rhel96` (CUDA) and/or `linux.rhel96-rocm` (ROCm) self-hosted runners must be registered and online
2. `podman` must be available on the runner for container-based builds
3. This repo must be on the [CRCR allowlist](https://github.com/pytorch/test-infra) to receive dispatches:
   ```yaml
   L2:
     - TorchedHat/pytorch-redhat-ci
   ```
4. For GPU test jobs, the runner must have NVIDIA GPUs with drivers installed

### Secrets

| Secret | Used By | Purpose |
|--------|---------|---------|
| `RHEL_SUBSCRIPTION_ACTIVATION_KEY` | Build (Dockerfile) | RHEL subscription for `dnf` access |
| `RHEL_SUBSCRIPTION_ORG_ID` | Build (Dockerfile) | RHEL org ID for subscription-manager |
| `QUAY_USERNAME` | Build (push step) | Quay.io robot account or username |
| `QUAY_PASSWORD` | Build (push step) | Quay.io password or token |

## Related Resources

- [Quay.io Container Registry](https://quay.io/repository/aipcc/pytorch)
- [CRCR Blog Post](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorchs-out-of-tree-backends/)
- [CRCR Relay Lambda](https://github.com/pytorch/test-infra/tree/main/aws/lambda/cross_repo_ci_relay)
- [Callback Action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback)
- [crcr-test (in-org health check repo)](https://github.com/pytorch/crcr-test)
- [PyTorch HUD — CRCR Summary](https://hud.pytorch.org/crcr)
- [PyTorch HUD — TorchedHat Results](https://hud.pytorch.org/crcr/TorchedHat/pytorch-redhat-ci)
- [RFC-0050: Cross-Repository CI Relay](https://github.com/pytorch/rfcs/blob/main/RFC-0050-Cross-Repository-CI-Relay-for-PyTorch-Out-of-Tree-Backends.md)
- [RFC-0056: CRCR Nightly & Periodic CI](https://github.com/pytorch/rfcs/pull/98)
