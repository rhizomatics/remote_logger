"""Unit tests for config flow helpers."""

from __future__ import annotations

from custom_components.remote_logger.config_flow import _build_endpoint_url


class TestBuildEndpointUrl:
    def test_http(self) -> None:
        assert _build_endpoint_url("localhost", 4318, False) == "http://localhost:4318/v1/logs"

    def test_https(self) -> None:
        assert _build_endpoint_url("otel.example.com", 443, True) == "https://otel.example.com:443/v1/logs"

    def test_custom_port(self) -> None:
        assert _build_endpoint_url("host", 9999, False) == "http://host:9999/v1/logs"
