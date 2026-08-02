#!/usr/bin/env bash
set -euo pipefail

# 为 LangMem 建立独立 Python 3.12 runtime；主框架环境不吸收其 LangChain 依赖树。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANGMEM_ROOT="$ROOT/third_party/methods/langmem"
REQUIREMENTS="$ROOT/scripts/requirements/langmem-runtime.txt"

uv sync --project "$LANGMEM_ROOT" --frozen --python 3.12
uv pip install \
  --python "$LANGMEM_ROOT/.venv/bin/python" \
  --requirements "$REQUIREMENTS"

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  "$LANGMEM_ROOT/.venv/bin/python" -c \
  'import langmem, sentence_transformers; print("LangMem runtime ready")'
