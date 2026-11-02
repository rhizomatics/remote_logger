"""The remote_logger integration: ship HA system_log_event to an OTLP collector or syslog server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from homeassistant.components.system_log import EVENT_SYSTEM_LOG
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import EVENT_HOMEASSISTANT_CLOSE, EVENT_HOMEASSISTANT_FINAL_WRITE, SupportsResponse, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from custom_components.remote_logger.handler import ExportingLogHandler

from .compat import vol
from .config_flow import OTEL_CONNECTION_KEYS, SYSLOG_CONNECTION_KEYS
from .const import (
    BACKEND_SYSLOG,
    CONF_BACKEND,
    CONF_CUSTOM_EVENTS,
    CONF_EVENT_BASED_LOGGING,
    CONF_LOG_HA_CORE_ACTIVITY,
    CONF_LOG_HA_CORE_CHANGES,
    CONF_LOG_HA_EVENT_BODY,
    CONF_LOG_HA_FULL_STATE_CHANGES,
    CONF_LOG_HA_LIFECYCLE,
    CONF_LOG_HA_STATE_CHANGES,
    CONF_LOG_LEVEL,
    CORE_ACTIVITY_EVENTS,
    CORE_CHANGE_EVENTS,
    CORE_STATE_EVENTS,
    DEFAULT_LOG_LEVEL,
    DOMAIN,
    LIFECYCLE_EVENTS,
    PLATFORMS,
)
from .otel.exporter import OtlpLogExporter
from .sensor import SENSORS
from .syslog.exporter import SyslogExporter

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SEND_LOG = "send_log"
SERVICE_SEND_LOG_SCHEMA = vol.Schema({
    vol.Required("event"): str,
    vol.Required("message"): str,
    vol.Optional("level", default="INFO"): vol.In(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    vol.Optional("attributes"): dict,
})

SERVICE_FLUSH = "flush"

SERVICE_LAST_LOG = "last_log"
SERVICE_LAST_LOG_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
})

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall
    from homeassistant.helpers.typing import ConfigType

    from custom_components.remote_logger.exporter import LogExporter, LogSubmission

_LOGGER = logging.getLogger(__name__)


@dataclass
class RemoteLoggerData:
    """Runtime state for a loaded remote_logger config entry."""

    exporter: LogExporter
    flush_task: asyncio.Task[None]
    cancel_listeners: list[Callable[[], None]]
    log_handler: logging.Handler | None


type RemoteLoggerConfigEntry = ConfigEntry[RemoteLoggerData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions, whether or not an entry is loaded."""
    hass.services.async_register(DOMAIN, SERVICE_SEND_LOG, handle_send_log, schema=SERVICE_SEND_LOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FLUSH, handle_flush)
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAST_LOG,
        handle_last_log,
        schema=SERVICE_LAST_LOG_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> bool:
    """Migrate an older config entry to the current version (HA itself refuses entries from a newer major version)."""
    if entry.minor_version < 2:
        await _async_migrate_unique_ids(hass, entry)
        hass.config_entries.async_update_entry(entry, version=2, minor_version=2)
    if entry.minor_version < 3:
        _migrate_connection_options(hass, entry)
    return True


def _migrate_connection_options(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> None:
    """Move connection settings saved by the old options flow into data, where reconfigure keeps them.

    Options used to override data for every key, so the options copy is the one in effect.
    """
    keys = SYSLOG_CONNECTION_KEYS if entry.data.get(CONF_BACKEND) == BACKEND_SYSLOG else OTEL_CONNECTION_KEYS
    moved = {k: v for k, v in entry.options.items() if k in keys}
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, **moved},
        options={k: v for k, v in entry.options.items() if k not in keys},
        version=2,
        minor_version=3,
    )


