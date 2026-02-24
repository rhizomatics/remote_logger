"""Binary sensor platform for remote_logger."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN
from .remote_logger import REF_EXPORTER

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up remote_logger binary sensor from a config entry."""
    exporter = hass.data[DOMAIN][entry.entry_id][REF_EXPORTER]
    async_add_entities([exporter])
