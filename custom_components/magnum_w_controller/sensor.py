"""Sensor platform: battery + signal for thermostats, signal for controllers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import MagnumCoordinator
from .entity import control_unit_device_info, zone_device_info

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .api import ControlUnit, Zone
    from .coordinator import MagnumConfigEntry


@dataclass(frozen=True, kw_only=True)
class MagnumZoneSensorDescription(SensorEntityDescription):
    """Describes a sensor derived from a Zone."""

    value_fn: Callable[[Zone], float | int | None]


@dataclass(frozen=True, kw_only=True)
class MagnumCuSensorDescription(SensorEntityDescription):
    """Describes a sensor derived from a ControlUnit."""

    value_fn: Callable[[ControlUnit], float | int | None]


ZONE_SENSORS: tuple[MagnumZoneSensorDescription, ...] = (
    MagnumZoneSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda zone: zone.room_temp,
    ),
    MagnumZoneSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda zone: zone.battery_pct,
    ),
    MagnumZoneSensorDescription(
        key="signal",
        translation_key="signal_strength",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
        value_fn=lambda zone: zone.link_quality_pct,
    ),
)

CU_SENSORS: tuple[MagnumCuSensorDescription, ...] = (
    MagnumCuSensorDescription(
        key="signal",
        translation_key="signal_strength",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:wifi",
        value_fn=lambda unit: unit.link_quality_pct,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: MagnumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for zones and control units."""
    coordinator = entry.runtime_data

    entities: list[SensorEntity] = []
    for zone in coordinator.data.zones:
        entities.extend(
            MagnumZoneSensor(coordinator, entry.entry_id, zone.zone_id, desc)
            for desc in ZONE_SENSORS
        )
    for unit in coordinator.data.control_units:
        entities.extend(
            MagnumCuSensor(coordinator, entry.entry_id, unit.cu_index, desc)
            for desc in CU_SENSORS
        )
    async_add_entities(entities)


class MagnumZoneSensor(CoordinatorEntity[MagnumCoordinator], SensorEntity):
    """A diagnostic/temperature sensor for a single zone."""

    _attr_has_entity_name = True
    entity_description: MagnumZoneSensorDescription

    def __init__(
        self,
        coordinator: MagnumCoordinator,
        entry_id: str,
        zone_id: int,
        description: MagnumZoneSensorDescription,
    ) -> None:
        """Initialize the zone sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}_{description.key}"

    @property
    def _zone(self) -> Zone | None:
        for zone in self.coordinator.data.zones:
            if zone.zone_id == self._zone_id:
                return zone
        return None

    @property
    def available(self) -> bool:
        """Whether the zone is still present in the latest snapshot."""
        return super().available and self._zone is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Device entry for the zone this sensor belongs to."""
        zone = self._zone
        return zone_device_info(self._entry_id, zone) if zone else None

    @property
    def native_value(self) -> float | int | None:
        """Return the mapped value for this sensor."""
        zone = self._zone
        return self.entity_description.value_fn(zone) if zone else None


class MagnumCuSensor(CoordinatorEntity[MagnumCoordinator], SensorEntity):
    """A diagnostic sensor for a single control unit."""

    _attr_has_entity_name = True
    entity_description: MagnumCuSensorDescription

    def __init__(
        self,
        coordinator: MagnumCoordinator,
        entry_id: str,
        cu_index: int,
        description: MagnumCuSensorDescription,
    ) -> None:
        """Initialize the control unit sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._entry_id = entry_id
        self._cu_index = cu_index
        self._attr_unique_id = f"{entry_id}_cu_{cu_index}_{description.key}"

    @property
    def _unit(self) -> ControlUnit | None:
        for unit in self.coordinator.data.control_units:
            if unit.cu_index == self._cu_index:
                return unit
        return None

    @property
    def available(self) -> bool:
        """Whether the control unit is still present in the latest snapshot."""
        return super().available and self._unit is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Device entry for the control unit this sensor belongs to."""
        unit = self._unit
        return control_unit_device_info(self._entry_id, unit) if unit else None

    @property
    def native_value(self) -> float | int | None:
        """Return the mapped value for this sensor."""
        unit = self._unit
        return self.entity_description.value_fn(unit) if unit else None
