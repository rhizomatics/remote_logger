from __future__ import annotations

import datetime as dt
import logging
import re
import typing

from homeassistant import __path__ as HOMEASSISTANT_PATH
from homeassistant.components.system_log import LogEntry
from homeassistant.util import dt as dt_util

if typing.TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

type KeyType = tuple[str, tuple[str, int], tuple[str, int, str] | None]


class EntryHandler(typing.Protocol):
    """Receives each log entry, as LogExporter.handle_entry does."""

    def __call__(self, entry: Mapping[str, typing.Any], time_fired: dt.datetime) -> None: ...


class ExportingLogHandler(logging.Handler):
    """Log handler for error messages."""

    def __init__(
        self,
        hass: HomeAssistant,
        handler: EntryHandler,
    ) -> None:
        """Initialize a new LogErrorHandler."""
        super().__init__()
        self.handler = handler
        self.tz = dt_util.get_default_time_zone()
        self.paths_re = re.compile(rf"(?:{re.escape(HOMEASSISTANT_PATH[0])}|{re.escape(hass.config.config_dir)})/(.*)")

    def emit(self, record: logging.LogRecord) -> None:
        """Save error and warning logs.

        Everything logged with error or warning is saved in local buffer. A
        default upper limit is set to 50 (older entries are discarded) but can
        be changed if needed.
        """
        if record.name.startswith("custom_components.remote_logger"):
            # guard against loops, use exposed entities to check for remote_logger errors
            return
        entry: LogEntry = LogEntry(record, self.paths_re, formatter=self.formatter, figure_out_source=True)
        self.handler(entry.to_dict(), time_fired=dt.datetime.fromtimestamp(record.created, tz=self.tz))
