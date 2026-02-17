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
