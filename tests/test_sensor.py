"""Unit tests for the sensor platform."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.remote_logger.sensor import SENSORS, LoggerEntity


@pytest.fixture
def mock_exporter() -> MagicMock:
    exporter = MagicMock()
    exporter.name = "OTLP @ localhost:4318"
    exporter.logger_type = "otel"
    return exporter


class TestLoggerEntity:
    def test_name_uses_exporter_name(self, mock_exporter: MagicMock) -> None:
        description = SENSORS[0]  # format_errors
        entity = LoggerEntity(mock_exporter, description)
        assert entity.name == "OTLP @ localhost:4318 Format Errors"

    def test_unique_id_uses_exporter_name(self, mock_exporter: MagicMock) -> None:
        description = SENSORS[0]  # format_errors
        entity = LoggerEntity(mock_exporter, description)
        assert entity._attr_unique_id == "OTLP @ localhost:4318_format_errors"

    def test_unique_ids_differ_for_same_type_different_name(self, mock_exporter: MagicMock) -> None:
        exporter2 = MagicMock()
        exporter2.name = "OTLP @ remote:4318"
        exporter2.logger_type = "otel"

        description = SENSORS[0]
        entity1 = LoggerEntity(mock_exporter, description)
        entity2 = LoggerEntity(exporter2, description)

        assert entity1._attr_unique_id != entity2._attr_unique_id

    def test_unique_ids_differ_for_different_sensors_same_exporter(self, mock_exporter: MagicMock) -> None:
        entities = [LoggerEntity(mock_exporter, d) for d in SENSORS]
        unique_ids = [e._attr_unique_id for e in entities]
        assert len(unique_ids) == len(set(unique_ids))
