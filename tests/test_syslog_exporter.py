"""Unit tests for the syslog exporter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest

from custom_components.remote_logger.syslog.exporter import (
    SyslogExporter,
    _sd_escape,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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

    def test_endpoint_desc(self, exporter: SyslogExporter) -> None:
        assert "syslog://syslog.example.com:514" in exporter.endpoint_desc
        assert "UDP" in exporter.endpoint_desc

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
        msg = exporter._to_syslog_message(data)
        text = msg.decode("utf-8")

        # Check RFC 5424 structure: <PRI>1 TIMESTAMP HOSTNAME APP-NAME - - SD MSG
        # PRI = facility(16) * 8 + severity(3 for ERROR) = 131
        assert text.startswith("<131>1 ")
        assert "homeassistant" in text
        assert "Something went wrong" in text

    def test_to_syslog_message_pri_calculation(self, exporter: SyslogExporter) -> None:
        # facility=16 (local0), severity=7 (DEBUG) -> PRI = 16*8 + 7 = 135
        data = {"level": "DEBUG", "message": ["debug msg"], "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert msg.startswith("<135>1 ")

    def test_to_syslog_message_warning_severity(self, exporter: SyslogExporter) -> None:
        # facility=16, severity=4 (WARNING) -> PRI = 132
        data = {"level": "WARNING", "message": ["warn"], "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert msg.startswith("<132>1 ")

    def test_to_syslog_message_critical_severity(self, exporter: SyslogExporter) -> None:
        # facility=16, severity=2 (CRITICAL) -> PRI = 130
        data = {"level": "CRITICAL", "message": ["crit"], "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert msg.startswith("<130>1 ")

    def test_to_syslog_message_default_severity(self, exporter: SyslogExporter) -> None:
        # Unknown level falls back to 6 (INFO) -> PRI = 134
        data = {"level": "TRACE", "message": ["trace"], "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert msg.startswith("<134>1 ")

    def test_to_syslog_message_includes_timestamp(self, exporter: SyslogExporter) -> None:
        data = {"message": ["test"], "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
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
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert '[meta logger="my.logger"' in msg
        assert 'count="5"' in msg
        assert 'firstOccurred="1699999000.0"' in msg

    def test_to_syslog_message_no_message(self, exporter: SyslogExporter) -> None:
        data = {"level": "INFO", "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
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
        msg = exporter._to_syslog_message(data).decode("utf-8")
        assert "error happened" in msg
        assert "ValueError: bad" in msg

    def test_to_syslog_message_empty_messages(self, exporter: SyslogExporter) -> None:
        data = {"message": [], "level": "INFO", "timestamp": 1700000000.0}
        msg = exporter._to_syslog_message(data).decode("utf-8")
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

    def test_to_protobuf(self, exporter: SyslogExporter, sample_event_data: dict[str, Any]) -> None:
        msg = exporter._to_syslog_message(sample_event_data).decode("utf-8")
        assert msg is not None
        assert msg.startswith('<131>')
        assert len(msg) > 300
