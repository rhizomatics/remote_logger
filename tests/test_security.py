"""Regression tests for the security hardening of remote_logger."""

# Flow results are TypedDicts with no required keys; a missing one failing with KeyError is what the test should do.
# pyright: reportTypedDictNotRequiredAccess=false

from __future__ import annotations

import logging
import ssl
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.core import Context, Event, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import issue_registry as ir

from custom_components.remote_logger.config_flow import OtelLogsConfigFlow
from custom_components.remote_logger.const import (
    CONF_EVENT_BASED_LOGGING,
    CONF_TLS_CA_FILE,
    CONF_TLS_CLIENT_CERT,
    CONF_TLS_CLIENT_KEY,
    CONF_USE_TLS,
    DOMAIN,
    MAX_BUFFERED_RECORDS,
)
from custom_components.remote_logger.helpers import flatten_event_data
from custom_components.remote_logger.otel.exporter import OtlpJsonSubmission, OtlpLogExporter, OtlpMessage
from custom_components.remote_logger.otel.exporter import validate as otel_validate
from custom_components.remote_logger.syslog.exporter import SyslogExporter
from custom_components.remote_logger.syslog.exporter import validate as syslog_validate
from tests.ha_testing import MockConfigEntry
from tests.test_syslog_exporter import _sd_block

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from custom_components.remote_logger.exporter import LogExporter

SECRET = "s3cr3t-value"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


