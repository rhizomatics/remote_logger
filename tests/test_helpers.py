import datetime as dt
from unittest.mock import patch

from custom_components.remote_logger.helpers import flatten_event_data, isotimestamp


def test_bad_time() -> None:
    assert isotimestamp(-1) is None


@patch("custom_components.remote_logger.helpers.dt_util.get_default_time_zone", lambda: dt.UTC)
def test_utc_time() -> None:
    assert isotimestamp(1771491792.3491662) == "2026-02-19T09:03:12.349166Z"


@patch("custom_components.remote_logger.helpers.dt_util.get_default_time_zone", lambda: dt.timezone(dt.timedelta(hours=3)))
def test_offset_time() -> None:
    assert isotimestamp(1771491792.3491662) == "2026-02-19T12:03:12.349166+03:00"


class TestFlattenEventData:
    def test_scalar_returned_as_is(self) -> None:
        assert flatten_event_data("a.b", "hello", False) == [("a.b", "hello")]

    def test_scalar_int(self) -> None:
        assert flatten_event_data("a.b", 42, False) == [("a.b", 42)]

    def test_dict_flattened(self) -> None:
        result = flatten_event_data("ev", {"x": 1, "y": "two"}, False)
        assert ("ev.x", 1) in result
        assert ("ev.y", "two") in result

    def test_nested_dict_flattened_recursively(self) -> None:
        result = flatten_event_data("ev", {"outer": {"inner": "val"}}, False)
        assert result == [("ev.outer.inner", "val")]

    def test_as_dict_called(self) -> None:
        class Obj:
            def as_dict(self) -> dict:
                return {"k": "v"}

        assert flatten_event_data("ev", Obj(), False) == [("ev.k", "v")]

    def test_as_dict_nested(self) -> None:
        class Nested:
            def as_dict(self) -> dict:
                return {"a": 1, "b": 2}

        result = flatten_event_data("ev", {"child": Nested()}, False)
        assert ("ev.child.a", 1) in result
        assert ("ev.child.b", 2) in result

    def test_dict_flattened_with_attrs(self) -> None:
        data = {"new": {"state": "on", "attributes": {"foo": 1, "bar": False}}}
        result = flatten_event_data("ev", data, False)
        assert result == [("ev.new.state", "on"), ("ev.new.attributes.foo", 1), ("ev.new.attributes.bar", False)]

    def test_dict_flattened_without_attrs(self) -> None:
        data = {"new": {"state": "on", "attributes": {"foo": 1, "bar": False}}}
        result = flatten_event_data("ev", data, True)
        assert result == [("ev.new.state", "on")]
