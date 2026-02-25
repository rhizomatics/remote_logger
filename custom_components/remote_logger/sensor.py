"""Binary sensor platform for remote_logger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.util import slugify

from .const import DOMAIN
from .remote_logger import REF_EXPORTER

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from custom_components.remote_logger.exporter import LogExporter

from typing import TYPE_CHECKING, Any

from homeassistant.const import EntityCategory


@dataclass(frozen=True, kw_only=True)
class RemoteLoggerDiagnosticEntityDescription(SensorEntityDescription):
    """Describes diagnostic sensor entity."""

    value_fn: Callable[[LogExporter], str | int | float | None]
    attr_fn: Callable[[LogExporter], dict[str, Any]] = lambda _: {}


SENSORS: tuple[RemoteLoggerDiagnosticEntityDescription, ...] = (
    RemoteLoggerDiagnosticEntityDescription(
        key="format_errors",
        name="Format Errors",
        translation_key="format_errors",
        native_unit_of_measurement="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda logger: logger.format_error_count,
        attr_fn=lambda exporter: {
            "last_error_time": exporter.last_format_error,
            "last_error_message": exporter.last_format_error_message,
        },
    ),
    RemoteLoggerDiagnosticEntityDescription(
        key="post_errors",
        translation_key="post_errors",
        name="Posting Errors",
        native_unit_of_measurement="error",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda logger: logger.posting_error_count,
        attr_fn=lambda exporter: {
            "last_error_time": exporter.last_posting_error,
            "last_error_message": exporter.last_posting_error_message,
        },
    ),
    RemoteLoggerDiagnosticEntityDescription(
        key="events",
        translation_key="events",
        name="Log Events",
        native_unit_of_measurement="event",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda exporter: exporter.event_count,
        attr_fn=lambda exporter: {"last_event_time": exporter.last_event},
    ),
    RemoteLoggerDiagnosticEntityDescription(
        key="postings",
        name="Postings",
        translation_key="postings",
        native_unit_of_measurement="posting",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda exporter: exporter.posting_count,
        attr_fn=lambda exporter: {"last_posting_time": exporter.last_posting},
    ),
)


class LoggerEntity(SensorEntity):
    """Represent a diagnostic tracking loggwe."""

    _attr_entity_category: EntityCategory = EntityCategory.DIAGNOSTIC  # pyright: ignore[reportIncompatibleVariableOverride]
    _attr_should_poll = True
    entity_description: RemoteLoggerDiagnosticEntityDescription

    def __init__(self, exporter: LogExporter, description: RemoteLoggerDiagnosticEntityDescription) -> None:
        super().__init__()
        self._exporter = exporter
        self.entity_description = description  # pyright: ignore[reportIncompatibleVariableOverride]
        self._attr_unique_id = f"{slugify(exporter.name)}_{description.key}"
        self.name = f"{exporter.name} {description.name}"

    @property
    def native_value(self) -> str | int | float | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state."""
        return self.entity_description.value_fn(self._exporter)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state attributes."""
        return self.entity_description.attr_fn(self._exporter)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up remote_logger binary sensor from a config entry."""
    exporter = hass.data[DOMAIN][entry.entry_id][REF_EXPORTER]
    async_add_entities(LoggerEntity(exporter, description) for description in SENSORS)
