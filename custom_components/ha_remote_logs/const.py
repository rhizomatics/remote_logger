"""Constants for the ha_remote_logs integration."""

DOMAIN = "remote_logs"

# Backend selection
CONF_BACKEND = "backend"
BACKEND_OTEL = "otel"
BACKEND_SYSLOG = "syslog"

# Common config entry data keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_USE_TLS = "use_tls"

# OTel-specific config keys
CONF_RESOURCE_ATTRIBUTES = "resource_attributes"
CONF_ENCODING = "encoding"
CONF_BATCH_MAX_SIZE = "batch_max_size"

# Syslog-specific config keys
CONF_PROTOCOL = "protocol"
CONF_APP_NAME = "app_name"
CONF_FACILITY = "facility"

# OTel defaults
DEFAULT_PORT = 4318
DEFAULT_USE_TLS = False
DEFAULT_RESOURCE_ATTRIBUTES = ""
ENCODING_JSON = "json"
ENCODING_PROTOBUF = "protobuf"
DEFAULT_ENCODING = ENCODING_JSON

# Syslog defaults
DEFAULT_SYSLOG_PORT = 514
PROTOCOL_UDP = "udp"
PROTOCOL_TCP = "tcp"
DEFAULT_PROTOCOL = PROTOCOL_UDP
DEFAULT_APP_NAME = "homeassistant"
DEFAULT_FACILITY = "user"

# OTLP endpoint path
OTLP_LOGS_PATH = "/v1/logs"

# Integration metadata (used in InstrumentationScope)
SCOPE_NAME = "homeassistant"
SCOPE_VERSION = "1.0.0"

# Default resource attribute
DEFAULT_SERVICE_NAME = "core"

# HA event type
EVENT_SYSTEM_LOG = "system_log_event"

# Severity mapping: HA log level string -> (OTLP severityNumber, OTLP severityText)
SEVERITY_MAP: dict[str, tuple[int, str]] = {
    "DEBUG": (5, "DEBUG"),
    "INFO": (9, "INFO"),
    "WARNING": (13, "WARN"),
    "ERROR": (17, "ERROR"),
    "CRITICAL": (21, "FATAL"),
}

DEFAULT_SEVERITY = (9, "INFO")

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

# Batch flush settings
BATCH_FLUSH_INTERVAL_SECONDS = 5.0
DEFAULT_BATCH_MAX_SIZE = 100
