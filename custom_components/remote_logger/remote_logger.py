"""The remote_logger integration: ship HA system_log_event to an OTLP collector or syslog server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from functools import partial
from typing import TYPE_CHECKING

from .const import (
    BACKEND_SYSLOG,
    CONF_BACKEND,
    CONF_CUSTOM_EVENTS,
    CONF_LOG_HA_CORE_ACTIVITY,
    CONF_LOG_HA_CORE_CHANGES,
    CONF_LOG_HA_LIFECYCLE,
    CONF_LOG_HA_STATE_CHANGES,
    CORE_ACTIVITY_EVENTS,
    CORE_CHANGE_EVENTS,
    CORE_STATE_EVENTS,
    DOMAIN,
    EVENT_SYSTEM_LOG,
    LIFECYCLE_EVENTS,
    PLATFORMS,
)
from .otel.exporter import OtlpLogExporter
from .syslog.exporter import SyslogExporter

REF_CANCEL_LISTENERS = "cancel_listeners"
REF_FLUSH_TASK = "flush_task"
REF_EXPORTER = "exporter"

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up remote logs from a config entry."""
    backend = entry.data.get(CONF_BACKEND)

    exporter: OtlpLogExporter | SyslogExporter
    if backend == BACKEND_SYSLOG:
        exporter = SyslogExporter(hass, entry)
        label: str = exporter.endpoint_desc
    else:
        exporter = OtlpLogExporter(hass, entry)
        label = exporter.endpoint_url

    # Options take precedence over initial data for the three event-subscription keys
    opts = {**entry.data, **entry.options}

    cancel_listeners: list[Callable[[], None]] = [
        hass.bus.async_listen(EVENT_SYSTEM_LOG, exporter.handle_event),
        entry.add_update_listener(_async_update_listener),
    ]
    _LOGGER.info("remote_logger: listening for system_log_event, exporting %s to %s", backend, label)

    if opts.get(CONF_LOG_HA_LIFECYCLE):
        cancel_listeners.extend(hass.bus.async_listen(et, partial(exporter.handle_ha_event, et)) for et in LIFECYCLE_EVENTS)
        _LOGGER.info("remote_logger: listening for HA lifecycle events")

    if opts.get(CONF_LOG_HA_CORE_CHANGES):
        cancel_listeners.extend(hass.bus.async_listen(et, partial(exporter.handle_ha_event, et)) for et in CORE_CHANGE_EVENTS)
        _LOGGER.info("remote_logger: listening for HA core config events")

    if opts.get(CONF_LOG_HA_STATE_CHANGES):
        cancel_listeners.extend(hass.bus.async_listen(et, partial(exporter.handle_ha_event, et)) for et in CORE_STATE_EVENTS)
        _LOGGER.info("remote_logger: listening for HA state changes")

    if opts.get(CONF_LOG_HA_CORE_ACTIVITY):
        cancel_listeners.extend(hass.bus.async_listen(et, partial(exporter.handle_ha_event, et)) for et in CORE_ACTIVITY_EVENTS)
        _LOGGER.info("remote_logger: listening for HA core activity")

    custom_events_raw = opts.get(CONF_CUSTOM_EVENTS, "")
    cancel_listeners.extend(
        hass.bus.async_listen(et, partial(exporter.handle_ha_event, et))
        for et in (e.strip() for e in custom_events_raw.splitlines() if e.strip())
    )

    flush_task: asyncio.Task[None] = asyncio.create_task(exporter.flush_loop())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        REF_CANCEL_LISTENERS: cancel_listeners,
        REF_FLUSH_TASK: flush_task,
        REF_EXPORTER: exporter,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload remote_logger config entry."""
    await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data is None:
        return True

    for cancel in data.get(REF_CANCEL_LISTENERS, []):
        cancel()

    if data.get(REF_FLUSH_TASK):
        data[REF_FLUSH_TASK].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await data[REF_FLUSH_TASK]

    if data.get(REF_EXPORTER):
        await data[REF_EXPORTER].flush()
        await data[REF_EXPORTER].close()

    _LOGGER.info("remote_logger: unloaded, flushed remaining logs")
    return True
