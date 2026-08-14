#!/bin/bash
# Report sccache build statistics after a podman build.
#
# Usage:
#   scripts/sccache_stats.sh --image IMAGE_TAG --cache-dir CACHE_DIR

set -euo pipefail

IMAGE_TAG=""
SCCACHE_CACHE_DIR=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --image)      IMAGE_TAG="$2"; shift 2 ;;
    --cache-dir)  SCCACHE_CACHE_DIR="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

echo "=== sccache host cache ==="
if [ -d "${SCCACHE_CACHE_DIR}" ]; then
  echo "Cache size: $(du -sh "${SCCACHE_CACHE_DIR}" 2>/dev/null | cut -f1 || echo 'N/A')"
  echo "Cache files: $(find "${SCCACHE_CACHE_DIR}" -type f 2>/dev/null | wc -l || echo 'N/A')"
else
  echo "Cache directory not found: ${SCCACHE_CACHE_DIR}"
fi

echo ""
echo "=== sccache compilation stats ==="
if [ -n "${IMAGE_TAG}" ] && podman image exists "${IMAGE_TAG}" 2>/dev/null; then
  podman run --rm "${IMAGE_TAG}" bash -c \
    'source /miniconda/etc/profile.d/conda.sh && conda activate cuda_torch_build && sccache --show-stats 2>/dev/null' || true
else
  echo "Image not available for stats: ${IMAGE_TAG}"
fi
