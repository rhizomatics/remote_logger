import datetime as dt

from homeassistant.util import dt as dt_util


def isotimestamp(time_value: float) -> str | None:
    if time_value and isinstance(time_value, float):
        ts = dt.datetime.fromtimestamp(time_value, tz=dt_util.get_default_time_zone())
        if dt_util.get_default_time_zone() == dt.UTC:
            return f"{ts.isoformat()[:26]}Z"
        return f"{ts.isoformat()}"
    return None
