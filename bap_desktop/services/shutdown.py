"""Coordinated cleanup for Desktop App process-lifetime resources."""

from __future__ import annotations

from collections.abc import Callable


class ShutdownCoordinator:
    """Run registered cleanup callbacks once, in reverse registration order."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[[], None]] = []
        self._completed = False

    def register(self, callback: Callable[[], None]) -> None:
        if self._completed:
            callback()
            return
        self._callbacks.append(callback)

    def unregister(self, callback: Callable[[], None]) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    def shutdown(self) -> None:
        if self._completed:
            return
        self._completed = True
        for callback in reversed(self._callbacks):
            try:
                callback()
            except Exception:
                # Closing the App must continue even if one optional cleanup fails.
                pass
        self._callbacks.clear()

