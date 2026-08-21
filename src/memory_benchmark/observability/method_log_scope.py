"""run 级 method logger 落盘作用域。

本模块给一次 benchmark run 在 root logger 上挂一个 run-scoped 的
``FileHandler``，把 method 自己 logger 打的 INFO/WARNING（如 LightMem
``LightMemory`` 的 "Created N MemoryEntry objects"、segment/token 统计、
"No entries found" 警告等）落盘到 ``logs/method.log``，让成本/异常可事后追溯。

设计要点（与 ws04 卡 Y 一致）：

- **run 起挂、run 止摘**：用 ``with method_log_scope(logs_dir)`` 包住 run 主体，
  ``_MethodLogScope.__exit__`` 在正常退出与异常下都 ``removeHandler`` 并 ``close``，
  避免 ① handler 泄漏（重复 run / 并行 run 累积）、② 跨 run 串写。
- **不改终端行为**：只额外落一份文件，不动 method / 第三方现有 ConsoleHandler。
- **降噪**：``_NoisyThirdPartyFilter`` 过滤掉已知刷屏且无诊断价值的第三方
  namespace（transformers、urllib3、httpx、sentence_transformers）的 INFO；
  method 自身 logger 与框架 INFO 保留。
- **run 级而非 conversation 级**：handler 只挂一次到 root logger，并行
  conversation（同进程线程）下 Python logging 本身线程安全，无需额外锁。
- **INFO level + 时间戳格式**：``%(asctime)s %(name)s %(levelname)s %(message)s``。

线程安全说明：Python logging 的 handler 调用链是线程安全的（每次 emit 持
``Handler.lock``），FileHandler 追加写同一线程并发安全。
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import sys
from threading import RLock

#: method.log 文件名。
METHOD_LOG_FILENAME = "method.log"

#: 已知刷屏、INFO 无诊断价值的第三方 logger namespace；命中即被本作用域过滤。
#:
#: 名字按 logger 层级前缀匹配（``startswith``），因此 ``httpx`` 覆盖
#: ``httpx.core`` / ``httpx._client`` 等子 logger。
NOISY_THIRD_PARTY_NAMESPACES: tuple[str, ...] = (
    "transformers",
    "urllib3",
    "httpx",
    "sentence_transformers",
)

#: method.log FileHandler 的日志格式。
_METHOD_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
#: method.log FileHandler 的时间戳格式（ISO-8601 风格、到秒）。
_METHOD_LOG_DATEFMT = "%Y-%m-%dT%H:%M:%S%z"
_METHOD_OUTPUT_WRITE_LOCK = RLock()
_ACTIVE_METHOD_HANDLERS: dict[Path, logging.FileHandler] = {}


class _LockedMethodFileHandler(logging.FileHandler):
    """与直接 diagnostic writer 共用锁的 FileHandler。"""

    def emit(self, record: logging.LogRecord) -> None:
        """串行追加一条 logging record，避免与 stdout/stderr 行交错。"""

        with _METHOD_OUTPUT_WRITE_LOCK:
            super().emit(record)


def append_method_output(
    *,
    log_path: str | Path | None,
    source: str,
    text: str,
    protected_values: tuple[str, ...] = (),
    level: str = "INFO",
) -> None:
    """把限定来源的第三方文本脱敏后追加到 method.log。

    `None` 表示当前调用没有 runner 注入的诊断目标，此时保持历史行为、不猜路径。
    空行被跳过；换行文本逐行写入，避免一条第三方输出污染日志结构。
    """

    if log_path is None:
        return
    normalized_source = source.strip()
    if not normalized_source:
        raise ValueError("method output source must not be blank")
    redacted = text
    for protected in protected_values:
        if protected:
            redacted = redacted.replace(protected, "<redacted>")
    lines = [line for line in redacted.splitlines() if line.strip()]
    if not lines:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    with _METHOD_OUTPUT_WRITE_LOCK:
        with path.open("a", encoding="utf-8") as output:
            for line in lines:
                output.write(
                    f"[{timestamp}] {normalized_source} {level} {line}\n"
                )


@contextmanager
def capture_method_output(
    *,
    log_path: str | Path | None,
    source: str,
    protected_values: tuple[str, ...] = (),
    mirror_to_terminal: bool = False,
) -> Iterator[None]:
    """在 adapter 已拥有的窄调用边界捕获 stdout/stderr 并脱敏落盘。

    该 helper 不应包住整个并行 run。显式显示开关只在调用结束后把原始文本镜像回
    进入作用域前的 stream；是否显示不影响脱敏后的 ``method.log`` 完整性。
    """

    outer_stdout = sys.stdout
    outer_stderr = sys.stderr
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            yield
    finally:
        stdout_text = stdout_buffer.getvalue()
        stderr_text = stderr_buffer.getvalue()
        append_method_output(
            log_path=log_path,
            source=f"{source}.stdout",
            text=stdout_text,
            protected_values=protected_values,
        )
        append_method_output(
            log_path=log_path,
            source=f"{source}.stderr",
            text=stderr_text,
            protected_values=protected_values,
            level="WARNING",
        )
        if mirror_to_terminal:
            if stdout_text:
                outer_stdout.write(stdout_text)
                outer_stdout.flush()
            if stderr_text:
                outer_stderr.write(stderr_text)
                outer_stderr.flush()


class _NoisyThirdPartyFilter(logging.Filter):
    """过滤掉刷屏第三方 namespace 的 INFO 级日志。

    只压这些 namespace 的低价值 INFO；WARNING 及以上保留（异常信号不能丢）。
    匹配方式为 logger 名前缀匹配，确保子 logger 也被覆盖。

    输入:
        record: 一条 ``logging.LogRecord``。

    输出:
        bool: 返回 ``True`` 表示保留该记录，``False`` 表示丢弃。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        """按 logger 名前缀过滤；仅 INFO 级第三方 noise 被压掉。"""

        name = record.name or ""
        if record.levelno < logging.WARNING and any(
            name == ns or name.startswith(ns + ".")
            for ns in NOISY_THIRD_PARTY_NAMESPACES
        ):
            return False
        return True


