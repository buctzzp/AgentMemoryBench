#!/usr/bin/env bash
# 为 EverOS v1.2.3 建立独立 Python 3.12 runtime；不把其依赖灌入主框架环境。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVEROS_ROOT="$ROOT/third_party/methods/EverOS"

test -f "$EVEROS_ROOT/uv.lock"
test -f "$EVEROS_ROOT/pyproject.toml"

uv sync --project "$EVEROS_ROOT" --frozen --python 3.12
"$EVEROS_ROOT/.venv/bin/python" -c \
  'import everos; assert everos.__version__ == "1.2.3"; print("EverOS runtime ready")'
