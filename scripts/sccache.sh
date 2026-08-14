#!/bin/bash
# sccache helper for CRCR nightly builds.
#
# Subcommands:
#   prepare  — Set up cache directory with 4-layer management (version, TTL, flush, kill switch)
#   stats    — Report host cache size and compilation hit/miss stats from built image
#
# Usage:
#   scripts/sccache.sh prepare [--enabled true|false] [--flush true|false]
#                              [--version VERSION] [--max-age-days DAYS]
#
#   scripts/sccache.sh stats --image IMAGE_TAG --cache-dir CACHE_DIR

set -euo pipefail

cmd_prepare() {
  local SCCACHE_ENABLED="true"
  local FLUSH_SCCACHE="false"
  local SCCACHE_CACHE_VERSION="v1"
  local SCCACHE_MAX_AGE_DAYS="30"

  while [[ $# -gt 0 ]]; do
    case $1 in
      --enabled)       SCCACHE_ENABLED="$2"; shift 2 ;;
      --flush)         FLUSH_SCCACHE="$2"; shift 2 ;;
      --version)       SCCACHE_CACHE_VERSION="$2"; shift 2 ;;
      --max-age-days)  SCCACHE_MAX_AGE_DAYS="$2"; shift 2 ;;
      *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
  done

  local SCCACHE_CACHE_DIR="$HOME/sccache-cache/crcr-rhel96/${SCCACHE_CACHE_VERSION}"
  mkdir -p "${SCCACHE_CACHE_DIR}"

  # TTL cleanup — remove entries older than N days
  if [ -n "${SCCACHE_MAX_AGE_DAYS}" ] && [ "${SCCACHE_MAX_AGE_DAYS}" -gt 0 ] 2>/dev/null; then
    echo "Cleaning sccache entries older than ${SCCACHE_MAX_AGE_DAYS} days"
    find "${SCCACHE_CACHE_DIR}" -type f -mtime +${SCCACHE_MAX_AGE_DAYS} -delete 2>/dev/null || true
  fi

  # On-demand flush
  if [ "${FLUSH_SCCACHE}" == "true" ]; then
    echo "Flushing entire sccache directory"
    rm -rf "${SCCACHE_CACHE_DIR}"/*
  fi

  # Kill switch — omit volume mount to build without cache
  local VOLUME_ARG=""
  if [ "${SCCACHE_ENABLED}" == "false" ]; then
    echo "sccache disabled — building without cache"
  else
    local CACHE_SIZE=$(du -sh "${SCCACHE_CACHE_DIR}" 2>/dev/null | cut -f1 || echo "empty")
    local CACHE_FILES=$(find "${SCCACHE_CACHE_DIR}" -type f 2>/dev/null | wc -l || echo "0")
    echo "sccache enabled — cache at ${SCCACHE_CACHE_DIR} (${CACHE_SIZE}, ${CACHE_FILES} files)"
    VOLUME_ARG="--volume ${SCCACHE_CACHE_DIR}:/sccache:Z"
  fi

  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "volume_arg=${VOLUME_ARG}" >> "$GITHUB_OUTPUT"
    echo "cache_dir=${SCCACHE_CACHE_DIR}" >> "$GITHUB_OUTPUT"
  else
    echo "volume_arg=${VOLUME_ARG}"
    echo "cache_dir=${SCCACHE_CACHE_DIR}"
  fi
}

cmd_stats() {
  local IMAGE_TAG=""
  local SCCACHE_CACHE_DIR=""

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
}

case "${1:-}" in
  prepare) shift; cmd_prepare "$@" ;;
  stats)   shift; cmd_stats "$@" ;;
  *) echo "Usage: $0 {prepare|stats} [options]" >&2; exit 1 ;;
esac
