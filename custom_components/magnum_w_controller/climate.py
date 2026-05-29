"""Climate platform: one thermostat entity per Magnum W zone."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, MagnumApiError, Zone
from .coordinator import MagnumCoordinator
from .entity import zone_device_info

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceInfo
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MagnumConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: MagnumConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for each zone."""
    coordinator = entry.runtime_data
    async_add_entities(
        MagnumClimate(coordinator, entry.entry_id, zone.zone_id)
        for zone in coordinator.data.zones
    )


class MagnumClimate(CoordinatorEntity[MagnumCoordinator], ClimateEntity):
    """A single Magnum W thermostat."""

    _attr_has_entity_name = True
    _attr_name = None  # the device name is the thermostat name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_target_temperature_step = 0.5

    def __init__(
        self, coordinator: MagnumCoordinator, entry_id: str, zone_id: int
    ) -> None:
        """Initialize the thermostat for a single zone."""
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}"

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
        """Device entry for this thermostat."""
        zone = self._zone
        if zone is None:
            return None
        return zone_device_info(self._entry_id, zone)

    @property
    def hvac_mode(self) -> HVACMode:
        """Heating or cooling, derived from the zone mode."""
        zone = self._zone
        if zone is not None and zone.is_cooling:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Available modes (heat/cool is system-wide, so only the current one)."""
        # Heat/cool is a system-level configuration, not switchable per zone,
        # so we only advertise the zone's current mode.
        return [self.hvac_mode]

    @property
    def hvac_action(self) -> HVACAction:
        """Whether the zone is actively heating, cooling, or idle."""
        zone = self._zone
        if zone is None or not zone.is_active:
            return HVACAction.IDLE
        return HVACAction.COOLING if zone.is_cooling else HVACAction.HEATING

    @property
    def current_temperature(self) -> float | None:
        """Current room temperature."""
        zone = self._zone
        return zone.room_temp if zone else None

    @property
    def target_temperature(self) -> float | None:
        """Target temperature for the active mode."""
        zone = self._zone
        return zone.setpoint if zone else None

    @property
    def min_temp(self) -> float:
        """Lowest selectable target temperature."""
        zone = self._zone
        if zone and zone.min_temp is not None:
            return zone.min_temp
        return DEFAULT_MIN_TEMP

    @property
    def max_temp(self) -> float:
        """Highest selectable target temperature."""
        zone = self._zone
        if zone and zone.max_temp is not None:
            return zone.max_temp
        return DEFAULT_MAX_TEMP

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set a new target temperature for the zone."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        zone = self._zone
        if zone is None:
            msg = "Zone is no longer available"
            raise HomeAssistantError(msg)
        try:
            await self.coordinator.client.async_set_zone_setpoint(zone, temperature)
        except MagnumApiError as err:
            raise ServiceValidationError(str(err)) from err
        await self.coordinator.async_request_refresh()