async def _setup(hass: HomeAssistant, template: ConfigEntry, **data: Any) -> Any:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=OtelLogsConfigFlow.VERSION,
        minor_version=OtelLogsConfigFlow.MINOR_VERSION,
        entry_id=template.entry_id,
        title=template.title,
        # Event-based logging keeps HA's own setup logging out of the exporter buffer
        data={**template.data, CONF_EVENT_BASED_LOGGING: True, **data},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _response(status: int, body: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.ok = status < 400
    resp.text = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session(resp: MagicMock) -> MagicMock:
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    return session


class TestActionPermissions:
    """last_log and flush are for administrators; send_log records who called it."""

    async def test_last_log_refused_for_non_admin(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, hass_read_only_user: Any
    ) -> None:
        await _setup(hass, mock_entry_otel)
        with pytest.raises(Unauthorized):
            await hass.services.async_call(
                DOMAIN,
                "last_log",
                {"config_entry_id": mock_entry_otel.entry_id},
                blocking=True,
                return_response=True,
                context=Context(user_id=hass_read_only_user.id),
            )

    async def test_flush_refused_for_non_admin(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, hass_read_only_user: Any
    ) -> None:
        await _setup(hass, mock_entry_otel)
        with pytest.raises(Unauthorized):
            await hass.services.async_call(DOMAIN, "flush", {}, blocking=True, context=Context(user_id=hass_read_only_user.id))

    async def test_last_log_allowed_for_admin(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, hass_admin_user: Any
    ) -> None:
        await _setup(hass, mock_entry_otel)
        result = await hass.services.async_call(
            DOMAIN,
            "last_log",
            {"config_entry_id": mock_entry_otel.entry_id},
            blocking=True,
            return_response=True,
            context=Context(user_id=hass_admin_user.id),
        )
        assert result == {}

    async def test_send_log_records_calling_user(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, hass_read_only_user: Any
    ) -> None:
        entry = await _setup(hass, mock_entry_otel)
        await hass.services.async_call(
            DOMAIN,
            "send_log",
            # a caller can't pass someone else's id off as their own
            {"event": "unit_test", "message": "hello", "attributes": {"user.id": "someone-else"}},
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
        attributes = entry.runtime_data.exporter._buffer[0].payload["attributes"]
        assert [a["value"]["stringValue"] for a in attributes if a["key"] == "user.id"] == [hass_read_only_user.id]


class TestLastLogMasking:
    def test_custom_header_values_masked(self) -> None:
        submission = OtlpJsonSubmission(
            {},
            records=[OtlpMessage(payload={})],
            extra_headers={"Authorization": f"Bearer {SECRET}", "X-API-Key": SECRET, "DD-API-KEY": SECRET},
        )
        headers = submission.for_display()["headers"]
        assert SECRET not in str(headers)
        assert headers["Content-Type"] == "application/json"
        assert headers["Authorization"] == f"Bearer {'*' * len(SECRET)}"


class TestRedaction:
    def test_flatten_redacts_sensitive_keys(self) -> None:
        flat = dict(flatten_event_data("event.data.service_data", {"code": SECRET, "entity_id": "lock.door"}, False))
        assert flat["event.data.service_data.entity_id"] == "lock.door"
        assert SECRET not in flat.values()

    @pytest.mark.parametrize("event_body", [True, False])
    @pytest.mark.parametrize("backend", ["otel", "syslog"])
    def test_service_call_code_not_exported(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, mock_entry_syslog: MagicMock, backend: str, event_body: bool
    ) -> None:
        exporter: LogExporter = (
            OtlpLogExporter(hass, mock_entry_otel) if backend == "otel" else SyslogExporter(hass, mock_entry_syslog)
        )
        event = Event(
            "call_service",
            {
                "domain": "alarm_control_panel",
                "service": "alarm_disarm",
                "service_data": {"entity_id": "alarm_control_panel.home", "code": SECRET},
                "password": SECRET,
            },
        )
        exporter.handle_ha_event("call_service", event, event_body=event_body)
        assert len(exporter._buffer) == 1
        assert SECRET not in str(exporter._buffer[0].payload)
        assert "alarm_control_panel.home" in str(exporter._buffer[0].payload)

    @pytest.mark.parametrize("event_body", [True, False])
    def test_camera_access_token_not_exported(self, hass: HomeAssistant, mock_entry_otel: MagicMock, event_body: bool) -> None:
        exporter = OtlpLogExporter(hass, mock_entry_otel)
        state = State(
            "camera.drive",
            "idle",
            {"access_token": SECRET, "entity_picture": f"/api/camera_proxy/camera.drive?token={SECRET}", "brand": "Acme"},
        )
        event = Event("state_changed", {"entity_id": "camera.drive", "old_state": None, "new_state": state})
        exporter.handle_ha_event("state_changed", event, event_body=event_body)
        assert len(exporter._buffer) == 1
        assert SECRET not in str(exporter._buffer[0].payload)
        assert "Acme" in str(exporter._buffer[0].payload)

    def test_handler_failure_does_not_log_event_data(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        exporter = OtlpLogExporter(hass, mock_entry_otel)
        event = Event("system_log_event", {"message": ["m"], "password": SECRET})
        with (
            patch.object(exporter, "create_log_record", side_effect=ValueError("boom")),
            caplog.at_level(logging.ERROR),
        ):
            exporter.handle_event(event)
            exporter.handle_entry({"name": "some.logger", "password": SECRET}, event.time_fired)
        assert exporter.format_error_count == 2
        assert SECRET not in caplog.text


class TestSyslogTlsNeedsTcp:
    async def test_tls_with_udp_rejected(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "syslog"})
        with patch("custom_components.remote_logger.config_flow.syslog_validate", new=AsyncMock(return_value=None)):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_HOST: "syslog.example.com", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: True},
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "syslog"
        assert result["errors"] == {CONF_USE_TLS: "tls_requires_tcp"}


class TestBufferCap:
    @pytest.mark.parametrize("backend", ["otel", "syslog"])
    def test_buffer_is_bounded(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, mock_entry_syslog: MagicMock, backend: str
    ) -> None:
        exporter: LogExporter = (
            OtlpLogExporter(hass, mock_entry_otel) if backend == "otel" else SyslogExporter(hass, mock_entry_syslog)
        )
        exporter._batch_max_size = MAX_BUFFERED_RECORDS * 10
        for i in range(MAX_BUFFERED_RECORDS + 5):
            exporter.log_direct("e", f"m{i}", "INFO")
        assert len(exporter._buffer) == MAX_BUFFERED_RECORDS

    async def test_syslog_backlog_bounded_while_server_down(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        mock_entry_syslog.data = {**mock_entry_syslog.data, "protocol": "tcp"}
        exporter = SyslogExporter(hass, mock_entry_syslog)
        exporter._batch_max_size = MAX_BUFFERED_RECORDS * 10
        with patch.object(exporter, "_connect_tcp", AsyncMock(side_effect=OSError("down"))):
            for _ in range(3):
                for i in range(MAX_BUFFERED_RECORDS):
                    exporter.log_direct("e", f"m{i}", "INFO")
                await exporter.flush()
        assert len(exporter._in_progress) + len(exporter._buffer) <= 2 * MAX_BUFFERED_RECORDS


class TestSyslogInjection:
    def test_send_log_cannot_forge_fields(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = SyslogExporter(hass, mock_entry_syslog)
        exporter.log_direct(
            'evt [forged@1 user="admin"]',
            "line1\n<34>1 2026-01-01T00:00:00Z host su - - - forged record",
            "INFO",
            {'a="1" injected': "v\n<34>1 forged again"},
        )
        line = exporter._buffer[0].payload.decode()
        fields = line.split(" ", 6)
        assert fields[5] == 'evt_[forged@1_user="admin"]'  # MSGID stays one field
        assert _sd_block(line) is not None  # structured data still follows the RFC 5424 grammar
        assert "[opentelemetry a__1__injected=" in line
        # a continuation line can't start with a PRI, so a line-splitting receiver sees no second record
        assert "\n<" not in line

    def test_event_type_and_data_keys_cannot_forge_fields(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = SyslogExporter(hass, mock_entry_syslog)
        record = exporter.create_log_record({'k="1" x': "v"}, event_type="my event", message_override=["hello"])
        line = record.payload.decode()
        assert line.split(" ", 6)[5] == "my_event"
        assert _sd_block(line) is not None

    def test_app_name_sanitised(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        mock_entry_syslog.data = {**mock_entry_syslog.data, "app_name": "home assistant"}
        exporter = SyslogExporter(hass, mock_entry_syslog)
        exporter.log_direct("e", "m", "INFO")
        assert exporter._buffer[0].payload.decode().split(" ")[3] == "home_assistant"

    def test_multi_line_messages_kept(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = SyslogExporter(hass, mock_entry_syslog)
        exporter.log_direct("e", "line1\nline2", "INFO")
        assert exporter._buffer[0].payload.decode().endswith("line1\nline2")


class TestOtlpRedirects:
    async def test_flush_does_not_follow_redirects(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        exporter = OtlpLogExporter(hass, mock_entry_otel)
        exporter.log_direct("e", "m", "INFO")
        session = _session(_response(307, "moved"))
        with patch("custom_components.remote_logger.otel.exporter.async_get_clientsession", return_value=session):
            await exporter.flush()
        assert session.post.call_args.kwargs["allow_redirects"] is False
        assert exporter.posting_error_count == 1

    async def test_validate_treats_redirect_as_failure(self) -> None:
        session = _session(_response(302, "moved"))
        assert await otel_validate(session, "http://localhost:4318/v1/logs", "json") == {"base": "cannot_connect"}
        assert session.post.call_args.kwargs["allow_redirects"] is False


class TestResponseBodyTruncated:
    async def test_error_body_truncated_in_sensor_attribute(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        exporter = OtlpLogExporter(hass, mock_entry_otel)
        exporter.log_direct("e", "m", "INFO")
        session = _session(_response(500, "x" * 5000))
        with patch("custom_components.remote_logger.otel.exporter.async_get_clientsession", return_value=session):
            await exporter.flush()
        assert exporter.last_posting_error_message is not None
        assert len(exporter.last_posting_error_message) <= 200

    async def test_validate_does_not_log_whole_body(self, caplog: pytest.LogCaptureFixture) -> None:
        session = _session(_response(500, "x" * 5000))
        with caplog.at_level(logging.ERROR):
            await otel_validate(session, "http://localhost:4318/v1/logs", "json")
        assert "x" * 201 not in caplog.text


class TestPlaintextTokenIssue:
    async def test_issue_raised_for_token_without_tls(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        entry = await _setup(hass, mock_entry_otel, token=SECRET)
        issue = ir.async_get(hass).async_get_issue(DOMAIN, f"plaintext_token_{entry.entry_id}")
        assert issue is not None
        assert issue.severity is ir.IssueSeverity.WARNING
        assert SECRET not in str(issue.translation_placeholders)

    async def test_no_issue_with_tls(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        entry = await _setup(hass, mock_entry_otel, token=SECRET, use_tls=True)
        assert ir.async_get(hass).async_get_issue(DOMAIN, f"plaintext_token_{entry.entry_id}") is None

    async def test_no_issue_without_token(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        entry = await _setup(hass, mock_entry_otel)
        assert ir.async_get(hass).async_get_issue(DOMAIN, f"plaintext_token_{entry.entry_id}") is None


class TestSyslogCustomTls:
    def _entry(self, mock_entry_syslog: MagicMock, **extra: str) -> MagicMock:
        mock_entry_syslog.data = {**mock_entry_syslog.data, "protocol": "tcp", "use_tls": True, **extra}
        return mock_entry_syslog

    async def test_private_ca_and_client_certificate_used(self, hass: HomeAssistant, mock_entry_syslog: MagicMock) -> None:
        exporter = SyslogExporter(
            hass,
            self._entry(
                mock_entry_syslog,
                **{
                    CONF_TLS_CA_FILE: "/ssl/ca.pem",
                    CONF_TLS_CLIENT_CERT: "/ssl/client.pem",
                    CONF_TLS_CLIENT_KEY: "/ssl/client.key",
                },
            ),
        )
        context = MagicMock(spec=ssl.SSLContext)
        with (
            patch("ssl.create_default_context", return_value=context) as create_context,
            patch("asyncio.open_connection", new=AsyncMock(return_value=(MagicMock(), MagicMock()))) as open_connection,
        ):
            await exporter._connect_tcp()
        create_context.assert_called_once_with(cafile="/ssl/ca.pem")
        context.load_cert_chain.assert_called_once_with("/ssl/client.pem", "/ssl/client.key")
        assert open_connection.call_args.kwargs["ssl"] is context

    async def test_missing_tls_file_reported(self, hass: HomeAssistant) -> None:
        with patch("asyncio.open_connection", new=AsyncMock()) as open_connection:
            error = await syslog_validate(hass, "secure.host", 6514, "tcp", True, ca_file="/nonexistent/ca.pem")
        assert error == "invalid_tls_files"
        open_connection.assert_not_called()

    def test_existing_udp_entry_with_tls_warns(
        self, hass: HomeAssistant, mock_entry_syslog: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mock_entry_syslog.data = {**mock_entry_syslog.data, "use_tls": True}
        with caplog.at_level(logging.WARNING):
            SyslogExporter(hass, mock_entry_syslog)
        assert "sent unencrypted" in caplog.text
