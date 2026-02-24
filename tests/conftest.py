"""Shared fixtures for remote_logger tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback


@pytest.fixture
def mock_entities_callback() -> AddConfigEntryEntitiesCallback:
    return MagicMock(spec=AddConfigEntryEntitiesCallback)


@pytest.fixture
def mock_entry_otel() -> ConfigEntry:
    """Create a mock ConfigEntry for OTEL backend."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_otel_entry"
    entry.domain = "remote_logger"
    entry.title = "OTel Remote Logger"
    entry.data = {
        "host": "localhost",
        "port": 4318,
        "use_tls": False,
        "encoding": "json",
        "batch_max_size": 20,
        "resource_attributes": "",
        "backend": "otel",
    }
    return entry


@pytest.fixture
def mock_entry_otel_protobuf() -> ConfigEntry:
    """Create a mock ConfigEntry for OTEL backend with protobuf encoding."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_otel_proto_entry"
    entry.domain = "remote_logger"
    entry.title = "OTel Remote Logger"
    entry.data = {
        "host": "localhost",
        "port": 4318,
        "use_tls": False,
        "encoding": "protobuf",
        "batch_max_size": 20,
        "resource_attributes": "env=prod,region=us-east-1",
        "backend": "otel",
    }
    return entry


@pytest.fixture
def mock_entry_syslog() -> ConfigEntry:
    """Create a mock ConfigEntry for syslog backend."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_syslog_entry"
    entry.domain = "remote_logger"
    entry.title = "Syslog Remote Logger"
    entry.data = {
        "host": "syslog.example.com",
        "port": 514,
        "protocol": "udp",
        "use_tls": False,
        "app_name": "homeassistant",
        "facility": "local0",
        "backend": "syslog",
    }
    return entry


@pytest.fixture
def sample_event_data() -> dict[str, Any]:
    """Create a sample system_log_event data dict."""
    return {
        "name": "homeassistant.components.sensor",
        "message": ["Something went wrong"],
        "level": "ERROR",
        "source": ("homeassistant/components/sensor/__init__.py", 42),
        "timestamp": 1700000000.0,
        "exception": "Traceback (most recent call last):\n  File ...\nValueError: bad value",
        "count": 3,
        "first_occurred": 1699999000.0,
    }


@pytest.fixture
def minimal_event_data() -> dict[str, Any]:
    """Create a minimal system_log_event data dict."""
    return {
        "message": ["Simple info message"],
        "level": "INFO",
        "timestamp": 1700000000.0,
    }


@pytest.fixture
def mock_event(sample_event_data: dict[str, Any]) -> Event:
    """Create a mock HA Event with sample data."""
    event = MagicMock(spec=Event)
    event.data = sample_event_data
    return event


@pytest.fixture
def mock_event_minimal(minimal_event_data: dict[str, Any]) -> Event:
    """Create a mock HA Event with minimal data."""
    event = MagicMock(spec=Event)
    event.data = minimal_event_data
    return event
