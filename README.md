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
                                              ├─ Fetches source SHA from nightly branch
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

**Build job** (`linux.rhel96`):
- Fetches the source SHA from `pytorch/pytorch`'s `nightly` branch
- Builds PyTorch from source inside a RHEL 9.6 container using `podman`
- Produces a tagged container image for test jobs

**Determine-tests job** (`linux.rhel96`):
- Computes the diff between the current and previous nightly SHA
- Runs `merge_test_results.py` (heuristic + structural call graph analysis)
- Outputs categorized test lists (cpu, inductor, sgpu, mgpu)
- Falls back to full test suite if delta produces no results

**Test jobs** (`linux.rhel96`, sequential):
- `cpu-tests` — CPU-only PyTorch tests (timeout: 180 min)
- `inductor-tests` — TorchInductor tests
- `sgpu-tests` — Single-GPU tests (skipped if no GPU available)
- `mgpu-tests` — Multi-GPU tests (skipped if < 2 GPUs available)

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
| `torchtalk_tests.py` | C++ call graph + binding analysis | C++ kernel/op changes |
| `merge_test_results.py` | Union of both | Combined coverage |

The unified merger (`merge_test_results.py`) runs both tools and deduplicates results. If the structural analyzer is not installed or its index is unavailable, the system gracefully falls back to heuristic-only mode.

Test commands are validated against `run_test.py`'s accepted test list before execution to filter out invalid entries.

**Environment variables:**
- `STRUCTURAL_ANALYSIS_DEPTH` — Override call graph walk depth (default: 3)

## Prerequisites

1. The `linux.rhel96` self-hosted runner must be registered and online.
2. `podman` must be available on the runner for container-based builds.
3. This repo must be on the [CRCR allowlist](https://github.com/pytorch/pytorch) to receive dispatches:
   ```yaml
   L2:
     - TorchedHat/pytorch-redhat-ci
   ```
4. The runner must have Python 3, GCC, CMake, and build dependencies installed.

## Related Resources

- [CRCR Blog Post](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorchs-out-of-tree-backends/)
- [CRCR Relay Lambda](https://github.com/pytorch/test-infra/tree/main/aws/lambda/cross_repo_ci_relay)
- [Callback Action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback)
- [crcr-test (in-org health check repo)](https://github.com/pytorch/crcr-test)
- [PyTorch HUD](https://hud.pytorch.org)
