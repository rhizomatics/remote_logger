"""Unit tests for custom_components.remote_logger (setup/unload)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.remote_logger import async_setup_entry, async_unload_entry
from custom_components.remote_logger.config_flow import OtelLogsConfigFlow
from custom_components.remote_logger.const import (
    CONF_CUSTOM_EVENTS,
    CONF_EVENT_BASED_LOGGING,
    CONF_LOG_HA_CORE_CHANGES,
    CONF_LOG_HA_LIFECYCLE,
    CONF_LOG_LEVEL,
    CORE_CHANGE_EVENTS,
    DOMAIN,
    LIFECYCLE_EVENTS,
)
from custom_components.remote_logger.remote_logger import RemoteLoggerData

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


class TestAsyncSetupEntry:
    async def test_otel_backend(self, hass: HomeAssistant, mock_entry_otel: ConfigEntry) -> None:
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            result = await async_setup_entry(hass, mock_entry_otel)

        assert result is True
        entry_data = mock_entry_otel.runtime_data
        assert isinstance(entry_data, RemoteLoggerData)

        # Cancel the background flush task
        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_syslog_backend(self, hass: HomeAssistant, mock_entry_syslog: ConfigEntry) -> None:
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            result = await async_setup_entry(hass, mock_entry_syslog)

        assert result is True
        entry_data = mock_entry_syslog.runtime_data
        assert isinstance(entry_data, RemoteLoggerData)

        # Cancel the background flush task
        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_lifecycle_events_registered(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_LOG_HA_LIFECYCLE: True}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        # stop + close + final_write + update_listener + lifecycle listeners
        assert len(entry_data.cancel_listeners) == 4 + len(LIFECYCLE_EVENTS)

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_core_change_events_registered(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_LOG_HA_CORE_CHANGES: True}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert len(entry_data.cancel_listeners) == 4 + len(CORE_CHANGE_EVENTS)

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_custom_events_registered(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_CUSTOM_EVENTS: ["my_event", "another_event"]}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert len(entry_data.cancel_listeners) == 4 + 2  # stop + close + final_write + update_listener + 2 custom

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_options_override_data(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        """Options take precedence over data for event config keys."""
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_LOG_HA_LIFECYCLE: False}
        mock_entry_otel.options = {CONF_LOG_HA_LIFECYCLE: True}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert len(entry_data.cancel_listeners) == 4 + len(LIFECYCLE_EVENTS)

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task


class TestAsyncUnloadEntry:
    async def _setup_entry_data(self, entry: MagicMock) -> tuple[MagicMock, asyncio.Task[None], AsyncMock]:
        cancel_listener = MagicMock()

        mock_exporter = AsyncMock()

        async def _long_sleep() -> None:
            await asyncio.sleep(1000)

        flush_task: asyncio.Task[None] = asyncio.create_task(_long_sleep())
        entry.runtime_data = RemoteLoggerData(
            exporter=mock_exporter,
            flush_task=flush_task,
            cancel_listeners=[cancel_listener],
            log_handler=None,
        )
        return cancel_listener, flush_task, mock_exporter

    async def test_unload_cancels_task_and_flushes(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        cancel_listener, flush_task, mock_exporter = await self._setup_entry_data(mock_entry_otel)

        with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
            result = await async_unload_entry(hass, mock_entry_otel)

        assert result is True
        assert flush_task.cancelled()
        cancel_listener.assert_called_once()
        mock_exporter.flush.assert_awaited_once()
        mock_exporter.close.assert_awaited_once()


class TestShutdownFlush:
    async def test_homeassistant_stop_flushes_exporter(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        from unittest.mock import AsyncMock, patch

        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        exporter = entry_data.exporter

        with patch.object(exporter, "flush", AsyncMock()) as mock_flush:
            hass.bus.async_fire("homeassistant_stop")
            await hass.async_block_till_done()

        mock_flush.assert_awaited_once()

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task


class TestEventBasedLogging:
    async def test_default_adds_log_handler_to_root(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        """Default config (no event_based_logging key) uses the log handler path."""
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert entry_data.log_handler is not None
        assert entry_data.log_handler in logging.root.handlers

        with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
            await async_unload_entry(hass, mock_entry_otel)

    async def test_event_based_true_uses_listener_not_handler(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_EVENT_BASED_LOGGING: True}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert entry_data.log_handler is None
        # stop + close + final_write + update_listener + system_log listener
        assert len(entry_data.cancel_listeners) == 5

        entry_data.flush_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry_data.flush_task

    async def test_log_handler_default_level_is_info(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert entry_data.log_handler.level == logging.INFO

        with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
            await async_unload_entry(hass, mock_entry_otel)

    async def test_log_handler_custom_level(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        mock_entry_otel.data = {**mock_entry_otel.data, CONF_LOG_LEVEL: "WARNING"}
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        entry_data = mock_entry_otel.runtime_data
        assert entry_data.log_handler.level == logging.WARNING

        with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
            await async_unload_entry(hass, mock_entry_otel)

    async def test_unload_removes_log_handler_from_root(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        with patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()):
            await async_setup_entry(hass, mock_entry_otel)

        handler = mock_entry_otel.runtime_data.log_handler
        assert handler in logging.root.handlers

        with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)):
            await async_unload_entry(hass, mock_entry_otel)

        assert handler not in logging.root.handlers


class TestUpdateListener:
    async def test_update_listener_triggers_reload(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        from custom_components.remote_logger.remote_logger import _async_update_listener

        with patch.object(hass.config_entries, "async_reload", AsyncMock()) as mock_reload:
            await _async_update_listener(hass, mock_entry_otel)

        mock_reload.assert_awaited_once_with(mock_entry_otel.entry_id)


class TestSetupConnectionCheck:
    """async_setup_entry checks the endpoint before starting (test-before-setup)."""

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(self, enable_custom_integrations: None) -> None:
        """Allow Home Assistant to load the integration from custom_components."""

    async def _setup(self, hass: HomeAssistant, template: ConfigEntry) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=OtelLogsConfigFlow.VERSION,
            minor_version=OtelLogsConfigFlow.MINOR_VERSION,
            entry_id=template.entry_id,
            title=template.title,
            data={**template.data, CONF_EVENT_BASED_LOGGING: True},
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    async def test_unreachable_endpoint_retries_setup(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, mock_connection_check: AsyncMock
    ) -> None:
        mock_connection_check.return_value = "cannot_connect"
        entry = await self._setup(hass, mock_entry_otel)
        assert entry.state is ConfigEntryState.SETUP_RETRY

    async def test_unreachable_syslog_retries_setup(
        self, hass: HomeAssistant, mock_entry_syslog: MagicMock, mock_connection_check: AsyncMock
    ) -> None:
        mock_connection_check.return_value = "cannot_connect"
        entry = await self._setup(hass, mock_entry_syslog)
        assert entry.state is ConfigEntryState.SETUP_RETRY

    async def test_rejected_token_starts_reauth(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, mock_connection_check: AsyncMock
    ) -> None:
        mock_connection_check.return_value = "invalid_auth"
        entry = await self._setup(hass, mock_entry_otel)
        assert entry.state is ConfigEntryState.SETUP_ERROR
        flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]

    async def test_reachable_endpoint_loads(
        self, hass: HomeAssistant, mock_entry_otel: MagicMock, mock_connection_check: AsyncMock
    ) -> None:
        entry = await self._setup(hass, mock_entry_otel)
        assert entry.state is ConfigEntryState.LOADED
        mock_connection_check.assert_awaited_once()
        await hass.config_entries.async_unload(entry.entry_id)


class TestUniqueIdMigration:
    """Entries from before 2.2 have sensors keyed by the entry title; migration re-keys them by entry_id."""

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(self, enable_custom_integrations: None) -> None:
        """Allow Home Assistant to load the integration from custom_components."""

    async def test_title_based_unique_ids_migrated(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            minor_version=1,
            entry_id="abc123",
            title="Renamed collector",
            data={**mock_entry_otel.data, CONF_EVENT_BASED_LOGGING: True},
        )
        entry.add_to_hass(hass)
        registry = er.async_get(hass)
        # Created when the entry had its original title, "OTLP @ localhost:4318"
        old = {
            key: registry.async_get_or_create("sensor", DOMAIN, f"otlp_localhost_4318_{key}", config_entry=entry)
            for key in ("format_errors", "posting_errors", "events", "postings")
        }

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.minor_version == 2
        for key, reg_entry in old.items():
            migrated = registry.async_get(reg_entry.entity_id)
            assert migrated is not None
            assert migrated.unique_id == f"abc123_{key}"
        # No new, orphaning duplicates were created
        assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 4
        await hass.config_entries.async_unload(entry.entry_id)

    async def test_conflicting_and_unknown_unique_ids_left_alone(self, hass: HomeAssistant, mock_entry_otel: MagicMock) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=2,
            minor_version=1,
            entry_id="abc123",
            title="x",
            data={**mock_entry_otel.data, CONF_EVENT_BASED_LOGGING: True},
        )
        entry.add_to_hass(hass)
        registry = er.async_get(hass)
        current = registry.async_get_or_create("sensor", DOMAIN, "abc123_events", config_entry=entry)
        stale = registry.async_get_or_create("sensor", DOMAIN, "old_title_events", config_entry=entry)
        unknown = registry.async_get_or_create("sensor", DOMAIN, "something_else", config_entry=entry)

        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get(current.entity_id).unique_id == "abc123_events"  # type: ignore[union-attr]
        assert registry.async_get(stale.entity_id).unique_id == "old_title_events"  # type: ignore[union-attr]
        assert registry.async_get(unknown.entity_id).unique_id == "something_else"  # type: ignore[union-attr]
        await hass.config_entries.async_unload(entry.entry_id)
