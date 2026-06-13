"""Method registry for UniversalMainWindow.

Usage in any ui_*.py module:

    from ui_registry import register

    @register("my_method")
    def my_method(self, ...):
        ...

Then in universal_ui.py:

    from ui_registry import bind_all

    class UniversalMainWindow(QMainWindow):
        ...

    bind_all(UniversalMainWindow)

No manual import / binding lines needed.
"""

from __future__ import annotations

from typing import Callable

_PENDING: list[tuple[str, Callable]] = []
_registered = 0


def register(method_name: str) -> Callable:
    """Decorator: register a standalone function as a UniversalMainWindow method."""
    def decorator(func: Callable) -> Callable:
        _PENDING.append((method_name, func))
        global _registered
        _registered += 1
        return func
    return decorator


def bind_all(target_class: type) -> int:
    """Bind all registered functions to the target class. Call once after all modules are imported."""
    count = 0
    for name, func in _PENDING:
        setattr(target_class, name, func)
        count += 1
    _PENDING.clear()
    return count
