"""Unit tests for the syslog exporter."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import pytest
from homeassistant.util import dt as dt_util

from custom_components.remote_logger.helpers import isotimestamp
from custom_components.remote_logger.syslog.exporter import (
    SyslogExporter,
    SyslogMessage,
    _sd_escape,
    _strict_param_name,
)

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from homeassistant.core import Event, HomeAssistant

# RFC 5424 SD-ELEMENT grammar: SD-NAME is 1-32 PRINTUSASCII excluding '=', SP, ']', '"';
# PARAM-VALUE may only contain '"', '\' and ']' when backslash-escaped.
_SD_NAME = "[" + re.escape("".join(chr(c) for c in range(33, 127) if chr(c) not in '="]')) + "]{1,32}"
_SD_PARAM = _SD_NAME + r'="(?:[^"\\\]]|\\["\\\]])*"'
_SD_ELEMENT = re.compile(r"\[" + _SD_NAME + r"(?: " + _SD_PARAM + r")*\]")


def _sd_block(line: str) -> re.Match[str] | None:
    """Match the STRUCTURED-DATA field of an RFC 5424 line against the grammar."""
    rest = line.split(" ", 6)[6]
    match = _SD_ELEMENT.match(rest)
    if match is None or (match.end() < len(rest) and rest[match.end()] != " "):
        return None
    return match


def _close(coro: Coroutine[Any, Any, Any]) -> None:
    """Stand-in for hass.async_create_task: close the coroutine so it isn't left un-awaited."""
    coro.close()


def _connections(exporter: SyslogExporter) -> tuple[object, object, object]:
    """The exporter's UDP transport, TCP writer and TCP reader, read afresh.

    mypy keeps an attribute narrowed to the mock a test assigned, even across an awaited call that resets it.
    """
    return exporter._udp_transport, exporter._tcp_writer, exporter._tcp_reader


def _mock_writer() -> MagicMock:
    """A StreamWriter stand-in: write() and close() are sync, drain() and wait_closed() are async."""
    writer = MagicMock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    return writer


# ---------------------------------------------------------------------------
# _sd_escape
# ---------------------------------------------------------------------------


class TestSdEscape:
    def test_no_special_chars(self) -> None:
        assert _sd_escape("hello world") == "hello world"

    def test_escape_backslash(self) -> None:
        assert _sd_escape("path\\to") == "path\\\\to"

    def test_escape_double_quote(self) -> None:
        assert _sd_escape('say "hi"') == 'say \\"hi\\"'

    def test_escape_closing_bracket(self) -> None:
        assert _sd_escape("data]end") == "data\\]end"

    def test_escape_all_combined(self) -> None:
        assert _sd_escape('a\\b"c]d') == 'a\\\\b\\"c\\]d'


# ---------------------------------------------------------------------------
# SyslogExporter
# ---------------------------------------------------------------------------


