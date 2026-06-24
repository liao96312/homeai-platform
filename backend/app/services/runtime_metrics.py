from collections import Counter
from threading import Lock
from typing import Any

_lock = Lock()
_counters: Counter[str] = Counter()
_last_errors: dict[str, str] = {}


def record_runtime_failure(name: str, exc: Exception | str) -> None:
    error_name = exc if isinstance(exc, str) else type(exc).__name__
    with _lock:
        _counters[name] += 1
        _last_errors[name] = str(error_name)


def runtime_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "failures": dict(_counters),
            "lastErrors": dict(_last_errors),
        }
