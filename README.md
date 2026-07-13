# pytorch-redhat-ci

Red Hat's downstream CI for [PyTorch](https://github.com/pytorch/pytorch), building and testing on **RHEL (Red Hat Enterprise Linux)**. Integrated with PyTorch's upstream CI via [Cross-Repository CI Relay (CRCR)](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorch-s-out-of-tree-backends/).

## How It Works

```
pytorch/pytorch (PR event)
  │
  ▼  repository_dispatch (via CRCR)
TorchedHat/pytorch-redhat-ci (this repo)
  │
  ├─ Receives dispatch payload (PR number, SHA, action)
  ├─ Builds PyTorch from source on RHEL
  ├─ Runs sanity + test suite
  └─ Reports results back to PyTorch HUD
```

When a pull request is opened or updated on `pytorch/pytorch`, the CRCR relay dispatches a `repository_dispatch` event to this repo. The workflow checks out PyTorch at the dispatched commit SHA, builds it on RHEL self-hosted runners, and runs tests.

## Platforms

| Runner | OS | Status |
|--------|-----|--------|
| `linux.rhel96` | RHEL 9.6 | Active (L1 — build & sanity) |

## Workflows

### `rhel96-build-test.yml` — RHEL 9.6 Build & Sanity Tests

Triggered by CRCR `repository_dispatch` (`pull_request` type) or manually via `workflow_dispatch`.

**Build job** (`linux.rhel96`):
- Checks out `pytorch/pytorch` at the dispatched SHA
- Builds PyTorch from source
- Logs system info (OS, GCC, Python, CMake)

**Sanity test job** (`linux.rhel96`):
- `import torch` verification
- Tensor ops and dtype checks (float32, float64, int32, int64, bfloat16)
- Autograd backward pass
- Model serialization round-trip
- Core `test_torch.py` smoke tests

### CRCR Test Workflows

The repo also contains CRCR integration test workflows (`test-l1-*`, `test-l2-*`, `test-security`, `test-concurrency`) that validate the CRCR dispatch and callback pipeline from an external org. These are separate from the RHEL build/test workflows.

## CRCR Integration Level

Currently at **L1** — dispatches are received and builds run, but results are not yet reported back to the [PyTorch HUD](https://hud.pytorch.org). Once stable, this will be promoted to L2+ with HUD callback reporting.

## Prerequisites

1. The `linux.rhel96` self-hosted runner must be registered and online.
2. This repo must be on the [CRCR allowlist](https://github.com/pytorch/pytorch) to receive dispatches:
   ```yaml
   L2:
     - TorchedHat/pytorch-redhat-ci
   ```
3. The runner must have Python 3, GCC, CMake, and build dependencies installed.

## Related Resources

- [CRCR Blog Post](https://pytorch.org/blog/introducing-cross-repository-ci-relay-scalable-ci-for-pytorch-s-out-of-tree-backends/)
- [CRCR Relay Lambda](https://github.com/pytorch/test-infra/tree/main/aws/lambda/cross_repo_ci_relay)
- [Callback Action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback)
- [crcr-test (in-org health check repo)](https://github.com/pytorch/crcr-test)
- [PyTorch HUD](https://hud.pytorch.org)
