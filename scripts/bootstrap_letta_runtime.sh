#!/usr/bin/env bash
set -euo pipefail

# 为 Letta 建立独立 Python 3.12 运行环境。主框架环境不得吸收 Letta 的依赖树。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LETTA_ROOT="$ROOT/third_party/methods/letta"

uv sync --project "$LETTA_ROOT" --frozen --python 3.12
uv pip install \
  --python "$LETTA_ROOT/.venv/bin/python" \
  --no-deps \
  'asyncpg==0.30.0' \
  'pg8000==1.31.4' \
  'pgvector==0.4.1' \
  'asn1crypto==1.5.1' \
  'scramp==1.4.15'

"$LETTA_ROOT/.venv/bin/python" -c \
  'import asyncpg, pg8000, pgvector, letta; print("Letta runtime ready")'
