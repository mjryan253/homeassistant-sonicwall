"""Custom types for sonicwall."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import SonicWallApiClient
    from .coordinator import SonicWallDataUpdateCoordinator


type SonicWallConfigEntry = ConfigEntry[SonicWallData]


@dataclass
class SonicWallData:
    """Data for the SonicWall integration."""

    client: SonicWallApiClient
    coordinator: SonicWallDataUpdateCoordinator
    integration: Integration
