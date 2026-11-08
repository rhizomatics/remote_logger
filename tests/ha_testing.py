"""Home Assistant's test helpers, from whichever package provides them for the Home Assistant
installed: pytest-homeassistant (`pytest_homeassistant`), published by Home Assistant itself from
2026.11, or pytest-homeassistant-custom-component before that. Remove once the oldest supported
Home Assistant has the first, importing from `pytest_homeassistant` directly (same model as
supernotify, hq-private#85)."""

try:
    from pytest_homeassistant.common import (  # type: ignore[import-not-found,unused-ignore]
        MockConfigEntry,
    )
except ImportError:
    from pytest_homeassistant_custom_component.common import (  # type: ignore[import-untyped,unused-ignore]
        MockConfigEntry,
    )

__all__ = [
    "MockConfigEntry",
]
