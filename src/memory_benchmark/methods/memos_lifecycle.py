"""MemOS async lifecycle 完成门：进程内 task tracker 与 task-scoped waiter。

MemOS 产品默认 add 走 ``async_mode="async"``：request 线程只写 fast/raw memory，真正的
fine extraction、raw 清理与 memory-manager refresh 由后台 ``MEM_READ`` task 完成。

upstream 的 :class:`memos.mem_scheduler.utils.status_tracker.TaskStatusTracker` 依赖 Redis；
local queue 部署下它查询恒为空，`/product/scheduler/wait` 会 fail-open 判 idle。本模块提供
一个**不依赖 Redis** 的线程安全替身，接口只覆盖 current scheduler/dispatcher 真正调用的方法，
并按 business ``task_id`` 精确等待本次 add 派生的 ``MEM_READ`` 终态。

设计约束（ws02.7 MemOS R2）：

- 不解析日志文本、不读 ``/scheduler/wait``、不轮询“全局队列是否为空”、不引入 Redis；
- 只有**本 user + 本 business task** 下的预期 ``MEM_READ`` 终态才能解锁；
- ``failed`` 立即抛 :class:`ConfigurationError` 并保留原始 error；
- timeout、查无任务、未知状态、主 ``MEM_READ`` 数量不符一律 fail-fast。
"""

from __future__ import annotations

import threading
import time

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError


#: MemOS ``MEM_READ`` task 的 label，与 ``memos.mem_scheduler.schemas.task_schemas`` 一致。
MEM_READ_TASK_LABEL = "mem_read"

#: upstream tracker 使用的状态字面量。
STATUS_WAITING = "waiting"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

_TERMINAL_STATUSES = frozenset({STATUS_COMPLETED, STATUS_FAILED})
_KNOWN_STATUSES = frozenset(
    {STATUS_WAITING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_FAILED}
)


