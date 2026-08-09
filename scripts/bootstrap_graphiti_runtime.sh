#!/usr/bin/env bash
set -euo pipefail

# 为 Graphiti OSS 建立隔离 Python 3.12 runtime；主框架不吸收 FalkorDB Lite、
# sentence-transformers 与 Graphiti 的依赖树。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GRAPHITI_ROOT="$ROOT/third_party/methods/graphiti"

uv sync \
  --project "$GRAPHITI_ROOT" \
  --frozen \
  --python 3.12 \
  --extra falkordblite \
  --extra sentence-transformers

GRAPHITI_TELEMETRY_ENABLED=false \
HF_HUB_OFFLINE=1 \
TRANSFORMERS_OFFLINE=1 \
  "$GRAPHITI_ROOT/.venv/bin/python" -c \
  'from redislite.async_falkordb_client import AsyncFalkorDB; import graphiti_core, sentence_transformers; print("Graphiti runtime ready")'
