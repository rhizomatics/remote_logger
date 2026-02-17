from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import ssl
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback

from custom_components.remote_logger.const import (
    BATCH_FLUSH_INTERVAL_SECONDS,
    CONF_APP_NAME,
    CONF_FACILITY,
    CONF_HOST,
    CONF_PORT,
    CONF_PROTOCOL,
    CONF_USE_TLS,
)

from .const import (
    DEFAULT_APP_NAME,
    DEFAULT_FACILITY,
    DEFAULT_SYSLOG_SEVERITY,
    PROTOCOL_UDP,
    SYSLOG_FACILITY_MAP,
    SYSLOG_SEVERITY_MAP,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


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
        if (
            event.data
            and event.data.get("source")
            and len(event.data["source"]) == 2
            and "custom_components/remote_logger/syslog" in event.data["source"][0]
        ):
            # prevent log loops
            return
        self._buffer.append(event.data)

    def _to_syslog_message(self, data: Any) -> bytes:
        """Convert a system_log_event payload to an RFC 5424 syslog message."""
        """
            "name": str
            "message": list(str)
            "level": str
            "source": (str,int)
            "timestamp": float
            "exception": str
            "count": int
            "first_occurred": float
        """
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
        if source and isinstance(source, tuple):
            source_path, source_linenum = source
            sd_params.append(f'source_file="{_sd_escape(source_path)}"')
            sd_params.append(f'source_line="{source_linenum}"')
        logger_name = data.get("name")
        if logger_name:
            sd_params.append(f'component="{_sd_escape(logger_name)}"')
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
            _LOGGER.exception("remote_logger: unexpected error sending syslog messages")

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
            _LOGGER.warning("remote_logger: failed to send syslog via UDP: %s", err)
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
            _LOGGER.warning("remote_logger: failed to send syslog via TCP: %s", err)
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


def _sd_escape(value: str) -> str:
    """Escape special characters for RFC 5424 structured data values."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")


async def validate(hass: Any, host: str, port: int, protocol: str, use_tls: bool) -> str | None:
    """Test connectivity to a syslog endpoint. Returns error key or None."""
    loop = hass.loop
    try:
        if protocol == PROTOCOL_UDP:
            # Quick UDP test: just resolve and create a socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setblocking(False)
                await loop.run_in_executor(None, lambda: socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_DGRAM))
            finally:
                sock.close()
        else:
            # TCP: actually connect
            ssl_ctx = True if use_tls else None
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=ssl_ctx),
                timeout=10,
            )
            writer.close()
            await writer.wait_closed()
    except (OSError, TimeoutError, ConnectionRefusedError) as err:
        _LOGGER.error("Syslog connect failed: %s", err)
        return "cannot_connect"
    except Exception as err:
        _LOGGER.error("Syslog connect unknown error: %s", err)
        return "unknown"
    return None
