"""Unit tests for the sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.remote_logger.sensor import SENSORS, LoggerEntity, RemoteLoggerDiagnosticEntityDescription


def _make_entity(exporter: MagicMock, sensor_index: int = 0) -> LoggerEntity:
    device_info = MagicMock(spec=DeviceInfo)
    return LoggerEntity(exporter, SENSORS[sensor_index], device_info)


class TestLoggerEntity:
    def test_unique_id_uses_exporter_name(self) -> None:
        exporter = MagicMock()
        exporter.name = "OTLP @ localhost:4318"
        entity = _make_entity(exporter)
        assert entity._attr_unique_id == "otlp_localhost_4318_format_errors"

    def test_unique_ids_differ_for_same_type_different_name(self) -> None:
        exporter1 = MagicMock()
        exporter1.name = "OTLP @ localhost:4318"
        exporter2 = MagicMock()
        exporter2.name = "OTLP @ remote:4318"

        assert _make_entity(exporter1)._attr_unique_id != _make_entity(exporter2)._attr_unique_id

    def test_unique_ids_differ_for_different_sensors_same_exporter(self) -> None:
        exporter = MagicMock()
        exporter.name = "OTLP @ localhost:4318"
        device_info = MagicMock(spec=DeviceInfo)
        entities = [LoggerEntity(exporter, d, device_info) for d in SENSORS]
        unique_ids = [e._attr_unique_id for e in entities]
        assert len(unique_ids) == len(set(unique_ids))

    def test_translation_key_matches_description(self) -> None:
        exporter = MagicMock()
        exporter.name = "OTLP @ localhost:4318"
        entity = _make_entity(exporter, sensor_index=0)
        assert entity.translation_key == "format_errors"


@pytest.mark.parametrize("description", SENSORS, ids=lambda d: d.key)
def test_counters_are_total_increasing(description: RemoteLoggerDiagnosticEntityDescription) -> None:
    """Counters only increase and reset on restart, so statistics must treat them as totals."""
    assert description.state_class == SensorStateClass.TOTAL_INCREASING


@pytest.mark.parametrize("description", SENSORS, ids=lambda d: d.key)
def test_entities_are_diagnostic(description: RemoteLoggerDiagnosticEntityDescription) -> None:
    exporter = MagicMock()
    exporter.name = "OTLP @ localhost:4318"
    entity = LoggerEntity(exporter, description, MagicMock(spec=DeviceInfo))
    assert entity.entity_category == EntityCategory.DIAGNOSTIC
