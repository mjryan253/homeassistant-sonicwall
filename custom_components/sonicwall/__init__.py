"""
Custom integration to integrate sonicwall with Home Assistant.

For more details about this integration, please refer to
https://github.com/mjryan253/homeassistant-sonicwall
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    Platform,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_loaded_integration

from .api import SonicWallApiClient
from .const import (
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL_SECONDS,
    DOMAIN,
    LOGGER,
)
from .coordinator import SonicWallDataUpdateCoordinator
from .data import SonicWallData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .data import SonicWallConfigEntry

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SonicWallConfigEntry,
) -> bool:
    """Set up this integration using UI."""
    coordinator = SonicWallDataUpdateCoordinator(
        hass=hass,
        logger=LOGGER,
        name=DOMAIN,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
    )
    entry.runtime_data = SonicWallData(
        client=SonicWallApiClient(
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            verify_ssl=entry.data[CONF_VERIFY_SSL],
            session=async_get_clientsession(hass),
        ),
        integration=async_get_loaded_integration(hass, entry.domain),
        coordinator=coordinator,
    )

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SonicWallConfigEntry,
) -> bool:
    """Handle removal of an entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_logout()
    return unloaded


async def async_reload_entry(
    hass: HomeAssistant,
    entry: SonicWallConfigEntry,
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
