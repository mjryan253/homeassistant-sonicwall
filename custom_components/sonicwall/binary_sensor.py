"""Binary sensor platform for sonicwall (interface link state)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)

from .entity import SonicWallEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SonicWallDataUpdateCoordinator
    from .data import SonicWallConfigEntry


# Interface names whose link state we expose as binary_sensors. Edit if you
# want to monitor different / additional interfaces.
LINK_INTERFACES: tuple[str, ...] = ("X0", "X1")

# /reporting/interfaces/ip's ``status`` field is e.g.:
#   "1 Gbps Full Duplex"   - link up (negotiated)
#   "100 Mbps Full Duplex" - link up
#   "No link"              - link down
# Anything starting with a digit-speed is treated as up; everything else as
# down. That fails closed if SonicOS introduces an unfamiliar status string.
_LINK_UP_RE = re.compile(r"^\d")


def _interface_status_string(interface_status: list | None, name: str) -> str | None:
    if not interface_status:
        return None
    for entry in interface_status:
        if entry.get("name") == name:
            raw = entry.get("status")
            return str(raw) if raw is not None else None
    return None


def _is_link_up(data: dict[str, Any], name: str) -> bool | None:
    status = _interface_status_string(data.get("interface_status"), name)
    if status is None:
        return None
    return bool(_LINK_UP_RE.match(status))


@dataclass(frozen=True, kw_only=True)
class SonicWallBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a SonicWall binary sensor."""

    value_fn: Callable[[dict[str, Any]], bool | None]


def _link_descriptions() -> tuple[SonicWallBinarySensorDescription, ...]:
    return tuple(
        SonicWallBinarySensorDescription(
            key=f"interface_{name.lower()}_link",
            name=f"{name} link",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            value_fn=lambda data, n=name: _is_link_up(data, n),
        )
        for name in LINK_INTERFACES
    )


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SonicWallConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary_sensor platform."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SonicWallLinkBinarySensor(coordinator=coordinator, description=description)
        for description in _link_descriptions()
    )


class SonicWallLinkBinarySensor(SonicWallEntity, BinarySensorEntity):
    """Per-interface link state binary sensor."""

    entity_description: SonicWallBinarySensorDescription

    def __init__(
        self,
        *,
        coordinator: SonicWallDataUpdateCoordinator,
        description: SonicWallBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True when the interface link is up."""
        return self.entity_description.value_fn(self.coordinator.data or {})
