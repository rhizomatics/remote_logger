"""Home Assistant's test helpers, from whichever package provides them for the Home Assistant
installed: pytest-homeassistant (`pytest_homeassistant`), published by Home Assistant itself from
2026.11, or pytest-homeassistant-custom-component before that. Remove once the oldest supported
Home Assistant has the first, importing from `pytest_homeassistant` directly (same model as
supernotify, hq-private#85)."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # One declaration for type checkers, which otherwise take the unresolved first import as Unknown
    from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped,unused-ignore]
        MockConfigEntry,
    )
else:
    try:
        from pytest_homeassistant.common import MockConfigEntry
    except ImportError:
        from pytest_homeassistant_custom_component.common import MockConfigEntry

__all__ = [
    "MockConfigEntry",
]
