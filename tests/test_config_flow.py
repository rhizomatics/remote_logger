"""Unit tests for config flow helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.data_entry_flow import FlowResultType

from custom_components.remote_logger.config_flow import _build_endpoint_url
from custom_components.remote_logger.const import (
    CONF_USE_TLS,
    DOMAIN,
)
from custom_components.remote_logger.otel.const import ENCODING_JSON

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
