
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp
import voluptuous as vol
from homeassistant.const import __version__ as hass_version
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    BATCH_FLUSH_INTERVAL_SECONDS,
    CONF_BATCH_MAX_SIZE,
    CONF_ENCODING,
    CONF_HOST,
    CONF_PORT,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DEFAULT_BATCH_MAX_SIZE,
    DEFAULT_ENCODING,
    DEFAULT_PORT,
    DEFAULT_RESOURCE_ATTRIBUTES,
    DEFAULT_SERVICE_NAME,
    DEFAULT_SEVERITY,
    DEFAULT_USE_TLS,
    ENCODING_JSON,
    ENCODING_PROTOBUF,
    OTLP_LOGS_PATH,
    SCOPE_NAME,
    SCOPE_VERSION,
    SEVERITY_MAP,
)
from .protobuf_encoder import encode_export_logs_request

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


OTEL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
        vol.Optional(CONF_ENCODING, default=DEFAULT_ENCODING): vol.In(
            [ENCODING_JSON, ENCODING_PROTOBUF]
        ),
        vol.Optional(
            CONF_BATCH_MAX_SIZE, default=DEFAULT_BATCH_MAX_SIZE
        ): vol.All(int, vol.Range(min=1, max=10000)),
        vol.Optional(
            CONF_RESOURCE_ATTRIBUTES, default=DEFAULT_RESOURCE_ATTRIBUTES
        ): str,
    }
)


def parse_resource_attributes(raw: str) -> list[tuple[str, str]]:
    """Parse 'key1=val1,key2=val2' into a list of (key, value) tuples.

    Raises ValueError if the format is invalid.
    """
    result = []
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise ValueError(f"Invalid attribute pair: {pair!r}")
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError("Attribute key cannot be empty")
        result.append((key, value))
    return result


def _kv(key: str, value: str) -> dict[str, Any]:
    """Build an OTLP KeyValue attribute with a stringValue."""
    return {"key": key, "value": {"stringValue": value}}


