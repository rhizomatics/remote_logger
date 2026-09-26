"""Unit tests for custom_components.remote_logger (setup/unload)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.remote_logger.config_flow import OtelLogsConfigFlow
from custom_components.remote_logger.const import CONF_EVENT_BASED_LOGGING, DOMAIN
from custom_components.remote_logger.otel.exporter import OtlpJsonSubmission, OtlpMessage, OtlpProtobufSubmission

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from custom_components.remote_logger.remote_logger import RemoteLoggerConfigEntry

type SetupEntry = Callable[[ConfigEntry], Awaitable[RemoteLoggerConfigEntry]]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


@pytest.fixture
async def setup_entry(hass: HomeAssistant) -> AsyncGenerator[SetupEntry]:
    """Set up a real config entry, built from a mock entry's data, and unload it afterwards."""
    entries: list[MockConfigEntry] = []

    async def _setup(template: ConfigEntry) -> RemoteLoggerConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=OtelLogsConfigFlow.VERSION,
            entry_id=template.entry_id,
            title=template.title,
            # Event-based logging keeps HA's own setup logging out of the exporter buffer
            data={**template.data, CONF_EVENT_BASED_LOGGING: True},
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entries.append(entry)
        return entry

    yield _setup
    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)


class TestSendLogService:
    async def test_service_registered_on_otel_setup(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        await setup_entry(mock_entry_otel)

        assert hass.services.has_service("remote_logger", "send_log")

    async def test_service_registered_on_syslog_setup(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_syslog: MagicMock
    ) -> None:
        await setup_entry(mock_entry_syslog)

        assert hass.services.has_service("remote_logger", "send_log")

    async def test_send_log_routes_to_otel_exporter(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        entry = await setup_entry(mock_entry_otel)

        exporter = entry.runtime_data.exporter

        await hass.services.async_call(
            "remote_logger",
            "send_log",
            {"event": "unit_test", "message": "direct log", "level": "ERROR"},
            blocking=True,
        )

        assert len(exporter._buffer) == 1
        assert exporter._buffer[0].payload["body"] == {"stringValue": "direct log"}
        assert exporter._buffer[0].payload["severityNumber"] == 17

    async def test_send_log_routes_to_syslog_exporter(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_syslog: MagicMock
    ) -> None:
        entry = await setup_entry(mock_entry_syslog)

        exporter = entry.runtime_data.exporter

        await hass.services.async_call(
            "remote_logger",
            "send_log",
            {"event": "unit_test", "message": "syslog direct"},
            blocking=True,
        )

        assert len(exporter._buffer) == 1
        assert b"syslog direct" in exporter._buffer[0].payload

    async def test_send_log_not_registered_twice(
        self,
        hass: HomeAssistant,
        setup_entry: SetupEntry,
        mock_entry_otel: MagicMock,
        mock_entry_syslog: MagicMock,
    ) -> None:
        """Service is registered once even when multiple entries are set up."""
        await setup_entry(mock_entry_otel)
        await setup_entry(mock_entry_syslog)

        assert hass.services.has_service("remote_logger", "send_log")


class TestFlushService:
    async def test_flush_service_registered(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        await setup_entry(mock_entry_otel)

        assert hass.services.has_service("remote_logger", "flush")

    async def test_flush_service_calls_exporter_flush(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        entry = await setup_entry(mock_entry_otel)

        exporter = entry.runtime_data.exporter

        with patch.object(exporter, "flush", AsyncMock()) as mock_flush:
            await hass.services.async_call("remote_logger", "flush", blocking=True)

        mock_flush.assert_awaited_once()

    async def test_flush_not_registered_twice(
        self,
        hass: HomeAssistant,
        setup_entry: SetupEntry,
        mock_entry_otel: MagicMock,
        mock_entry_syslog: MagicMock,
    ) -> None:
        await setup_entry(mock_entry_otel)
        await setup_entry(mock_entry_syslog)

        assert hass.services.has_service("remote_logger", "flush")


class TestLastLogService:
    async def test_last_log_service_registered(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        await setup_entry(mock_entry_otel)

        assert hass.services.has_service("remote_logger", "last_log")

    async def test_last_log_returns_empty_before_any_send(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        await setup_entry(mock_entry_otel)

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result == {}

    async def test_last_log_returns_payload_after_send(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        entry = await setup_entry(mock_entry_otel)

        exporter = entry.runtime_data.exporter
        exporter.last_sent_payload = OtlpJsonSubmission(
            {},
            records=[OtlpMessage(payload={"body": {"stringValue": "hello"}, "severityText": "INFO"})],
        )

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result == {
            "headers": {"Content-Type": "application/json"},
            "json": {
                "resourceLogs": [
                    {
                        "resource": {},
                        "scopeLogs": [
                            {
                                "scope": {"name": "homeassistant", "version": "1.0.0"},
                                "logRecords": [{"body": {"stringValue": "hello"}, "severityText": "INFO"}],
                            },
                        ],
                    },
                ],
            },
        }

    async def test_last_log_otel_json_after_flush(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        from unittest.mock import AsyncMock as _AsyncMock
        from unittest.mock import patch as _patch

        entry = await setup_entry(mock_entry_otel)

        exporter = entry.runtime_data.exporter
        exporter.log_direct("test.event", "hello json", "INFO")

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status = 200
        mock_resp.__aenter__ = _AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = _AsyncMock(return_value=False)

        with _patch("aiohttp.ClientSession.post", return_value=mock_resp):
            await exporter.flush()

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result["headers"]["Content-Type"] == "application/json"
        log_record = result["json"]["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
        assert log_record["body"]["stringValue"] == "hello json"

    async def test_last_log_otel_protobuf_after_flush(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel_protobuf: MagicMock
    ) -> None:
        from unittest.mock import AsyncMock as _AsyncMock
        from unittest.mock import patch as _patch

        entry = await setup_entry(mock_entry_otel_protobuf)

        exporter = entry.runtime_data.exporter
        exporter.log_direct("test.event", "hello protobuf", "WARNING")

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.status = 200
        mock_resp.__aenter__ = _AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = _AsyncMock(return_value=False)

        with _patch("aiohttp.ClientSession.post", return_value=mock_resp):
            await exporter.flush()

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel_protobuf.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result["headers"]["Content-Type"] == "application/x-protobuf"
        assert isinstance(result["data"], str)
        assert "hello protobuf" in result["data"]
        assert "\ufffd" not in result["data"]

    async def test_last_log_syslog_after_flush(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_syslog: MagicMock
    ) -> None:
        from unittest.mock import AsyncMock as _AsyncMock
        from unittest.mock import patch as _patch

        entry = await setup_entry(mock_entry_syslog)

        exporter = entry.runtime_data.exporter
        exporter.log_direct("test.event", "hello syslog", "ERROR")

        with _patch.object(exporter, "_send_udp", _AsyncMock()) as mock_send:
            mock_send.side_effect = lambda msgs: [setattr(m, "sent", True) for m in msgs]  # type:ignore[func-returns-value]
            await exporter.flush()

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_syslog.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result["protocol"] == "udp"
        assert "hello syslog" in result["data"]

    async def test_last_log_masks_bearer_token_in_json_headers(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        entry = await setup_entry(mock_entry_otel)

        credential = "mysecrettoken123"
        entry.runtime_data.exporter.last_sent_payload = OtlpJsonSubmission(
            {},
            records=[OtlpMessage(payload={})],
            extra_headers={"Authorization": f"Bearer {credential}"},
        )

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result["headers"]["Authorization"] == "Bearer ****************"

    async def test_last_log_masks_bearer_token_in_protobuf_headers(
        self,
        hass: HomeAssistant,
        setup_entry: SetupEntry,
        mock_entry_otel_protobuf: MagicMock,
    ) -> None:
        entry = await setup_entry(mock_entry_otel_protobuf)

        credential = "protosecret99"
        entry.runtime_data.exporter.last_sent_payload = OtlpProtobufSubmission(
            {},
            records=[OtlpMessage(payload={})],
            extra_headers={"Authorization": f"Bearer {credential}"},
        )

        result = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": mock_entry_otel_protobuf.entry_id},
            blocking=True,
            return_response=True,
        )

        assert result["headers"]["Authorization"] == "Bearer *************"

    async def test_last_log_returns_empty_dict_for_unknown_entry(
        self, hass: HomeAssistant, setup_entry: SetupEntry, mock_entry_otel: MagicMock
    ) -> None:
        await setup_entry(mock_entry_otel)

        result: dict[str, Any] = await hass.services.async_call(
            "remote_logger",
            "last_log",
            {"config_entry_id": "nonexistent"},
            blocking=True,
            return_response=True,
        )
        assert result == {}
