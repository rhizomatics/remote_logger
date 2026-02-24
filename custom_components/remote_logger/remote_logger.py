"""The remote_logger integration: ship HA system_log_event to an OTLP collector or syslog server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from .const import (
    BACKEND_SYSLOG,
    CONF_BACKEND,
    DOMAIN,
    EVENT_SYSTEM_LOG,
)
from .otel.exporter import OtlpLogExporter
from .syslog.exporter import SyslogExporter

REF_CANCEL_LISTENER = "cancel_listener"
REF_FLUSH_TASK = "flush_task"
REF_EXPORTER = "exporter"

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


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

    cancel_listener = hass.bus.async_listen(EVENT_SYSTEM_LOG, exporter.handle_event)
    flush_task: asyncio.Task[None] = asyncio.create_task(exporter.flush_loop())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        REF_CANCEL_LISTENER: cancel_listener,
        REF_FLUSH_TASK: flush_task,
        REF_EXPORTER: exporter,
    }
    await hass.config_entries.async_forward_entry_setups(entry, ["binary_sensor"])

    _LOGGER.info("remote_logger: listening for system_log_event, exporting %s to %s", backend, label)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload remote_logger config entry."""
    await hass.config_entries.async_unload_platforms(entry, ["binary_sensor"])
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data is None:
        return True

    if data.get(REF_CANCEL_LISTENER):
        data[REF_CANCEL_LISTENER]()
        del data[REF_CANCEL_LISTENER]

    if data.get(REF_FLUSH_TASK):
        data[REF_FLUSH_TASK].cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await data[REF_FLUSH_TASK]
        del data[REF_FLUSH_TASK]

    if data.get(REF_EXPORTER):
        await data[REF_EXPORTER].flush()
        await data[REF_EXPORTER].close()
        del data[REF_EXPORTER]

    _LOGGER.info("remote_logger: unloaded, flushed remaining logs")
    return True
