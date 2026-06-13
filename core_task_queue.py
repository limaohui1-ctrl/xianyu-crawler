"""
Thread-safe priority task queue with:

  - Priority ordering (0 = highest, 9 = lowest)
  - Delayed / scheduled tasks (execute after a timestamp)
  - Dead Letter Queue (DLQ) for tasks that fail after max_retries
  - Dynamic concurrency scaling based on API health
  - Task lifecycle: PENDING → RUNNING → COMPLETED / FAILED / DLQ'D

Integration point: UniversalCollector and AIWorker feed tasks into this queue.
The queue is designed to be consumed by multiple worker threads.

Usage:
    from core_task_queue import TaskQueue, TaskItem, TaskPriority

    queue = TaskQueue(max_workers=4)
    queue.submit(TaskItem(
        url="https://example.com", priority=TaskPriority.NORMAL,
    ))
    while queue.pending:
        task = queue.dequeue()
        process(task)
        queue.mark_completed(task)
"""

import heapq
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════
# Priority levels
# ═══════════════════════════════════════════════════════════════════

class TaskPriority(IntEnum):
    CRITICAL = 0    # user-initiated, must run NOW
    HIGH = 1        # important batch item
    NORMAL = 5      # default
    LOW = 7         # background refresh / scheduled
    BEST_EFFORT = 9 # can be dropped under load


# ═══════════════════════════════════════════════════════════════════
# Task item
# ═══════════════════════════════════════════════════════════════════

@dataclass(order=False)
class TaskItem:
    """A single unit of work in the queue."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    url: str = ""
    template_name: str = ""
    priority: int = TaskPriority.NORMAL
    max_retries: int = 3
    retry_count: int = 0
    scheduled_at: float = 0.0          # unix timestamp — delay until ready
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    status: str = "PENDING"            # PENDING | RUNNING | COMPLETED | FAILED | DLQ
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other: "TaskItem") -> bool:
        """Heap ordering: lower priority value = higher priority.
        Ties broken by creation time (older first)."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


# ═══════════════════════════════════════════════════════════════════
# Dead Letter Queue
# ═══════════════════════════════════════════════════════════════════

class DeadLetterQueue:
    """Holds tasks that failed after all retries.  Inspectable for debugging."""

    def __init__(self, max_size: int = 1000):
        self._items: List[TaskItem] = []
        self._lock = threading.Lock()
        self.max_size = max_size

    def push(self, task: TaskItem):
        task.status = "DLQ"
        task.completed_at = time.time()
        with self._lock:
            self._items.append(task)
            if len(self._items) > self.max_size:
                self._items = self._items[-self.max_size:]

    def all(self) -> List[TaskItem]:
        with self._lock:
            return list(self._items)

    def retry_all(self, queue: "TaskQueue"):
        """Re-enqueue all DLQ tasks (reset retry count)."""
        with self._lock:
            for task in self._items:
                task.retry_count = 0
                task.status = "PENDING"
                task.error_message = ""
                queue._push(task)
            self._items.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._items), "max_size": self.max_size}


# ═══════════════════════════════════════════════════════════════════
# Task Queue
# ═══════════════════════════════════════════════════════════════════

