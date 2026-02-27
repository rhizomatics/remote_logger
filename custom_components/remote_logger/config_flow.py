"""Config flow for the remote_logger integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HEADERS, CONF_HOST, CONF_PATH, CONF_PORT, CONF_PROTOCOL, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BACKEND_OTEL,
    BACKEND_SYSLOG,
    CONF_BACKEND,
    CONF_ENCODING,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DOMAIN,
)
from .otel.const import OTEL_DATA_SCHEMA, OTLP_LOGS_PATH, REAUTH_OTEL_DATA_SCHEMA
from .otel.exporter import parse_headers, parse_resource_attributes
from .otel.exporter import validate as otel_validate
from .syslog.const import SYSLOG_DATA_SCHEMA
from .syslog.exporter import validate as syslog_validate

_LOGGER = logging.getLogger(__name__)


def _build_endpoint_url(host: str, port: int, use_tls: bool, path: str = OTLP_LOGS_PATH) -> str:
    """Build the full OTLP endpoint URL."""
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}:{port}{path}"


class OtelLogsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenTelemetry Log Exporter."""

    VERSION = 2

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> ConfigFlowResult:
        """Show menu to choose backend type."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["otel", "syslog"],
        )

    async def async_step_otel(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle OpenTelemetry OTLP configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            use_tls = user_input[CONF_USE_TLS]
            url = _build_endpoint_url(host, port, use_tls, user_input.get(CONF_PATH, OTLP_LOGS_PATH))

            # Validate header fields format before connecting
            extra_headers: dict[str, str] = {}
            bearer_token = user_input.get(CONF_TOKEN, "").strip()
            if bearer_token:
                if not use_tls:
                    _LOGGER.warning("remote_logger: bearer token configured without TLS; token will be sent in plain text")
                extra_headers["Authorization"] = f"Bearer {bearer_token}"
            raw_headers = user_input.get(CONF_HEADERS, "").strip()
            if raw_headers:
                try:
                    extra_headers.update(parse_headers(raw_headers))
                except ValueError:
                    errors[CONF_HEADERS] = "invalid_headers"

            # Validate connectivity
            if not errors:
                session = async_get_clientsession(self.hass, verify_ssl=use_tls)
                errors = await otel_validate(session, url, user_input[CONF_ENCODING], extra_headers or None)
            # Validate resource attributes format
            if not errors:
                raw_attrs = user_input.get(CONF_RESOURCE_ATTRIBUTES, "")
                if raw_attrs.strip():
                    try:
                        parse_resource_attributes(raw_attrs)
                    except ValueError:
                        errors[CONF_RESOURCE_ATTRIBUTES] = "invalid_attributes"

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{BACKEND_OTEL}_{host}_{port}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"OTLP @ {host}:{port}",
                    data={**user_input, CONF_BACKEND: BACKEND_OTEL},
                )

        return self.async_show_form(
            step_id="otel",
            data_schema=self.add_suggested_values_to_schema(OTEL_DATA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:  # noqa: ARG002
        """Initiate reauth after authentication failure."""
        return await self.async_step_reauth_otel()

    async def async_step_reauth_otel(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle re-entry of the bearer token after an authentication failure."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            bearer_token = user_input.get(CONF_TOKEN, "").strip()
            extra_headers: dict[str, str] = {}
            if bearer_token:
                extra_headers["Authorization"] = f"Bearer {bearer_token}"
            raw_headers = reauth_entry.data.get(CONF_HEADERS, "").strip()
            if raw_headers:
                extra_headers.update(parse_headers(raw_headers))

            url = _build_endpoint_url(
                reauth_entry.data[CONF_HOST],
                reauth_entry.data[CONF_PORT],
                reauth_entry.data[CONF_USE_TLS],
                reauth_entry.data.get(CONF_PATH, OTLP_LOGS_PATH),
            )
            session = async_get_clientsession(self.hass, verify_ssl=reauth_entry.data[CONF_USE_TLS])
            errors = await otel_validate(session, url, reauth_entry.data[CONF_ENCODING], extra_headers or None)
            if not errors:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_TOKEN: user_input[CONF_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_otel",
            data_schema=self.add_suggested_values_to_schema(REAUTH_OTEL_DATA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_syslog(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle Syslog RFC 5424 configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            protocol = user_input[CONF_PROTOCOL]
            use_tls = user_input.get(CONF_USE_TLS, False)

            # Validate connectivity
            error = await syslog_validate(self.hass, host, port, protocol, use_tls)
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
            data_schema=self.add_suggested_values_to_schema(SYSLOG_DATA_SCHEMA, user_input or {}),
            errors=errors,
        )
