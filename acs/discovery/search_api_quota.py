"""SearchApiQuota — track daily usage and enforce rate limits."""
import time
import threading
from dataclasses import dataclass, field


@dataclass
class SearchApiQuota:
    daily_limit: int = 100
    remaining: int = 100
    reset_at: float = 0.0       # Unix timestamp of next reset
    calls_made: int = 0
    errors: int = 0
    last_error: str = ""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def check(self) -> bool:
        """Return True if a call can be made now. Auto-resets daily."""
        with self._lock:
            now = time.time()
            if now >= self.reset_at:
                self.remaining = self.daily_limit
                self.reset_at = now + 86400  # next midnight
            if self.remaining <= 0:
                self.last_error = "Daily quota exhausted"
                return False
            return True

    def record_call(self, success: bool = True):
        """Record one API call."""
        with self._lock:
            if self.remaining > 0:
                self.remaining -= 1
            self.calls_made += 1
            if not success:
                self.errors += 1

    def status(self) -> dict:
        """Return quota status for UI display."""
        with self._lock:
            return {
                "daily_limit": self.daily_limit,
                "remaining": self.remaining,
                "calls_made": self.calls_made,
                "errors": self.errors,
                "reset_hours": max(0, round((self.reset_at - time.time()) / 3600, 1)),
            }
