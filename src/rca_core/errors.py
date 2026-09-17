from __future__ import annotations

import functools
from typing import Any, Callable


class RcaError(Exception):
    """Structured error surfaced to the skill. `fix` is a one-sentence instruction."""

    def __init__(self, code: str, message: str, fix: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fix = fix

    def to_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "fix": self.fix}}


def guarded(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap an operation so RcaError becomes the standard error dict."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return fn(*args, **kwargs)
        except RcaError as e:
            return e.to_dict()

    return wrapper
