# PyTorch Redhat CI

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

Runs daily at 08:30 UTC via cron, or manually via `workflow_dispatch`.

**Pipeline: `build → determine-tests → cpu-tests → inductor-tests → sgpu-tests → mgpu-tests`** (sequential)

#### Manual Dispatch

The workflow can be triggered manually from the Actions tab with two optional inputs:

| Input | Description | Default |
|-------|-------------|---------|
| `sha` | pytorch/pytorch SHA to build against (leave empty for latest nightly) | _(empty = latest nightly)_ |
| `test_categories` | Which test stages to run after build | `all` |

**Test category options:**

| Selection | What runs |
|-----------|-----------|
| `all` | Build + all test stages (same as cron) |
| `cpu` | Build + determine-tests + CPU tests only |
| `inductor` | Build + determine-tests + inductor tests only |
| `sgpu` | Build + determine-tests + single-GPU tests only |
| `mgpu` | Build + determine-tests + multi-GPU tests only |
| `build-only` | Build only, skip all tests |

Cron-triggered runs always execute all stages regardless of these inputs. The run title displays the selected category (e.g., `[Nightly] RHEL 9.6 @ manual [sgpu]`).

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

#### Test Jobs (`linux.rhel96`, 24h job timeout)

| Job | Category | GPU Requirement | Per-command timeout | Runs After |
|-----|----------|-----------------|---------------------|------------|
| `cpu-tests` | CPU-only PyTorch tests | None | 2 hours | `determine-tests` |
| `inductor-tests` | TorchInductor + Dynamo + Export | None | 2 hours | `cpu-tests` |
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

### `rhel96-build-test.yml` — PR Build & Sanity Tests (Disabled)

Triggered by CRCR `repository_dispatch` (`pull_request` type). Currently disabled (`.disabled` suffix) while the nightly workflow is being stabilized. Will be re-enabled once nightly is promoted to L3+.

### `results-relay-receiver.yml` — External CI Results Relay

Receives CI results from external partners (e.g., `torch-spyre/torch-spyre`) via `repository_dispatch` (`external-ci-result` type). Partners authenticate to the RHEL Results Relay Lambda via OIDC and the Lambda dispatches results to this workflow.

| Field | Source |
|-------|--------|
| `source_repo` | OIDC `repository` claim (verified by Lambda) |
| `delivery_id` | Partner-provided pytorch/pytorch SHA |
| `conclusion` | `success` / `failure` / `timed_out` |
| `event_type` | `nightly` / `periodic` |

HUD forwarding is controlled by the `PUSH_TO_HUD` env var (currently `false` during testing). When enabled, results are forwarded to the PyTorch CRCR relay via the callback action.

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
| build | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / build` |
| cpu-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (cpu, linux.rhel96)` |
| inductor-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (inductor, linux.rhel96)` |
| sgpu-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (sgpu, linux.rhel96)` |
| mgpu-tests | `linux-rhel9.6-cuda13.0-py3.12-gcc11-x86_64 / test (mgpu, linux.rhel96)` |

GPU test jobs only report to CRCR when GPUs are actually available on the runner — skipped tests are not reported, avoiding misleading `success` entries on HUD.

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
  results-relay-receiver.yml    # Receives external partner CI results
  rhel96-build-test.yml.disabled # PR workflow (disabled)

aws/lambda/results_relay/
  lambda_function.py            # OIDC validation + repository_dispatch to receiver
  allowlist.py                  # YAML-based repo allowlist with TTL cache
  config.py                     # Lambda configuration (audience, dispatch repo)
  requirements.txt              # PyJWT, PyYAML, requests, cryptography
  tests/                        # Unit tests for Lambda and allowlist

config/
  rhel_allowlist.yml            # Authorized repos for the Results Relay

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
| `RESULTS_RELAY_ENDPOINT` | results-relay-receiver | Lambda URL for HUD forwarding |
| `DISPATCH_TOKEN` | results-relay-receiver | GitHub PAT for `repository_dispatch` (used by Lambda) |

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

## Partner Onboarding (Results Relay)

External partners can send their nightly CI results through the RHEL Results Relay. The flow is:

```
Partner repo (e.g., torch-spyre/torch-spyre)
    │
    ├─ Mint OIDC token (audience: "rhel-results-relay")
    ├─ POST result payload to RHEL Results Relay Lambda
    │     ↓
    │   Lambda validates OIDC + allowlist
    │     ↓
    │   repository_dispatch → results-relay-receiver.yml
    │     ↓
    │   (optional) Forward to PyTorch CRCR relay → HUD
    │
    └─ Partner can also report directly to PyTorch CRCR relay
```

To onboard a new partner:

1. Add their `owner/repo` to [`config/rhel_allowlist.yml`](config/rhel_allowlist.yml)
2. Partner adds OIDC token minting + POST step to their nightly workflow
3. Verify results appear in the receiver workflow's Actions tab
4. Set `PUSH_TO_HUD: "true"` in `results-relay-receiver.yml` when ready for HUD visibility
