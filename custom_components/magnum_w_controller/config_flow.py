"""
Config flow for the Magnum W Controller integration.

Supports two entry points:

* Automatic **DHCP discovery** — the controller presents the DHCP hostname
  ``Magnum_W-Controller`` (see the ``dhcp`` matcher in ``manifest.json``). The
  MAC address from the DHCP lease is used as a stable ``unique_id`` so the
  config entry survives IP changes.
* Manual setup — the user types the host; the IP doubles as the ``unique_id``.

Entries from the two paths are de-duplicated by host so the same controller
can't be added twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac

from .api import MagnumApiError, MagnumClient
from .const import CONF_HOST, DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

STEP_USER_SCHEMA = vol.Schema({vol.Required(CONF_HOST): str})


class MagnumConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Magnum W Controller."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow's discovery state."""
        self._host: str | None = None
        self._system_name: str | None = None

    async def _async_get_system_name(self, host: str) -> str:
        """Connect to the controller and return its system name."""
        session = async_get_clientsession(self.hass)
        client = MagnumClient(host, session)
        return await client.async_get_system_name()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            self._async_abort_entries_match({CONF_HOST: host})
            await self.async_set_unique_id(host)
            self._abort_if_unique_id_configured()
            try:
                system_name = await self._async_get_system_name(host)
            except MagnumApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=system_name, data={CONF_HOST: host}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via DHCP."""
        self._host = discovery_info.ip

        # The MAC is a stable id; update the stored host if the IP changed.
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        # Don't create a second entry if this host was already added manually.
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})

        try:
            self._system_name = await self._async_get_system_name(discovery_info.ip)
        except MagnumApiError:
            return self.async_abort(reason="cannot_connect")

        self.context["title_placeholders"] = {"name": self._system_name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered controller."""
        assert self._host is not None  # noqa: S101
        if user_input is not None:
            return self.async_create_entry(
                title=self._system_name or "Magnum W Controller",
                data={CONF_HOST: self._host},
            )

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={
                "name": self._system_name or self._host,
                "host": self._host,
            },
        )
