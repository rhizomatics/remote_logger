"""Config flow for the ha_remote_logs integration."""
from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BACKEND_OTEL,
    BACKEND_SYSLOG,
    CONF_APP_NAME,
    CONF_BACKEND,
    CONF_BATCH_MAX_SIZE,
    CONF_ENCODING,
    CONF_FACILITY,
    CONF_HOST,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DEFAULT_APP_NAME,
    DEFAULT_BATCH_MAX_SIZE,
    DEFAULT_ENCODING,
    DEFAULT_FACILITY,
    DEFAULT_PORT,
    DEFAULT_PROTOCOL,
    DEFAULT_RESOURCE_ATTRIBUTES,
    DEFAULT_SYSLOG_PORT,
    DEFAULT_USE_TLS,
    DOMAIN,
    ENCODING_JSON,
    ENCODING_PROTOBUF,
    OTLP_LOGS_PATH,
    PROTOCOL_TCP,
    PROTOCOL_UDP,
    SYSLOG_FACILITY_MAP,
)

_LOGGER = logging.getLogger(__name__)

STEP_OTEL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
        vol.Optional(CONF_ENCODING, default=DEFAULT_ENCODING): vol.In(
            [ENCODING_JSON, ENCODING_PROTOBUF]
        ),
        vol.Optional(
            CONF_BATCH_MAX_SIZE, default=DEFAULT_BATCH_MAX_SIZE
        ): vol.All(int, vol.Range(min=1, max=10000)),
        vol.Optional(
            CONF_RESOURCE_ATTRIBUTES, default=DEFAULT_RESOURCE_ATTRIBUTES
        ): str,
    }
)

STEP_SYSLOG_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_SYSLOG_PORT): int,
        vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(
            [PROTOCOL_UDP, PROTOCOL_TCP]
        ),
        vol.Optional(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
        vol.Optional(CONF_APP_NAME, default=DEFAULT_APP_NAME): str,
        vol.Optional(CONF_FACILITY, default=DEFAULT_FACILITY): vol.In(
            list(SYSLOG_FACILITY_MAP.keys())
        ),
    }
)


def _build_endpoint_url(host: str, port: int, use_tls: bool) -> str:
    """Build the full OTLP endpoint URL."""
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}:{port}{OTLP_LOGS_PATH}"


def parse_resource_attributes(raw: str) -> list[tuple[str, str]]:
    """Parse 'key1=val1,key2=val2' into a list of (key, value) tuples.

    Raises ValueError if the format is invalid.
    """
    result = []
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Invalid attribute pair: {pair!r}")
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError("Attribute key cannot be empty")
        result.append((key, value))
    return result


async def _test_syslog_connectivity(
    hass: Any, host: str, port: int, protocol: str, use_tls: bool
) -> str | None:
    """Test connectivity to a syslog endpoint. Returns error key or None."""
    loop = hass.loop
    try:
        if protocol == PROTOCOL_UDP:
            # Quick UDP test: just resolve and create a socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setblocking(False)
                await loop.run_in_executor(
                    None, lambda: socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM)
                )
            finally:
                sock.close()
        else:
            # TCP: actually connect
            ssl_ctx = True if use_tls else None
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx),
                timeout=10,
            )
            writer.close()
            await writer.wait_closed()
    except (OSError, TimeoutError, ConnectionRefusedError) as err:
        _LOGGER.error("Syslog connect failed: %s", err)
        return "cannot_connect"
    except Exception as err:
        _LOGGER.error("Syslog connect unknown error: %s", err)
        return "unknown"
    return None


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
            try:
                session = async_get_clientsession(self.hass, verify_ssl=use_tls)
                async with session.post(
                    url,
                    json={"resourceLogs": []},
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        errors["base"] = "cannot_connect"
                        _LOGGER.error("OTEL-LOGS connect failed: %s", resp)
            except aiohttp.ClientError as e1:
                errors["base"] = "cannot_connect"
                _LOGGER.error("OTEL-LOGS connect client error: %s", e1)
            except Exception as e2:
                errors["base"] = "unknown"
                _LOGGER.error("OTEL-LOGS connect unknown error: %s", e2)

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
            data_schema=STEP_OTEL_DATA_SCHEMA,
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
            error = await _test_syslog_connectivity(
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
            data_schema=STEP_SYSLOG_DATA_SCHEMA,
            errors=errors,
        )
