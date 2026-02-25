import asyncio
import logging
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.auth import HomeAssistant
from homeassistant.core import Event, callback
from homeassistant.util import dt as dt_util

from custom_components.remote_logger.const import BATCH_FLUSH_INTERVAL_SECONDS

if TYPE_CHECKING:
    import datetime as dt

_LOGGER = logging.getLogger(__name__)


@dataclass
class LogMessage:
    payload: Any
    sent: bool = False


class LogExporter:
    """Base class for log exporters"""

    logger_type: str

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass: HomeAssistant = hass
        self._batch_max_size: int
        self.format_error_count: int = 0
        self.posting_error_count: int = 0
        self.event_count: int = 0
        self.sent_count: int = 0
        self.last_format_error_message: str | None = None
        self.last_format_error: dt.datetime | None = None
        self.last_posting_error_message: str | None = None
        self.last_posting_error: dt.datetime | None = None
        self._buffer: list[LogMessage] = []
        self.self_source: str = f"custom_components/remote_logger/{self.logger_type}"

    @callback
    def handle_event(self, event: Event) -> None:
        self.on_event()
        if (
            event.data
            and event.data.get("source")
            and len(event.data["source"]) == 2
            and self.self_source in event.data["source"][0]
        ):
            # prevent log loops
            return
        try:
            record: LogMessage = self._to_log_record(event.data)
            self._buffer.append(record)

            if len(self._buffer) >= self._batch_max_size:
                self._hass.async_create_task(self.flush())
        except Exception as e:
            _LOGGER.error("remote_logger: %s handler failure %s on %s", self.logger_type, e, event.data)
            self.on_format_error(str(e))

    @abstractmethod
    def _to_log_record(self, data: Mapping[str, Any]) -> LogMessage:
        pass

    @callback
    @abstractmethod
    async def flush(self) -> None:
        pass

    async def flush_loop(self) -> None:
        """Periodically flush buffered log records."""
        try:
            while True:
                await asyncio.sleep(BATCH_FLUSH_INTERVAL_SECONDS)
                await self.flush()
        except asyncio.CancelledError:
            raise

    async def close(self) -> None:
        """Clean up resources (no-op for HTTP-based exporter)."""
        pass

    def on_format_error(self, message: str) -> None:
        self.format_error_count += 1
        self.last_format_error_message = message
        self.last_format_error = dt_util.now()

    def on_posting_error(self, message: str) -> None:
        self.posting_error_count += 1
        self.last_posting_error_message = message
        self.last_posting_error = dt_util.now()

    def on_success(self) -> None:
        self.sent_count += 1
        self.last_sent = dt_util.now()

    def on_event(self) -> None:
        self.event_count += 1
        self.last_event = dt_util.now()
