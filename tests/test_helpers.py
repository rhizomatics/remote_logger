import datetime as dt
from unittest.mock import patch

from custom_components.remote_logger.helpers import isotimestamp


def test_bad_time() -> None:
    assert isotimestamp(-1) is None


@patch("custom_components.remote_logger.helpers.dt_util.get_default_time_zone", lambda: dt.UTC)
def test_utc_time() -> None:
    assert isotimestamp(1771491792.3491662) == "2026-02-19T09:03:12.349166Z"


@patch("custom_components.remote_logger.helpers.dt_util.get_default_time_zone", lambda: dt.timezone(dt.timedelta(hours=3)))
def test_offset_time() -> None:
    assert isotimestamp(1771491792.3491662) == "2026-02-19T12:03:12.349166+03:00"