def ensure_method_log_handler(log_path: str | Path | None) -> None:
    """在第三方重配 root logger 后恢复当前 run 已登记的 handler。

    只有 ``method_log_scope`` 已登记的精确路径才会动作；没有 active scope 时不创建
    文件、不猜 run，也不会把某个 run 的 handler 绑定到另一个路径。
    """

    if log_path is None:
        return
    resolved = Path(log_path).expanduser().resolve()
    with _METHOD_OUTPUT_WRITE_LOCK:
        handler = _ACTIVE_METHOD_HANDLERS.get(resolved)
        if handler is None:
            return
        root_logger = logging.getLogger()
        if handler not in root_logger.handlers:
            root_logger.addHandler(handler)


@contextmanager
def method_log_scope(log_dir: str | Path) -> Iterator[Path]:
    """在 root logger 上挂一个 run-scoped ``method.log`` FileHandler。

    本函数只**额外**落一份文件：它不改变现有任何 handler、不收窄 root 的
    effective level、也不抑制 method 自身 logger 的传播。作用域结束（含异常）
    一定 ``removeHandler`` + ``close``，保证 root logger 上不残留本 handler，
    避免重复 run / 并行 run 累积与跨 run 串写。

    某些 isolated method factory 会重配 root logger；worker 构造完成后必须调用
    ``ensure_method_log_handler``，把本作用域登记的同一 handler 恢复回来。该门不会
    为未登记路径新建 handler。

    输入:
        log_dir: 本次 run 的日志目录（``<run_dir>/logs``），文件写到
            ``log_dir/method.log``。

    输出:
        Iterator[Path]: yield 实际写入的 ``method.log`` 路径。

    """

    log_path = Path(log_dir) / METHOD_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    formatter = logging.Formatter(
        fmt=_METHOD_LOG_FORMAT,
        datefmt=_METHOD_LOG_DATEFMT,
    )
    file_handler = _LockedMethodFileHandler(
        log_path,
        mode="a",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_NoisyThirdPartyFilter())

    resolved_log_path = log_path.expanduser().resolve()
    with _METHOD_OUTPUT_WRITE_LOCK:
        if resolved_log_path in _ACTIVE_METHOD_HANDLERS:
            raise RuntimeError(f"method log scope is already active: {resolved_log_path}")
        _ACTIVE_METHOD_HANDLERS[resolved_log_path] = file_handler
        root_logger.addHandler(file_handler)
    try:
        yield log_path
    finally:
        with _METHOD_OUTPUT_WRITE_LOCK:
            root_logger.removeHandler(file_handler)
            _ACTIVE_METHOD_HANDLERS.pop(resolved_log_path, None)
        try:
            file_handler.close()
        except Exception:
            # close 失败不能掩盖 run 本身的异常；吞掉只保证 handler 不残留。
            pass
        finally:
            pass
