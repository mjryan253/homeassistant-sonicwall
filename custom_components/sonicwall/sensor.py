"""
Sensor platform for sonicwall.

Field paths and parsing rules are pinned against the live JSON returned by a
TZ350 / SonicOS Enhanced 6.5.4.5-53n. Several fields are human-formatted
strings rather than raw numbers, so each value is extracted through a small
parser. Returning ``None`` from a parser leaves the entity unavailable, which
is the right behaviour if the firewall response shape changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfInformation, UnitOfTime

from .entity import SonicWallEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import SonicWallDataUpdateCoordinator
    from .data import SonicWallConfigEntry


_CPU_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_CONNECTIONS_CURRENT_RE = re.compile(r"Current:\s*(\d+)")
_UPTIME_RE = re.compile(
    r"(?:(?P<days>\d+)\s*Days?)?\s*"
    r"(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+)",
)


def _firmware_version(version: dict | None) -> str | None:
    if not version:
        return None
    raw = version.get("firmware_version")
    return str(raw) if raw else None


def _parse_cpu(system: dict | None) -> float | None:
    if not system:
        return None
    match = _CPU_RE.match(str(system.get("cpus", "")))
    return float(match.group(1)) if match else None


def _parse_connection_count(system: dict | None) -> int | None:
    if not system:
        return None
    match = _CONNECTIONS_CURRENT_RE.search(str(system.get("connections", "")))
    return int(match.group(1)) if match else None


def _parse_connection_usage(system: dict | None) -> float | None:
    if not system:
        return None
    raw = str(system.get("connection_usage", "")).rstrip("%").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_uptime_seconds(system: dict | None) -> int | None:
    if not system:
        return None
    match = _UPTIME_RE.search(str(system.get("up_time", "")))
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def _interface(interfaces: list | None, name: str) -> dict:
    if not interfaces:
        return {}
    for entry in interfaces:
        if entry.get("interface_name") == name:
            return entry
    return {}


@dataclass(frozen=True, kw_only=True)
class SonicWallSensorDescription(SensorEntityDescription):
    """Describe a SonicWall sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


DEVICE_SENSORS: tuple[SonicWallSensorDescription, ...] = (
    SonicWallSensorDescription(
        key="firmware_version",
        name="Firmware version",
        icon="mdi:chip",
        value_fn=lambda data: _firmware_version(data.get("version")),
    ),
    SonicWallSensorDescription(
        key="cpu_utilization",
        name="CPU utilization",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: _parse_cpu(data.get("system")),
    ),
    SonicWallSensorDescription(
        key="active_connections",
        name="Active connections",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:lan-connect",
        value_fn=lambda data: _parse_connection_count(data.get("system")),
    ),
    SonicWallSensorDescription(
        key="connection_usage",
        name="Connection usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        icon="mdi:gauge",
        value_fn=lambda data: _parse_connection_usage(data.get("system")),
    ),
    SonicWallSensorDescription(
        key="uptime",
        name="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:timer-outline",
        value_fn=lambda data: _parse_uptime_seconds(data.get("system")),
    ),
)


def _interface_sensors(name: str) -> tuple[SonicWallSensorDescription, ...]:
    """Return RX/TX byte sensors for a single interface name (e.g. ``X1``)."""
    lower = name.lower()
    return (
        SonicWallSensorDescription(
            key=f"interface_{lower}_rx_bytes",
            name=f"{name} RX bytes",
            native_unit_of_measurement=UnitOfInformation.BYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            value_fn=(
                lambda data, n=name: _interface(data.get("interfaces"), n).get(
                    "rx_bytes",
                )
            ),
        ),
        SonicWallSensorDescription(
            key=f"interface_{lower}_tx_bytes",
            name=f"{name} TX bytes",
            native_unit_of_measurement=UnitOfInformation.BYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            value_fn=(
                lambda data, n=name: _interface(data.get("interfaces"), n).get(
                    "tx_bytes",
                )
            ),
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: SonicWallConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data.coordinator
    interfaces = (coordinator.data or {}).get("interfaces") or []
    descriptions: list[SonicWallSensorDescription] = list(DEVICE_SENSORS)
    for iface in interfaces:
        name = iface.get("interface_name")
        if name:
            descriptions.extend(_interface_sensors(name))
    async_add_entities(
        SonicWallSensor(coordinator=coordinator, description=description)
        for description in descriptions
    )


class SonicWallSensor(SonicWallEntity, SensorEntity):
    """SonicWall sensor entity."""

    entity_description: SonicWallSensorDescription

    def __init__(
        self,
        *,
        coordinator: SonicWallDataUpdateCoordinator,
        description: SonicWallSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the entity's current value."""
        return self.entity_description.value_fn(self.coordinator.data or {})