async def validate(session: aiohttp.ClientSession, url: str, encoding: str) -> dict[str, str]:
 # Validate connectivity
    errors: dict[str, str] = {}
    if encoding == ENCODING_PROTOBUF:
        data: bytes = encode_export_logs_request({"resourceLogs": []})
        content_type = "application/x-protobuf"
    elif encoding == ENCODING_JSON:
        data = json.dumps({"resourceLogs": []}).encode("utf-8")
        content_type = "application/json"
    else:
        raise ValueError(f"Unknown encoding {encoding}")
    try:
        async with session.post(
            url,
            data=data,
            headers={"Content-Type": content_type},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400 and resp.status < 500:
                errors["base"] = "cannot_connect"
                _LOGGER.error("OTEL-LOGS client connect failed (%s): %s", resp.status, await resp.text())
            if resp.status >= 500:
                errors["base"] = "cannot_connect"
                _LOGGER.error("OTEL-LOGS server connect failed (%s): %s", resp.status, await resp.text())
    except aiohttp.ClientError as e1:
        errors["base"] = "cannot_connect"
        _LOGGER.error("OTEL-LOGS connect client error: %s", e1)
    except Exception as e2:
        errors["base"] = "unknown"
        _LOGGER.error("OTEL-LOGS connect unknown error: %s", e2)
    return errors


class OtlpLogExporter:
    """Buffers system_log_event records and flushes them as OTLP/HTTP JSON."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._buffer: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        use_tls = entry.data[CONF_USE_TLS]
        scheme = "https" if use_tls else "http"
        self.endpoint_url = f"{scheme}://{host}:{port}{OTLP_LOGS_PATH}"
        self._use_tls = use_tls
        self._use_protobuf = entry.data.get(CONF_ENCODING) == ENCODING_PROTOBUF
        self._batch_max_size = entry.data.get(CONF_BATCH_MAX_SIZE, 100)

        self._resource = self._build_resource(entry)

    def _build_resource(self, entry: ConfigEntry) -> dict[str, Any]:
        """Build the OTLP Resource object with attributes."""
        attrs: list[dict[str, Any]] = [
            _kv("service.name", DEFAULT_SERVICE_NAME),
            _kv("service.version", hass_version or "unknown"),
        ]

        raw = entry.data.get(CONF_RESOURCE_ATTRIBUTES, DEFAULT_RESOURCE_ATTRIBUTES)
        if raw and raw.strip():
            for key, value in parse_resource_attributes(raw):
                attrs.append(_kv(key, value))

        return {"attributes": attrs}

    @callback
    def handle_event(self, event: Event) -> None:
        """Receive a system_log_event and buffer an OTLP logRecord."""
        if event.data and event.data.get("source") and len(event.data["source"]) == 2 and "ha_remote_logs/otel" in event.data["source"]:
            # prevent log loops
            return
        record = self._to_log_record(event.data)
        self._buffer.append(record)

        if len(self._buffer) >= self._batch_max_size:
            self._hass.async_create_task(self.flush())

    def _to_log_record(self, data: Any) -> dict[str, Any]:
        """Convert a system_log_event payload to an OTLP logRecord dict."""
        '''
            "name": str
            "message": list(str)
            "level": str
            "source": (str,int)
            "timestamp": float
            "exception": str
            "count": int
            "first_occurred": float
        '''
        timestamp_s: float = data.get("timestamp", time.time())
        time_unix_nano = str(int(timestamp_s * 1_000_000_000))
        observed_time_unix_nano = str(int(time.time() * 1_000_000_000))

        level: str = data.get("level", "INFO").upper()
        severity_number, severity_text = SEVERITY_MAP.get(level, DEFAULT_SEVERITY)

        messages: list[str] = data.get("message", [])
        message: str = "\n".join(messages)

        attributes: list[dict[str, Any]] = []
        source = data.get("source")
        if source and isinstance(source, tuple):
            source_path, source_lineno = source
            attributes.append(_kv("code.file.path", source_path))
            attributes.append(_kv("code.line.number", source_lineno))
        logger_name = data.get("name")
        if data.get("count"):
            attributes.append(_kv("count", data["count"]))
        if data.get("first_occurred"):
            attributes.append(_kv("first_occurred", data["first_occurred"]))
        if logger_name:
            attributes.append(_kv("logger.name", logger_name))
        exception = data.get("exception")
        if exception:
            attributes.append(_kv("exception.stacktrace", exception))

        return {
            "timeUnixNano": time_unix_nano,
            "observedTimeUnixNano": observed_time_unix_nano,
            "severityNumber": severity_number,
            "severityText": severity_text,
            "body": {"stringValue": message},
            "attributes": attributes,
        }

    async def flush_loop(self) -> None:
        """Periodically flush buffered log records."""
        try:
            while True:
                await asyncio.sleep(BATCH_FLUSH_INTERVAL_SECONDS)
                await self.flush()
        except asyncio.CancelledError:
            raise

    async def flush(self) -> None:
        """Flush all buffered log records to the OTLP endpoint."""
        async with self._lock:
            if not self._buffer:
                return
            records = self._buffer.copy()
            self._buffer.clear()

        request = self._build_export_request(records)

        if self._use_protobuf:
            data = encode_export_logs_request(request)
            content_type = "application/x-protobuf"
        else:
            data = None
            content_type = "application/json"

        try:
            session = async_get_clientsession(self._hass, verify_ssl=self._use_tls)
            kwargs: dict[str, Any] = {
                "headers": {"Content-Type": content_type},
                "timeout": aiohttp.ClientTimeout(total=10),
            }
            if self._use_protobuf:
                kwargs["data"] = data
            else:
                kwargs["json"] = request
            async with session.post(
                self.endpoint_url,
                **kwargs,
            ) as resp:
                if resp.status >= 400:
                    body = await resp.text()
                    _LOGGER.warning(
                        "ha_remote_logs: OTLP endpoint returned HTTP %s: %s",
                        resp.status,
                        body[:200],
                    )

        except aiohttp.ClientError as err:
            _LOGGER.warning("ha_remote_logs: failed to send logs: %s", err)
        except Exception:
            _LOGGER.exception("ha_remote_logs: unexpected error sending logs")

    async def close(self) -> None:
        """Clean up resources (no-op for HTTP-based exporter)."""

    def _build_export_request(
        self, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Wrap logRecords in the ExportLogsServiceRequest envelope."""
        return {
            "resourceLogs": [
                {
                    "resource": self._resource,
                    "scopeLogs": [
                        {
                            "scope": {
                                "name": SCOPE_NAME,
                                "version": SCOPE_VERSION,
                            },
                            "logRecords": records,
                        }
                    ],
                }
            ],
        }
