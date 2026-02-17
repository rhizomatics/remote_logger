"""Unit tests for the OTEL exporter."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from custom_components.remote_logger.otel.exporter import (
    OtlpLogExporter,
    _kv,
    parse_resource_attributes,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# ---------------------------------------------------------------------------
# parse_resource_attributes
# ---------------------------------------------------------------------------


class TestParseResourceAttributes:
    def test_simple_pair(self) -> None:
        assert parse_resource_attributes("env=prod") == [("env", "prod")]

    def test_multiple_pairs(self) -> None:
        result = parse_resource_attributes("env=prod,region=us-east-1")
        assert result == [("env", "prod"), ("region", "us-east-1")]

    def test_whitespace_handling(self) -> None:
        result = parse_resource_attributes("  env = prod , region = us-east-1  ")
        assert result == [("env", "prod"), ("region", "us-east-1")]

    def test_empty_string(self) -> None:
        assert parse_resource_attributes("") == []

    def test_blank_string(self) -> None:
        assert parse_resource_attributes("   ") == []

    def test_trailing_comma(self) -> None:
        assert parse_resource_attributes("env=prod,") == [("env", "prod")]

    def test_value_with_equals(self) -> None:
        result = parse_resource_attributes("key=val=ue")
        assert result == [("key", "val=ue")]

    def test_empty_value(self) -> None:
        result = parse_resource_attributes("key=")
        assert result == [("key", "")]

    def test_missing_equals_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid attribute pair"):
            parse_resource_attributes("no_equals_sign")

    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="key cannot be empty"):
            parse_resource_attributes("=value")


# ---------------------------------------------------------------------------
# _kv helper
# ---------------------------------------------------------------------------


class TestKv:
    def test_string_value(self) -> None:
        assert _kv("key", "val") == {"key": "key", "value": {"string_value": "val"}}

    def test_int_value(self) -> None:
        assert _kv("key", 42) == {"key": "key", "value": {"int_value": 42}}

    def test_bool_value(self) -> None:
        # Note: bool is subclass of int, so isinstance(True, int) matches first in _kv
        assert _kv("key", True) == {"key": "key", "value": {"int_value": True}}

    def test_float_value(self) -> None:
        assert _kv("key", 3.14) == {"key": "key", "value": {"float_value": 3.14}}

    def test_bytes_value(self) -> None:
        assert _kv("key", b"data") == {"key": "key", "value": {"byte_value": b"data"}}

    def test_other_value_becomes_string(self) -> None:
        result = _kv("key", [1, 2, 3])
        assert result == {"key": "key", "value": {"string_value": "[1, 2, 3]"}}


# ---------------------------------------------------------------------------
# OtlpLogExporter
# ---------------------------------------------------------------------------


class TestOtlpLogExporter:
    @pytest.fixture
    def exporter(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> OtlpLogExporter:
        return OtlpLogExporter(hass, mock_entry_otel)

    @pytest.fixture
    def exporter_with_attrs(self, hass: HomeAssistant, mock_entry_otel_protobuf: MagicMock) -> OtlpLogExporter:
        return OtlpLogExporter(hass, mock_entry_otel_protobuf)

    def test_endpoint_url_http(self, exporter: OtlpLogExporter) -> None:
        assert exporter.endpoint_url == "http://localhost:4318/v1/logs"

    def test_endpoint_url_https(self, hass: HomeAssistant) -> None:
        entry = MagicMock()
        entry.data = {
            "host": "otel.example.com",
            "port": 443,
            "use_tls": True,
            "encoding": "json",
            "batch_max_size": 20,
            "resource_attributes": "",
        }
        exp = OtlpLogExporter(hass, entry)
        assert exp.endpoint_url == "https://otel.example.com:443/v1/logs"

    def test_resource_has_service_name(self, exporter: OtlpLogExporter) -> None:
        attrs = exporter._resource["attributes"]
        keys = [a["key"] for a in attrs]
        assert "service.name" in keys
        assert "service.version" in keys

    def test_resource_custom_attributes(self, exporter_with_attrs: OtlpLogExporter) -> None:
        attrs = exporter_with_attrs._resource["attributes"]
        keys = [a["key"] for a in attrs]
        assert "env" in keys
        assert "region" in keys

    def test_to_log_record_full(self, exporter: OtlpLogExporter, sample_event_data: dict[str, Any]) -> None:
        record = exporter._to_log_record(sample_event_data)

        assert record["severityNumber"] == 17
        assert record["severityText"] == "ERROR"
        assert record["body"] == {"string_value": "Something went wrong"}
        assert "timeUnixNano" in record
        assert "observedTimeUnixNano" in record

        attr_keys = [a["key"] for a in record["attributes"]]
        assert "code.file.path" in attr_keys
        assert "code.line.number" in attr_keys
        assert "code.function.name" in attr_keys
        assert "exception.stacktrace" in attr_keys
        assert "exception.count" in attr_keys
        assert "exception.first_occurred" in attr_keys

    def test_to_log_record_minimal(self, exporter: OtlpLogExporter, minimal_event_data: dict[str, Any]) -> None:
        record = exporter._to_log_record(minimal_event_data)

        assert record["severityNumber"] == 9
        assert record["severityText"] == "INFO"
        assert record["body"] == {"string_value": "Simple info message"}
        # No source, name, exception attributes
        assert record["attributes"] == []

    def test_to_log_record_unknown_level(self, exporter: OtlpLogExporter) -> None:
        record = exporter._to_log_record({"level": "TRACE", "message": ["test"]})
        # Falls back to default severity (INFO)
        assert record["severityNumber"] == 9
        assert record["severityText"] == "INFO"

    def test_to_log_record_multiple_messages(self, exporter: OtlpLogExporter) -> None:
        record = exporter._to_log_record({"message": ["line 1", "line 2", "line 3"]})
        assert record["body"]["string_value"] == "line 1\nline 2\nline 3"

    def test_to_protobuf(self, exporter: OtlpLogExporter, sample_event_data: dict[str, Any]) -> None:
        record = exporter._to_log_record(sample_event_data)
        exporter._use_protobuf = True
        result = exporter.generate_submission([record])
        assert result["data"] is not None
        assert isinstance(result["data"], bytes)
        assert len(result["data"]) > 400

    def test_to_json(self, exporter: OtlpLogExporter, sample_event_data: dict[str, Any]) -> None:
        record = exporter._to_log_record(sample_event_data)
        exporter._use_protobuf = False
        result = exporter.generate_submission([record])
        payload = json.dumps(result["json"])
        assert (
            payload[:324]
            == '{"resourceLogs": [{"resource": {"attributes": [{"key": "service.name", "value": {"string_value": "core"}}, '
            '{"key": "service.version", "value": {"string_value": "2026.1.1"}}]}, "scopeLogs": '
            '[{"scope": {"name": "homeassistant", "version": "1.0.0"}, "logRecords": '
            '[{"timeUnixNano": "1700000000000000000", "observedTimeUnixNano"'
        )

    def test_handle_event_buffers(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        assert len(exporter._buffer) == 0
        exporter.handle_event(mock_event)
        assert len(exporter._buffer) == 1

    def test_handle_event_loop_check_(self, exporter: OtlpLogExporter) -> None:
        """Tuple `in` check doesn't do substring matching on elements."""
        event = MagicMock()
        event.data = {
            "message": ["some otel error"],
            "level": "ERROR",
            "source": ("custom_components/remote_logger/otel/exporter.py", 100),
        }
        exporter.handle_event(event)
        assert len(exporter._buffer) == 0

    def test_handle_event_allows_non_otel_source(self, exporter: OtlpLogExporter) -> None:
        event = MagicMock()
        event.data = {
            "message": ["some error"],
            "level": "ERROR",
            "source": ("homeassistant/core.py", 50),
        }
        exporter.handle_event(event)
        assert len(exporter._buffer) == 1

    def test_build_export_request_structure(self, exporter: OtlpLogExporter) -> None:
        records = [{"body": {"string_value": "test"}, "severityNumber": 9}]
        request = exporter._build_export_request(records)

        assert "resourceLogs" in request
        rl = request["resourceLogs"][0]
        assert "resource" in rl
        assert "scopeLogs" in rl
        sl = rl["scopeLogs"][0]
        assert sl["scope"]["name"] == "homeassistant"
        assert sl["scope"]["version"] == "1.0.0"
        assert sl["logRecords"] == records

    async def test_flush_empty_buffer_is_noop(self, exporter: OtlpLogExporter) -> None:
        # Should not raise and not attempt any HTTP calls
        await exporter.flush()
        assert len(exporter._buffer) == 0
