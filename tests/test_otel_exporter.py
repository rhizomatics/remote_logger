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
        assert _kv("key", True) == {"key": "key", "value": {"bool_value": True}}

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

    def test_init_with_api_config(self, mock_entry_otel: MagicMock) -> None:
        mock_hass = MagicMock()
        mock_hass.config.api.local_ip = "192.168.1.100"
        mock_hass.config.api.port = 8123

        exporter = OtlpLogExporter(mock_hass, mock_entry_otel)

        assert exporter.server_address == "192.168.1.100"
        assert exporter.server_port == 8123
        attr_keys = [a["key"] for a in exporter._resource["attributes"]]
        assert "service.address" in attr_keys
        assert "service.port" in attr_keys

    def test_handle_event_triggers_flush_at_batch_size(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import patch

        exporter._batch_max_size = 1
        with patch.object(exporter._hass, "async_create_task") as mock_create_task:
            exporter.handle_event(mock_event)
        mock_create_task.assert_called_once()

    def test_handle_event_exception_is_logged(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import patch

        with patch.object(exporter, "_to_log_record", side_effect=RuntimeError("bad")):
            exporter.handle_event(mock_event)
        assert len(exporter._buffer) == 0

    async def test_flush_loop_cancelled(self, exporter: OtlpLogExporter) -> None:
        import asyncio
        from unittest.mock import patch

        with patch("asyncio.sleep", side_effect=asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                await exporter.flush_loop()

    async def test_flush_sends_data_json(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        exporter.handle_event(mock_event)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch(
            "custom_components.remote_logger.otel.exporter.async_get_clientsession",
            return_value=mock_session,
        ):
            await exporter.flush()

        assert len(exporter._buffer) == 0
        mock_session.post.assert_called_once()

    async def test_flush_logs_on_http_error(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        exporter.handle_event(mock_event)

        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="server error")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch(
            "custom_components.remote_logger.otel.exporter.async_get_clientsession",
            return_value=mock_session,
        ):
            await exporter.flush()
        # Should not raise

    async def test_flush_handles_client_error(self, exporter: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import patch

        import aiohttp

        exporter.handle_event(mock_event)

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("conn failed"))

        with patch(
            "custom_components.remote_logger.otel.exporter.async_get_clientsession",
            return_value=mock_session,
        ):
            await exporter.flush()
        # Should not raise

    async def test_flush_protobuf(self, exporter_with_attrs: OtlpLogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        exporter_with_attrs.handle_event(mock_event)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        with patch(
            "custom_components.remote_logger.otel.exporter.async_get_clientsession",
            return_value=mock_session,
        ):
            await exporter_with_attrs.flush()

        assert len(exporter_with_attrs._buffer) == 0

    async def test_close_is_noop(self, exporter: OtlpLogExporter) -> None:
        await exporter.close()  # Should not raise


class TestOtelValidate:
    async def test_json_success(self) -> None:
        from unittest.mock import AsyncMock

        from custom_components.remote_logger.otel.exporter import validate

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "json")
        assert result == {}

    async def test_protobuf_success(self) -> None:
        from unittest.mock import AsyncMock

        from custom_components.remote_logger.otel.exporter import validate

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "protobuf")
        assert result == {}

    async def test_4xx_returns_cannot_connect(self) -> None:
        from unittest.mock import AsyncMock

        from custom_components.remote_logger.otel.exporter import validate

        mock_resp = MagicMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value="unauthorized")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "json")
        assert result == {"base": "cannot_connect"}

    async def test_5xx_returns_cannot_connect(self) -> None:
        from unittest.mock import AsyncMock

        from custom_components.remote_logger.otel.exporter import validate

        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.text = AsyncMock(return_value="service unavailable")
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_resp)

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "json")
        assert result == {"base": "cannot_connect"}

    async def test_client_error(self) -> None:
        import aiohttp

        from custom_components.remote_logger.otel.exporter import validate

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=aiohttp.ClientError("refused"))

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "json")
        assert result == {"base": "cannot_connect"}

    async def test_unknown_error(self) -> None:
        from custom_components.remote_logger.otel.exporter import validate

        mock_session = MagicMock()
        mock_session.post = MagicMock(side_effect=RuntimeError("unexpected"))

        result = await validate(mock_session, "http://localhost:4318/v1/logs", "json")
        assert result == {"base": "unknown"}

    async def test_unknown_encoding_raises(self) -> None:
        from custom_components.remote_logger.otel.exporter import validate

        mock_session = MagicMock()
        with pytest.raises(ValueError, match="Unknown encoding"):
            await validate(mock_session, "http://localhost/v1/logs", "xml")
