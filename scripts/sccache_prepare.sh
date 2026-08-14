#!/bin/bash
# Prepare sccache cache directory before a podman build.
#
# Implements 4-layer cache management:
#   1. Versioned cache path   — bump version to start fresh
#   2. TTL cleanup            — evict entries older than N days
#   3. On-demand flush        — wipe entire cache
#   4. Kill switch            — disable sccache entirely
#
# Usage:
#   scripts/sccache_prepare.sh [--enabled true|false]
#                              [--flush true|false]
#                              [--version VERSION]
#                              [--max-age-days DAYS]
#
# Outputs (written to $GITHUB_OUTPUT if set, otherwise printed):
#   volume_arg  — podman --volume flag (empty if disabled)
#   cache_dir   — host-side cache directory path

set -euo pipefail

SCCACHE_ENABLED="true"
FLUSH_SCCACHE="false"
SCCACHE_CACHE_VERSION="v1"
SCCACHE_MAX_AGE_DAYS="30"

while [[ $# -gt 0 ]]; do
  case $1 in
    --enabled)       SCCACHE_ENABLED="$2"; shift 2 ;;
    --flush)         FLUSH_SCCACHE="$2"; shift 2 ;;
    --version)       SCCACHE_CACHE_VERSION="$2"; shift 2 ;;
    --max-age-days)  SCCACHE_MAX_AGE_DAYS="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

SCCACHE_CACHE_DIR="$HOME/sccache-cache/crcr-rhel96/${SCCACHE_CACHE_VERSION}"
mkdir -p "${SCCACHE_CACHE_DIR}"

# Layer 2: TTL cleanup — remove entries older than N days
if [ -n "${SCCACHE_MAX_AGE_DAYS}" ] && [ "${SCCACHE_MAX_AGE_DAYS}" -gt 0 ] 2>/dev/null; then
  echo "Cleaning sccache entries older than ${SCCACHE_MAX_AGE_DAYS} days"
  find "${SCCACHE_CACHE_DIR}" -type f -mtime +${SCCACHE_MAX_AGE_DAYS} -delete 2>/dev/null || true
fi

# Layer 3: On-demand flush
if [ "${FLUSH_SCCACHE}" == "true" ]; then
  echo "Flushing entire sccache directory"
  rm -rf "${SCCACHE_CACHE_DIR}"/*
fi

# Layer 4: Kill switch — omit volume mount to build without cache
if [ "${SCCACHE_ENABLED}" == "false" ]; then
  echo "sccache disabled — building without cache"
  VOLUME_ARG=""
else
  CACHE_SIZE=$(du -sh "${SCCACHE_CACHE_DIR}" 2>/dev/null | cut -f1 || echo "empty")
  CACHE_FILES=$(find "${SCCACHE_CACHE_DIR}" -type f 2>/dev/null | wc -l || echo "0")
  echo "sccache enabled — cache at ${SCCACHE_CACHE_DIR} (${CACHE_SIZE}, ${CACHE_FILES} files)"
  VOLUME_ARG="--volume ${SCCACHE_CACHE_DIR}:/sccache:Z"
fi

# Write outputs
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "volume_arg=${VOLUME_ARG}" >> "$GITHUB_OUTPUT"
  echo "cache_dir=${SCCACHE_CACHE_DIR}" >> "$GITHUB_OUTPUT"
else
  echo "volume_arg=${VOLUME_ARG}"
  echo "cache_dir=${SCCACHE_CACHE_DIR}"
fi
