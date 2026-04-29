"""DataUpdateCoordinator for sonicwall."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    SonicWallApiClientAuthenticationError,
    SonicWallApiClientError,
)

if TYPE_CHECKING:
    from .data import SonicWallConfigEntry


class SonicWallDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the SonicOS API."""

    config_entry: SonicWallConfigEntry

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        client = self.config_entry.runtime_data.client
        try:
            version, system, interfaces, interface_status = await asyncio.gather(
                client.async_version(),
                client.async_system_reporting(),
                client.async_interfaces_ipv4(),
                client.async_interface_status(),
            )
        except SonicWallApiClientAuthenticationError as exception:
            raise ConfigEntryAuthFailed(exception) from exception
        except SonicWallApiClientError as exception:
            raise UpdateFailed(exception) from exception
        return {
            "version": version,
            "system": system,
            "interfaces": interfaces,
            "interface_status": interface_status,
        }
