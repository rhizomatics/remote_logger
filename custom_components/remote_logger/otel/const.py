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
DEFAULT_ENCODING = ENCODING_JSON


# Integration metadata (used in InstrumentationScope)
SCOPE_NAME = "homeassistant"
SCOPE_VERSION = "1.0.0"

# Default resource attribute
DEFAULT_SERVICE_NAME = "core"
