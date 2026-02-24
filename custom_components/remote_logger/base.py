from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    import datetime as dt


class LoggerEntity(BinarySensorEntity):
    """Represent a diagnostic tracking loggwe."""

    _attr_entity_category: EntityCategory = EntityCategory.DIAGNOSTIC  # pyright: ignore[reportIncompatibleVariableOverride]
    _attr_should_poll = True

    def __init__(self) -> None:
        super().__init__()
        self.exception_count: int = 0
        self.event_count: int = 0
        self.sent_count: int = 0
        self.last_exception_message: str | None = None
        self.last_exception: dt.datetime | None = None

    @property
    def is_on(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self.sent_count > 0

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the state attributes."""
        return {
            "last_exception_message": self.last_exception_message,
            "last_exception": self.last_exception.isoformat() if self.last_exception else None,
            "exception_count": self.exception_count,
            "event_count": self.event_count,
            "last_event": self.last_event.isoformat() if self.last_event else None,
            "sent_count": self.sent_count,
            "last_sent": self.last_sent.isoformat() if self.last_sent else None,
        }

    def on_error(self, message: str) -> None:
        self.exception_count += 1
        self.last_exception_message = message
        self.last_exception = dt_util.now()

    def on_success(self) -> None:
        self.sent_count += 1
        self.last_sent = dt_util.now()

    def on_event(self) -> None:
        self.event_count += 1
        self.last_event = dt_util.now()
