"""Tests for remote_logger diagnostics and default entity enablement."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.remote_logger.config_flow import OtelLogsConfigFlow
from custom_components.remote_logger.const import CONF_EVENT_BASED_LOGGING, DOMAIN
from custom_components.remote_logger.diagnostics import async_get_config_entry_diagnostics
from tests.ha_testing import MockConfigEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the integration from custom_components."""


async def _setup(hass: HomeAssistant, template: MagicMock) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=OtelLogsConfigFlow.VERSION,
        minor_version=OtelLogsConfigFlow.MINOR_VERSION,
        entry_id=template.entry_id,
        title=template.title,
        data={
            **template.data,
            CONF_EVENT_BASED_LOGGING: True,
            "token": "s3cret-token",
            "headers": ["X-Api-Key: s3cret-header"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_diagnostics_redacts_credentials(hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
    entry = await _setup(hass, mock_entry_otel)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"]["token"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["headers"] == "**REDACTED**"
    assert diagnostics["entry"]["data"]["host"] == "localhost"
    assert "s3cret" not in str(diagnostics)
    assert diagnostics["exporter"]["logger_type"] == "otel"
    assert diagnostics["exporter"]["reachable"] is True
    assert diagnostics["last_sent_payload"] is None
    await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_includes_last_payload(hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
    entry = await _setup(hass, mock_entry_otel)
    submission = MagicMock()
    submission.for_display.return_value = {"data": "payload"}
    entry.runtime_data.exporter.last_sent_payload = submission

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["last_sent_payload"] == {"data": "payload"}
    await hass.config_entries.async_unload(entry.entry_id)


async def test_busy_counters_disabled_by_default(hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
    entry = await _setup(hass, mock_entry_otel)

    registry = er.async_get(hass)
    disabled = {
        e.unique_id.removeprefix(f"{entry.entry_id}_"): e.disabled_by is not None
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    }
    assert disabled == {"format_errors": False, "posting_errors": False, "events": True, "postings": True}
    await hass.config_entries.async_unload(entry.entry_id)