def _utc_now_iso() -> str:
    """返回 UTC ISO 时间串，与 upstream tracker 的字段格式保持一致。"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    """单个 scheduler item 的状态记录。

    ``task_id`` 是 MemOS 内部的 ``ScheduleMessageItem.item_id``；``business_task_id`` 是
    adapter 为一次 add 生成的唯一业务 id。
    """

    task_id: str
    user_id: str
    task_type: str
    mem_cube_id: str | None = None
    business_task_id: str | None = None
    status: str = STATUS_WAITING
    error: str | None = None
    submitted_at: str = field(default_factory=_utc_now_iso)
    started_at: str | None = None
    completed_at: str | None = None
    failed_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        """转成与 upstream tracker 兼容的 dict（供 ``get_task_status`` 返回）。"""
        payload: dict[str, Any] = {
            "status": self.status,
            "task_type": self.task_type,
            "mem_cube_id": self.mem_cube_id,
            "submitted_at": self.submitted_at,
        }
        if self.business_task_id:
            payload["business_task_id"] = self.business_task_id
        if self.started_at:
            payload["started_at"] = self.started_at
        if self.completed_at:
            payload["completed_at"] = self.completed_at
        if self.failed_at:
            payload["failed_at"] = self.failed_at
        if self.error is not None:
            payload["error"] = self.error
        return payload


class MemosLocalTaskTracker:
    """进程内、线程安全的 MemOS task 状态跟踪器（Redis-free）。

    只实现 current MemOS scheduler/dispatcher 真正调用的方法；不实现
    ``get_all_tasks_global`` 等只服务于 HTTP ``/scheduler`` 端点的接口，因为本项目
    禁用该完成门。
    """

    def __init__(self) -> None:
        """初始化空跟踪表与用于 waiter 唤醒的条件变量。"""
        self._condition = threading.Condition(threading.RLock())
        self._records: dict[tuple[str, str], TaskRecord] = {}
        self._business_index: dict[tuple[str, str], list[str]] = {}

    # ---- MemOS scheduler / dispatcher 调用面 ----

    def task_submitted(
        self,
        task_id: str,
        user_id: str,
        task_type: str,
        mem_cube_id: str | None = None,
        business_task_id: str | None = None,
    ) -> None:
        """登记一个新提交的 scheduler item（由 ``queue_ops.submit_messages`` 调用）。

        Anti-corruption：本 tracker 是严格完成门，不继承 upstream Redis tracker 的
        permissive 覆盖语义。

        - 同一 ``(user_id, task_id)`` 重复提交且身份完全相同时**幂等**，不把已 started
          或已终态的记录重置回 ``waiting``；
        - 身份不同（改绑 business task / 换 label / 换 cube）一律 fail-fast，
          且不污染既有 business index。

        Raises:
            ConfigurationError: 同一 item id 被改绑到不同身份。
        """
        with self._condition:
            existing = self._records.get((user_id, task_id))
            if existing is not None:
                conflicts = []
                if existing.business_task_id != business_task_id:
                    conflicts.append(
                        f"business_task_id {existing.business_task_id!r} -> {business_task_id!r}"
                    )
                if existing.task_type != task_type:
                    conflicts.append(f"task_type {existing.task_type!r} -> {task_type!r}")
                if existing.mem_cube_id != mem_cube_id:
                    conflicts.append(f"mem_cube_id {existing.mem_cube_id!r} -> {mem_cube_id!r}")
                if conflicts:
                    raise ConfigurationError(
                        f"MemOS task item {task_id!r}（user_id={user_id}）被改绑到不同身份，"
                        f"拒绝静默覆盖：{'; '.join(conflicts)}"
                    )
                # 身份一致：幂等，保留既有状态与时间戳。
                self._condition.notify_all()
                return

            self._records[(user_id, task_id)] = TaskRecord(
                task_id=task_id,
                user_id=user_id,
                task_type=task_type,
                mem_cube_id=mem_cube_id,
                business_task_id=business_task_id,
            )
            if business_task_id:
                items = self._business_index.setdefault((user_id, business_task_id), [])
                if task_id not in items:
                    items.append(task_id)
            self._condition.notify_all()

    def _require_record_locked(self, task_id: str, user_id: str, transition: str) -> TaskRecord:
        """取出已登记记录；从未 submit 过则 fail-fast，不创建 orphan record。

        Raises:
            ConfigurationError: 该 item 从未经过 ``task_submitted``。
        """
        record = self._records.get((user_id, task_id))
        if record is None:
            raise ConfigurationError(
                f"MemOS task item {task_id!r}（user_id={user_id}）在 {transition} 前"
                f"从未登记；拒绝创建无 business-index 的 orphan record"
            )
        return record

    def _guard_terminal_locked(self, record: TaskRecord, new_status: str) -> bool:
        """终态单调性守卫：已终态时拒绝被后来的冲突 callback 覆盖。

        Returns:
            ``True`` 表示允许写入新状态；``False`` 表示重复的同种终态，忽略即可。

        Raises:
            ConfigurationError: 试图把一个终态改写成另一个终态。
        """
        if record.status not in _TERMINAL_STATUSES:
            return True
        if record.status == new_status:
            return False
        raise ConfigurationError(
            f"MemOS task item {record.task_id!r}（user_id={record.user_id}）已处于终态 "
            f"{record.status!r}，拒绝被改写为 {new_status!r}"
            + (f"；原始 error={record.error!r}" if record.error is not None else "")
        )

    def task_started(self, task_id: str, user_id: str) -> None:
        """标记 item 开始执行（由 dispatcher 的 task wrapper 调用）。"""
        with self._condition:
            record = self._require_record_locked(task_id, user_id, "task_started")
            if record.status in _TERMINAL_STATUSES:
                raise ConfigurationError(
                    f"MemOS task item {task_id!r}（user_id={user_id}）已处于终态 "
                    f"{record.status!r}，拒绝回退为 in_progress"
                )
            record.status = STATUS_IN_PROGRESS
            record.started_at = _utc_now_iso()
            self._condition.notify_all()

    def task_completed(self, task_id: str, user_id: str) -> None:
        """标记 item 成功结束。"""
        with self._condition:
            record = self._require_record_locked(task_id, user_id, "task_completed")
            if not self._guard_terminal_locked(record, STATUS_COMPLETED):
                return
            record.status = STATUS_COMPLETED
            record.completed_at = _utc_now_iso()
            self._condition.notify_all()

    def task_failed(self, task_id: str, user_id: str, error_message: str) -> None:
        """标记 item 失败并保留原始错误文本。"""
        with self._condition:
            record = self._require_record_locked(task_id, user_id, "task_failed")
            if not self._guard_terminal_locked(record, STATUS_FAILED):
                return
            record.status = STATUS_FAILED
            record.error = error_message
            record.failed_at = _utc_now_iso()
            self._condition.notify_all()

    def get_task_status(self, task_id: str, user_id: str) -> dict[str, Any] | None:
        """按内部 item id 查询状态；查无返回 ``None``。"""
        with self._condition:
            record = self._records.get((user_id, task_id))
            return record.to_payload() if record else None

    def get_task_status_by_business_id(
        self, business_task_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """按 business task id 聚合状态，聚合规则与 upstream tracker 一致。

        任一 item ``failed`` → ``failed``；仍有 ``waiting``/``in_progress`` → ``in_progress``；
        全部 ``completed`` → ``completed``；否则 ``unknown``。查无返回 ``None``。
        """
        with self._condition:
            return self._aggregate_locked(business_task_id, user_id)

    # ---- 本项目的等待面 ----

    def _aggregate_locked(
        self, business_task_id: str, user_id: str
    ) -> dict[str, Any] | None:
        """在已持锁状态下做聚合，供查询与 waiter 复用。"""
        item_ids = self._business_index.get((user_id, business_task_id))
        if not item_ids:
            return None

        statuses: list[str] = []
        errors: list[str] = []
        task_types: list[str] = []
        for item_id in item_ids:
            record = self._records.get((user_id, item_id))
            if record is None:
                continue
            statuses.append(record.status)
            task_types.append(record.task_type)
            if record.status == STATUS_FAILED and record.error is not None:
                errors.append(record.error)

        if not statuses:
            return None

        if STATUS_FAILED in statuses:
            aggregated = STATUS_FAILED
        elif STATUS_IN_PROGRESS in statuses or STATUS_WAITING in statuses:
            aggregated = STATUS_IN_PROGRESS
        elif all(s == STATUS_COMPLETED for s in statuses):
            aggregated = STATUS_COMPLETED
        else:
            aggregated = "unknown"

        return {
            "status": aggregated,
            "business_task_id": business_task_id,
            "item_count": len(item_ids),
            "item_statuses": statuses,
            "item_task_types": task_types,
            "errors": errors,
        }

    def _mem_read_records_locked(
        self, business_task_id: str, user_id: str, task_label: str
    ) -> list[TaskRecord]:
        """在已持锁状态下取出本 business task 下指定 label 的 item 记录。"""
        item_ids = self._business_index.get((user_id, business_task_id), [])
        records = []
        for item_id in item_ids:
            record = self._records.get((user_id, item_id))
            if record is not None and record.task_type == task_label:
                records.append(record)
        return records

    def wait_for_business_task(
        self,
        user_id: str,
        business_task_id: str,
        timeout_seconds: float = 300.0,
        expected_task_count: int = 1,
        task_label: str = MEM_READ_TASK_LABEL,
    ) -> list[dict[str, Any]]:
        """等待某个 business task 下的预期后台 task 全部到达终态。

        只认 ``user_id`` + ``business_task_id`` + ``task_label`` 三元组；其他 namespace、
        其他 business task 或其他 label 的完成都不会解锁。

        Args:
            user_id: 本次 add 使用的 user id（也是 namespace）。
            business_task_id: adapter 为本次 add 生成的唯一 task id。
            timeout_seconds: 最长等待秒数。
            expected_task_count: 预期的后台 task 条数，默认 1。
            task_label: 预期 task 的 label，默认 ``mem_read``。

        Returns:
            终态记录 payload 列表。

        Raises:
            ConfigurationError: 失败、超时、查无任务、数量不符或状态未知。
        """
        if expected_task_count < 1:
            raise ConfigurationError(
                f"expected_task_count 必须 >= 1，收到 {expected_task_count}"
            )

        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                records = self._mem_read_records_locked(
                    business_task_id, user_id, task_label
                )

                failed = [r for r in records if r.status == STATUS_FAILED]
                if failed:
                    detail = "; ".join(
                        f"{r.task_id}: {r.error or '<no error recorded>'}" for r in failed
                    )
                    raise ConfigurationError(
                        f"MemOS 后台 {task_label} task 失败"
                        f"（user_id={user_id}, task_id={business_task_id}）：{detail}"
                    )

                unknown = [r for r in records if r.status not in _KNOWN_STATUSES]
                if unknown:
                    detail = "; ".join(f"{r.task_id}: {r.status}" for r in unknown)
                    raise ConfigurationError(
                        f"MemOS 后台 task 出现未知状态"
                        f"（user_id={user_id}, task_id={business_task_id}）：{detail}"
                    )

                if len(records) > expected_task_count:
                    raise ConfigurationError(
                        f"MemOS 后台 {task_label} task 数量超出预期"
                        f"（user_id={user_id}, task_id={business_task_id}）："
                        f"预期 {expected_task_count}，实际 {len(records)}"
                    )

                terminal = [r for r in records if r.status in _TERMINAL_STATUSES]
                if len(terminal) == expected_task_count:
                    return [r.to_payload() for r in terminal]

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if not records:
                        raise ConfigurationError(
                            f"等待 MemOS 后台 {task_label} task 超时且从未登记任何 task"
                            f"（user_id={user_id}, task_id={business_task_id}，"
                            f"timeout={timeout_seconds}s）：add 可能未提交后台任务"
                        )
                    detail = "; ".join(f"{r.task_id}: {r.status}" for r in records)
                    raise ConfigurationError(
                        f"等待 MemOS 后台 {task_label} task 超时"
                        f"（user_id={user_id}, task_id={business_task_id}，"
                        f"timeout={timeout_seconds}s）：预期 {expected_task_count} 条终态，"
                        f"实际 {len(terminal)} 条；当前状态 {detail}"
                    )
                self._condition.wait(remaining)

    def pending_tasks(self) -> list[dict[str, Any]]:
        """返回所有尚未到达终态的 task payload（供关闭前自检）。"""
        with self._condition:
            return [
                r.to_payload()
                for r in self._records.values()
                if r.status not in _TERMINAL_STATUSES
            ]

    def assert_no_pending_tasks(self) -> None:
        """关闭前置门：仍有未完成 task 时 fail-fast，不静默关闭。

        Raises:
            ConfigurationError: 存在未到达终态的 task。
        """
        pending = self.pending_tasks()
        if pending:
            detail = "; ".join(
                f"{p.get('business_task_id') or '<no-business-id>'}"
                f"/{p.get('task_type')}={p.get('status')}"
                for p in pending
            )
            raise ConfigurationError(
                f"MemOS scheduler 仍有 {len(pending)} 个未完成 task，拒绝静默关闭：{detail}"
            )

    def reset(self) -> None:
        """清空跟踪表（仅供同一 worker 复用实例时显式调用）。"""
        with self._condition:
            self._records.clear()
            self._business_index.clear()
            self._condition.notify_all()


def install_local_tracker(
    scheduler: Any, tracker: MemosLocalTaskTracker | None = None
) -> MemosLocalTaskTracker:
    """把同一个 tracker 实例安装到 scheduler 与其 dispatcher 上。

    MemOS 的 ``BaseScheduler.status_tracker`` setter 会把值向 dispatcher 与
    message queue 传播；但该 setter 只在 ``use_redis_queue`` 时才惰性自建，因此这里
    显式赋值并复核 dispatcher 已拿到同一个对象。

    Args:
        scheduler: 已构造的 MemOS scheduler（``OptimizedScheduler`` 等）。
        tracker: 复用的 tracker；为 ``None`` 时新建。

    Returns:
        实际安装的 tracker 实例。

    Raises:
        ConfigurationError: scheduler 没有 dispatcher，或安装后两侧不是同一实例。
    """
    tracker = tracker if tracker is not None else MemosLocalTaskTracker()
    scheduler.status_tracker = tracker

    dispatcher = getattr(scheduler, "dispatcher", None)
    if dispatcher is None:
        raise ConfigurationError(
            "MemOS scheduler 没有 dispatcher，无法安装 task tracker；"
            "请确认 scheduler 已 initialize_modules"
        )
    # setter 未必覆盖所有版本的传播路径，显式对齐一次并复核。
    dispatcher.status_tracker = tracker

    if getattr(scheduler, "status_tracker", None) is not tracker:
        raise ConfigurationError("MemOS scheduler.status_tracker 安装失败：实例不一致")
    if getattr(dispatcher, "status_tracker", None) is not tracker:
        raise ConfigurationError("MemOS dispatcher.status_tracker 安装失败：实例不一致")
    return tracker
