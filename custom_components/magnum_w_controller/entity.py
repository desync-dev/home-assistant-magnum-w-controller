"""Shared device-registry helpers for Magnum W entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER

if TYPE_CHECKING:
    from .api import ControlUnit, Zone


def control_unit_device_info(entry_id: str, unit: ControlUnit) -> DeviceInfo:
    """Device entry for a control unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{unit.unique_key}")},
        name=unit.name,
        manufacturer=MANUFACTURER,
        model="Magnum W Control Unit",
    )


def zone_device_info(entry_id: str, zone: Zone) -> DeviceInfo:
    """Device entry for a thermostat/zone, linked to its control unit."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{zone.unique_key}")},
        name=zone.name,
        manufacturer=MANUFACTURER,
        model="Magnum W Thermostat",
        via_device=(DOMAIN, f"{entry_id}_cu_{zone.cu_index}"),
    )
