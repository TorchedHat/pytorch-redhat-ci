# pytorch-redhat-ci

A standalone test repository for validating the [Cross-Repository CI Relay (CRCR)](https://github.com/pytorch/pytorch/issues/175022) pipeline **outside the PyTorch GitHub org**. This simulates a real-world downstream backend (e.g., Red Hat's PyTorch CI) integrating with PyTorch's CI infrastructure.

## Purpose

The CRCR system dispatches `repository_dispatch` events from `pytorch/pytorch` to downstream repos whenever a pull request is opened or synchronized. Downstream repos run their CI, then report results back via the [callback action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback), which ultimately surface on the [PyTorch HUD](https://hud.pytorch.org).

This repo exists to:

- **Test cross-org dispatch**: Verify that the CRCR relay successfully delivers `repository_dispatch` events to repos outside `pytorch/` and `pytorch-labs/`.
- **Test OIDC callback authentication**: Confirm that OIDC tokens issued by GitHub Actions in a non-PyTorch org are correctly validated by the callback Lambda.
- **Test HUD ingestion end-to-end**: Ensure that CI results from an external org flow through DynamoDB → ClickHouse → HUD frontend.
- **Validate allowlist levels**: Test L2/L3/L4 level assignment for repos not in the PyTorch ecosystem.
- **Catch org-boundary edge cases**: Surface issues with permissions, OIDC audience claims, or rate limiting that only appear for external contributors.

## How It Works

```
pytorch/pytorch (PR event)
  │
  ▼  repository_dispatch
TorchedHat/pytorch-redhat-ci (this repo)
  │
  ├─ Receives dispatch payload (PR number, SHA, action)
  ├─ Runs simulated CI (build + test)
  ├─ Sends in_progress callback (OIDC-authenticated)
  ├─ Sends completed callback with conclusion + test results
  │
  ▼
CRCR Callback Lambda → HUD API → DynamoDB → ClickHouse → HUD UI
```

## Prerequisites

1. This repo must be added to the CRCR allowlist (hosted in `pytorch/pytorch`) at the desired level (L2/L3/L4):
   ```yaml
   L2:
     - TorchedHat/pytorch-redhat-ci
   ```

2. The CRCR relay Lambda must be configured to dispatch to this repo.

3. GitHub Actions must be enabled with `id-token: write` permission for OIDC callbacks.

## Workflow Structure

The repo should contain a `.github/workflows/` directory with workflows triggered by `repository_dispatch` events of type `pull_request`. A typical workflow:

1. **Receives** the dispatch event with the PyTorch PR payload
2. **Reports** `in_progress` status via the callback action
3. **Checks out** PyTorch at the dispatched SHA
4. **Runs** build and test steps (can be real or simulated)
5. **Reports** `completed` status with `conclusion` (`success`/`failure`) and optional `test-results`

See [`pytorch/crcr-test`](https://github.com/pytorch/crcr-test) for reference workflow implementations.

## Callback Action Usage

```yaml
- name: Report CI started
  uses: pytorch/test-infra/.github/actions/cross-repo-ci-relay-callback@main
  with:
    status: in_progress

- name: Report CI completed
  if: always()
  uses: pytorch/test-infra/.github/actions/cross-repo-ci-relay-callback@main
  with:
    status: completed
    conclusion: ${{ steps.tests.outcome || 'failure' }}
    test-results: '{"passed": 100, "failed": 2, "skipped": 5, "total": 107}'
    artifact-url: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
```

## What This Validates That `pytorch/crcr-test` Cannot

| Scenario | crcr-test (in-org) | This repo (external org) |
|---|---|---|
| OIDC token from non-PyTorch org | N/A | Tested |
| Cross-org `repository_dispatch` delivery | Same org | Different org |
| Allowlist entry for external org | `pytorch/*` | `TorchedHat/*` |
| GitHub App installation scope | Already installed | May need separate install |
| Rate limiting for external callers | Shared limits | Isolated limits |

## Related Resources

- [RFC: OOT HUD Integration](https://github.com/pytorch/pytorch/issues/175022)
- [CRCR Relay Lambda](https://github.com/pytorch/test-infra/tree/main/aws/lambda/cross_repo_ci_relay)
- [Callback Action](https://github.com/pytorch/test-infra/tree/main/.github/actions/cross-repo-ci-relay-callback)
- [crcr-test (in-org test repo)](https://github.com/pytorch/crcr-test)
- [OOT HUD Mockups](https://subinz1.github.io/rfcs/RFC-0054-assets/oot-hud-mockup.html)
