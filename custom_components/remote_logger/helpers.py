import datetime as dt
from typing import Any

from homeassistant.util import dt as dt_util


def flatten_event_data(prefix: str, value: Any) -> list[tuple[str, Any]]:
    """Flatten a value into (key, scalar) pairs using dotted key notation.

    If the value has an ``as_dict`` method it is called first.  The resulting
    dict (or any plain dict) is recursively expanded.  Any other value is
    returned as-is as a single pair.
    """
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for k, v in value.items():
            result.extend(flatten_event_data(f"{prefix}.{k}", v))
        return result
    return [(prefix, value)]


def isotimestamp(time_value: float) -> str | None:
    if time_value and isinstance(time_value, float):
        ts = dt.datetime.fromtimestamp(time_value, tz=dt_util.get_default_time_zone())
        if dt_util.get_default_time_zone() == dt.UTC:
            return f"{ts.isoformat()[:26]}Z"
        return f"{ts.isoformat()}"
    return None
