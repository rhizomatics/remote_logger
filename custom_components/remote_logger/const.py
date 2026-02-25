"""Constants for the remote_logger integration."""

from homeassistant.const import EntityPlatforms, Platform

DOMAIN = "remote_logger"

PLATFORMS: list[EntityPlatforms] = [Platform.SENSOR]

# Backend selection
CONF_BACKEND = "backend"
BACKEND_OTEL = "otel"
BACKEND_SYSLOG = "syslog"

# Common config entry data keys
CONF_USE_TLS = "use_tls"

# OTel-specific config keys
CONF_RESOURCE_ATTRIBUTES = "resource_attributes"
CONF_ENCODING = "encoding"
CONF_BATCH_MAX_SIZE = "batch_max_size"

# Syslog-specific config keys
CONF_APP_NAME = "app_name"
CONF_FACILITY = "facility"


# HA event type
EVENT_SYSTEM_LOG = "system_log_event"

BATCH_FLUSH_INTERVAL_SECONDS = 120
DEFAULT_BATCH_MAX_SIZE = 20

DEFAULT_USE_TLS = False
