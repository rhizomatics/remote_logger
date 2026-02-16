"""The ha_remote_logs integration: ship HA system_log_event to an OTLP collector or syslog server."""
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
from .otel import OtlpLogExporter
from .syslog import SyslogExporter

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:  # noqa: RUF029
    """Set up remote logs from a config entry."""
    backend = entry.data.get(CONF_BACKEND)

    exporter: OtlpLogExporter | SyslogExporter
    if backend == BACKEND_SYSLOG:
        syslog_exp = SyslogExporter(hass, entry)
        label = syslog_exp.endpoint_desc
        exporter = syslog_exp
    else:
        otel_exp = OtlpLogExporter(hass, entry)
        label = otel_exp.endpoint_url
        exporter = otel_exp

    cancel_listener = hass.bus.async_listen(EVENT_SYSTEM_LOG, exporter.handle_event)
    flush_task = asyncio.create_task(exporter.flush_loop())

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "cancel_listener": cancel_listener,
        "flush_task": flush_task,
        "exporter": exporter,
    }

    _LOGGER.info(
        "ha_remote_logs: listening for system_log_event, exporting to %s",
        label,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload ha_remote_logs config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data is None:
        return True

    data["cancel_listener"]()

    data["flush_task"].cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await data["flush_task"]

    await data["exporter"].flush()
    await data["exporter"].close()

    _LOGGER.info("ha_remote_logs: unloaded, flushed remaining logs")
    return True
