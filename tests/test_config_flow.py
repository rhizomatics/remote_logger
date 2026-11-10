"""Unit tests for config flow helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.remote_logger.config_flow import _build_endpoint_url
from custom_components.remote_logger.const import (
    CONF_CUSTOM_EVENTS,
    CONF_LOG_HA_CORE_CHANGES,
    CONF_LOG_HA_FULL_STATE_CHANGES,
    CONF_LOG_HA_LIFECYCLE,
    CONF_LOG_HA_STATE_CHANGES,
    CONF_USE_TLS,
    DOMAIN,
)
from custom_components.remote_logger.otel.const import ENCODING_JSON, VALIDATION_MESSAGE

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class TestBuildEndpointUrl:
    def test_http(self) -> None:
        assert _build_endpoint_url("localhost", 4318, False) == "http://localhost:4318/v1/logs"

    def test_https(self) -> None:
        assert _build_endpoint_url("otel.example.com", 443, True) == "https://otel.example.com:443/v1/logs"

    def test_custom_port(self) -> None:
        assert _build_endpoint_url("host", 9999, False) == "http://host:9999/v1/logs"


@pytest.mark.usefixtures("enable_custom_integrations")
class TestOtelConfigFlow:
    async def test_step_user_shows_menu(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert result["type"] == FlowResultType.MENU
        assert "otel" in result["menu_options"]
        assert "syslog" in result["menu_options"]

    async def test_step_otel_shows_form(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "otel"})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "otel"
        assert result["description_placeholders"] == {"validation_message": VALIDATION_MESSAGE}

    async def test_step_otel_success(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "otel"})
        with patch(
            "custom_components.remote_logger.config_flow.otel_validate",
            new=AsyncMock(return_value={}),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "localhost",
                    CONF_PORT: 4318,
                    CONF_USE_TLS: False,
                    "encoding": ENCODING_JSON,
                    "batch_max_size": 20,
                    "resource_attributes": "",
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "common"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ha_standard_events": {
                    "log_ha_lifecycle": False,
                    "log_ha_core_changes": False,
                    "log_ha_core_activity": False,
                    "log_ha_state_changes": False,
                    "log_ha_full_state_changes": False,
                },
                "custom_events": [],
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "OTLP @ localhost:4318"
        assert result["data"][CONF_HOST] == "localhost"

    async def test_step_otel_connection_error(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "otel"})
        with patch(
            "custom_components.remote_logger.config_flow.otel_validate",
            new=AsyncMock(return_value={"base": "cannot_connect"}),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "badhost",
                    CONF_PORT: 4318,
                    CONF_USE_TLS: False,
                    "encoding": ENCODING_JSON,
                    "batch_max_size": 20,
                    "resource_attributes": "",
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "cannot_connect"

    async def test_step_otel_basic_auth_stored(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "otel"})
        with patch(
            "custom_components.remote_logger.config_flow.otel_validate",
            new=AsyncMock(return_value={}),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "localhost",
                    CONF_PORT: 4318,
                    CONF_USE_TLS: False,
                    "encoding": ENCODING_JSON,
                    "batch_max_size": 20,
                    "resource_attributes": "",
                    "token_type": "basic",
                    "token": "user:pass",
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "common"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ha_standard_events": {
                    "log_ha_lifecycle": False,
                    "log_ha_core_changes": False,
                    "log_ha_core_activity": False,
                    "log_ha_state_changes": False,
                    "log_ha_full_state_changes": False,
                },
                "custom_events": [],
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"]["token_type"] == "basic"

    async def test_step_otel_invalid_resource_attributes(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "otel"})
        with patch(
            "custom_components.remote_logger.config_flow.otel_validate",
            new=AsyncMock(return_value={}),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "localhost",
                    CONF_PORT: 4318,
                    CONF_USE_TLS: False,
                    "encoding": ENCODING_JSON,
                    "batch_max_size": 20,
                    "resource_attributes": "bad_format_no_equals",
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert "resource_attributes" in result["errors"]


@pytest.mark.usefixtures("enable_custom_integrations")
class TestSyslogConfigFlow:
    async def test_step_syslog_shows_form(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "syslog"})
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "syslog"

    async def test_step_syslog_success(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "syslog"})
        with patch(
            "custom_components.remote_logger.config_flow.syslog_validate",
            new=AsyncMock(return_value=None),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "syslog.example.com",
                    CONF_PORT: 514,
                    CONF_PROTOCOL: "udp",
                    CONF_USE_TLS: False,
                    "app_name": "homeassistant",
                    "facility": "local0",
                    "batch_max_size": 20,
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "common"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "ha_standard_events": {
                    "log_ha_lifecycle": False,
                    "log_ha_core_changes": False,
                    "log_ha_core_activity": False,
                    "log_ha_state_changes": False,
                    "log_ha_full_state_changes": False,
                },
                "custom_events": [],
            },
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert "Syslog @" in result["title"]

    async def test_step_syslog_connection_error(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "syslog"})
        with patch(
            "custom_components.remote_logger.config_flow.syslog_validate",
            new=AsyncMock(return_value="cannot_connect"),
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_HOST: "badhost",
                    CONF_PORT: 514,
                    CONF_PROTOCOL: "udp",
                    CONF_USE_TLS: False,
                    "app_name": "homeassistant",
                    "facility": "local0",
                    "batch_max_size": 20,
                },
            )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "cannot_connect"


@pytest.mark.usefixtures("enable_custom_integrations")
class TestOptionsFlow:
    def _make_otel_entry(self, extra: dict | None = None) -> ConfigEntry:
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "opt_test"
        entry.domain = DOMAIN
        entry.data = {
            "backend": "otel",
            CONF_HOST: "localhost",
            CONF_PORT: 4318,
            CONF_USE_TLS: False,
            "encoding": ENCODING_JSON,
            "batch_max_size": 100,
            "resource_attributes": "",
            CONF_LOG_HA_LIFECYCLE: False,
            CONF_LOG_HA_CORE_CHANGES: False,
            CONF_CUSTOM_EVENTS: [],
            **(extra or {}),
        }
        entry.options = {}
        return entry

    async def test_options_flow_shows_only_event_settings(self, hass: HomeAssistant) -> None:
        """Connection settings moved to the reconfigure step; options are the event subscriptions only."""
        from custom_components.remote_logger.config_flow import RemoteLoggerOptionsFlow

        entry = self._make_otel_entry()
        flow = RemoteLoggerOptionsFlow(entry)
        flow.hass = hass
        result = await flow.async_step_init(None)
        assert result["type"] == FlowResultType.FORM  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["step_id"] == "events"  # pyright: ignore[reportTypedDictNotRequiredAccess]
        fields = {str(k) for k in result["data_schema"].schema}  # type: ignore
        assert not fields & {CONF_HOST, CONF_PORT, CONF_USE_TLS, "token", "encoding"}

    async def test_options_flow_saves_only_event_settings(self, hass: HomeAssistant) -> None:
        from custom_components.remote_logger.config_flow import RemoteLoggerOptionsFlow

        entry = self._make_otel_entry()
        flow = RemoteLoggerOptionsFlow(entry)
        flow.hass = hass
        result = await flow.async_step_events({
            "ha_standard_events": {CONF_LOG_HA_LIFECYCLE: True, CONF_LOG_HA_CORE_CHANGES: False},
            CONF_CUSTOM_EVENTS: ["my_event"],
        })
        assert result["type"] == FlowResultType.CREATE_ENTRY  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["data"] == {  # pyright: ignore[reportTypedDictNotRequiredAccess]
            CONF_LOG_HA_LIFECYCLE: True,
            CONF_LOG_HA_CORE_CHANGES: False,
            CONF_CUSTOM_EVENTS: ["my_event"],
        }

    async def test_options_flow_prefers_existing_options(self, hass: HomeAssistant) -> None:
        from custom_components.remote_logger.config_flow import RemoteLoggerOptionsFlow

        entry: ConfigEntry[Any] = self._make_otel_entry()
        entry.options[CONF_LOG_HA_LIFECYCLE] = True  # type: ignore
        entry.options[CONF_CUSTOM_EVENTS] = ["zha_event"]  # type: ignore
        flow = RemoteLoggerOptionsFlow(entry)
        flow.hass = hass
        result = await flow.async_step_init(None)
        data_schema = result["data_schema"].schema  # type: ignore
        custom_key = next(k for k in data_schema if k.schema == CONF_CUSTOM_EVENTS)
        assert custom_key.description["suggested_value"] == ["zha_event"]

    async def test_options_flow_events_error_keeps_attempted_toggle(self, hass: HomeAssistant) -> None:
        """On a validation error, the re-shown form must reflect the just-submitted toggles, not stored options."""
        from custom_components.remote_logger.config_flow import RemoteLoggerOptionsFlow

        entry = self._make_otel_entry({CONF_LOG_HA_STATE_CHANGES: True})
        flow = RemoteLoggerOptionsFlow(entry)
        flow.hass = hass

        result = await flow.async_step_events({
            "ha_standard_events": {
                CONF_LOG_HA_LIFECYCLE: False,
                CONF_LOG_HA_CORE_CHANGES: False,
                CONF_LOG_HA_STATE_CHANGES: True,
                CONF_LOG_HA_FULL_STATE_CHANGES: True,
            },
            CONF_CUSTOM_EVENTS: [],
        })

        assert result["type"] == FlowResultType.FORM  # pyright: ignore[reportTypedDictNotRequiredAccess]
        assert result["errors"] == {CONF_LOG_HA_FULL_STATE_CHANGES: "state_changes_exclusive"}  # pyright: ignore[reportTypedDictNotRequiredAccess]
        data_schema = result["data_schema"].schema  # type: ignore
        section_key = next(k for k in data_schema if k.schema == "ha_standard_events")
        section_schema = data_schema[section_key].schema.schema
        suggested = {
            key.schema: key.description.get("suggested_value")
            for key in section_schema
            if hasattr(key, "description") and key.description
        }
        assert suggested[CONF_LOG_HA_FULL_STATE_CHANGES] is True


@pytest.mark.usefixtures("enable_custom_integrations")
class TestReauthFlow:
    """Reauth must not combine an update listener with async_update_reload_and_abort (raises from HA 2026.12)."""

    def _make_entry(self, hass: HomeAssistant, options: dict[str, Any] | None = None) -> Any:
        from tests.ha_testing import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            unique_id=f"{DOMAIN}_otel_localhost_4318",
            data={
                "backend": "otel",
                CONF_HOST: "localhost",
                CONF_PORT: 4318,
                CONF_USE_TLS: False,
                "encoding": ENCODING_JSON,
                "token": "old-token",
                "token_type": "bearer",
            },
            options=options or {},
        )
        entry.add_to_hass(hass)
        # async_setup_entry registers one; reproduced here without starting an exporter
        entry.add_update_listener(AsyncMock())
        return entry

    async def _reauth(self, hass: HomeAssistant, entry: Any) -> ConfigFlowResult:
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_otel"
        with (
            patch("custom_components.remote_logger.config_flow.otel_validate", new=AsyncMock(return_value={})),
            patch.object(hass.config_entries, "async_schedule_reload"),
        ):
            return await hass.config_entries.flow.async_configure(
                result["flow_id"], {"token": "new-token", "token_type": "bearer"}
            )

    async def test_reauth_does_not_reload_alongside_update_listener(
        self, hass: HomeAssistant, caplog: pytest.LogCaptureFixture
    ) -> None:
        entry = self._make_entry(hass)
        result = await self._reauth(hass, entry)
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data["token"] == "new-token"
        assert "should use it for scheduling a reload" not in caplog.text


@pytest.mark.usefixtures("enable_custom_integrations")
class TestReconfigureFlow:
    """Connection settings are entry data, changed by a reconfigure step (config-flow, reconfiguration-flow)."""

    def _otel_entry(self, hass: HomeAssistant, title: str = "OTLP @ localhost:4318", **data: Any) -> Any:
        from tests.ha_testing import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            minor_version=3,
            title=title,
            unique_id=f"{DOMAIN}_otel_localhost_4318",
            data={
                "backend": "otel",
                CONF_HOST: "localhost",
                CONF_PORT: 4318,
                CONF_USE_TLS: False,
                "encoding": ENCODING_JSON,
                "token": "old-token",
                "token_type": "bearer",
                CONF_LOG_HA_LIFECYCLE: True,
                **data,
            },
        )
        entry.add_to_hass(hass)
        return entry

    async def _submit(self, hass: HomeAssistant, entry: Any, user_input: dict[str, Any], errors: dict | None = None) -> Any:
        result = await entry.start_reconfigure_flow(hass)
        with (
            patch("custom_components.remote_logger.config_flow.otel_validate", new=AsyncMock(return_value=errors or {})),
            patch("custom_components.remote_logger.config_flow.syslog_validate", new=AsyncMock(return_value=None)),
            patch.object(hass.config_entries, "async_schedule_reload"),
        ):
            return await hass.config_entries.flow.async_configure(result["flow_id"], user_input)

    async def test_otel_form_prefilled_from_data(self, hass: HomeAssistant) -> None:
        entry = self._otel_entry(hass, headers="a: 1\nb: 2")
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure_otel"
        suggested = {k.schema: k.description["suggested_value"] for k in result["data_schema"].schema if k.description}
        assert suggested[CONF_HOST] == "localhost"
        assert suggested["headers"] == ["a: 1", "b: 2"]

    async def test_otel_updates_data_unique_id_and_generated_title(self, hass: HomeAssistant) -> None:
        entry = self._otel_entry(hass)
        result = await self._submit(
            hass, entry, {CONF_HOST: "newhost", CONF_PORT: 4319, CONF_USE_TLS: True, "encoding": ENCODING_JSON}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == "newhost"
        assert entry.data[CONF_USE_TLS] is True
        # A token cleared in the form is removed, not kept from before
        assert not entry.data["token"]
        # Event settings in data are untouched; nothing goes to options
        assert entry.data[CONF_LOG_HA_LIFECYCLE] is True
        assert entry.options == {}
        assert entry.unique_id == f"{DOMAIN}_otel_newhost_4319"
        assert entry.title == "OTLP @ newhost:4319"

    async def test_otel_keeps_user_title(self, hass: HomeAssistant) -> None:
        entry = self._otel_entry(hass, title="My collector")
        await self._submit(hass, entry, {CONF_HOST: "newhost", CONF_PORT: 4318, CONF_USE_TLS: False, "encoding": ENCODING_JSON})
        assert entry.title == "My collector"

    async def test_otel_validation_error_shown(self, hass: HomeAssistant) -> None:
        entry = self._otel_entry(hass)
        result = await self._submit(
            hass,
            entry,
            {CONF_HOST: "newhost", CONF_PORT: 4318, CONF_USE_TLS: False, "encoding": ENCODING_JSON},
            errors={"base": "cannot_connect"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "cannot_connect"}
        assert entry.data[CONF_HOST] == "localhost"

    async def test_otel_aborts_if_other_entry_has_endpoint(self, hass: HomeAssistant) -> None:
        from tests.ha_testing import MockConfigEntry

        MockConfigEntry(domain=DOMAIN, unique_id=f"{DOMAIN}_otel_other_4318", data={"backend": "otel"}).add_to_hass(hass)
        entry = self._otel_entry(hass)
        result = await self._submit(
            hass, entry, {CONF_HOST: "other", CONF_PORT: 4318, CONF_USE_TLS: False, "encoding": ENCODING_JSON}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"
        assert entry.data[CONF_HOST] == "localhost"

    async def test_syslog(self, hass: HomeAssistant) -> None:
        from tests.ha_testing import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            minor_version=3,
            title="Syslog @ old:514 (UDP)",
            unique_id=f"{DOMAIN}_syslog",
            data={"backend": "syslog", CONF_HOST: "old", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: False},
        )
        entry.add_to_hass(hass)
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure_syslog"
        result = await self._submit(hass, entry, {CONF_HOST: "new", CONF_PORT: 6514, CONF_PROTOCOL: "tcp", CONF_USE_TLS: True})
        assert result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == "new"
        assert entry.data[CONF_PROTOCOL] == "tcp"
        assert entry.unique_id == f"{DOMAIN}_syslog"
        assert entry.title == "Syslog @ new:6514 (TCP)"

    async def test_syslog_strict_mode(self, hass: HomeAssistant) -> None:
        from tests.ha_testing import MockConfigEntry

        connection = {CONF_HOST: "old", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: False}
        entry = MockConfigEntry(
            domain=DOMAIN, version=2, minor_version=3, unique_id=f"{DOMAIN}_syslog", data={"backend": "syslog", **connection}
        )
        entry.add_to_hass(hass)
        result = await self._submit(hass, entry, {**connection, "strict_mode": True, "enterprise_number": 32473})
        assert result["reason"] == "reconfigure_successful"
        assert entry.data["strict_mode"] is True
        assert entry.data["enterprise_number"] == 32473

        # Clearing the enterprise number in the form removes it
        await self._submit(hass, entry, {**connection, "strict_mode": True})
        assert "enterprise_number" not in entry.data

    async def test_syslog_enterprise_number_must_be_positive(self, hass: HomeAssistant) -> None:
        from homeassistant.data_entry_flow import InvalidData

        from tests.ha_testing import MockConfigEntry

        connection = {CONF_HOST: "old", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: False}
        entry = MockConfigEntry(
            domain=DOMAIN, version=2, minor_version=3, unique_id=f"{DOMAIN}_syslog", data={"backend": "syslog", **connection}
        )
        entry.add_to_hass(hass)
        result = await entry.start_reconfigure_flow(hass)
        with pytest.raises(InvalidData):
            await hass.config_entries.flow.async_configure(result["flow_id"], {**connection, "enterprise_number": 0})

    async def test_syslog_validation_error_shown(self, hass: HomeAssistant) -> None:
        from tests.ha_testing import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            minor_version=3,
            unique_id=f"{DOMAIN}_syslog",
            data={"backend": "syslog", CONF_HOST: "old", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: False},
        )
        entry.add_to_hass(hass)
        result = await entry.start_reconfigure_flow(hass)
        with patch("custom_components.remote_logger.config_flow.syslog_validate", new=AsyncMock(return_value="cannot_connect")):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: "new", CONF_PORT: 514, CONF_PROTOCOL: "udp", CONF_USE_TLS: False}
            )
        assert result["errors"] == {"base": "cannot_connect"}
        assert entry.data[CONF_HOST] == "old"

    @pytest.mark.parametrize(("headers", "error"), [(["stream: a"], None), (["no-colon"], "invalid_headers")])
    async def test_otel_headers_checked(self, hass: HomeAssistant, headers: list[str], error: str | None) -> None:
        entry = self._otel_entry(hass)
        result = await self._submit(
            hass,
            entry,
            {CONF_HOST: "localhost", CONF_PORT: 4318, CONF_USE_TLS: False, "encoding": ENCODING_JSON, "headers": headers},
        )
        if error:
            assert result["errors"] == {"headers": error}
        else:
            assert result["reason"] == "reconfigure_successful"
            assert entry.data["headers"] == headers
