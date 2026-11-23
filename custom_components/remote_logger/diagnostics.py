"""Diagnostics support for remote_logger."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HEADERS, CONF_TOKEN

from .const import CONF_TLS_CLIENT_KEY

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .remote_logger import RemoteLoggerConfigEntry

# Headers can carry credentials as well as the token; the client key path names a secret file
TO_REDACT: frozenset[str] = frozenset({CONF_TOKEN, CONF_HEADERS, CONF_TLS_CLIENT_KEY})


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    exporter = entry.runtime_data.exporter
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "exporter": {
            "logger_type": exporter.logger_type,
            "reachable": exporter.reachable,
            "event_count": exporter.event_count,
            "last_event": exporter.last_event,
            "posting_count": exporter.posting_count,
            "last_posting": exporter.last_posting,
            "format_error_count": exporter.format_error_count,
            "last_format_error": exporter.last_format_error,
            "last_format_error_message": exporter.last_format_error_message,
            "posting_error_count": exporter.posting_error_count,
            "last_posting_error": exporter.last_posting_error,
            "last_posting_error_message": exporter.last_posting_error_message,
        },
        "last_sent_payload": exporter.last_sent_payload.for_display() if exporter.last_sent_payload else None,
    }
