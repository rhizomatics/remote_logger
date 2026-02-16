"""Config flow for the ha_remote_logs integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BACKEND_OTEL,
    BACKEND_SYSLOG,
    CONF_BACKEND,
    CONF_ENCODING,
    CONF_HOST,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DOMAIN,
    OTLP_LOGS_PATH,
)
from .otel import OTEL_DATA_SCHEMA, parse_resource_attributes
from .otel import validate as otel_validate
from .syslog import SYSLOG_DATA_SCHEMA
from .syslog import validate as syslog_validate

_LOGGER = logging.getLogger(__name__)


def _build_endpoint_url(host: str, port: int, use_tls: bool) -> str:
    """Build the full OTLP endpoint URL."""
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}:{port}{OTLP_LOGS_PATH}"


class OtelLogsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenTelemetry Log Exporter."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Show menu to choose backend type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["otel", "syslog"],
        )

    async def async_step_otel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle OpenTelemetry OTLP configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            use_tls = user_input[CONF_USE_TLS]
            url = _build_endpoint_url(host, port, use_tls)

            # Validate connectivity
            session = async_get_clientsession(self.hass, verify_ssl=use_tls)
            errors = await otel_validate(session, url, user_input[CONF_ENCODING])
            # Validate resource attributes format
            if not errors:
                raw_attrs = user_input.get(CONF_RESOURCE_ATTRIBUTES, "")
                if raw_attrs.strip():
                    try:
                        parse_resource_attributes(raw_attrs)
                    except ValueError:
                        errors[CONF_RESOURCE_ATTRIBUTES] = "invalid_attributes"

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{BACKEND_OTEL}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"OTLP @ {host}:{port}",
                    data={**user_input, CONF_BACKEND: BACKEND_OTEL},
                )

        return self.async_show_form(
            step_id="otel",
            data_schema=OTEL_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_syslog(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Syslog RFC 5424 configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            protocol = user_input[CONF_PROTOCOL]
            use_tls = user_input.get(CONF_USE_TLS, False)

            # Validate connectivity
            error = await syslog_validate(
                self.hass, host, port, protocol, use_tls
            )
            if error:
                errors["base"] = error

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{BACKEND_SYSLOG}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Syslog @ {host}:{port} ({protocol.upper()})",
                    data={**user_input, CONF_BACKEND: BACKEND_SYSLOG},
                )

        return self.async_show_form(
            step_id="syslog",
            data_schema=SYSLOG_DATA_SCHEMA,
            errors=errors,
        )
