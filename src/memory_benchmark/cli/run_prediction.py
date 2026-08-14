"""旧 registered prediction import/模块命令的兼容入口。

真实 application service 已下沉到 :mod:`memory_benchmark.runners.registered_prediction`。
导入旧模块时直接返回 canonical module，既保留历史 monkeypatch/import 行为，也避免形成
第二份转发状态；新生产代码不得继续依赖本路径。
"""

from __future__ import annotations

import sys

from memory_benchmark.runners import registered_prediction as _canonical


if __name__ == "__main__":
    raise SystemExit(_canonical.main())

# 旧测试和扩展会 monkeypatch 模块级装配依赖。单纯 ``from ... import *`` 会产生两个
# module namespace，使 monkeypatch 只改到 shim。这里让旧 import 返回 canonical module
# 本身，在兼容期内保持对象身份与副作用完全一致。
sys.modules[__name__] = _canonical
