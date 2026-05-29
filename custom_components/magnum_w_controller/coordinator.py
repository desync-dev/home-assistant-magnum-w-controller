"""Data update coordinator for the Magnum W Controller."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MagnumApiError, MagnumData
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .api import MagnumClient

_LOGGER = logging.getLogger(__name__)

type MagnumConfigEntry = ConfigEntry[MagnumCoordinator]


class MagnumCoordinator(DataUpdateCoordinator[MagnumData]):
    """Polls the controller and shares one snapshot with all entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MagnumConfigEntry,
        client: MagnumClient,
    ) -> None:
        """Initialize the coordinator with its API client."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> MagnumData:
        try:
            return await self.client.async_update()
        except MagnumApiError as err:
            raise UpdateFailed(str(err)) from err
