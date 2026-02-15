"""The ha_remote_logs integration: ship HA system_log_event to an OTLP collector or syslog server."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import ssl
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.const import __version__ as hass_version
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_flow import parse_resource_attributes
from .const import (
    BACKEND_SYSLOG,
    BATCH_FLUSH_INTERVAL_SECONDS,
    CONF_APP_NAME,
    CONF_BACKEND,
    CONF_BATCH_MAX_SIZE,
    CONF_ENCODING,
    CONF_FACILITY,
    CONF_HOST,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DEFAULT_APP_NAME,
    DEFAULT_FACILITY,
    DEFAULT_RESOURCE_ATTRIBUTES,
    DEFAULT_SERVICE_NAME,
    DEFAULT_SEVERITY,
    DEFAULT_SYSLOG_SEVERITY,
    DOMAIN,
    ENCODING_PROTOBUF,
    EVENT_SYSTEM_LOG,
    OTLP_LOGS_PATH,
    PROTOCOL_UDP,
    SCOPE_NAME,
    SCOPE_VERSION,
    SEVERITY_MAP,
    SYSLOG_FACILITY_MAP,
    SYSLOG_SEVERITY_MAP,
)
from .protobuf_encoder import encode_export_logs_request

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

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
        record = self._to_log_record(event.data)
        self._buffer.append(record)

        if len(self._buffer) >= self._batch_max_size and len(self._buffer)<10:
            self._hass.async_create_task(self.flush())

    def _to_log_record(self, data: Any) -> dict[str, Any]:
        """Convert a system_log_event payload to an OTLP logRecord dict."""
        timestamp_s: float = data.get("timestamp", time.time())
        time_unix_nano = str(int(timestamp_s * 1_000_000_000))
        observed_time_unix_nano = str(int(time.time() * 1_000_000_000))

        level: str = data.get("level", "INFO").upper()
        severity_number, severity_text = SEVERITY_MAP.get(level, DEFAULT_SEVERITY)

        messages: list[str] = data.get("message", [])
        message: str = "/n/r".join(messages)

        attributes: list[dict[str, Any]] = []
        source = data.get("source")
        if source:
            attributes.append(_kv("source", source))
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


class SyslogExporter:
    """Buffers system_log_event records and flushes them as RFC 5424 syslog messages."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._buffer: list[Any] = []
        self._lock = asyncio.Lock()

        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_PORT]
        self._protocol = entry.data.get(CONF_PROTOCOL, PROTOCOL_UDP)
        self._use_tls = entry.data.get(CONF_USE_TLS, False)
        self._app_name = entry.data.get(CONF_APP_NAME, DEFAULT_APP_NAME)
        facility_name = entry.data.get(CONF_FACILITY, DEFAULT_FACILITY)
        self._facility = SYSLOG_FACILITY_MAP.get(facility_name, 1)
        self._hostname = "-"

        # TCP connection state (lazily created)
        self._tcp_reader: asyncio.StreamReader | None = None
        self._tcp_writer: asyncio.StreamWriter | None = None

        # UDP transport state (lazily created)
        self._udp_transport: asyncio.DatagramTransport | None = None

        self.endpoint_desc = (
            f"syslog://{self._host}:{self._port} ({self._protocol.upper()}"
            f"{'+TLS' if self._use_tls and self._protocol != PROTOCOL_UDP else ''})"
        )

    @callback
    def handle_event(self, event: Event) -> None:
        """Receive a system_log_event and buffer it."""
        self._buffer.append(event.data)

    def _to_syslog_message(self, data: Any) -> bytes:
        """Convert a system_log_event payload to an RFC 5424 syslog message."""
        level: str = data.get("level", "INFO").upper()
        severity = SYSLOG_SEVERITY_MAP.get(level, DEFAULT_SYSLOG_SEVERITY)
        pri = self._facility * 8 + severity

        # RFC 5424 timestamp
        timestamp_s: float = data.get("timestamp", time.time())
        dt = datetime.fromtimestamp(timestamp_s, tz=UTC)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Message body
        messages: list[str] = data.get("message", [])
        msg = " ".join(messages) if messages else "-"

        # Structured data with meta info
        sd = "-"
        sd_params: list[str] = []
        source = data.get("source")
        if source:
            sd_params.append(f'source="{_sd_escape(source)}"')
        logger_name = data.get("name")
        if logger_name:
            sd_params.append(f'logger="{_sd_escape(logger_name)}"')
        if data.get("count"):
            sd_params.append(f'count="{data["count"]}"')
        if data.get("first_occurred"):
            sd_params.append(f'firstOccurred="{data["first_occurred"]}"')
        if sd_params:
            sd = f"[meta {' '.join(sd_params)}]"

        # Include exception as part of message if present
        exception = data.get("exception")
        if exception:
            msg = f"{msg}\n{exception}"

        # RFC 5424: <PRI>VERSION SP TIMESTAMP SP HOSTNAME SP APP-NAME SP PROCID SP MSGID SP SD [SP MSG]
        # VERSION = 1, PROCID = -, MSGID = -
        syslog_line = f"<{pri}>1 {timestamp} {self._hostname} {self._app_name} - - {sd} {msg}"

        return syslog_line.encode("utf-8", errors="replace")

    async def flush_loop(self) -> None:
        """Periodically flush buffered log records."""
        try:
            while True:
                await asyncio.sleep(BATCH_FLUSH_INTERVAL_SECONDS)
                await self.flush()
        except asyncio.CancelledError:
            raise

    async def flush(self) -> None:
        """Flush all buffered log records to the syslog endpoint."""
        async with self._lock:
            if not self._buffer:
                return
            records = self._buffer.copy()
            self._buffer.clear()

        messages = [self._to_syslog_message(r) for r in records]

        try:
            if self._protocol == PROTOCOL_UDP:
                await self._send_udp(messages)
            else:
                await self._send_tcp(messages)
        except Exception:
            _LOGGER.exception("ha_remote_logs: unexpected error sending syslog messages")

    async def _send_udp(self, messages: list[bytes]) -> None:
        """Send syslog messages over UDP."""
        try:
            if self._udp_transport is None or self._udp_transport.is_closing():
                loop = asyncio.get_running_loop()
                self._udp_transport, _ = await loop.create_datagram_endpoint(
                    asyncio.DatagramProtocol,
                    remote_addr=(self._host, self._port),
                )
            for msg in messages:
                self._udp_transport.sendto(msg)
        except OSError as err:
            _LOGGER.warning("ha_remote_logs: failed to send syslog via UDP: %s", err)
            self._udp_transport = None

    async def _send_tcp(self, messages: list[bytes]) -> None:
        """Send syslog messages over TCP with octet-counting framing (RFC 6587)."""
        try:
            if self._tcp_writer is None or self._tcp_writer.is_closing():
                await self._connect_tcp()

            writer = self._tcp_writer
            assert writer is not None  # Set by _connect_tcp above

            for msg in messages:
                # Octet-counting: "LEN SP MSG"
                frame = f"{len(msg)} ".encode("ascii") + msg
                writer.write(frame)
            await writer.drain()
        except (OSError, ConnectionError) as err:
            _LOGGER.warning("ha_remote_logs: failed to send syslog via TCP: %s", err)
            await self._close_tcp()

    async def _connect_tcp(self) -> None:
        """Establish a TCP connection to the syslog server."""
        ssl_ctx: ssl.SSLContext | None = None
        if self._use_tls:
            ssl_ctx = ssl.create_default_context()

        self._tcp_reader, self._tcp_writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port, ssl=ssl_ctx),
            timeout=10,
        )

    async def _close_tcp(self) -> None:
        """Close the TCP connection."""
        if self._tcp_writer is not None:
            with contextlib.suppress(Exception):
                self._tcp_writer.close()
                await self._tcp_writer.wait_closed()
            self._tcp_writer = None
            self._tcp_reader = None

    async def close(self) -> None:
        """Clean up transport resources."""
        if self._udp_transport is not None:
            self._udp_transport.close()
            self._udp_transport = None
        await self._close_tcp()


def _kv(key: str, value: str) -> dict[str, Any]:
    """Build an OTLP KeyValue attribute with a stringValue."""
    return {"key": key, "value": {"stringValue": value}}


def _sd_escape(value: str) -> str:
    """Escape special characters for RFC 5424 structured data values."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")
