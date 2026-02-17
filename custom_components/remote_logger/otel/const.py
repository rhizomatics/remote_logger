import voluptuous as vol

from custom_components.remote_logger.const import (
    CONF_BATCH_MAX_SIZE,
    CONF_ENCODING,
    CONF_HOST,
    CONF_PORT,
    CONF_RESOURCE_ATTRIBUTES,
    CONF_USE_TLS,
    DEFAULT_BATCH_MAX_SIZE,
)

# OTLP endpoint path
OTLP_LOGS_PATH = "/v1/logs"

# Severity mapping: HA log level string -> (OTLP severityNumber, OTLP severityText)
SEVERITY_MAP: dict[str, tuple[int, str]] = {
    "DEBUG": (5, "DEBUG"),
    "INFO": (9, "INFO"),
    "WARNING": (13, "WARN"),
    "ERROR": (17, "ERROR"),
    "CRITICAL": (21, "FATAL"),
}

DEFAULT_SEVERITY = (9, "INFO")

# OTel defaults
DEFAULT_PORT = 4318
DEFAULT_USE_TLS = False
DEFAULT_RESOURCE_ATTRIBUTES = ""
ENCODING_JSON = "json"
ENCODING_PROTOBUF = "protobuf"
DEFAULT_ENCODING = ENCODING_PROTOBUF


# Integration metadata (used in InstrumentationScope)
SCOPE_NAME = "homeassistant"
SCOPE_VERSION = "1.0.0"

# Default resource attribute
DEFAULT_SERVICE_NAME = "core"

OTEL_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_HOST): str,
    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    vol.Optional(CONF_USE_TLS, default=DEFAULT_USE_TLS): bool,
    vol.Optional(CONF_ENCODING, default=DEFAULT_ENCODING): vol.In([ENCODING_JSON, ENCODING_PROTOBUF]),
    vol.Optional(CONF_BATCH_MAX_SIZE, default=DEFAULT_BATCH_MAX_SIZE): vol.All(int, vol.Range(min=1, max=10000)),
    vol.Optional(CONF_RESOURCE_ATTRIBUTES, default=DEFAULT_RESOURCE_ATTRIBUTES): str,
})
