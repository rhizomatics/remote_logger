"""Config flow for the remote_logger integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HEADERS, CONF_HOST, CONF_PATH, CONF_PORT, CONF_PROTOCOL, CONF_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .compat import vol
from .const import (
    BACKEND_OTEL,
    BACKEND_SYSLOG,
    CONF_BACKEND,
    CONF_CUSTOM_EVENTS,
    CONF_ENCODING,
    CONF_EVENT_BASED_LOGGING,
    CONF_LOG_HA_CORE_ACTIVITY,
    CONF_LOG_HA_CORE_CHANGES,
    CONF_LOG_HA_EVENT_BODY,
    CONF_LOG_HA_FULL_STATE_CHANGES,
    CONF_LOG_HA_LIFECYCLE,
    CONF_LOG_HA_STATE_CHANGES,
    CONF_LOG_LEVEL,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_SUPPRESS_SYSTEM_LOG_EVENT_NAME,
    CONF_USE_TLS,
    DEFAULT_LOG_LEVEL,
    DOMAIN,
)
from .otel.const import (
    CONF_TOKEN_TYPE,
    OTEL_DATA_SCHEMA,
    OTLP_LOGS_PATH,
    REAUTH_OTEL_DATA_SCHEMA,
    TOKEN_TYPE_BEARER,
    VALIDATION_MESSAGE,
)
from .otel.exporter import build_auth_header, parse_headers, parse_resource_attributes
from .otel.exporter import validate as otel_validate
from .syslog.const import SYSLOG_DATA_SCHEMA
from .syslog.exporter import validate as syslog_validate

_LOGGER = logging.getLogger(__name__)


def _to_list(value: Any) -> list[str]:
    """Coerce a stored string (comma/newline-separated) or list to a list of strings."""
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [v.strip() for v in re.split(r"[\n,]+", str(value)) if v.strip()]


COMMON_DATA_SCHEMA = vol.Schema({
    vol.Optional(CONF_EVENT_BASED_LOGGING, default=False): selector.BooleanSelector(),
    vol.Optional(CONF_LOG_LEVEL, default=DEFAULT_LOG_LEVEL): selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            mode=selector.SelectSelectorMode.DROPDOWN,
        ),
    ),
    vol.Required("ha_standard_events"): section(
        vol.Schema({
            vol.Optional(CONF_LOG_HA_LIFECYCLE, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_LOG_HA_CORE_CHANGES, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_LOG_HA_CORE_ACTIVITY, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_LOG_HA_STATE_CHANGES, default=False): selector.BooleanSelector(),
            vol.Optional(CONF_LOG_HA_FULL_STATE_CHANGES, default=False): selector.BooleanSelector(),
        }),
        {"collapsed": False},
    ),
    vol.Optional(CONF_LOG_HA_EVENT_BODY, default=True): selector.BooleanSelector(),
    vol.Optional(CONF_SUPPRESS_SYSTEM_LOG_EVENT_NAME, default=True): selector.BooleanSelector(),
    vol.Optional(CONF_CUSTOM_EVENTS, default=[]): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
})


def _build_endpoint_url(host: str, port: int, use_tls: bool, path: str = OTLP_LOGS_PATH) -> str:
    """Build the full OTLP endpoint URL."""
    scheme = "https" if use_tls else "http"
    return f"{scheme}://{host}:{port}{path}"


# Connection settings live in entry.data, set by the user step and changed by the reconfigure step;
# the options flow only covers the event subscription settings in COMMON_DATA_SCHEMA.
OTEL_CONNECTION_KEYS: frozenset[str] = frozenset(str(k) for k in OTEL_DATA_SCHEMA.schema)
SYSLOG_CONNECTION_KEYS: frozenset[str] = frozenset(str(k) for k in SYSLOG_DATA_SCHEMA.schema)


def _otel_title(host: str, port: int) -> str:
    return f"OTLP @ {host}:{port}"


def _syslog_title(host: str, port: int, protocol: str) -> str:
    return f"Syslog @ {host}:{port} ({protocol.upper()})"


async def _async_validate_otel(
    hass: HomeAssistant, user_input: dict[str, Any], warn_plain_token: bool = False
) -> dict[str, str]:
    """Check OTLP form input: header and attribute formats, then a test record to the collector."""
    errors: dict[str, str] = {}
    use_tls = user_input[CONF_USE_TLS]
    url = _build_endpoint_url(user_input[CONF_HOST], user_input[CONF_PORT], use_tls, user_input.get(CONF_PATH, OTLP_LOGS_PATH))

    # Validate header fields format before connecting
    extra_headers: dict[str, str] = {}
    token = user_input.get(CONF_TOKEN, "").strip()
    if token:
        if warn_plain_token and not use_tls:
            _LOGGER.warning("remote_logger: token configured without TLS; token will be sent in plain text")
        token_type = user_input.get(CONF_TOKEN_TYPE, TOKEN_TYPE_BEARER)
        extra_headers["Authorization"] = build_auth_header(token, token_type)
    raw_headers = "\n".join(user_input.get(CONF_HEADERS, []))
    if raw_headers:
        try:
            extra_headers.update(parse_headers(raw_headers))
        except ValueError:
            errors[CONF_HEADERS] = "invalid_headers"

    # Validate connectivity
    if not errors:
        session = async_get_clientsession(hass, verify_ssl=use_tls)
        errors = await otel_validate(session, url, user_input[CONF_ENCODING], extra_headers or None)
    # Validate resource attributes format
    if not errors:
        raw_attrs = user_input.get(CONF_RESOURCE_ATTRIBUTES, "")
        if raw_attrs.strip():
            try:
                parse_resource_attributes(raw_attrs)
            except ValueError:
                errors[CONF_RESOURCE_ATTRIBUTES] = "invalid_attributes"
    return errors


async def _async_validate_syslog(hass: HomeAssistant, user_input: dict[str, Any]) -> dict[str, str]:
    """Check the syslog server can be reached with the form's settings."""
    error = await syslog_validate(
        hass, user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_PROTOCOL], user_input.get(CONF_USE_TLS, False)
    )
    return {"base": error} if error else {}


class OtelLogsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for OpenTelemetry Log Exporter."""

    VERSION = 2
    # 2.2: sensor unique IDs keyed by entry_id instead of the entry title
    # 2.3: connection settings only in data (the options flow used to copy them into options)
    MINOR_VERSION = 3

    def __init__(self) -> None:
        super().__init__()
        self._pending_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return RemoteLoggerOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
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
            errors = await _async_validate_otel(self.hass, user_input, warn_plain_token=True)

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{BACKEND_OTEL}_{host}_{port}")
                self._abort_if_unique_id_configured()
                self._pending_data = {**user_input, CONF_BACKEND: BACKEND_OTEL}
                self._pending_data["_title"] = _otel_title(host, port)
                return await self.async_step_common()

        return self.async_show_form(
            step_id="otel",
            data_schema=self.add_suggested_values_to_schema(OTEL_DATA_SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders={"validation_message": VALIDATION_MESSAGE},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Initiate reauth after authentication failure."""
        return await self.async_step_reauth_otel()

    async def async_step_reauth_otel(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle re-entry of the bearer token after an authentication failure."""
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get(CONF_TOKEN, "").strip()
            extra_headers: dict[str, str] = {}
            if token:
                token_type = user_input.get(CONF_TOKEN_TYPE, TOKEN_TYPE_BEARER)
                extra_headers["Authorization"] = build_auth_header(token, token_type)
            raw_headers = "\n".join(reauth_entry.data.get(CONF_HEADERS, []))
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
                # async_update_and_abort, not async_update_reload_and_abort: async_setup_entry
                # registers an update listener that already reloads on any entry change. Using the
                # "_reload" variant as well is deprecated, and raises from HA 2026.12.
                return self.async_update_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_TOKEN: user_input[CONF_TOKEN],
                        CONF_TOKEN_TYPE: user_input.get(CONF_TOKEN_TYPE, TOKEN_TYPE_BEARER),
                    },
                )

        return self.async_show_form(
            step_id="reauth_otel",
            data_schema=self.add_suggested_values_to_schema(REAUTH_OTEL_DATA_SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders={"validation_message": VALIDATION_MESSAGE},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the connection settings of an existing entry.

        These are config entry *data*, so HA's guidance is a reconfigure step rather than the
        options flow, which covers only the event subscriptions.
        """
        if self._get_reconfigure_entry().data.get(CONF_BACKEND) == BACKEND_SYSLOG:
            return await self.async_step_reconfigure_syslog()
        return await self.async_step_reconfigure_otel()

    async def async_step_reconfigure_otel(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the OTLP collector connection."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_validate_otel(self.hass, user_input, warn_plain_token=True)
            if not errors:
                return await self._async_update_connection(
                    entry,
                    user_input,
                    OTEL_CONNECTION_KEYS,
                    f"{DOMAIN}_{BACKEND_OTEL}_{user_input[CONF_HOST]}_{user_input[CONF_PORT]}",
                    _otel_title(entry.data[CONF_HOST], entry.data[CONF_PORT]),
                    _otel_title(user_input[CONF_HOST], user_input[CONF_PORT]),
                )
        suggested = user_input or {**entry.data, CONF_HEADERS: _to_list(entry.data.get(CONF_HEADERS, []))}
        return self.async_show_form(
            step_id="reconfigure_otel",
            data_schema=self.add_suggested_values_to_schema(OTEL_DATA_SCHEMA, suggested),
            errors=errors,
            description_placeholders={"validation_message": VALIDATION_MESSAGE},
        )

    async def async_step_reconfigure_syslog(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the syslog server connection."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_validate_syslog(self.hass, user_input)
            if not errors:
                return await self._async_update_connection(
                    entry,
                    user_input,
                    SYSLOG_CONNECTION_KEYS,
                    entry.unique_id,  # one syslog entry only, whatever its server
                    _syslog_title(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_PROTOCOL]),
                    _syslog_title(user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_PROTOCOL]),
                )
        return self.async_show_form(
            step_id="reconfigure_syslog",
            data_schema=self.add_suggested_values_to_schema(SYSLOG_DATA_SCHEMA, user_input or dict(entry.data)),
            errors=errors,
        )

    async def _async_update_connection(
        self,
        entry: ConfigEntry,
        user_input: dict[str, Any],
        connection_keys: frozenset[str],
        unique_id: str | None,
        old_default_title: str,
        new_default_title: str,
    ) -> ConfigFlowResult:
        if unique_id != entry.unique_id:
            # Pointing at a collector that another entry already exports to
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
        # Replace every connection key, so an optional field cleared in the form (e.g. the token)
        # is removed rather than keeping its old value.
        data = {k: v for k, v in entry.data.items() if k not in connection_keys}
        # async_update_and_abort, not async_update_reload_and_abort: the update listener reloads
        return self.async_update_and_abort(
            entry,
            unique_id=unique_id,
            # Keep a title the user chose; follow the endpoint only if it's still the generated one
            title=new_default_title if entry.title == old_default_title else entry.title,
            data={**data, **user_input},
        )

    async def async_step_syslog(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle Syslog RFC 5424 configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            protocol = user_input[CONF_PROTOCOL]
            errors = await _async_validate_syslog(self.hass, user_input)

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_{BACKEND_SYSLOG}")
                self._abort_if_unique_id_configured()
                self._pending_data = {**user_input, CONF_BACKEND: BACKEND_SYSLOG}
                self._pending_data["_title"] = _syslog_title(host, port, protocol)
                return await self.async_step_common()

        return self.async_show_form(
            step_id="syslog",
            data_schema=self.add_suggested_values_to_schema(SYSLOG_DATA_SCHEMA, user_input or {}),
            errors=errors,
        )

    async def async_step_common(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure common event subscription options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            flat: dict[str, Any] = {k: v for k, v in user_input.items() if not isinstance(v, dict)}
            for v in user_input.values():
                if isinstance(v, dict):
                    flat.update(v)
            if flat.get(CONF_LOG_HA_STATE_CHANGES) and flat.get(CONF_LOG_HA_FULL_STATE_CHANGES):
                errors[CONF_LOG_HA_FULL_STATE_CHANGES] = "state_changes_exclusive"
            else:
                title = self._pending_data.pop("_title")
                return self.async_create_entry(
                    title=title,
                    data={**self._pending_data, **flat},
                )

        return self.async_show_form(
            step_id="common",
            data_schema=self.add_suggested_values_to_schema(COMMON_DATA_SCHEMA, user_input or {}),
            errors=errors,
            description_placeholders={
                "learn_more": "[Learn about HA events](https://www.home-assistant.io/docs/configuration/events/)",
            },
        )


class RemoteLoggerOptionsFlow(OptionsFlow):
    """Allow editing event subscriptions after setup. Connection settings use the reconfigure step."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the event subscription form."""
        return await self.async_step_events()

    async def async_step_events(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle event subscription options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            flat: dict[str, Any] = {k: v for k, v in user_input.items() if not isinstance(v, dict)}
            for v in user_input.values():
                if isinstance(v, dict):
                    flat.update(v)
            if flat.get(CONF_LOG_HA_STATE_CHANGES) and flat.get(CONF_LOG_HA_FULL_STATE_CHANGES):
                errors[CONF_LOG_HA_FULL_STATE_CHANGES] = "state_changes_exclusive"
            else:
                return self.async_create_entry(title="", data=flat)

        if user_input is not None:
            suggested = user_input
        else:
            merged = {**self._config_entry.data, **self._config_entry.options}
            suggested = {
                CONF_EVENT_BASED_LOGGING: merged.get(CONF_EVENT_BASED_LOGGING, False),
                CONF_LOG_LEVEL: merged.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL),
                "ha_standard_events": {
                    CONF_LOG_HA_LIFECYCLE: merged.get(CONF_LOG_HA_LIFECYCLE, False),
                    CONF_LOG_HA_CORE_CHANGES: merged.get(CONF_LOG_HA_CORE_CHANGES, False),
                    CONF_LOG_HA_CORE_ACTIVITY: merged.get(CONF_LOG_HA_CORE_ACTIVITY, False),
                    CONF_LOG_HA_STATE_CHANGES: merged.get(CONF_LOG_HA_STATE_CHANGES, False),
                    CONF_LOG_HA_FULL_STATE_CHANGES: merged.get(CONF_LOG_HA_FULL_STATE_CHANGES, False),
                },
                CONF_LOG_HA_EVENT_BODY: merged.get(CONF_LOG_HA_EVENT_BODY, False),
                CONF_SUPPRESS_SYSTEM_LOG_EVENT_NAME: merged.get(CONF_SUPPRESS_SYSTEM_LOG_EVENT_NAME, True),
                CONF_CUSTOM_EVENTS: _to_list(merged.get(CONF_CUSTOM_EVENTS, [])),
            }
        return self.async_show_form(
            step_id="events",
            data_schema=self.add_suggested_values_to_schema(COMMON_DATA_SCHEMA, suggested),
            errors=errors,
            description_placeholders={
                "learn_more": "[Learn about HA events](https://www.home-assistant.io/docs/configuration/events/)",
            },
        )
