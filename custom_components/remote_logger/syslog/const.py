from homeassistant.const import CONF_HOST, CONF_PORT, CONF_PROTOCOL
from homeassistant.helpers import selector

from custom_components.remote_logger.compat import vol
from custom_components.remote_logger.const import (
    CONF_APP_NAME,
    CONF_BATCH_MAX_SIZE,
    CONF_CLIENT_TIMEOUT,
    CONF_ENTERPRISE_NUMBER,
    CONF_FACILITY,
    CONF_STRICT_MODE,
    CONF_USE_TLS,
    DEFAULT_BATCH_MAX_SIZE,
    DEFAULT_CLIENT_TIMEOUT,
    DEFAULT_USE_TLS,
)

# Syslog severity mapping: HA log level string -> RFC 5424 severity code
SYSLOG_SEVERITY_MAP: dict[str, int] = {
    "DEBUG": 7,
    "INFO": 6,
    "WARNING": 4,
    "ERROR": 3,
    "CRITICAL": 2,
}

DEFAULT_SYSLOG_SEVERITY = 6  # Informational

# Syslog facility mapping: name -> numeric code
SYSLOG_FACILITY_MAP: dict[str, int] = {
    "kern": 0,
    "user": 1,
    "mail": 2,
    "daemon": 3,
    "auth": 4,
    "syslog": 5,
    "lpr": 6,
    "news": 7,
    "local0": 16,
    "local1": 17,
    "local2": 18,
    "local3": 19,
    "local4": 20,
    "local5": 21,
    "local6": 22,
    "local7": 23,
}

# Syslog defaults
DEFAULT_SYSLOG_PORT = 514
PROTOCOL_UDP = "udp"
PROTOCOL_TCP = "tcp"
DEFAULT_PROTOCOL = PROTOCOL_UDP
DEFAULT_APP_NAME = "homeassistant"
DEFAULT_FACILITY = "local0"
SD_ID = "opentelemetry"
MSGID_MAX_LENGTH = 32  # RFC 5424 section 6
SD_NAME_MAX_LENGTH = 32  # RFC 5424 section 6

# Strict mode: a private SD-ID of homeassistant@<IANA Private Enterprise Number>
STRICT_SD_ID = "homeassistant"
# IANA PEN assigned to Rhizomatics; can be overridden, e.g. with 32473, the RFC 5612 documentation PEN
DEFAULT_ENTERPRISE_NUMBER = 67614

# Structured data PARAM-NAMEs for system_log_event fields: OpenTelemetry by default, Home Assistant in strict mode
OTEL_SD_NAMES: dict[str, str] = {
    "logger": "code.function.name",
    "count": "exception.count",
    "first_occurred": "exception.first_occurred",
    "exception": "exception.stacktrace",
    "event_type": "eventName",
}
STRICT_SD_NAMES: dict[str, str] = {
    "logger": "name",
    "count": "count",
    "first_occurred": "first_occurred",
    "exception": "exception",
    "event_type": "event_type",
}

# Strict mode: dotted event data key segments shortened to keep PARAM-NAMEs within 32 characters
STRICT_PARAM_ABBREVIATIONS: dict[str, str] = {
    "new_state": "new",
    "old_state": "old",
    "attributes": "attr",
    "context": "ctx",
    "parent_id": "parent",
    "last_changed": "changed",
    "last_updated": "updated",
    "last_reported": "reported",
    "service_data": "data",
}

SYSLOG_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_SYSLOG_PORT): int,
    vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): selector.SelectSelector(
        selector.SelectSelectorConfig(options=[PROTOCOL_UDP, PROTOCOL_TCP]),
    ),
    vol.Optional(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
    vol.Optional(CONF_APP_NAME, default=DEFAULT_APP_NAME): str,
    vol.Optional(CONF_FACILITY, default=DEFAULT_FACILITY): selector.SelectSelector(
        selector.SelectSelectorConfig(options=list(SYSLOG_FACILITY_MAP.keys())),
    ),
    vol.Optional(CONF_BATCH_MAX_SIZE, default=DEFAULT_BATCH_MAX_SIZE): vol.All(int, vol.Range(min=1, max=10000)),
    vol.Optional(CONF_CLIENT_TIMEOUT, default=DEFAULT_CLIENT_TIMEOUT): vol.All(int, vol.Range(min=1, max=300)),
    vol.Optional(CONF_STRICT_MODE, default=False): bool,
    # IANA Private Enterprise Number, giving a private SD-ID of homeassistant@<number> in strict mode
    vol.Optional(CONF_ENTERPRISE_NUMBER): vol.All(int, vol.Range(min=1)),
})