async def _async_migrate_unique_ids(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> None:
    """Re-key sensors from the title-based unique ID (slugified "<title>_<key>") to "<entry_id>_<key>"."""
    registry = er.async_get(hass)
    # Longest key first so a key that's a suffix of another can't match the wrong sensor
    keys = sorted((d.key for d in SENSORS), key=len, reverse=True)

    @callback
    def _new_unique_id(entity_entry: er.RegistryEntry) -> dict[str, Any] | None:
        old: str = entity_entry.unique_id
        if entity_entry.domain != "sensor" or old.startswith(f"{entry.entry_id}_"):
            return None
        key = next((k for k in keys if old.endswith(f"_{k}")), None)
        if key is None:
            return None
        new = f"{entry.entry_id}_{key}"
        if registry.async_get_entity_id("sensor", DOMAIN, new):
            _LOGGER.warning("remote_logger: not migrating %s, unique ID %s already in use", entity_entry.entity_id, new)
            return None
        _LOGGER.info("remote_logger: migrating %s unique ID from %s to %s", entity_entry.entity_id, old, new)
        return {"new_unique_id": new}

    await er.async_migrate_entries(hass, entry.entry_id, _new_unique_id)


async def _async_update_listener(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> bool:
    """Set up remote logs from a config entry."""
    backend = entry.data.get(CONF_BACKEND)

    exporter: OtlpLogExporter | SyslogExporter
    if backend == BACKEND_SYSLOG:
        exporter = SyslogExporter(hass, entry)
        label: str = exporter.endpoint_desc
    else:
        exporter = OtlpLogExporter(hass, entry)
        label = exporter.endpoint_url

    error: str | None = await exporter.async_check_connection()
    if error == "invalid_auth":
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="setup_auth_failed", translation_placeholders={"endpoint": label}
        )
    if error:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN, translation_key="setup_cannot_connect", translation_placeholders={"endpoint": label}
        )

    # Options take precedence over initial data for the three event-subscription keys
    opts = {**entry.data, **entry.options}

    async def _flush_on_stop(_: Any) -> None:
        await exporter.disable_buffer()

    cancel_listeners: list[Callable[[], None]] = [
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _flush_on_stop),
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_CLOSE, _flush_on_stop),
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_FINAL_WRITE, _flush_on_stop),
        entry.add_update_listener(_async_update_listener),
    ]

    log_handler: logging.Handler | None = None
    event_based_logging: bool = bool(opts.get(CONF_EVENT_BASED_LOGGING))
    if event_based_logging:
        cancel_listeners.append(hass.bus.async_listen(EVENT_SYSTEM_LOG, exporter.handle_event))
    else:
        log_level_name: str = opts.get(CONF_LOG_LEVEL, DEFAULT_LOG_LEVEL)
        log_handler = ExportingLogHandler(hass, exporter.handle_entry)
        log_handler.setLevel(getattr(logging, log_level_name, logging.INFO))
        logging.root.addHandler(log_handler)

    _LOGGER.info("remote_logger: exporting %s to %s", backend, label)

    event_body: bool = bool(opts.get(CONF_LOG_HA_EVENT_BODY))

    if opts.get(CONF_LOG_HA_LIFECYCLE):
        cancel_listeners.extend(
            hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, event_body=event_body)) for et in LIFECYCLE_EVENTS
        )
        _LOGGER.info("remote_logger: listening for HA lifecycle events")

    if opts.get(CONF_LOG_HA_CORE_CHANGES):
        cancel_listeners.extend(
            hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, event_body=event_body)) for et in CORE_CHANGE_EVENTS
        )
        _LOGGER.info("remote_logger: listening for HA core config events")

    if opts.get(CONF_LOG_HA_STATE_CHANGES):
        cancel_listeners.extend(
            hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, state_only=True, event_body=event_body))
            for et in CORE_STATE_EVENTS
        )
        _LOGGER.info("remote_logger: listening for HA state changes")

    if opts.get(CONF_LOG_HA_FULL_STATE_CHANGES):
        cancel_listeners.extend(
            hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, state_only=False, event_body=event_body))
            for et in CORE_STATE_EVENTS
        )
        _LOGGER.info("remote_logger: listening for HA state changes")

    if opts.get(CONF_LOG_HA_CORE_ACTIVITY):
        cancel_listeners.extend(
            hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, event_body=event_body))
            for et in CORE_ACTIVITY_EVENTS
        )
        _LOGGER.info("remote_logger: listening for HA core activity")

    for et in opts.get(CONF_CUSTOM_EVENTS, []):
        if et.strip():
            cancel_listeners.append(hass.bus.async_listen(et, partial(exporter.handle_ha_event, et, event_body=event_body)))
            _LOGGER.info("remote_logger: Subscribed to custom event %s", et)

    flush_task: asyncio.Task[None] = asyncio.create_task(exporter.flush_loop())

    entry.runtime_data = RemoteLoggerData(
        exporter=exporter,
        flush_task=flush_task,
        cancel_listeners=cancel_listeners,
        log_handler=log_handler,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _loaded_entries(hass: HomeAssistant) -> list[RemoteLoggerConfigEntry]:
    entries: list[RemoteLoggerConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="no_loaded_entries")
    return entries


async def handle_flush(call: ServiceCall) -> None:
    for entry in _loaded_entries(call.hass):
        await entry.runtime_data.exporter.flush()


@callback
def handle_last_log(call: ServiceCall) -> dict[str, Any]:
    entry_id: str = call.data["config_entry_id"]
    entry: RemoteLoggerConfigEntry | None = call.hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"config_entry_id": entry_id},
        )
    submission: LogSubmission | None = entry.runtime_data.exporter.last_sent_payload
    if submission is None:
        return {}
    return submission.for_display()


@callback
def handle_send_log(call: ServiceCall) -> None:
    message: str = call.data["message"]
    level: str = call.data["level"]
    event_name: str = call.data["event"]
    attributes: dict[str, Any] | None = call.data.get("attributes")
    for entry in _loaded_entries(call.hass):
        entry.runtime_data.exporter.log_direct(event_name, message, level, attributes)


async def async_unload_entry(hass: HomeAssistant, entry: RemoteLoggerConfigEntry) -> bool:
    """Unload remote_logger config entry.

    https://developers.home-assistant.io/docs/config_entries_index#unloading-entries
    """
    await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    data = entry.runtime_data

    for cancel in data.cancel_listeners:
        try:
            cancel()
        except Exception as e:  # ruff: ignore[blind-except]
            _LOGGER.warning("remote_logger: Failed to cancel listener on unload: %s", e)

    if data.log_handler is not None:
        logging.root.removeHandler(data.log_handler)

    data.flush_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await data.flush_task

    await data.exporter.flush()
    await data.exporter.close()

    _LOGGER.info("remote_logger: unloaded, flushed remaining logs")
    return True