class TaskQueue:
    """Thread-safe priority task queue with delayed execution and DLQ.

    Supports:
      - submit(task)        — enqueue immediately or at scheduled_at
      - dequeue()           — pop highest-priority ready task
      - mark_completed(id)  — record completion
      - mark_failed(id, err)— retry or move to DLQ
      - dynamic scale_up/scale_down based on error rate

    The queue does NOT execute tasks — it only manages scheduling.
    Worker threads poll dequeue() and call mark_*() when done.
    """

    def __init__(self, max_workers: int = 3, retry_delay_base: float = 2.0):
        self.max_workers = max_workers
        self.retry_delay_base = retry_delay_base
        self._heap: List[TaskItem] = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self.dlq = DeadLetterQueue()
        self._active_tasks: Dict[str, TaskItem] = {}
        self._completed_count = 0
        self._failed_count = 0

    # ── Enqueue ─────────────────────────────────────────────────

    def submit(self, task: TaskItem):
        """Enqueue a task.  If scheduled_at is in the future, it won't be
        dequeued until that time."""
        with self._lock:
            self._push(task)
            self._not_empty.notify()

    def submit_batch(self, tasks: List[TaskItem]):
        with self._lock:
            for task in tasks:
                self._push(task)
            self._not_empty.notify_all()

    def _push(self, task: TaskItem):
        task.status = "PENDING"
        if not task.created_at:
            task.created_at = time.time()
        heapq.heappush(self._heap, task)

    # ── Dequeue ─────────────────────────────────────────────────

    def dequeue(self, timeout: Optional[float] = None) -> Optional[TaskItem]:
        """Pop the highest-priority ready task.  Blocks up to *timeout* seconds.

        Returns None on timeout or if queue is empty.
        Skips tasks whose scheduled_at is in the future.
        """
        deadline = time.time() + timeout if timeout is not None else None
        with self._lock:
            while True:
                # Check for ready task
                ready = self._peek_ready()
                if ready:
                    task = heapq.heappop(self._heap)
                    task.started_at = time.time()
                    task.status = "RUNNING"
                    self._active_tasks[task.id] = task
                    return task

                # No ready task — wait or return
                if timeout is not None:
                    remaining = deadline - time.time()
                    if remaining <= 0:
                        return None
                    self._not_empty.wait(timeout=min(remaining, 1.0))
                else:
                    self._not_empty.wait()

    def _peek_ready(self) -> bool:
        """Check if the heap top is ready (scheduled_at <= now)."""
        if not self._heap:
            return False
        return self._heap[0].scheduled_at <= time.time()

    # ── Completion / failure ────────────────────────────────────

    def mark_completed(self, task_id: str):
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
            if task:
                task.status = "COMPLETED"
                task.completed_at = time.time()
                self._completed_count += 1

    def mark_failed(self, task_id: str, error_message: str = ""):
        """Record a failure.  If retries remain, re-enqueue with backoff."""
        with self._lock:
            task = self._active_tasks.pop(task_id, None)
            if not task:
                return
            task.error_message = str(error_message)[:500]
            task.retry_count += 1
            if task.retry_count < task.max_retries:
                # Re-enqueue with exponential backoff
                delay = self.retry_delay_base * (2 ** (task.retry_count - 1))
                task.scheduled_at = time.time() + delay
                task.status = "PENDING"
                self._push(task)
                self._not_empty.notify()
            else:
                # Move to DLQ
                self.dlq.push(task)
                self._failed_count += 1

    def cancel(self, task_id: str) -> bool:
        """Remove a task from the queue if still PENDING.  Returns True if removed."""
        with self._lock:
            # Remove from heap (rebuild — acceptable for occasional cancel)
            for i, task in enumerate(self._heap):
                if task.id == task_id:
                    self._heap.pop(i)
                    heapq.heapify(self._heap)
                    return True
            # Also check active
            if task_id in self._active_tasks:
                del self._active_tasks[task_id]
                return True
        return False

    # ── Dynamic concurrency scaling ─────────────────────────────

    def scale_up(self):
        """Increase concurrency (capped at a hard maximum of 20)."""
        with self._lock:
            self.max_workers = min(self.max_workers + 1, 20)

    def scale_down(self):
        """Decrease concurrency (floor at 1)."""
        with self._lock:
            self.max_workers = max(self.max_workers - 1, 1)

    def adjust_concurrency(self, error_rate: float, target_error_rate: float = 0.1):
        """Auto-scale based on recent error rate.

        error_rate > target → scale down (too many failures)
        error_rate < target/2 → scale up (healthy, room for more)
        """
        if error_rate > target_error_rate and self.max_workers > 1:
            self.scale_down()
        elif error_rate < target_error_rate / 2 and self.max_workers < 20:
            self.scale_up()

    # ── Introspection ───────────────────────────────────────────

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._heap)

    @property
    def active(self) -> int:
        with self._lock:
            return len(self._active_tasks)

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "pending": len(self._heap),
                "active": len(self._active_tasks),
                "max_workers": self.max_workers,
                "completed": self._completed_count,
                "failed": self._failed_count,
                "dlq_size": self.dlq.size,
            }

    def ready_tasks(self, limit: int = 50) -> List[TaskItem]:
        """List ready (non-future) pending tasks without dequeuing."""
        with self._lock:
            ready = [t for t in self._heap if t.scheduled_at <= time.time()]
            ready.sort()
            return ready[:limit]

    def all_tasks(self) -> List[TaskItem]:
        with self._lock:
            return sorted(list(self._heap))


# ═══════════════════════════════════════════════════════════════════
# Global singleton
# ═══════════════════════════════════════════════════════════════════

_default_queue: Optional[TaskQueue] = None
_queue_lock = threading.Lock()


def get_task_queue(max_workers: int = 3) -> TaskQueue:
    global _default_queue
    if _default_queue is None:
        with _queue_lock:
            if _default_queue is None:
                _default_queue = TaskQueue(max_workers=max_workers)
    return _default_queue


def reset_task_queue():
    global _default_queue
    with _queue_lock:
        _default_queue = None