class TestSyslogExporter:
    @pytest.fixture
    def exporter(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> SyslogExporter:
        return SyslogExporter(hass, mock_entry_syslog)

    def test_init_properties(self, exporter: SyslogExporter) -> None:
        assert exporter._host == "syslog.example.com"
        assert exporter._port == 514
        assert exporter._protocol == "udp"
        assert exporter._app_name == "homeassistant"
        assert exporter._facility == 16  # local0
        assert exporter._hostname == "-"

    def test_name_from_entry_title(self, exporter: SyslogExporter) -> None:
        assert exporter.name == "Syslog Remote Logger"

    def test_endpoint_desc(self, exporter: SyslogExporter) -> None:
        url, protocol = exporter.endpoint_desc.split(" ")
        assert protocol == "(UDP)"
        parsed = urlparse(url)
        assert parsed.scheme == "syslog"
        assert parsed.hostname == "syslog.example.com"
        assert parsed.port == 514

    def test_endpoint_desc_tcp_tls(self, hass: HomeAssistant) -> None:
        entry = MagicMock()
        entry.data = {
            "host": "secure.example.com",
            "port": 6514,
            "protocol": "tcp",
            "use_tls": True,
            "app_name": "ha",
            "facility": "local0",
        }
        exp = SyslogExporter(hass, entry)
        assert "+TLS" in exp.endpoint_desc

    def test_to_syslog_message_format(self, exporter: SyslogExporter) -> None:
        data = {
            "name": "homeassistant.components.sensor",
            "message": ["Something went wrong"],
            "level": "ERROR",
            "timestamp": 1700000000.0,
            "exception": "Traceback (most recent call last):\n  File ...\nValueError: bad value",
            "count": 3,
            "first_occurred": 1699999000.0,
        }
        msg = exporter.create_log_record(data, "system_log_event", None)
        text = msg.payload.decode("utf-8")

        # Check RFC 5424 structure: <PRI>1 TIMESTAMP HOSTNAME APP-NAME - - SD MSG
        # PRI = facility(16) * 8 + severity(3 for ERROR) = 131
        assert text.startswith("<131>1 ")
        assert "homeassistant" in text
        assert "Something went wrong" in text

    def test_to_syslog_message_pri_calculation(self, exporter: SyslogExporter) -> None:
        # facility=16 (local0), severity=7 (DEBUG) -> PRI = 16*8 + 7 = 135
        data = {"level": "DEBUG", "message": ["debug msg"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert msg.startswith("<135>1 ")

    def test_to_syslog_message_warning_severity(self, exporter: SyslogExporter) -> None:
        # facility=16, severity=4 (WARNING) -> PRI = 132
        data = {"level": "WARNING", "message": ["warn"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert msg.startswith("<132>1 ")

    def test_to_syslog_message_critical_severity(self, exporter: SyslogExporter) -> None:
        # facility=16, severity=2 (CRITICAL) -> PRI = 130
        data = {"level": "CRITICAL", "message": ["crit"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert msg.startswith("<130>1 ")

    def test_to_syslog_message_default_severity(self, exporter: SyslogExporter) -> None:
        # Unknown level falls back to 6 (INFO) -> PRI = 134
        data = {"level": "TRACE", "message": ["trace"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert msg.startswith("<134>1 ")

    def test_to_syslog_message_includes_timestamp(self, exporter: SyslogExporter) -> None:
        data = {"message": ["test"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        # Should contain ISO 8601 timestamp
        assert "2023-11-14T" in msg

    def test_to_syslog_message_structured_data_with_logger(self, exporter: SyslogExporter) -> None:
        data = {
            "name": "my.logger",
            "message": ["test"],
            "level": "INFO",
            "timestamp": 1700000000.0,
            "count": 5,
            "first_occurred": 1699999000.0,
        }
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert '[opentelemetry code.function.name="my.logger"' in msg
        assert 'exception.count="5"' in msg
        assert 'exception.first_occurred="2023-11-14T13:56:40-08:00"' in msg

    def test_to_syslog_message_no_message(self, exporter: SyslogExporter) -> None:
        data = {"level": "INFO", "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        # Empty message list -> "-"
        # The msg field should be just "-" before any exception
        assert "- -" in msg  # PROCID=- MSGID=-

    def test_to_syslog_message_with_exception(self, exporter: SyslogExporter) -> None:
        data = {
            "message": ["error happened"],
            "level": "ERROR",
            "timestamp": 1700000000.0,
            "exception": "ValueError: bad",
        }
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert "error happened" in msg
        assert "ValueError: bad" in msg

    def test_exception_stacktrace_is_escaped(self, exporter: SyslogExporter) -> None:
        data = {"message": ["x"], "level": "ERROR", "exception": 'ValueError: "bad]" in C:\\path'}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        assert 'exception.stacktrace="ValueError: \\"bad\\]\\" in C:\\\\path"' in msg
        assert _sd_block(msg) is not None

    def test_event_name_is_quoted(self, exporter: SyslogExporter) -> None:
        msg = exporter.create_log_record({}, "homeassistant_started", None).payload.decode("utf-8")
        assert '[opentelemetry eventName="homeassistant_started"]' in msg
        assert _sd_block(msg) is not None

    def test_to_syslog_message_empty_messages(self, exporter: SyslogExporter) -> None:
        data = {"message": [], "level": "INFO", "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        # empty message list -> "-"
        assert " - -" in msg or msg.endswith(" -")

    def test_handle_event_buffers(self, exporter: SyslogExporter, mock_event: MagicMock) -> None:
        assert len(exporter._buffer) == 0
        exporter.handle_event(mock_event)
        assert len(exporter._buffer) == 1

    def test_handle_event_prevents_syslog_loop(self, exporter: SyslogExporter) -> None:
        event = MagicMock()
        event.data = {
            "message": ["syslog error"],
            "level": "ERROR",
            "source": ("custom_components/remote_logger/syslog/exporter.py", 100),
        }
        exporter.handle_event(event)
        assert len(exporter._buffer) == 0

    def test_handle_event_allows_non_syslog_source(self, exporter: SyslogExporter) -> None:
        event = MagicMock()
        event.data = {
            "message": ["some error"],
            "level": "ERROR",
            "source": ("homeassistant/core.py", 50),
        }
        exporter.handle_event(event)
        assert len(exporter._buffer) == 1

    def test_different_facility(self, hass: HomeAssistant) -> None:
        entry = MagicMock()
        entry.data = {
            "host": "localhost",
            "port": 514,
            "protocol": "udp",
            "use_tls": False,
            "app_name": "ha",
            "facility": "daemon",
        }
        exp = SyslogExporter(hass, entry)
        assert exp._facility == 3  # daemon facility code

    async def test_flush_empty_buffer_is_noop(self, exporter: SyslogExporter) -> None:
        await exporter.flush()
        assert len(exporter._buffer) == 0

    def test_to_protobuf(self, exporter: SyslogExporter, sample_log_event: Event) -> None:
        msg = exporter.create_log_record(
            sample_log_event.data,
            sample_log_event.event_type,
            sample_log_event.time_fired,
        ).payload.decode("utf-8")
        assert msg is not None
        assert msg.startswith("<131>")
        assert len(msg) > 300

    def test_handle_event_triggers_flush_at_batch_size(self, exporter: SyslogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import patch

        exporter._batch_max_size = 1
        with patch.object(exporter._hass, "async_create_task", side_effect=_close) as mock_create_task:
            exporter.handle_event(mock_event)
        mock_create_task.assert_called_once()

    async def test_flush_loop_cancelled(self, exporter: SyslogExporter) -> None:
        import asyncio
        from unittest.mock import patch

        with (
            patch("custom_components.remote_logger.exporter.sleep", side_effect=asyncio.CancelledError),
            pytest.raises(asyncio.CancelledError),
        ):
            await exporter.flush_loop()

    async def test_flush_sends_via_udp(self, exporter: SyslogExporter, mock_event: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        exporter.handle_event(mock_event)

        mock_transport = MagicMock()
        mock_transport.is_closing.return_value = False
        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = AsyncMock(return_value=(mock_transport, None))

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await exporter.flush()

        assert len(exporter._buffer) == 0
        mock_transport.sendto.assert_called_once()

    async def test_flush_sends_via_tcp(self, hass: HomeAssistant, mock_event: MagicMock) -> None:
        from unittest.mock import patch

        entry = MagicMock()
        entry.data = {
            "host": "syslog.example.com",
            "port": 514,
            "protocol": "tcp",
            "use_tls": False,
            "app_name": "homeassistant",
            "facility": "local0",
        }
        exporter = SyslogExporter(hass, entry)
        exporter.handle_event(mock_event)

        mock_writer = _mock_writer()
        mock_writer.is_closing.return_value = False

        async def fake_connect() -> None:
            exporter._tcp_writer = mock_writer

        with patch.object(exporter, "_connect_tcp", side_effect=fake_connect):
            await exporter.flush()

        assert len(exporter._buffer) == 0
        mock_writer.drain.assert_awaited_once()

    async def test_send_udp_creates_transport(self, exporter: SyslogExporter) -> None:
        from unittest.mock import AsyncMock, patch

        mock_transport = MagicMock()
        mock_transport.is_closing.return_value = False
        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = AsyncMock(return_value=(mock_transport, None))

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await exporter._send_udp([SyslogMessage(b"hello"), SyslogMessage(b"world")])

        assert exporter._udp_transport is mock_transport
        assert mock_transport.sendto.call_count == 2

    async def test_send_udp_reuses_existing_transport(self, exporter: SyslogExporter) -> None:
        mock_transport = MagicMock()
        mock_transport.is_closing.return_value = False
        exporter._udp_transport = mock_transport

        await exporter._send_udp([SyslogMessage(b"msg")])

        mock_transport.sendto.assert_called_once_with(b"msg")

    async def test_send_udp_os_error_clears_transport(self, exporter: SyslogExporter) -> None:
        from unittest.mock import AsyncMock, patch

        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = AsyncMock(side_effect=OSError("refused"))

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await exporter._send_udp([SyslogMessage(b"msg")])

        assert exporter._udp_transport is None

    async def test_send_tcp_with_existing_writer(self, exporter: SyslogExporter) -> None:
        from unittest.mock import AsyncMock

        # Use MagicMock for is_closing (sync) and AsyncMock only for drain (async)
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        exporter._tcp_writer = mock_writer

        await exporter._send_tcp([SyslogMessage(b"test")])

        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_awaited_once()

    async def test_send_tcp_os_error_closes(self, exporter: SyslogExporter) -> None:
        from unittest.mock import AsyncMock

        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock(side_effect=OSError("broken pipe"))
        exporter._tcp_writer = mock_writer

        await exporter._send_tcp([SyslogMessage(b"test")])
        # Should have called _close_tcp
        assert exporter._tcp_writer is None

    async def test_connect_tcp_no_tls(self, exporter: SyslogExporter) -> None:
        from unittest.mock import AsyncMock, patch

        mock_reader = MagicMock()
        mock_writer = MagicMock()

        with patch("asyncio.open_connection", new=AsyncMock(return_value=(mock_reader, mock_writer))):
            await exporter._connect_tcp()

        assert exporter._tcp_reader is mock_reader
        assert exporter._tcp_writer is mock_writer

    async def test_connect_tcp_with_tls(self, hass: HomeAssistant) -> None:
        from unittest.mock import AsyncMock, patch

        from homeassistant.util.ssl import client_context

        entry = MagicMock()
        entry.data = {
            "host": "secure.host",
            "port": 6514,
            "protocol": "tcp",
            "use_tls": True,
            "app_name": "ha",
            "facility": "local0",
        }
        exporter = SyslogExporter(hass, entry)

        mock_reader = MagicMock()
        mock_writer = MagicMock()

        with patch("asyncio.open_connection", new=AsyncMock(return_value=(mock_reader, mock_writer))) as open_connection:
            await exporter._connect_tcp()

        assert exporter._tcp_writer is mock_writer
        # HA's shared, preloaded client context - not a fresh one loading the CA store in the loop
        assert open_connection.call_args.kwargs["ssl"] is client_context()

    async def test_close_tcp_with_writer(self, exporter: SyslogExporter) -> None:

        mock_writer = _mock_writer()
        exporter._tcp_writer = mock_writer
        exporter._tcp_reader = MagicMock()

        await exporter._close_tcp()

        mock_writer.close.assert_called_once()
        _, writer, reader = _connections(exporter)
        assert writer is None
        assert reader is None

    async def test_close_all_resources(self, exporter: SyslogExporter) -> None:

        mock_udp = MagicMock()
        mock_writer = _mock_writer()
        exporter._udp_transport = mock_udp
        exporter._tcp_writer = mock_writer

        await exporter.close()

        mock_udp.close.assert_called_once()
        udp_transport, writer, _ = _connections(exporter)
        assert udp_transport is None
        assert writer is None

    def test_to_syslog_message_event_data_in_sd(self, exporter: SyslogExporter) -> None:
        data = {
            "domain": "light",
            "service": "turn_on",
        }
        msg = exporter.create_log_record(data, "service_registered", None).payload.decode("utf-8")
        assert 'event.data.domain="light"' in msg
        assert 'event.data.service="turn_on"' in msg

    def test_to_syslog_message_msgid_from_event(self, exporter: SyslogExporter) -> None:
        msg = exporter.create_log_record({}, "component_loaded", None).payload.decode("utf-8")
        # MSGID field (6th SP-delimited token) should be the event type
        parts = msg.split(" ")
        assert parts[5] == "component_loaded"

    def test_to_syslog_message_msgid_default_for_system_log(self, exporter: SyslogExporter) -> None:
        data = {"level": "ERROR", "message": ["err"], "timestamp": 1700000000.0}
        msg = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        parts = msg.split(" ")
        assert parts[5] == "-"

    def test_handle_ha_event_buffers(self, exporter: SyslogExporter) -> None:
        event = MagicMock()
        event.time_fired.timestamp.return_value = 1700000000.0
        event.data = {"domain": "light"}
        exporter.handle_ha_event("homeassistant_stop", event)
        assert len(exporter._buffer) == 1
        assert exporter.event_count == 1


class TestSyslogHandleEntry:
    """handle_entry is called by the root log handler, often from worker threads with no running loop."""

    @pytest.fixture
    def mock_hass(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def exporter(self, mock_hass: MagicMock, mock_entry_syslog: MagicMock) -> SyslogExporter:
        exporter = SyslogExporter(mock_hass, mock_entry_syslog)
        exporter._batch_max_size = 1
        return exporter

    def test_flush_handed_to_running_loop(
        self, exporter: SyslogExporter, mock_hass: MagicMock, sample_event_data: dict[str, Any]
    ) -> None:
        mock_hass.loop.is_running.return_value = True
        mock_hass.create_task.side_effect = _close
        exporter.handle_entry(sample_event_data, dt_util.utcnow())
        mock_hass.create_task.assert_called_once()
        assert len(exporter._buffer) == 1

    def test_no_flush_once_loop_stopped(
        self, exporter: SyslogExporter, mock_hass: MagicMock, sample_event_data: dict[str, Any]
    ) -> None:
        # At the end of shutdown HA's loop has stopped or closed: scheduling a flush would leave the
        # coroutine un-awaited, and create_task raising on a closed loop was counted as a format error
        mock_hass.loop.is_running.return_value = False
        mock_hass.create_task.side_effect = RuntimeError("Event loop is closed")
        exporter.handle_entry(sample_event_data, dt_util.utcnow())
        mock_hass.create_task.assert_not_called()
        assert len(exporter._buffer) == 1
        assert exporter.format_error_count == 0


class TestSyslogLogDirectMethod:
    @pytest.fixture
    def exporter(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> SyslogExporter:
        return SyslogExporter(hass, mock_entry_syslog)

    def test_log_direct_buffers_record(self, exporter: SyslogExporter) -> None:
        exporter.log_direct("unit_test", "hello syslog", "INFO")
        assert len(exporter._buffer) == 1
        assert exporter.event_count == 1

    def test_log_direct_message_in_payload(self, exporter: SyslogExporter) -> None:
        exporter.log_direct("unit_test", "my message", "INFO")
        payload = exporter._buffer[0].payload.decode()
        assert "my message" in payload

    def test_log_direct_rfc5424_format(self, exporter: SyslogExporter) -> None:
        exporter.log_direct("unit_test", "test", "ERROR")
        payload = exporter._buffer[0].payload.decode()
        # <PRI>1 TIMESTAMP HOSTNAME APP-NAME PROCID MSGID SD MSG
        assert payload.startswith("<")
        assert ">1 " in payload
        assert "homeassistant" in payload

    def test_log_direct_with_attributes(self, exporter: SyslogExporter) -> None:
        exporter.log_direct("unit_test", "msg", "INFO", {"env": "prod"})
        payload = exporter._buffer[0].payload.decode()
        assert 'env="prod"' in payload

    def test_log_direct_no_attributes_uses_nil_sd(self, exporter: SyslogExporter) -> None:
        exporter.log_direct("unit_test", "msg", "WARNING")
        payload = exporter._buffer[0].payload.decode()
        assert " - " in payload  # nil SD field

    def test_log_direct_triggers_flush_at_batch_size(self, exporter: SyslogExporter) -> None:
        from unittest.mock import patch

        exporter._batch_max_size = 1
        with patch.object(exporter._hass, "async_create_task", side_effect=_close) as mock_create_task:
            exporter.log_direct("unit_test", "msg", "INFO")
        mock_create_task.assert_called_once()


class TestSyslogValidate:
    async def test_udp_success(self, hass: HomeAssistant) -> None:
        from unittest.mock import patch

        from custom_components.remote_logger.syslog.exporter import validate

        with patch("socket.socket"):
            with patch("socket.getaddrinfo", return_value=[("AF_INET", "SOCK_DGRAM", 0, "", ("127.0.0.1", 514))]):
                result = await validate(hass, "localhost", 514, "udp", False)

        assert result is None

    async def test_tcp_success(self, hass: HomeAssistant) -> None:
        from unittest.mock import AsyncMock, patch

        from custom_components.remote_logger.syslog.exporter import validate

        mock_writer = _mock_writer()
        with patch("asyncio.open_connection", new=AsyncMock(return_value=(MagicMock(), mock_writer))):
            result = await validate(hass, "localhost", 514, "tcp", False)

        assert result is None
        mock_writer.close.assert_called_once()

    async def test_tcp_connection_refused(self, hass: HomeAssistant) -> None:
        from unittest.mock import AsyncMock, patch

        from custom_components.remote_logger.syslog.exporter import validate

        with patch("asyncio.open_connection", new=AsyncMock(side_effect=ConnectionRefusedError)):
            result = await validate(hass, "localhost", 514, "tcp", False)

        assert result == "cannot_connect"

    async def test_udp_os_error(self, hass: HomeAssistant) -> None:
        from unittest.mock import patch

        from custom_components.remote_logger.syslog.exporter import validate

        with patch("socket.socket", side_effect=OSError("network unreachable")):
            result = await validate(hass, "localhost", 514, "udp", False)

        assert result == "cannot_connect"

    async def test_unknown_error(self, hass: HomeAssistant) -> None:
        from unittest.mock import patch

        from custom_components.remote_logger.syslog.exporter import validate

        with patch("socket.socket", side_effect=RuntimeError("unexpected")):
            result = await validate(hass, "localhost", 514, "udp", False)

        assert result == "unknown"


@pytest.mark.real_connection_check
class TestSyslogCheckConnection:
    async def test_passes_entry_settings_to_validate(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        exporter = SyslogExporter(hass, mock_entry_syslog)
        with patch(
            "custom_components.remote_logger.syslog.exporter.validate", AsyncMock(return_value="cannot_connect")
        ) as mock_validate:
            assert await exporter.async_check_connection() == "cannot_connect"
        mock_validate.assert_awaited_once_with(hass, "syslog.example.com", 514, "udp", False)


# ---------------------------------------------------------------------------
# Strict RFC 5424 mode
# ---------------------------------------------------------------------------

LONG_EVENT = "a_custom_event_type_longer_than_thirty_two_chars"


class TestSyslogStrictMode:
    def _exporter(self, hass: HomeAssistant, mock_entry_syslog: MagicMock, **opts: object) -> SyslogExporter:
        mock_entry_syslog.options = opts
        return SyslogExporter(hass, mock_entry_syslog)

    def test_off_by_default_keeps_long_msgid_and_otel_names(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, enterprise_number=12345)
        line = exporter.create_log_record({"entity_id": "light.x"}, LONG_EVENT, None).payload.decode("utf-8")
        assert line.split(" ")[5] == LONG_EVENT
        assert f'[opentelemetry eventName="{LONG_EVENT}" event.data.entity_id="light.x"]' in line

    def test_msgid_truncated_to_32(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True)
        line = exporter.create_log_record({}, LONG_EVENT, None).payload.decode("utf-8")
        assert line.split(" ")[5] == LONG_EVENT[:32]
        # The full event type is still carried in the structured data
        assert f'event_type="{LONG_EVENT}"' in line

    def test_log_direct_msgid_truncated_to_32(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True)
        exporter.log_direct(LONG_EVENT, "hello", "INFO")
        assert exporter._buffer[0].payload.decode("utf-8").split(" ")[5] == LONG_EVENT[:32]

    def test_sd_id_defaults_to_documentation_pen(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True)
        line = exporter.create_log_record({}, "homeassistant_started", None).payload.decode("utf-8")
        assert '[homeassistant@32473 event_type="homeassistant_started"]' in line
        assert _sd_block(line) is not None

    def test_sd_id_with_enterprise_number(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True, enterprise_number=12345)
        line = exporter.create_log_record({}, "homeassistant_started", None).payload.decode("utf-8")
        assert '[homeassistant@12345 event_type="homeassistant_started"]' in line

    def test_system_log_event_uses_ha_names(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True, suppress_system_log_event_name=False)
        data = {
            "name": "homeassistant.components.sensor",
            "message": ["Something went wrong"],
            "level": "ERROR",
            "source": ("homeassistant/core.py", 50),
            "exception": 'ValueError: "bad]"',
            "count": 3,
            "first_occurred": 1699999000.0,
        }
        line = exporter.create_log_record(data, "system_log_event", None).payload.decode("utf-8")
        sd = _sd_block(line)
        assert sd is not None
        assert sd.group(0) == (
            '[homeassistant@32473 source="homeassistant/core.py:50" name="homeassistant.components.sensor"'
            f' count="3" first_occurred="{isotimestamp(1699999000.0)}"'
            ' exception="ValueError: \\"bad\\]\\"" event_type="system_log_event"]'
        )

    def test_event_data_names_shortened(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True)
        data = {
            "entity_id": "light.x",
            "new_state": {
                "state": "on",
                "attributes": {"friendly_name": "X"},
                "last_changed": "t",
                "context": {"parent_id": "p"},
            },
        }
        line = exporter.create_log_record(data, "state_changed", None).payload.decode("utf-8")
        sd = _sd_block(line)
        assert sd is not None
        assert sd.group(0) == (
            '[homeassistant@32473 event_type="state_changed" entity_id="light.x" new.state="on"'
            ' new.attr.friendly_name="X" new.changed="t" new.ctx.parent="p"]'
        )

    def test_log_direct_attributes(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = self._exporter(hass, mock_entry_syslog, strict_mode=True, enterprise_number=12345)
        exporter.log_direct("unit_test", "hello", "INFO", {"k": "v", "bad key": "w"})
        line = exporter._buffer[0].payload.decode("utf-8")
        assert '[homeassistant@12345 k="v" bad_key="w"]' in line
        assert _sd_block(line) is not None


class TestStrictParamName:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("entity_id", "entity_id"),
            ("old_state.attributes.unit_of_measurement", "old.attr.unit_of_measurement"),
            ("service_data.brightness", "data.brightness"),
            ("new_state.last_updated", "new.updated"),
            ("new_state.last_reported", "new.reported"),
            # A segment is only abbreviated when it matches exactly
            ("my_attributes.x", "my_attributes.x"),
            # Characters not allowed in an RFC 5424 PARAM-NAME are replaced
            ('a b=c]d"e', "a_b_c_d_e"),
            ("température", "temp_rature"),
            # Anything still over 32 characters is cut to the limit
            ("new_state.attributes.supported_color_modes_extra", "new.attr.supported_color_modes_e"),
        ],
    )
    def test_strict_param_name(self, key: str, expected: str) -> None:
        assert _strict_param_name(key) == expected
        assert len(_strict_param_name(key)) <= 32
